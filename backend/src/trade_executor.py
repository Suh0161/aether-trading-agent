"""Trade execution layer for the Autonomous Trading Agent."""

import ccxt
import logging
import time
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
        if exchange_type == "binance_demo":
            # Binance Demo Trading uses demo.binance.com URLs
            # Demo trading is DIFFERENT from testnet - do NOT use set_sandbox_mode
            # Just override URLs directly to point to demo.binance.com
            logger.info("DEMO TRADING MODE: Using Binance Demo Trading environment.")
            logger.info("Using demo API keys from demo.binance.com")
            exchange = ccxt.binance({
                'apiKey': config.exchange_api_key,
                'secret': config.exchange_api_secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',  # Use USD-M Futures
                    'adjustForTimeDifference': True,
                }
            })
            # Override ALL URLs to demo endpoints - DO NOT use set_sandbox_mode
            # because ccxt will block Futures in sandbox mode
            # Override base API URLs to prevent calls to live SAPI endpoints
            exchange.urls['api'].update({
                'public': 'https://demo.binance.com/api',
                'private': 'https://demo.binance.com/api',
                'fapiPublic': 'https://demo-fapi.binance.com/fapi/v1',
                'fapiPrivate': 'https://demo-fapi.binance.com/fapi/v1',
            })
        elif exchange_type == "binance_testnet":
            # NOTE: Binance Futures does not support testnet/sandbox mode anymore
            # We'll use live Futures API endpoints (user should use small amounts for testing)
            logger.warning("TESTNET MODE: Binance Futures testnet is deprecated. Using live Futures API.")
            logger.warning("IMPORTANT: You MUST use LIVE API keys (not testnet keys) for Futures trading.")
            logger.warning("IMPORTANT: Ensure your API key has 'Enable Futures' enabled in Binance API Management.")
            logger.warning("IMPORTANT: Use small amounts for testing. Switch to RUN_MODE=live for Futures trading.")
            exchange = ccxt.binance({
                'apiKey': config.exchange_api_key,
                'secret': config.exchange_api_secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',  # Use USD-M Futures
                }
            })
            # DO NOT call set_sandbox_mode(True) for Futures - it's not supported
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
            # Note: _calculate_order_size may adjust leverage for small accounts to meet minimum
            leverage = getattr(decision, 'leverage', 1.0)  # Default to 1.0 if not provided
            order_size, actual_leverage = self._calculate_order_size(snapshot.symbol, equity, decision.size_pct, snapshot.price, leverage)
            # Update decision with actual leverage used (may be higher for small accounts)
            if actual_leverage != leverage:
                decision.leverage = actual_leverage
            
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
    
    def _calculate_order_size(self, symbol: str, equity: float, size_pct: float, price: float, leverage: float = 1.0) -> tuple:
        """
        Calculate order size based on equity, size percentage, and leverage.
        
        Args:
            symbol: Trading symbol (e.g., "BTC/USDT") - needed for precision rounding
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
        
        # Binance Futures minimum notional value is $20 USD
        # (Binance Spot has $10 minimum, but Futures requires $20)
        MIN_ORDER_VALUE_USD = 20.0
        
        if order_value_usd < MIN_ORDER_VALUE_USD:
            # Smart money: For small accounts, calculate what leverage is needed to reach minimum
            # This allows trading with $5, $10, or any small amount
            required_leverage = MIN_ORDER_VALUE_USD / capital_amount if capital_amount > 0 else 0
            
            # Maximum allowed leverage (Binance Futures typically allows 10-20x for small accounts)
            # Use conservative limit: max 10x leverage for small accounts
            MAX_LEVERAGE_FOR_MINIMUM = 10.0
            
            if required_leverage > MAX_LEVERAGE_FOR_MINIMUM:
                # Even with max leverage, can't reach minimum
                logger.warning(
                    f"Order value ${order_value_usd:.2f} is below minimum ${MIN_ORDER_VALUE_USD:.2f}, "
                    f"and would require {required_leverage:.1f}x leverage (max {MAX_LEVERAGE_FOR_MINIMUM:.1f}x). "
                    f"Account too small to place minimum order (capital: ${capital_amount:.2f})."
                )
                return 0.0, leverage  # Return 0 to indicate order cannot be placed
            
            # Can reach minimum with higher leverage - adjust leverage and increase to minimum
            if required_leverage > leverage:
                logger.info(
                    f"Increasing leverage from {leverage:.1f}x to {required_leverage:.1f}x "
                    f"to reach minimum order size ${MIN_ORDER_VALUE_USD:.2f} "
                    f"(capital: ${capital_amount:.2f})"
                )
                leverage = required_leverage
            
            # Increase to minimum order value
            logger.info(
                f"Order value ${order_value_usd:.2f} increased to minimum ${MIN_ORDER_VALUE_USD:.2f} "
                f"(using {leverage:.1f}x leverage with ${capital_amount:.2f} capital)"
            )
            order_value_usd = MIN_ORDER_VALUE_USD
            order_size = order_value_usd / price
        
        # Get market precision for the symbol and round to correct decimals
        order_size = self._round_to_precision(symbol, order_size)
        
        # Get base currency symbol for display
        base_symbol = symbol.split('/')[0] if '/' in symbol else 'COIN'
        
        logger.info(
            f"  |-- Order Size: {order_size:.8f} {base_symbol} (${order_value_usd:.2f})"
        )
        logger.info(
            f"  |-- Capital: ${capital_amount:.2f} ({size_pct*100:.1f}%) | Leverage: {leverage:.1f}x"
        )
        logger.info(
            f"  \\-- Price: ${price:.2f} | Equity: ${equity:.2f}"
        )
        return order_size, leverage  # Return both order size and actual leverage used
    
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
            # For demo trading, use Futures-specific order placement method
            if self.config.exchange_type.lower() == "binance_demo":
                # Use Futures order endpoint directly (ensures demo endpoints are used)
                futures_symbol = symbol.replace('/', '')
                logger.debug(f"Demo order params: symbol={futures_symbol}, side=BUY, type=MARKET, quantity={order_size}")
                order = self.exchange.fapiPrivatePostOrder({
                    'symbol': futures_symbol,
                    'side': 'BUY',
                    'type': 'MARKET',
                    'quantity': order_size
                })
                logger.debug(f"Demo order response: {order}")
                result = self._parse_futures_order_response(order, symbol)
                
                # For market orders, if status is 'NEW' and not filled, wait and check status
                order_status = order.get('status', '')
                if not result.executed and order_status == 'NEW' and order.get('orderId'):
                    # Wait briefly for market order to fill (should be instant for market orders)
                    time.sleep(0.5)
                    # Check order status
                    result = self._check_order_status(futures_symbol, order.get('orderId'), symbol)
                
                if not result.executed:
                    logger.warning(f"Order returned but executed=False. Response: {order}")
                return result
            else:
                # For live/testnet, use standard ccxt method
                order = self.exchange.create_market_buy_order(symbol, order_size)
                return self._parse_order_response(order)
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Long execution failed: {error_msg}")
            logger.error(f"Full exception: {type(e).__name__}: {e}", exc_info=True)
            return ExecutionResult(
                executed=False,
                order_id=None,
                filled_size=None,
                fill_price=None,
                error=error_msg
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
            # For demo trading, use Futures-specific order placement method
            if self.config.exchange_type.lower() == "binance_demo":
                # Use Futures order endpoint directly (ensures demo endpoints are used)
                futures_symbol = symbol.replace('/', '')
                logger.debug(f"Demo order params: symbol={futures_symbol}, side=SELL, type=MARKET, quantity={order_size}")
                order = self.exchange.fapiPrivatePostOrder({
                    'symbol': futures_symbol,
                    'side': 'SELL',  # SELL opens a short position in Futures
                    'type': 'MARKET',
                    'quantity': order_size
                })
                logger.debug(f"Demo order response: {order}")
                result = self._parse_futures_order_response(order, symbol)
                
                # For market orders, if status is 'NEW' and not filled, wait and check status
                order_status = order.get('status', '')
                if not result.executed and order_status == 'NEW' and order.get('orderId'):
                    # Wait briefly for market order to fill (should be instant for market orders)
                    time.sleep(0.5)
                    # Check order status
                    result = self._check_order_status(futures_symbol, order.get('orderId'), symbol)
                
                if not result.executed:
                    logger.warning(f"Order returned but executed=False. Response: {order}")
                return result
            else:
                # For live/testnet, use standard ccxt method
                # For Futures, use 'sell' side to open short position
                # Futures API automatically handles short positions
                order = self.exchange.create_market_sell_order(symbol, order_size)
                return self._parse_order_response(order)
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Short execution failed: {error_msg}")
            logger.error(f"Full exception: {type(e).__name__}: {e}", exc_info=True)
            return ExecutionResult(
                executed=False,
                order_id=None,
                filled_size=None,
                fill_price=None,
                error=error_msg
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
            
            # For demo trading, use Futures-specific order placement method (like long/short)
            if self.config.exchange_type.lower() == "binance_demo":
                # Use Futures order endpoint directly (ensures demo endpoints are used)
                futures_symbol = symbol.replace('/', '')
                
                # If long position (positive), sell to close
                if position_size > 0:
                    logger.info(f"Executing CLOSE: market sell {close_size} {symbol} (closing long)")
                    logger.debug(f"Demo close order params: symbol={futures_symbol}, side=SELL, type=MARKET, quantity={close_size}")
                    order = self.exchange.fapiPrivatePostOrder({
                        'symbol': futures_symbol,
                        'side': 'SELL',
                        'type': 'MARKET',
                        'quantity': close_size
                    })
                # If short position (negative), buy to close
                else:
                    logger.info(f"Executing CLOSE: market buy {close_size} {symbol} (closing short)")
                    logger.debug(f"Demo close order params: symbol={futures_symbol}, side=BUY, type=MARKET, quantity={close_size}")
                    order = self.exchange.fapiPrivatePostOrder({
                        'symbol': futures_symbol,
                        'side': 'BUY',
                        'type': 'MARKET',
                        'quantity': close_size
                    })
                
                logger.debug(f"Demo close order response: {order}")
                result = self._parse_futures_order_response(order, symbol)
                
                # For market orders, if status is 'NEW' and not filled, wait and check status
                order_status = order.get('status', '')
                if not result.executed and order_status == 'NEW' and order.get('orderId'):
                    # Wait briefly for market order to fill (should be instant for market orders)
                    time.sleep(0.5)
                    # Check order status
                    result = self._check_order_status(futures_symbol, order.get('orderId'), symbol)
                
                if not result.executed:
                    logger.warning(f"Close order returned but executed=False. Response: {order}")
            else:
                # For live/testnet, use standard ccxt method
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
    
    def _parse_futures_order_response(self, order: dict, symbol: str) -> ExecutionResult:
        """
        Parse Futures order response from fapiPrivatePostOrder endpoint.
        
        Args:
            order: Raw order response from Futures API
            symbol: Trading symbol (for logging)
            
        Returns:
            ExecutionResult with order details
        """
        try:
            # Check if response contains error
            if 'code' in order and order.get('code') != 200:
                error_msg = order.get('msg', f"Order failed with code {order.get('code')}")
                logger.error(f"Order API returned error: {error_msg} | Full response: {order}")
                return ExecutionResult(
                    executed=False,
                    order_id=None,
                    filled_size=None,
                    fill_price=None,
                    error=error_msg
                )
            
            # Futures API returns different format than standard ccxt response
            order_id = order.get('orderId') or order.get('order_id')
            filled_qty = float(order.get('executedQty', 0) or order.get('executed_qty', 0) or order.get('cumQty', 0))
            avg_price = float(order.get('avgPrice', 0) or order.get('avg_price', 0) or order.get('price', 0))
            order_status = order.get('status', '').upper()
            
            # Check if order is filled based on status
            # Binance Futures order statuses: NEW, PARTIALLY_FILLED, FILLED, CANCELED, EXPIRED
            is_filled = order_status in ['FILLED', 'PARTIALLY_FILLED']
            
            # If no average price, try to get from fills
            if avg_price == 0 and 'fills' in order and len(order['fills']) > 0:
                # Calculate weighted average price from fills
                total_qty = 0
                total_value = 0
                for fill in order['fills']:
                    qty = float(fill.get('qty', 0))
                    price = float(fill.get('price', 0))
                    total_qty += qty
                    total_value += qty * price
                if total_qty > 0:
                    avg_price = total_value / total_qty
            
            # Order is executed if it has filled quantity OR if status shows FILLED/PARTIALLY_FILLED
            executed = filled_qty > 0 or is_filled
            
            # For demo trading, if order status is NEW but we have an orderId, 
            # it might still be pending (demo trading may not fill immediately)
            if not executed and order_status == 'NEW' and self.config.exchange_type.lower() == "binance_demo":
                logger.debug(f"Demo order status is NEW (not yet filled) - orderId: {order_id}")
            
            return ExecutionResult(
                executed=executed,
                order_id=str(order_id) if order_id else None,
                filled_size=filled_qty,
                fill_price=avg_price if avg_price > 0 else None,
                error=None
            )
        except Exception as e:
            logger.error(f"Failed to parse Futures order response: {e}")
            return ExecutionResult(
                executed=False,
                order_id=None,
                filled_size=None,
                fill_price=None,
                error=f"Failed to parse order response: {str(e)}"
            )
    
    def _check_order_status(self, futures_symbol: str, order_id: int, symbol: str) -> ExecutionResult:
        """
        Check the status of an order by querying the exchange.
        
        Args:
            futures_symbol: Futures symbol (e.g., "BTCUSDT")
            order_id: Order ID from exchange
            symbol: Trading symbol (e.g., "BTC/USDT") for display
            
        Returns:
            ExecutionResult with order details
        """
        try:
            # Query order status using fapiPrivateGetOrder
            order_status = self.exchange.fapiPrivateGetOrder({
                'symbol': futures_symbol,
                'orderId': order_id
            })
            
            logger.debug(f"Order status check response: {order_status}")
            
            # Parse the order status response
            return self._parse_futures_order_response(order_status, symbol)
            
        except Exception as e:
            logger.error(f"Failed to check order status: {e}")
            return ExecutionResult(
                executed=False,
                order_id=str(order_id),
                filled_size=None,
                fill_price=None,
                error=f"Failed to check order status: {str(e)}"
            )
    
    def _round_to_precision(self, symbol: str, order_size: float) -> float:
        """
        Round order size to the correct precision for the symbol.
        Binance Futures has specific quantity precision requirements per asset.
        Ensures order size never rounds to 0.0 by using minimum step_size.
        
        Args:
            symbol: Trading symbol (e.g., "BTC/USDT")
            order_size: Order size to round
            
        Returns:
            Rounded order size (never 0.0 if input > 0)
        """
        import math
        
        try:
            # Fetch market info to get precision
            futures_symbol = symbol.replace('/', '')
            step_size = None
            precision = None
            
            # For demo trading, use Futures exchange info endpoint
            if self.config.exchange_type.lower() == "binance_demo":
                try:
                    exchange_info = self.exchange.fapiPublicGetExchangeInfo()
                    for s in exchange_info.get('symbols', []):
                        if s.get('symbol') == futures_symbol:
                            # Get quantity precision from filters
                            for f in s.get('filters', []):
                                if f.get('filterType') == 'LOT_SIZE':
                                    step_size = float(f.get('stepSize', '1.0'))
                                    # Calculate precision from step size
                                    # e.g., stepSize=0.001 means 3 decimals
                                    precision = len(str(step_size).rstrip('0').split('.')[-1]) if '.' in str(step_size) else 0
                                    break
                except Exception as e:
                    logger.warning(f"Failed to fetch precision for {symbol}, using default: {e}")
            
            # Default precision based on symbol (common Binance Futures precisions)
            # These are fallback values if we can't fetch from exchange
            if step_size is None:
                symbol_precision = {
                    'BTC/USDT': (3, 0.001),   # 0.001 BTC minimum
                    'ETH/USDT': (3, 0.001),   # 0.001 ETH minimum
                    'SOL/USDT': (2, 0.01),   # 0.01 SOL minimum
                    'DOGE/USDT': (0, 1.0),    # 1 DOGE minimum (whole numbers)
                    'BNB/USDT': (2, 0.01),    # 0.01 BNB minimum
                    'XRP/USDT': (1, 0.1),     # 0.1 XRP minimum
                }
                if symbol in symbol_precision:
                    precision, step_size = symbol_precision[symbol]
                else:
                    precision = 3
                    step_size = 0.001
            
            # Round DOWN to nearest step_size multiple (floor division)
            # This ensures we don't exceed precision requirements
            if order_size > 0:
                # Round DOWN to step_size
                rounded = math.floor(order_size / step_size) * step_size
                
                # If rounding down results in 0.0, round UP to minimum step_size instead
                # This ensures we can still place very small orders (e.g., $25 on BTC)
                if rounded == 0.0 and order_size > 0:
                    rounded = step_size
                    logger.debug(f"Order size {order_size} too small, rounding UP to minimum step_size {step_size}")
                
                # Round to precision for display/consistency
                rounded = round(rounded, precision)
                
                logger.debug(f"Rounded {symbol} order size: {order_size} -> {rounded} (step_size: {step_size}, precision: {precision})")
                return rounded
            else:
                return 0.0
            
        except Exception as e:
            logger.warning(f"Error rounding order size for {symbol}: {e}, using default 3 decimals")
            # Fallback: ensure we don't round to 0.0
            if order_size > 0:
                rounded = round(order_size, 3)
                return max(rounded, 0.001)  # Minimum 0.001 for BTC-like assets
            return 0.0
    
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
