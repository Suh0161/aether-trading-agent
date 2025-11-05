"""Technical indicator calculations and utilities."""

import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)


def analyze_trend_alignment(indicators: Dict[str, Any], action: str, price: float = 0.0) -> Tuple[str, str]:
    """
    Analyze multi-timeframe trend alignment for entry decisions.

    Args:
        indicators: Indicator dictionary
        action: "long" or "short"

    Returns:
        Tuple of (trend_alignment, timeframe_info)
    """
    # Extract multi-timeframe indicators
    trend_1d = indicators.get("trend_1d", "neutral")
    trend_4h = indicators.get("trend_4h", "neutral")
    trend_1h = indicators.get("trend_1h", "neutral")
    trend_15m = indicators.get("trend_15m", "neutral")

    # Higher timeframes for trend confirmation
    ema_50_4h = indicators.get("ema_50_4h", 0)
    ema_50_1d = indicators.get("ema_50_1d", 0)

    if action == "long":
        # LONG alignment analysis
        higher_tf_bullish = trend_1d == "bullish" and trend_4h == "bullish"
        higher_tf_bullish_partial = trend_4h == "bullish"
        ema_50 = indicators.get("ema_50", 0)
        primary_bullish = price > ema_50 and ema_50 > 0  # Price > EMA50

        if higher_tf_bullish and primary_bullish:
            alignment = "strong"
        elif higher_tf_bullish_partial and primary_bullish:
            alignment = "partial"
        elif primary_bullish:
            alignment = "weak"
        else:
            alignment = "neutral"
    else:  # short
        # SHORT alignment analysis
        higher_tf_bearish = trend_1d == "bearish" and trend_4h == "bearish"
        higher_tf_bearish_partial = trend_4h == "bearish"
        ema_50 = indicators.get("ema_50", 0)
        primary_bearish = price < ema_50 and ema_50 > 0  # Price < EMA50

        if higher_tf_bearish and primary_bearish:
            alignment = "strong"
        elif higher_tf_bearish_partial and primary_bearish:
            alignment = "partial"
        elif primary_bearish:
            alignment = "weak"
        else:
            alignment = "neutral"

    # Create timeframe info string
    timeframe_info = f"Trend: 1D={trend_1d}, 4H={trend_4h}, 1H={trend_1h}, 15M={trend_15m}"

    return alignment, timeframe_info


def check_support_resistance_levels(indicators: Dict[str, Any], price: float) -> Tuple[bool, bool, str]:
    """
    Check if price is at support or resistance levels.

    Args:
        indicators: Indicator dictionary
        price: Current price

    Returns:
        Tuple of (near_support, near_resistance, level_description)
    """
    # Get S/R levels
    s1 = indicators.get("support_1", 0)
    s2 = indicators.get("support_2", 0)
    swing_low = indicators.get("swing_low", 0)
    r1 = indicators.get("resistance_1", 0)
    r2 = indicators.get("resistance_2", 0)
    swing_high = indicators.get("swing_high", 0)

    # Check if price is near support/resistance (within 0.5%)
    near_support = (s1 > 0 and abs(price - s1) / s1 < 0.005) or \
                  (s2 > 0 and abs(price - s2) / s2 < 0.005) or \
                  (swing_low > 0 and abs(price - swing_low) / swing_low < 0.005)

    near_resistance = (r1 > 0 and abs(price - r1) / r1 < 0.005) or \
                     (r2 > 0 and abs(price - r2) / r2 < 0.005) or \
                     (swing_high > 0 and abs(price - swing_high) / swing_high < 0.005)

    # Create level description
    if near_support:
        support_level = min([s for s in [s1, s2, swing_low] if s > 0], default=price)
        level_desc = f"support ${support_level:.2f}"
    elif near_resistance:
        resistance_level = max([r for r in [r1, r2, swing_high] if r > 0], default=price)
        level_desc = f"resistance ${resistance_level:.2f}"
    else:
        level_desc = "neutral"

    return near_support, near_resistance, level_desc


def validate_keltner_bands(indicators: Dict[str, Any], price: float, timeframe: str = "1h") -> Tuple[float, float]:
    """
    Validate and return Keltner band values, with fallbacks.

    Args:
        indicators: Indicator dictionary
        price: Current price
        timeframe: Timeframe for bands ("1h", "5m", "15m")

    Returns:
        Tuple of (keltner_upper, keltner_lower)
    """
    if timeframe == "1h":
        keltner_upper = indicators.get("keltner_upper", 0)
        keltner_lower = indicators.get("keltner_lower", 0)
    elif timeframe == "5m":
        keltner_upper = indicators.get("keltner_upper_5m", 0)
        keltner_lower = indicators.get("keltner_lower_5m", 0)
    elif timeframe == "15m":
        keltner_upper = indicators.get("keltner_upper_15m", 0)
        keltner_lower = indicators.get("keltner_lower_15m", 0)
    else:
        keltner_upper = indicators.get("keltner_upper", 0)
        keltner_lower = indicators.get("keltner_lower", 0)

    # Validate Keltner Channel values are reasonable
    if keltner_upper > 0 and price > 0:
        price_deviation = abs(keltner_upper - price) / price
        if price_deviation > 0.15:  # More than 15% away seems unreasonable
            logger.warning(
                f"Keltner upper band seems too far: price=${price:.2f}, "
                f"upper=${keltner_upper:.2f}, deviation={price_deviation*100:.1f}%"
            )
            # Fallback: use a dynamic calculation based on price and EMA
            ema_20 = indicators.get("ema_20", price)
            # Calculate reasonable upper band: EMA20 + 3% of price
            keltner_upper = ema_20 + (price * 0.03)
            keltner_lower = ema_20 - (price * 0.03)
            logger.info(f"Using fallback Keltner bands: upper=${keltner_upper:.2f}, lower=${keltner_lower:.2f}")

    return keltner_upper, keltner_lower


def analyze_volume_confirmation(indicators: Dict[str, Any], action: str) -> Tuple[float, str, str]:
    """
    Analyze volume for trade confirmation.

    Args:
        indicators: Indicator dictionary
        action: "long" or "short"

    Returns:
        Tuple of (volume_ratio, volume_description, obv_trend)
    """
    # Extract volume indicators
    volume_ratio_1h = indicators.get("volume_ratio_1h", 1.0)
    volume_trend_1h = indicators.get("volume_trend_1h", "stable")
    obv_trend_1h = indicators.get("obv_trend_1h", "neutral")

    # Use 1h volume as primary for confirmation
    volume_ratio = volume_ratio_1h

    # Create volume description
    if volume_ratio >= 1.5:
        volume_desc = f"Vol: {volume_ratio:.2f}x [STRONG]"
    elif volume_ratio >= 1.2:
        volume_desc = f"Vol: {volume_ratio:.2f}x [GOOD]"
    elif volume_ratio >= 1.0:
        volume_desc = f"Vol: {volume_ratio:.2f}x [OK]"
    else:
        volume_desc = f"Vol: {volume_ratio:.2f}x [LOW]"

    return volume_ratio, volume_desc, obv_trend_1h


def check_breakout_conditions(
    indicators: Dict[str, Any],
    price: float,
    action: str,
    timeframe: str = "1h"
) -> Tuple[bool, float, str]:
    """
    Check for breakout conditions on specified timeframe.

    Args:
        indicators: Indicator dictionary
        price: Current price
        action: "long" or "short"
        timeframe: Timeframe to check ("1h", "5m", "15m")

    Returns:
        Tuple of (has_breakout, entry_level, timeframe_desc)
    """
    keltner_upper, keltner_lower = validate_keltner_bands(indicators, price, timeframe)

    if action == "long":
        has_breakout = keltner_upper > 0 and price > keltner_upper
        entry_level = keltner_upper
        direction = ">"
    else:  # short
        has_breakout = keltner_lower > 0 and price < keltner_lower
        entry_level = keltner_lower
        direction = "<"

    timeframe_desc = f"{timeframe} {direction} Keltner ${entry_level:.2f}"

    return has_breakout, entry_level, timeframe_desc


def check_near_band_conditions(
    indicators: Dict[str, Any],
    price: float,
    action: str,
    timeframe: str = "1h"
) -> Tuple[bool, float, str]:
    """
    Check if price is near band edge (for momentum entries).

    Args:
        indicators: Indicator dictionary
        price: Current price
        action: "long" or "short"
        timeframe: Timeframe to check

    Returns:
        Tuple of (near_band, band_level, description)
    """
    keltner_upper, keltner_lower = validate_keltner_bands(indicators, price, timeframe)

    if action == "long":
        # Near upper band = within 0.5% of upper band
        near_band = keltner_upper > 0 and price > (keltner_upper * 0.995)
        band_level = keltner_upper
        desc = f"near {timeframe} upper band"
    else:  # short
        # Near lower band = within 0.5% of lower band
        near_band = keltner_lower > 0 and price < (keltner_lower * 1.005)
        band_level = keltner_lower
        desc = f"near {timeframe} lower band"

    return near_band, band_level, desc


def get_scalp_trend_bias(indicators: Dict[str, Any], action: str) -> Tuple[bool, str]:
    """
    Get 15m trend bias for scalping decisions.

    Args:
        indicators: Indicator dictionary
        action: "long" or "short"

    Returns:
        Tuple of (bias_aligned, bias_description)
    """
    trend_15m = indicators.get("trend_15m", "neutral")
    ema_50_15m = indicators.get("ema_50_15m", 0)
    price = indicators.get("price", 0)  # This should be passed separately, but using as fallback

    if action == "long":
        bias_aligned = trend_15m == "bullish" or (ema_50_15m > 0 and price > ema_50_15m)
        bias_desc = "bullish" if bias_aligned else "not bullish"
    else:  # short
        bias_aligned = trend_15m == "bearish" or (ema_50_15m > 0 and price < ema_50_15m)
        bias_desc = "bearish" if bias_aligned else "not bearish"

    return bias_aligned, f"15m bias: {bias_desc}"


def check_volatility_filter(indicators: Dict[str, Any], price: float = 0.0) -> bool:
    """
    Check if volatility is sufficient for scalping.

    Args:
        indicators: Indicator dictionary
        price: Current price (if not provided in indicators)

    Returns:
        True if volatility is sufficient, False otherwise
    """
    # Check 5m ATR / price ratio - need minimum volatility to overcome fees
    # Use 5m timeframe ATR (atr_14_5m) for scalping, fallback to 1h ATR (atr_14) if not available
    atr_5m = indicators.get("atr_14_5m", indicators.get("atr_14", 0.0))
    current_price = indicators.get("price", price)

    if current_price == 0:
        return False

    # Dynamic volatility threshold by regime using daily ATR/price
    atr_1d = indicators.get("atr_14_1d", indicators.get("atr_14", 0.0))
    price_1d = indicators.get("close_1d", price) or price
    daily_vol = (atr_1d / price_1d) if price_1d else 0.0

    # Regime mapping (low/med/high) → threshold for 5m ATR/price
    # - Low vol (daily < 1%): 0.03%
    # - Medium vol (1-2%): 0.05%
    # - High vol (>= 2%): 0.10%
    if daily_vol >= 0.02:
        min_vol_threshold_pct = 0.0010
    elif daily_vol >= 0.01:
        min_vol_threshold_pct = 0.0005
    else:
        min_vol_threshold_pct = 0.0003
    atr_to_price_ratio = atr_5m / current_price

    sufficient_volatility = atr_to_price_ratio >= min_vol_threshold_pct

    if not sufficient_volatility:
        logger.debug(f"Scalp volatility filter failed: ATR/price={atr_to_price_ratio*100:.2f}% < {min_vol_threshold_pct*100:.2f}%")

    return sufficient_volatility
