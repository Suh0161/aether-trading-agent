"""Order validation logic."""

import logging

logger = logging.getLogger(__name__)


class OrderValidator:
    """Handles validation of trading orders."""

    def __init__(self):
        """Initialize order validator."""
        pass

    def validate_order_size(self, order_size: float, min_notional: float = 20.0) -> bool:
        """
        Validate that order size meets minimum requirements.

        Args:
            order_size: Order size to validate
            min_notional: Minimum notional value required

        Returns:
            True if order size is valid, False otherwise
        """
        if order_size <= 0:
            logger.error(f"Invalid order size: {order_size} (must be positive)")
            return False

        # Additional validation can be added here
        return True

    def validate_price(self, price: float) -> bool:
        """
        Validate that price is reasonable.

        Args:
            price: Price to validate

        Returns:
            True if price is valid, False otherwise
        """
        if price <= 0:
            logger.error(f"Invalid price: {price} (must be positive)")
            return False

        # Check for extreme prices (potential data issues)
        if price > 1000000:  # Arbitrary high limit
            logger.warning(f"Very high price detected: ${price:,.2f} - proceeding with caution")
        elif price < 0.000001:  # Arbitrary low limit
            logger.warning(f"Very low price detected: ${price:,.8f} - proceeding with caution")

        return True

    def validate_equity(self, equity: float, required_capital: float) -> bool:
        """
        Validate that account has sufficient equity.

        Args:
            equity: Current account equity
            required_capital: Required capital for the trade

        Returns:
            True if equity is sufficient, False otherwise
        """
        if equity <= 0:
            logger.error(f"Invalid equity: ${equity:.2f} (must be positive)")
            return False

        if required_capital > equity:
            logger.error(f"Insufficient equity: need ${required_capital:.2f}, have ${equity:.2f}")
            return False

        return True

    def validate_leverage(self, leverage: float, max_leverage: float = 10.0) -> bool:
        """
        Validate leverage is within acceptable bounds.

        Args:
            leverage: Leverage multiplier
            max_leverage: Maximum allowed leverage

        Returns:
            True if leverage is valid, False otherwise
        """
        if leverage < 1.0:
            logger.error(f"Invalid leverage: {leverage:.2f} (must be >= 1.0)")
            return False

        if leverage > max_leverage:
            logger.warning(f"High leverage detected: {leverage:.1f}x (max recommended: {max_leverage:.1f}x)")
            # Allow but warn about high leverage

        return True
