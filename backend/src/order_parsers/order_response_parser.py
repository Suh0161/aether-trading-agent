"""Order response parsing and status checking logic."""

import logging
import time
from typing import Optional

from src.models import ExecutionResult

logger = logging.getLogger(__name__)


class OrderResponseParser:
    """Handles parsing of order responses and status checking."""

    def __init__(self, exchange, config):
        """
        Initialize order response parser.

        Args:
            exchange: CCXT exchange instance
            config: Configuration object
        """
        self.exchange = exchange
        self.config = config

    def parse_futures_order_response(self, order: dict, symbol: str) -> ExecutionResult:
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

    def check_order_status(self, futures_symbol: str, order_id: int, symbol: str) -> ExecutionResult:
        """
        Check the status of an order by querying the exchange.

        Args:
            futures_symbol: Futures symbol (e.g., "BTCUSDT")
            order_id: Order ID from exchange
            symbol: Trading symbol (e.g., "BTC/USDT") for display

        Returns:
            ExecutionResult with updated order status
        """
        try:
            # Query order status using Futures API
            order_status = self.exchange.fapiPrivateGetOrder({
                'symbol': futures_symbol,
                'orderId': order_id
            })

            # Parse the status response
            return self.parse_futures_order_response(order_status, symbol)

        except Exception as e:
            logger.error(f"Failed to check order status for {symbol} order {order_id}: {e}")
            return ExecutionResult(
                executed=False,
                order_id=str(order_id),
                filled_size=None,
                fill_price=None,
                error=f"Failed to check order status: {str(e)}"
            )

    def parse_order_response(self, order: dict) -> ExecutionResult:
        """
        Parse standard ccxt order response.

        Args:
            order: Order response from ccxt

        Returns:
            ExecutionResult with order details
        """
        try:
            # Standard ccxt order response format
            order_id = order.get('id')
            filled_qty = float(order.get('filled', 0))
            avg_price = float(order.get('average', 0) or order.get('price', 0))
            order_status = order.get('status', '').upper()

            # Check if order is filled
            is_filled = order_status in ['closed', 'filled'] or filled_qty > 0
            executed = is_filled and filled_qty > 0

            return ExecutionResult(
                executed=executed,
                order_id=str(order_id) if order_id else None,
                filled_size=filled_qty,
                fill_price=avg_price if avg_price > 0 else None,
                error=None
            )
        except Exception as e:
            logger.error(f"Failed to parse order response: {e}")
            return ExecutionResult(
                executed=False,
                order_id=None,
                filled_size=None,
                fill_price=None,
                error=f"Failed to parse order response: {str(e)}"
            )
