"""Order size and position calculation logic."""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class OrderSizer:
    """Handles order size calculations and leverage adjustments."""

    def __init__(self, exchange):
        """
        Initialize order sizer.

        Args:
            exchange: CCXT exchange instance
        """
        self.exchange = exchange

    def calculate_order_size(self, symbol: str, equity: float, size_pct: float,
                           price: float, leverage: float = 1.0) -> Tuple[float, float]:
        """
        Calculate order size based on equity, size percentage, and leverage.

        Args:
            symbol: Trading symbol (e.g., "BTC/USDT") - needed for precision rounding
            equity: Current account equity
            size_pct: Percentage of equity to use as capital (0.0 to 1.0)
            price: Current market price
            leverage: Leverage multiplier (1.0 = no leverage, 2.0 = 2x, 3.0 = 3x)

        Returns:
            Tuple of (order_size, actual_leverage)
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
                    ".2f"                    f"and would require {required_leverage:.1f}x leverage (max {MAX_LEVERAGE_FOR_MINIMUM:.1f}x). "
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

        # CRITICAL: After rounding, recalculate actual notional value
        # If it's less than $20, increase order size by one step to meet minimum
        actual_notional = order_size * price
        if actual_notional < MIN_ORDER_VALUE_USD:
            # Need to increase order size to meet minimum
            # Get step size for this symbol
            try:
                futures_symbol = symbol.replace('/', '')
                market_info = self.exchange.fapiPublicGetExchangeInfo()
                step_size = None
                for market in market_info.get('symbols', []):
                    if market['symbol'] == futures_symbol:
                        for filt in market.get('filters', []):
                            if filt.get('filterType') == 'LOT_SIZE':
                                step_size = float(filt.get('stepSize', '0.001'))
                                break
                        break

                if step_size and step_size > 0:
                    # Increase by one step until we meet minimum
                    while actual_notional < MIN_ORDER_VALUE_USD:
                        order_size += step_size
                        actual_notional = order_size * price
                        # Safety check to prevent infinite loop
                        if actual_notional > MIN_ORDER_VALUE_USD * 2:
                            break
                    # Round again after adjustment
                    order_size = self._round_to_precision(symbol, order_size)
                    actual_notional = order_size * price
                    logger.debug(f"Adjusted order size to meet minimum: {order_size:.8f} = ${actual_notional:.2f} notional")
            except Exception as e:
                logger.warning(f"Failed to adjust order size for minimum: {e}")
                # Fallback: use a slightly larger multiplier
                if actual_notional < MIN_ORDER_VALUE_USD:
                    multiplier = MIN_ORDER_VALUE_USD / actual_notional
                    order_size = order_size * multiplier
                    order_size = self._round_to_precision(symbol, order_size)
                    actual_notional = order_size * price

        # Get base currency symbol for display
        base_symbol = symbol.split('/')[0] if '/' in symbol else 'COIN'

        # Use actual notional value for display (after rounding)
        display_notional = order_size * price

        logger.info(
            f"  |-- Order Size: {order_size:.8f} {base_symbol} (${display_notional:.2f})"
        )
        logger.info(
            f"  |-- Capital: ${capital_amount:.2f} ({size_pct*100:.1f}%) | Leverage: {leverage:.1f}x"
        )
        logger.info(
            f"  \\-- Price: ${price:.2f} | Equity: ${equity:.2f}"
        )
        return order_size, leverage  # Return both order size and actual leverage used

    def _round_to_precision(self, symbol: str, order_size: float) -> float:
        """
        Round order size to the correct precision for the symbol.

        Args:
            symbol: Trading symbol
            order_size: Raw order size

        Returns:
            Rounded order size
        """
        try:
            futures_symbol = symbol.replace('/', '')
            market_info = self.exchange.fapiPublicGetExchangeInfo()

            for market in market_info.get('symbols', []):
                if market['symbol'] == futures_symbol:
                    step_size = None
                    for filt in market.get('filters', []):
                        if filt.get('filterType') == 'LOT_SIZE':
                            step_size = float(filt.get('stepSize', '0.001'))
                            break
                    if step_size:
                        # Round to step size precision
                        precision = str(step_size).find('1') - 1 if '1' in str(step_size) else 3
                        order_size = round(order_size / step_size) * step_size
                        order_size = round(order_size, precision)
                    break
        except Exception as e:
            logger.warning(f"Failed to round order size for {symbol}: {e}")
            # Fallback: round to 3 decimal places
            order_size = round(order_size, 3)

        return order_size
