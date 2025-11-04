"""Confidence calculation utilities for trading strategies."""

import logging

logger = logging.getLogger(__name__)


def calculate_swing_confidence(
    volume_ratio: float,
    obv_trend: str,
    trend_alignment: str = "neutral",
    resistance_bonus: bool = False
) -> float:
    """
    Calculate confidence for swing trades based on volume and trend factors.

    Args:
        volume_ratio: Volume ratio (current/average)
        obv_trend: OBV trend ("bullish", "bearish", "neutral")
        trend_alignment: "strong", "partial", "weak", "neutral"
        resistance_bonus: Whether this is at resistance (for short trades)

    Returns:
        Confidence score (0.0-1.0)
    """
    # Base confidence for swing trades
    base_confidence = 0.8

    # Progressive volume confidence boost/penalty
    if volume_ratio >= 1.5:
        volume_confidence_boost = 0.15  # Strong volume (50%+ above average)
    elif volume_ratio >= 1.2:
        volume_confidence_boost = 0.10  # Good volume (20%+ above average)
    elif volume_ratio >= 1.0:
        volume_confidence_boost = 0.05  # Acceptable volume (at least average)
    elif volume_ratio >= 0.8:
        volume_confidence_boost = 0.00  # Below average but acceptable
    else:
        volume_confidence_boost = -0.10  # Very low volume (penalty but still allow)

    # OBV bonus (money flow confirmation)
    obv_bullish = obv_trend == "bullish"
    obv_bonus = 0.05 if obv_bullish else 0.0

    # Trend alignment bonus
    if trend_alignment == "strong":
        alignment_bonus = 0.05
    elif trend_alignment == "partial":
        alignment_bonus = 0.03
    else:
        alignment_bonus = 0.0

    # Resistance bonus for counter-trend shorts
    resistance_bonus_value = 0.05 if resistance_bonus else 0.0

    # Perfect setup bonus (breakout with multi-TF alignment)
    perfect_setup_bonus = alignment_bonus + resistance_bonus_value

    # Final confidence (clamped to 0.3-0.95)
    confidence = max(0.3, min(0.95, base_confidence + volume_confidence_boost + obv_bonus + perfect_setup_bonus))

    logger.debug(f"Swing confidence calc: base={base_confidence:.2f}, vol_boost={volume_confidence_boost:+.2f}, obv={obv_bonus:+.2f}, align={alignment_bonus:+.2f}, resist={resistance_bonus_value:+.2f} = {confidence:.2f}")

    return confidence


def calculate_scalp_confidence(
    volume_ratio_5m: float,
    volume_ratio_1m: float,
    obv_trend: str,
    vwap_alignment: bool = False,
    support_resistance_bonus: bool = False
) -> float:
    """
    Calculate confidence for scalp trades based on volume and micro-trend factors.

    Args:
        volume_ratio_5m: 5m volume ratio
        volume_ratio_1m: 1m volume ratio
        obv_trend: OBV trend ("bullish", "bearish", "neutral")
        vwap_alignment: Whether price is properly aligned with VWAP
        support_resistance_bonus: Whether this is at S/R level

    Returns:
        Confidence score (0.0-1.0)
    """
    # Base confidence for scalps (lower than swings)
    base_confidence = 0.7

    # Use the higher of 5m or 1m volume for confidence calculation
    active_volume_ratio = max(volume_ratio_5m, volume_ratio_1m)

    # Progressive volume confidence boost/penalty for scalps
    if active_volume_ratio >= 1.5:
        volume_confidence_boost = 0.10  # Strong volume
    elif active_volume_ratio >= 1.3:
        volume_confidence_boost = 0.08  # Good volume (30%+ above average)
    elif active_volume_ratio >= 1.1:
        volume_confidence_boost = 0.05  # Acceptable volume (10%+ above average)
    elif active_volume_ratio >= 1.0:
        volume_confidence_boost = 0.02  # At least average
    elif active_volume_ratio >= 0.9:
        volume_confidence_boost = 0.00  # Below average but acceptable
    else:
        volume_confidence_boost = -0.08  # Very low volume (penalty but still allow)

    # OBV bonus for scalps
    obv_bonus = 0.03 if obv_trend == "bullish" else 0.0

    # Perfect setup bonus (breakout with VWAP alignment)
    vwap_bonus = 0.03 if vwap_alignment else 0.0
    sr_bonus = 0.03 if support_resistance_bonus else 0.0
    perfect_setup_bonus = vwap_bonus + sr_bonus

    # Final confidence for scalps (clamped to 0.4-0.85)
    confidence = max(0.4, min(0.85, base_confidence + volume_confidence_boost + obv_bonus + perfect_setup_bonus))

    logger.debug(f"Scalp confidence calc: base={base_confidence:.2f}, vol_boost={volume_confidence_boost:+.2f}, obv={obv_bonus:+.2f}, vwap={vwap_bonus:+.2f}, sr={sr_bonus:+.2f} = {confidence:.2f}")

    return confidence


def get_volume_description(volume_ratio: float) -> str:
    """
    Get human-readable volume description.

    Args:
        volume_ratio: Volume ratio (current/average)

    Returns:
        Volume description string
    """
    if volume_ratio >= 1.5:
        return f"Vol: {volume_ratio:.2f}x [STRONG]"
    elif volume_ratio >= 1.3:
        return f"Vol: {volume_ratio:.2f}x [GOOD]"
    elif volume_ratio >= 1.1:
        return f"Vol: {volume_ratio:.2f}x [OK]"
    elif volume_ratio >= 1.0:
        return f"Vol: {volume_ratio:.2f}x [AVG]"
    else:
        return f"Vol: {volume_ratio:.2f}x [LOW]"
