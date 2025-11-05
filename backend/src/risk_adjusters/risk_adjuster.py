"""Risk adjustment logic for trading."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class RiskAdjuster:
    """Handles risk adjustments like leverage and position sizing."""

    def __init__(self):
        """Initialize risk adjuster."""
        pass

    def get_smart_leverage(self, equity: float) -> float:
        """
        Calculate smart leverage based on account equity.
        Returns whole numbers only (1x or 2x) - Binance doesn't support decimals.

        Args:
            equity: Account equity

        Returns:
            Recommended leverage multiplier (whole number: 1 or 2)
        """
        # Conservative leverage based on account size - MAX 2x (not greedy)
        if equity >= 100:
            return 2.0  # Max 2x for accounts $100+
        else:
            return 1.0  # Max 1x for accounts <$100

    def adjust_leverage_by_confidence(self, base_leverage: float, confidence: float) -> float:
        """
        Adjust leverage based on signal confidence.
        Returns whole numbers only (1x or 2x) - Binance doesn't support decimals.

        Args:
            base_leverage: Base leverage from account size
            confidence: Signal confidence (0.0-1.0)

        Returns:
            Adjusted leverage (whole number: 1 or 2)
        """
        original_leverage = base_leverage

        if confidence >= 0.9:
            adjusted_leverage = base_leverage  # Full leverage for very high confidence
            logger.debug(f"Leverage: Confidence {confidence:.2f} >= 0.9 -> Full leverage: {adjusted_leverage:.1f}x")
        elif confidence >= 0.8:
            adjusted_leverage = base_leverage  # High confidence: use full leverage (2x)
            logger.debug(f"Leverage: Confidence {confidence:.2f} >= 0.8 -> Full leverage: {adjusted_leverage:.1f}x")
        elif confidence >= 0.7:
            adjusted_leverage = base_leverage  # Medium-high confidence: use full leverage (2x)
            logger.debug(f"Leverage: Confidence {confidence:.2f} >= 0.7 -> Full leverage: {adjusted_leverage:.1f}x")
        elif confidence >= 0.6:
            adjusted_leverage = 1.0  # Medium confidence: use 1x (conservative)
            logger.debug(f"Leverage: Confidence {confidence:.2f} >= 0.6 -> 1x leverage (conservative)")
        else:
            adjusted_leverage = 1.0  # Low confidence: use 1x (conservative)
            logger.debug(f"Leverage: Confidence {confidence:.2f} < 0.6 -> 1x leverage (conservative)")

        # Round to whole number (Binance doesn't support decimals)
        adjusted_leverage = int(round(adjusted_leverage))
        if adjusted_leverage > 2:
            adjusted_leverage = 2
        elif adjusted_leverage < 1:
            adjusted_leverage = 1

        if adjusted_leverage != int(round(original_leverage)):
            logger.info(f"Leverage adjusted: Base {int(round(original_leverage))}x -> Final {adjusted_leverage}x (confidence: {confidence:.2f})")

        return float(adjusted_leverage)

    def validate_position_size(self, signal, equity: float, available_cash: float) -> bool:
        """
        Validate that position size is reasonable.

        Args:
            signal: Strategy signal
            equity: Account equity
            available_cash: Available cash

        Returns:
            True if position size is valid, False otherwise
        """
        required_cash = equity * signal.size_pct

        if available_cash < required_cash:
            logger.warning(f"Insufficient cash for position: need ${required_cash:,.2f}, have ${available_cash:,.2f}")
            return False

        # Check minimum position size (Binance Futures minimum notional is $20 USD)
        min_notional = 20.0
        position_notional = equity * signal.size_pct * getattr(signal, 'leverage', 1.0)
        if position_notional < min_notional:
            logger.warning(f"Position notional too small: ${position_notional:.2f} < ${min_notional:.2f}")
            return False

        return True
