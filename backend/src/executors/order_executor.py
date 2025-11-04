"""Order execution logic for different trade types."""

import logging
import time
from typing import Optional

from src.models import ExecutionResult

logger = logging.getLogger(__name__)


class OrderExecutor:
    """Handles execution of different order types (long, short, close)."""

    def __init__(self, exchange, config, order_parser):
        """
        Initialize order executor.

        Args:
            exchange: CCXT exchange instance
            config: Configuration object
            order_parser: Order response parser instance
        """
        self.exchange = exchange
        self.config = config
        self.order_parser = order_parser

    def execute_long(self, symbol: str, order_size: float) -> ExecutionResult:
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
                result = self.order_parser.parse_futures_order_response(order, symbol)

                # For market orders, if status is 'NEW' and not filled, wait and check status
                order_status = order.get('status', '')
                if not result.executed and order_status == 'NEW' and order.get('orderId'):
                    # Wait briefly for market order to fill (should be instant for market orders)
                    time.sleep(0.5)
                    # Check order status
                    result = self.order_parser.check_order_status(futures_symbol, order.get('orderId'), symbol)

                if not result.executed:
                    logger.warning(f"Order returned but executed=False. Response: {order}")
                return result
            else:
                # For live/testnet, use standard ccxt method
                order = self.exchange.create_market_buy_order(symbol, order_size)
                return self.order_parser.parse_order_response(order)

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

    def execute_short(self, symbol: str, order_size: float) -> ExecutionResult:
        """
        Execute a market sell order (short) on Futures.

        For Futures, shorting means opening a short position (selling contracts).
        This is the opposite of spot trading where selling means closing a position.

        Args:
            symbol: Trading symbol
            order_size: Size of the order

        Returns:
            ExecutionResult with order details
        """
        try:
            logger.info(f"Executing SHORT: market sell {order_size} {symbol}")
            # For demo trading, use Futures-specific order placement method
            if self.config.exchange_type.lower() == "binance_demo":
                # Use Futures order endpoint directly (ensures demo endpoints are used)
                futures_symbol = symbol.replace('/', '')
                logger.debug(f"Demo order params: symbol={futures_symbol}, side=SELL, type=MARKET, quantity={order_size}")
                order = self.exchange.fapiPrivatePostOrder({
                    'symbol': futures_symbol,
                    'side': 'SELL',
                    'type': 'MARKET',
                    'quantity': order_size
                })
                logger.debug(f"Demo order response: {order}")
                result = self.order_parser.parse_futures_order_response(order, symbol)

                # For market orders, if status is 'NEW' and not filled, wait and check status
                order_status = order.get('status', '')
                if not result.executed and order_status == 'NEW' and order.get('orderId'):
                    # Wait briefly for market order to fill (should be instant for market orders)
                    time.sleep(0.5)
                    # Check order status
                    result = self.order_parser.check_order_status(futures_symbol, order.get('orderId'), symbol)

                if not result.executed:
                    logger.warning(f"Order returned but executed=False. Response: {order}")
                return result
            else:
                # For live/testnet, use standard ccxt method
                order = self.exchange.create_market_sell_order(symbol, order_size)
                return self.order_parser.parse_order_response(order)

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

    def execute_close(self, symbol: str, position_size: float, current_price: float,
                     is_emergency: bool = False) -> ExecutionResult:
        """
        Close an existing position (works for both long and short positions).

        For Futures, closing means:
        - If position_size > 0 (long): Sell to close
        - If position_size < 0 (short): Buy to close

        Args:
            symbol: Trading symbol
            position_size: Current position size (positive = long, negative = short)
            current_price: Current market price (for emergency close logging)
            is_emergency: Whether this is an emergency close

        Returns:
            ExecutionResult with close order details
        """
        try:
            # Determine direction based on position
            if position_size > 0:
                # Long position - sell to close
                close_size = position_size
                logger.info(f"{'EMERGENCY ' if is_emergency else ''}Closing LONG position: market sell {close_size} {symbol}")
            elif position_size < 0:
                # Short position - buy to close
                close_size = abs(position_size)
                logger.info(f"{'EMERGENCY ' if is_emergency else ''}Closing SHORT position: market buy {close_size} {symbol}")
            else:
                logger.warning("Attempted to close position with size 0")
                return ExecutionResult(
                    executed=False,
                    order_id=None,
                    filled_size=0.0,
                    fill_price=current_price,
                    error="No position to close"
                )

            # For demo trading, use Futures-specific order placement method
            if self.config.exchange_type.lower() == "binance_demo":
                # Use Futures order endpoint directly (ensures demo endpoints are used)
                futures_symbol = symbol.replace('/', '')
                side = 'SELL' if position_size > 0 else 'BUY'  # Sell to close long, buy to close short

                logger.debug(f"Demo close order params: symbol={futures_symbol}, side={side}, type=MARKET, quantity={close_size}")
                order = self.exchange.fapiPrivatePostOrder({
                    'symbol': futures_symbol,
                    'side': side,
                    'type': 'MARKET',
                    'quantity': close_size
                })
                logger.debug(f"Demo close order response: {order}")
                result = self.order_parser.parse_futures_order_response(order, symbol)

                # For market orders, if status is 'NEW' and not filled, wait and check status
                order_status = order.get('status', '')
                if not result.executed and order_status == 'NEW' and order.get('orderId'):
                    # Wait briefly for market order to fill (should be instant for market orders)
                    time.sleep(0.5)
                    # Check order status
                    result = self.order_parser.check_order_status(futures_symbol, order.get('orderId'), symbol)

                if not result.executed:
                    logger.warning(f"Close order returned but executed=False. Response: {order}")
                return result
            else:
                # For live/testnet, use standard ccxt method
                if position_size > 0:
                    # Close long position
                    order = self.exchange.create_market_sell_order(symbol, close_size)
                else:
                    # Close short position
                    order = self.exchange.create_market_buy_order(symbol, close_size)
                return self.order_parser.parse_order_response(order)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Close execution failed: {error_msg}")
            logger.error(f"Full exception: {type(e).__name__}: {e}", exc_info=True)
            return ExecutionResult(
                executed=False,
                order_id=None,
                filled_size=None,
                fill_price=current_price,
                error=error_msg
            )
