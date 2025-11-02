"""Trade execution layer for the Autonomous Trading Agent."""

import ccxt
import logging
from typing import Optional
from src.config import Config
from src.models import DecisionObject, MarketSnapshot, ExecutionResult


logger = logging.getLogger(__name__)


class TradeExecutor:
    """Handles trade execution on the exchange."""
    
    def __init__(self, config: Config):
        """
        Initialize the trade executor with exchange configuration.
        
        Args:
            config: Configuration object containing exchange credentials and settings
        """
        self.config = config
        self.exchange = self._init_exchange(config)
    
    def _init_exchange(self, config: Config) -> ccxt.Exchange:
        """
        Initialize ccxt exchange client based on configuration.
        Uses Binance USD-M Futures for shorting support.
        
        Args:
            config: Configuration object
            
        Returns:
            Configured ccxt exchange instance
        """
        exchange_type = config.exchange_type.lower()
        
        # Map exchange types to ccxt classes
        if exchange_type == "binance_testnet":
            exchange = ccxt.binance({
                'apiKey': config.exchange_api_key,
                'secret': config.exchange_api_secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',  # Use USD-M Futures
                }
            })
            # Override to testnet URL
            exchange.set_sandbox_mode(True)
        elif exchange_type == "binance":
            exchange = ccxt.binance({
                'apiKey': config.exchange_api_key,
                'secret': config.exchange_api_secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',  # Use USD-M Futures
                }
            })
        else:
            raise ValueError(f"Unsupported exchange type: {exchange_type}")
        
        logger.info(f"Initialized {exchange_type} exchange client (USD-M Futures)")
        return exchange
    
    def execute(
        self,
        decision: DecisionObject,
        snapshot: MarketSnapshot,
        position_size: float,
        equity: float
    ) -> ExecutionResult:
        """
        Execute a trading decision on the exchange.
        
        Args:
            decision: Parsed decision object from LLM
            snapshot: Current market snapshot
            position_size: Current position size (positive for long, negative for short)
            equity: Current account equity
            
        Returns:
            ExecutionResult with execution details or error
        """
        action = decision.action.lower()
        
        # Handle hold action - no execution needed
        if action == "hold":
            logger.info("Action is 'hold', no execution needed")
            return ExecutionResult(
                executed=False,
                order_id=None,
                filled_size=None,
                fill_price=None,
                error=None
            )
        
        try:
            # Handle close action
            if action == "close":
                # Check if this is an emergency close
                is_emergency = 'emergency' in decision.reason.lower()
                return self._execute_close(snapshot.symbol, position_size, snapshot.price, is_emergency=is_emergency)
            
            # Calculate order size for long/short actions (with leverage)
            leverage = getattr(decision, 'leverage', 1.0)  # Default to 1.0 if not provided
            order_size = self._calculate_order_size(equity, decision.size_pct, snapshot.price, leverage)
            
            if order_size <= 0:
                logger.warning(f"Calculated order size is {order_size}, skipping execution")
                return ExecutionResult(
                    executed=False,
                    order_id=None,
                    filled_size=None,
                    fill_price=None,
                    error="Order size is zero or negative"
                )
            
            # Execute long or short action
            if action == "long":
                return self._execute_long(snapshot.symbol, order_size)
            elif action == "short":
                return self._execute_short(snapshot.symbol, order_size)
            else:
                logger.error(f"Unknown action: {action}")
                return ExecutionResult(
                    executed=False,
                    order_id=None,
                    filled_size=None,
                    fill_price=None,
                    error=f"Unknown action: {action}"
                )
        
        except Exception as e:
            logger.error(f"Execution error: {str(e)}")
            return ExecutionResult(
                executed=False,
                order_id=None,
                filled_size=None,
                fill_price=None,
                error=str(e)
            )
    
    def _calculate_order_size(self, equity: float, size_pct: float, price: float, leverage: float = 1.0) -> float:
        """
        Calculate order size based on equity, size percentage, and leverage.
        
        Args:
            equity: Current account equity
            size_pct: Percentage of equity to use as capital (0.0 to 1.0)
            price: Current market price
            leverage: Leverage multiplier (1.0 = no leverage, 2.0 = 2x, 3.0 = 3x)
            
        Returns:
            Order size in base currency units
        """
        # LAYER 1: Calculate capital allocation (how much $ to use from account)
        capital_amount = equity * size_pct
        
        # LAYER 2: Apply leverage multiplier (how much to amplify)
        order_value_usd = capital_amount * leverage
        order_size = order_value_usd / price
        
        # Binance minimum notional value is ~$10 USD (testnet requires higher minimum)
        MIN_ORDER_VALUE_USD = 10.0
        
        if order_value_usd < MIN_ORDER_VALUE_USD:
            logger.warning(
                f"Order value ${order_value_usd:.2f} is below minimum ${MIN_ORDER_VALUE_USD:.2f}. "
                f"Increasing to minimum."
            )
            order_value_usd = MIN_ORDER_VALUE_USD
            order_size = order_value_usd / price
        
        # Round to exchange precision (8 decimals - Binance's maximum for BTC)
        order_size = round(order_size, 8)
        
        logger.info(
            f"Calculated order size: {order_size} BTC (${order_value_usd:.2f} USD) "
            f"[Capital: ${capital_amount:.2f} ({size_pct*100:.1f}%), Leverage: {leverage:.1f}x] "
            f"(equity={equity}, price={price})"
        )
        return order_size
    
    def _execute_long(self, symbol: str, order_size: float) -> ExecutionResult:
        """
        Execute a market buy order (long).
        
        Args:
            symbol: Trading symbol
            order_size: Size of the order
            
        Returns:
            ExecutionResult with order details
        """
        try:
            logger.info(f"Executing LONG: market buy {order_size} {symbol}")
            order = self.exchange.create_market_buy_order(symbol, order_size)
            return self._parse_order_response(order)
        
        except Exception as e:
            logger.error(f"Long execution failed: {str(e)}")
            return ExecutionResult(
                executed=False,
                order_id=None,
                filled_size=None,
                fill_price=None,
                error=str(e)
            )
    
    def _execute_short(self, symbol: str, order_size: float) -> ExecutionResult:
        """
        Execute a market sell order (short) on Futures.
        
        For Futures, shorting means opening a short position (selling contracts).
        The exchange uses 'sell' side for short positions.
        
        Args:
            symbol: Trading symbol
            order_size: Size of the order (in contracts for Futures)
            
        Returns:
            ExecutionResult with order details
        """
        try:
            logger.info(f"Executing SHORT: market sell {order_size} {symbol} (Futures)")
            # For Futures, use 'sell' side to open short position
            # Futures API automatically handles short positions
            order = self.exchange.create_market_sell_order(symbol, order_size)
            return self._parse_order_response(order)
        
        except Exception as e:
            logger.error(f"Short execution failed: {str(e)}")
            return ExecutionResult(
                executed=False,
                order_id=None,
                filled_size=None,
                fill_price=None,
                error=str(e)
            )
    
    def _execute_close(self, symbol: str, position_size: float, current_price: float, is_emergency: bool = False) -> ExecutionResult:
        """
        Execute a close order to flatten the current position.
        
        Args:
            symbol: Trading symbol
            position_size: Current position size (positive for long, negative for short)
            current_price: Current market price from snapshot (for validation)
            is_emergency: Whether this is an emergency close (user-triggered)
            
        Returns:
            ExecutionResult with order details
        """
        try:
            if position_size == 0:
                logger.warning("No position to close")
                return ExecutionResult(
                    executed=False,
                    order_id=None,
                    filled_size=None,
                    fill_price=None,
                    error="No position to close"
                )
            
            # Calculate the size needed to close
            close_size = abs(position_size)
            
            # If long position (positive), sell to close
            if position_size > 0:
                logger.info(f"Executing CLOSE: market sell {close_size} {symbol} (closing long)")
                order = self.exchange.create_market_sell_order(symbol, close_size)
            # If short position (negative), buy to close
            else:
                logger.info(f"Executing CLOSE: market buy {close_size} {symbol} (closing short)")
                order = self.exchange.create_market_buy_order(symbol, close_size)
            
            result = self._parse_order_response(order)
            
            # BUG FIX 1: Validate fill_price - if exchange returns suspicious price, use current price
            if result.executed and result.fill_price:
                # Check if fill_price differs from current price
                price_diff_pct = abs(result.fill_price - current_price) / current_price if current_price > 0 else 1.0
                
                # Stricter threshold for emergency closes (1.5%) vs regular closes (3%)
                # Emergency closes must be accurate - user expects current market price
                threshold_pct = 0.015 if is_emergency else 0.03
                warning_threshold_pct = 0.01  # Log warning for >1% difference
                
                if price_diff_pct > threshold_pct:
                    # More than threshold difference is suspicious - use current price
                    logger.warning(
                        f"Exchange fill_price ${result.fill_price:.2f} differs significantly from "
                        f"current price ${current_price:.2f} ({price_diff_pct*100:.1f}% diff). "
                        f"{'Emergency close - ' if is_emergency else ''}Using current price as fill_price to avoid misleading info."
                    )
                    result.fill_price = current_price
                elif price_diff_pct > warning_threshold_pct:
                    # More than 1% difference - log warning but don't override (normal slippage)
                    logger.warning(
                        f"Exchange fill_price ${result.fill_price:.2f} differs from "
                        f"current price ${current_price:.2f} ({price_diff_pct*100:.1f}% diff). "
                        f"This might indicate exchange latency or slippage."
                    )
            
            return result
        
        except Exception as e:
            logger.error(f"Close execution failed: {str(e)}")
            return ExecutionResult(
                executed=False,
                order_id=None,
                filled_size=None,
                fill_price=None,
                error=str(e)
            )
    
    def _parse_order_response(self, order: dict) -> ExecutionResult:
        """
        Parse exchange order response into ExecutionResult.
        
        Args:
            order: Order response from ccxt
            
        Returns:
            ExecutionResult with parsed order details
        """
        try:
            order_id = order.get('id')
            filled_size = order.get('filled', 0.0)
            
            # Calculate average fill price
            fill_price = None
            if filled_size > 0:
                cost = order.get('cost', 0.0)
                if cost > 0:
                    fill_price = cost / filled_size
                else:
                    # Fallback to average or price field
                    fill_price = order.get('average') or order.get('price')
            
            executed = order.get('status') in ['closed', 'filled']
            
            logger.info(f"Order executed: id={order_id}, filled={filled_size}, price={fill_price}, status={order.get('status')}")
            
            return ExecutionResult(
                executed=executed,
                order_id=order_id,
                filled_size=filled_size,
                fill_price=fill_price,
                error=None
            )
        
        except Exception as e:
            logger.error(f"Failed to parse order response: {str(e)}")
            return ExecutionResult(
                executed=False,
                order_id=None,
                filled_size=None,
                fill_price=None,
                error=f"Failed to parse order response: {str(e)}"
            )
