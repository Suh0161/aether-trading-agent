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

    def _get_symbol_minimums(self, symbol: str) -> Tuple[float, float, float]:
        """
        Fetch symbol-specific minimum requirements from Binance.

        Args:
            symbol: Trading symbol (e.g., "BTC/USDT")

        Returns:
            Tuple of (min_notional_usd, min_qty, step_size)
        """
        try:
            futures_symbol = symbol.replace('/', '')
            market_info = self.exchange.fapiPublicGetExchangeInfo()
            
            # Default fallback: Binance Futures demo enforces $20 min notional for many symbols
            # Some symbols or environments may require higher; API will override when available
            min_notional = 20.0  # Safer default to avoid rejections when API lacks MIN_NOTIONAL
            min_qty = 0.001  # Default fallback
            step_size = 0.001  # Default fallback

            for market in market_info.get('symbols', []):
                if market['symbol'] == futures_symbol:
                    for filt in market.get('filters', []):
                        if filt.get('filterType') == 'MIN_NOTIONAL':
                            min_notional = float(filt.get('minNotional', '10.0'))
                        elif filt.get('filterType') == 'LOT_SIZE':
                            min_qty = float(filt.get('minQty', '0.001'))
                            step_size = float(filt.get('stepSize', '0.001'))
                    break
            # Demo safety: Futures demo often enforces $20 minimum even if API reports lower
            try:
                api_urls = getattr(self.exchange, 'urls', {}).get('api', {})
                url_blob = ' '.join(api_urls.values()) if isinstance(api_urls, dict) else str(api_urls)
                is_demo = ('demo' in url_blob.lower()) or ('testnet' in url_blob.lower())
            except Exception:
                is_demo = False

            # Floor to $20 for demo; also guard against missing/invalid values
            if is_demo:
                min_notional = max(min_notional or 0.0, 20.0)
            elif not min_notional or min_notional <= 0:
                min_notional = 20.0
            return min_notional, min_qty, step_size
        except Exception as e:
            logger.warning(f"Failed to fetch minimums for {symbol}: {e}, using defaults")
            # Safe defaults: Use $20 to match Binance Futures demo minimum
            return 20.0, 0.001, 0.001  # Safe defaults

    def calculate_order_size(self, symbol: str, equity: float, size_pct: float,
                           price: float, leverage: float = 1.0, confidence: float = None) -> Tuple[float, float]:
        """
        Calculate order size based on equity, size percentage, and leverage.
        
        SMART MONEY MANAGEMENT PRINCIPLES:
        - Accounts $100+: Max leverage 2x (not greedy)
        - Accounts <$100: Max leverage 1x (conservative)
        - AI confidence influences leverage:
          * High confidence (0.8+): Up to 2x (whole numbers only: 1x or 2x)
          * Medium confidence (0.6-0.8): 1x (conservative)
          * Low confidence (<0.6): 1x
        - Binance does NOT support decimal leverage (no 1.5x, 2.5x, etc.)
        
        This ensures:
        1. Small accounts can trade (1x max for <$100)
        2. Large accounts don't over-leverage (2x max, not greedy)
        3. AI confidence directly controls leverage (smart money)
        4. All accounts respect exchange minimums (dynamic fetching from API)

        Args:
            symbol: Trading symbol (e.g., "BTC/USDT") - needed for precision rounding
            equity: Current account equity
            size_pct: Percentage of equity to use as capital (0.0 to 1.0)
            price: Current market price
            leverage: Leverage multiplier from strategy/AI (1.0 = no leverage, 2.0 = 2x)
            confidence: Optional confidence score (0.0-1.0) for leverage adjustment

        Returns:
            Tuple of (order_size, actual_leverage, capital_amount)
            capital_amount: The actual capital allocated (before order size inflation to meet minimums)
        """
        # Fetch symbol-specific minimum requirements
        min_notional_usd, min_qty, step_size = self._get_symbol_minimums(symbol)
        logger.debug(f"Symbol {symbol} minimums: notional=${min_notional_usd:.2f}, min_qty={min_qty}, step_size={step_size}")

        # LAYER 1: Calculate capital allocation (how much $ to use from account)
        capital_amount = equity * size_pct

        # SMART MONEY: Equity-based leverage caps (simple and not greedy)
        if equity >= 100:
            MAX_LEVERAGE_BY_EQUITY = 2.0  # Max 2x for accounts $100+
            logger.debug(f"Account (${equity:.2f}): Max leverage {int(MAX_LEVERAGE_BY_EQUITY)}x allowed")
        else:
            MAX_LEVERAGE_BY_EQUITY = 1.0  # Max 1x for accounts <$100
            logger.debug(f"Small account (${equity:.2f}): Max leverage {int(MAX_LEVERAGE_BY_EQUITY)}x (conservative)")

        # SMART MONEY: AI confidence-based leverage adjustment
        # If confidence provided, adjust leverage based on confidence (but respect equity cap)
        # Binance only supports whole numbers: 1x or 2x (no decimals)
        if confidence is not None:
            if confidence >= 0.8:
                # High confidence: Use max leverage (up to equity cap)
                confidence_based_leverage = MAX_LEVERAGE_BY_EQUITY
                logger.debug(f"High confidence ({confidence:.2f}): Using max leverage {int(confidence_based_leverage)}x")
            elif confidence >= 0.6:
                # Medium confidence: Use 1x (conservative for medium confidence)
                # For accounts with 2x max: medium confidence stays at 1x (not greedy)
                confidence_based_leverage = 1.0
                logger.debug(f"Medium confidence ({confidence:.2f}): Using 1x leverage (conservative)")
            else:
                # Low confidence: Use 1x (conservative)
                confidence_based_leverage = 1.0
                logger.debug(f"Low confidence ({confidence:.2f}): Using 1x leverage (conservative)")
            
            # Override strategy leverage with confidence-based leverage
            if confidence_based_leverage != leverage:
                logger.info(
                    f"Smart money: Adjusting leverage from {int(leverage)}x to {int(confidence_based_leverage)}x "
                    f"based on AI confidence {confidence:.2f}"
                )
            leverage = confidence_based_leverage
        else:
            # No confidence provided - cap leverage to equity-based maximum
            if leverage > MAX_LEVERAGE_BY_EQUITY:
                logger.info(
                    f"Smart money: Capping leverage from {int(leverage)}x to {int(MAX_LEVERAGE_BY_EQUITY)}x "
                    f"(equity-based limit for ${equity:.2f} account)"
                )
                leverage = MAX_LEVERAGE_BY_EQUITY

        # Round leverage to whole numbers only (1x or 2x) - Binance does NOT support decimal leverage
        leverage = int(round(leverage))
        if leverage > 2:
            leverage = 2
        elif leverage < 1:
            leverage = 1

        # LAYER 2: Apply leverage multiplier (how much to amplify)
        order_value_usd = capital_amount * leverage
        order_size = order_value_usd / price

        # Smart money management: Adjust leverage if needed to reach minimum
        # Calculate minimum order quantity: max(minQty, minNotional / price)
        min_order_qty = max(min_qty, min_notional_usd / price)
        
        logger.debug(f"Pre-adjustment: order_value=${order_value_usd:.2f}, min_notional=${min_notional_usd:.2f}, leverage={leverage:.1f}x")
        
        if order_value_usd < min_notional_usd:
            # Smart money: For small accounts, calculate what leverage is needed to reach minimum
            # BUT respect the equity-based maximum (can't exceed 2x for $100+, 1x for <$100)
            required_leverage = min_notional_usd / capital_amount if capital_amount > 0 else 0

            # CRITICAL: Don't exceed equity-based maximum leverage cap
            MAX_LEVERAGE_FOR_MINIMUM = MAX_LEVERAGE_BY_EQUITY

            if required_leverage > MAX_LEVERAGE_FOR_MINIMUM:
                # Even with max leverage, can't reach minimum
                logger.warning(
                    f"Order value ${order_value_usd:.2f} below minimum ${min_notional_usd:.2f} "
                    f"and would require {required_leverage:.1f}x leverage (max {MAX_LEVERAGE_FOR_MINIMUM:.1f}x). "
                    f"Account too small to place minimum order (capital: ${capital_amount:.2f}, equity: ${equity:.2f}). "
                    f"Need at least ${min_notional_usd/MAX_LEVERAGE_FOR_MINIMUM:.2f} capital per position."
                )
                return 0.0, int(round(min(max(leverage, 1.0), 2.0))), capital_amount  # Cannot place order

            # Can reach minimum with higher leverage - adjust leverage up to maximum allowed
            if required_leverage > leverage:
                # Cap at maximum allowed leverage
                adjusted_leverage = min(required_leverage, MAX_LEVERAGE_FOR_MINIMUM)
                if adjusted_leverage != leverage:
                    logger.info(
                        f"Smart money: Increasing leverage from {int(leverage)}x to {int(adjusted_leverage)}x "
                        f"to reach minimum order size ${min_notional_usd:.2f} "
                        f"(capital: ${capital_amount:.2f}, equity: ${equity:.2f})"
                    )
                    leverage = adjusted_leverage
                    # Round leverage to whole number (Binance doesn't support decimals)
                    leverage = int(round(min(leverage, 2.0)))
                    if leverage < 1:
                        leverage = 1
                    order_value_usd = capital_amount * leverage
                    order_size = order_value_usd / price

            # If still below minimum after leverage adjustment, increase order value to minimum
            if order_value_usd < min_notional_usd:
                logger.info(
                    f"Order value ${order_value_usd:.2f} increased to minimum ${min_notional_usd:.2f} "
                    f"(using {leverage:.1f}x leverage with ${capital_amount:.2f} capital)"
                )
                order_value_usd = min_notional_usd
                order_size = order_value_usd / price

        # Ensure order size meets minimum quantity requirement
        if order_size < min_order_qty:
            order_size = min_order_qty
            order_value_usd = order_size * price
            logger.debug(f"Adjusted order size to meet min quantity: {order_size:.8f} = ${order_value_usd:.2f}")

        # Get market precision for the symbol and round to correct decimals
        order_size = self._round_to_precision(symbol, order_size)

        # CRITICAL: After rounding, recalculate actual notional value
        # If it's less than minimum, increase order size to meet minimum
        actual_notional = order_size * price
        # Guard: if precision rounding zeroed quantity, lift to min order qty immediately
        min_order_qty = max(min_qty, min_notional_usd / price)
        if order_size <= 0 and min_order_qty > 0:
            order_size = min_order_qty
            actual_notional = order_size * price
        if actual_notional < min_notional_usd:
            logger.warning(
                f"Order notional ${actual_notional:.2f} below minimum ${min_notional_usd:.2f} after rounding. "
                f"Increasing order size to meet minimum..."
            )
            # Calculate required order size to meet minimum
            required_order_size = min_notional_usd / price
            logger.debug(f"Required order size to meet minimum: {required_order_size:.8f} (current: {order_size:.8f})")
            
            # Increase order size using step_size if available
            if step_size and step_size > 0:
                # Increase by steps until we meet minimum
                max_iterations = 1000  # Safety limit
                iterations = 0
                while actual_notional < min_notional_usd and iterations < max_iterations:
                    order_size += step_size
                    actual_notional = order_size * price
                    iterations += 1
                    # Safety check to prevent infinite loop
                    if actual_notional > min_notional_usd * 2:
                        logger.warning(f"Order size adjustment exceeded 2x minimum, stopping at ${actual_notional:.2f}")
                        break
                
                # Round again after adjustment
                order_size = self._round_to_precision(symbol, order_size)
                actual_notional = order_size * price
                
                if actual_notional >= min_notional_usd:
                    logger.info(f"Adjusted order size to meet minimum: {order_size:.8f} = ${actual_notional:.2f} notional")
                else:
                    logger.warning(f"Failed to reach minimum after step adjustment: ${actual_notional:.2f} < ${min_notional_usd:.2f}")
            else:
                # Fallback: calculate exact order size needed, then round up
                order_size = required_order_size
                # Round UP to ensure we meet minimum (add one step_size if available, else round to precision)
                if step_size and step_size > 0:
                    # Round up to next step
                    order_size = ((int(order_size / step_size) + 1) * step_size)
                order_size = self._round_to_precision(symbol, order_size)
                # If rounding zeroed again, force min_order_qty
                if order_size <= 0 and min_order_qty > 0:
                    order_size = max(min_order_qty, step_size or 0)
                actual_notional = order_size * price
                logger.info(f"Adjusted order size via calculation: {order_size:.8f} = ${actual_notional:.2f} notional")
            
            # Final check: if still below minimum, we have a problem
            if actual_notional < min_notional_usd:
                logger.error(
                    f"CRITICAL: Order notional ${actual_notional:.2f} still below minimum ${min_notional_usd:.2f} "
                    f"after all adjustments. Order will likely be rejected by exchange."
                )

        # Get base currency symbol for display
        base_symbol = symbol.split('/')[0] if '/' in symbol else 'COIN'

        # Use actual notional value for display (after rounding)
        display_notional = order_size * price

        logger.info(
            f"  |-- Order Size: {order_size:.8f} {base_symbol} (${display_notional:.2f})"
        )
        logger.info(
            f"  |-- Capital: ${capital_amount:.2f} ({size_pct*100:.1f}%) | Leverage: {int(leverage)}x"
        )
        logger.info(
            f"  \\-- Price: ${price:.2f} | Equity: ${equity:.2f}"
        )
        # Final leverage rounding: ensure it's whole number between 1 and 2 (Binance doesn't support decimals)
        leverage = int(round(min(max(leverage, 1.0), 2.0)))
        return order_size, leverage, capital_amount  # Return order size, leverage, and actual capital allocated

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
