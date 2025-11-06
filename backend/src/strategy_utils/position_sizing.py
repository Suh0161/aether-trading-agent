"""Position sizing calculations for trading strategies."""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


def get_max_equity_usage():
    """
    Get MAX_EQUITY_USAGE_PCT from environment, default to 0.30 (30%).

    This allows easy configuration via .env file without code changes.
    """
    import os
    return float(os.getenv("MAX_EQUITY_USAGE_PCT", "0.30"))


def calculate_position_size(
    equity: float,
    available_cash: float,
    confidence: float,
    price: float,
    stop_distance: float,
    position_type: str = "swing",
    leverage: float = 1.0
) -> Tuple[float, float, float, float, float]:
    """
    Calculate position size using two-layer system.

    Args:
        equity: Account equity
        available_cash: Available cash
        confidence: Confidence level (0.0-1.0)
        price: Current price
        stop_distance: Stop loss distance in price terms
        position_type: "swing" or "scalp"
        leverage: Leverage multiplier

    Returns:
        Tuple of (position_size_pct, capital_amount, position_notional, risk_amount, reward_amount)
    """
    # LAYER 1: Capital Allocation (how much $ to use from account)
    max_equity_pct = get_max_equity_usage()

    if position_type == "scalp":
        # Scalps use smaller percentages than swings
        if confidence >= 0.8:
            capital_allocation_pct = max_equity_pct * 0.50  # 15% of 30% max
        elif confidence >= 0.6:
            capital_allocation_pct = max_equity_pct * 0.333  # 10% of 30% max
        else:
            capital_allocation_pct = max_equity_pct * 0.167  # 5% of 30% max
    else:
        # Swing trades
        if confidence >= 0.8:
            capital_allocation_pct = max_equity_pct * 0.833  # 25% of 30% max
        elif confidence >= 0.6:
            capital_allocation_pct = max_equity_pct * 0.40  # 12% of 30% max
        else:
            capital_allocation_pct = max_equity_pct * 0.20  # 6% of 30% max

    # Calculate risk and reward amounts
    capital_amount = equity * capital_allocation_pct
    position_notional = capital_amount * leverage
    position_quantity = position_notional / price

    # Risk: if SL hits, how much $ do we lose?
    risk_amount = stop_distance * position_quantity

    # Reward: if TP hits, how much $ do we gain?
    # This is a placeholder - actual reward calculation depends on take profit distance
    reward_amount = risk_amount * 2  # Default 2R

    # Ensure minimum position size (Binance Futures minimum notional is $20 USD)
    min_notional = 20.0
    if position_notional < min_notional:
        required_capital = min_notional / leverage
        capital_allocation_pct = required_capital / equity
        logger.info(f"Adjusted position size to meet minimum notional: {capital_allocation_pct*100:.2f}% capital")

    # Cap maximum position size
    capital_allocation_pct = min(capital_allocation_pct, max_equity_pct)

    # Check if we have enough available cash
    required_cash = equity * capital_allocation_pct
    if available_cash < required_cash:
        logger.warning(f"Insufficient cash: need ${required_cash:,.2f}, have ${available_cash:,.2f}")
        return 0.0, 0.0, 0.0, 0.0, 0.0

    return capital_allocation_pct, capital_amount, position_notional, risk_amount, reward_amount


def calculate_leverage(confidence: float, position_type: str = "swing", base_leverage: float = None) -> float:
    """
    Calculate leverage based on confidence and position type.
    Now standardized to match RiskAdjuster logic for consistency.

    Args:
        confidence: Confidence level (0.0-1.0)
        position_type: "swing" or "scalp" (currently no difference in logic)
        base_leverage: Optional base leverage from account size (if None, assumes max base)

    Returns:
        Leverage multiplier
    """
    # Use base leverage if provided, otherwise assume we can use max (will be capped by RiskAdjuster)
    if base_leverage is None:
        # For compatibility, assume a reasonable base leverage if not provided
        base_leverage = 3.0  # Assume large account by default

    # Apply confidence adjustment using the same logic as RiskAdjuster
    if confidence >= 0.9:
        return base_leverage  # Full leverage for very high confidence
    elif confidence >= 0.8:
        return base_leverage * 0.9  # 90% for high confidence
    elif confidence >= 0.7:
        return base_leverage * 0.8  # 80% for medium-high confidence
    elif confidence >= 0.6:
        return base_leverage * 0.7  # 70% for medium confidence
    else:
        return base_leverage * 0.5  # 50% for low confidence

    # Note: position_type parameter kept for backward compatibility but no longer affects leverage


def calculate_dynamic_sl_tp(price: float, atr_value: float, action: str) -> Tuple[float, float]:
    """
    Calculate dynamic stop loss and take profit based on ATR.
    
    For SWING trades:
    - Stop loss: 2x ATR (allows for normal volatility)
    - Take profit: 4x ATR (2:1 risk/reward ratio)
    - Minimum SL distance: 1% of price (prevents SL too close to entry)
    - Minimum TP distance: 2% of price (ensures meaningful profit target)

    Args:
        price: Current price
        atr_value: ATR value
        action: "long" or "short"

    Returns:
        Tuple of (stop_loss_price, take_profit_price)
    """
    # ATR-based stop loss (2x ATR for swing trades)
    sl_distance_atr = atr_value * 2.0
    
    # Minimum SL distance: 1% of price (prevents SL=entry bugs)
    sl_distance_min = price * 0.01
    sl_distance = max(sl_distance_atr, sl_distance_min)

    # Take profit at 2R (4x ATR distance for 2:1 risk/reward)
    tp_distance_atr = atr_value * 4.0
    
    # Minimum TP distance: 2% of price (ensures meaningful profit target)
    tp_distance_min = price * 0.02
    tp_distance = max(tp_distance_atr, tp_distance_min)
    
    # Ensure TP is at least 2x the SL distance (maintain 2:1 R:R minimum)
    if tp_distance < sl_distance * 2.0:
        tp_distance = sl_distance * 2.0

    if action == "long":
        stop_loss = price - sl_distance
        take_profit = price + tp_distance
        
        # Safety check: ensure SL < entry < TP
        if stop_loss >= price:
            stop_loss = price * 0.99  # Fallback: 1% below entry
        if take_profit <= price:
            take_profit = price * 1.02  # Fallback: 2% above entry
    else:  # short
        stop_loss = price + sl_distance
        take_profit = price - tp_distance
        
        # Safety check: ensure TP < entry < SL
        if stop_loss <= price:
            stop_loss = price * 1.01  # Fallback: 1% above entry
        if take_profit >= price:
            take_profit = price * 0.98  # Fallback: 2% below entry

    return stop_loss, take_profit


def calculate_dynamic_scalp_sl_tp(price: float, atr_value: float, action: str) -> Tuple[float, float]:
    """
    Calculate dynamic stop loss and take profit for scalps based on ATR.

    Args:
        price: Current price
        atr_value: ATR value (5m timeframe)
        action: "long" or "short"

    Returns:
        Tuple of (stop_loss_price, take_profit_price)
    """
    # ATR-based percentages for scalps
    atr_pct = atr_value / price if price > 0 else 0.003

    # Dynamic SL/TP based on ATR, with min AND sane max caps to avoid nonsense values
    # Min caps account for fees; max caps prevent extreme values from broken ATR inputs
    dynamic_sl_pct = max(0.003, atr_pct * 0.5)
    dynamic_tp_pct = max(0.005, atr_pct * 0.8)
    # Cap to 2% SL and 4% TP for scalps
    dynamic_sl_pct = min(dynamic_sl_pct, 0.02)
    dynamic_tp_pct = min(dynamic_tp_pct, 0.04)

    if action == "long":
        stop_loss = price - (price * dynamic_sl_pct)
        take_profit = price + (price * dynamic_tp_pct)
    else:  # short
        stop_loss = price + (price * dynamic_sl_pct)
        take_profit = price - (price * dynamic_tp_pct)

    return stop_loss, take_profit
