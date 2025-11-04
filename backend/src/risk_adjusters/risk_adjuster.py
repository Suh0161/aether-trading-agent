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

        Args:
            equity: Account equity

        Returns:
            Recommended leverage multiplier
        """
        # Conservative leverage based on account size
        if equity >= 10000:  # $10k+
            return 3.0  # Higher leverage for larger accounts
        elif equity >= 5000:  # $5k-$10k
            return 2.5
        elif equity >= 1000:  # $1k-$5k
            return 2.0
        elif equity >= 500:   # $500-$1k
            return 1.5
        else:                 # <$500
            return 1.0  # No leverage for small accounts

    def adjust_leverage_by_confidence(self, base_leverage: float, confidence: float) -> float:
        """
        Adjust leverage based on signal confidence.

        Args:
            base_leverage: Base leverage from account size
            confidence: Signal confidence (0.0-1.0)

        Returns:
            Adjusted leverage
        """
        original_leverage = base_leverage

        if confidence >= 0.9:
            adjusted_leverage = base_leverage  # Full leverage for very high confidence
            logger.debug(f"Leverage: Confidence {confidence:.2f} >= 0.9 -> Full leverage: {adjusted_leverage:.1f}x")
        elif confidence >= 0.8:
            adjusted_leverage = base_leverage * 0.9  # 90% for high confidence
            logger.debug(f"Leverage: Confidence {confidence:.2f} >= 0.8 -> 90% leverage: {adjusted_leverage:.1f}x (from {base_leverage:.1f}x)")
        elif confidence >= 0.7:
            adjusted_leverage = base_leverage * 0.8  # 80% for medium-high confidence
            logger.debug(f"Leverage: Confidence {confidence:.2f} >= 0.7 -> 80% leverage: {adjusted_leverage:.1f}x (from {base_leverage:.1f}x)")
        elif confidence >= 0.6:
            adjusted_leverage = base_leverage * 0.7  # 70% for medium confidence
            logger.debug(f"Leverage: Confidence {confidence:.2f} >= 0.6 -> 70% leverage: {adjusted_leverage:.1f}x (from {base_leverage:.1f}x)")
        else:
            adjusted_leverage = base_leverage * 0.5  # 50% for low confidence
            logger.debug(f"Leverage: Confidence {confidence:.2f} < 0.6 -> 50% leverage: {adjusted_leverage:.1f}x (from {base_leverage:.1f}x)")

        if adjusted_leverage != original_leverage:
            logger.info(f"Leverage adjusted: Base {original_leverage:.1f}x -> Final {adjusted_leverage:.1f}x (confidence: {confidence:.2f})")

        return adjusted_leverage

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
