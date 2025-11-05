"""Objective entry quality scoring for precise entries."""

from __future__ import annotations
from typing import Literal
import logging

logger = logging.getLogger(__name__)


def _safe(v, default=0.0):
    return v if isinstance(v, (int, float)) else default


def compute_entry_qualifier(snapshot, position_type: Literal["scalp", "swing"], direction: Literal["long", "short"]) -> float:
    """Compute an objective entry quality score (0.0-1.0).

    Factors:
    - VWAP alignment (stronger for scalps)
    - 5m/15m micro momentum agreement
    - OBV money flow direction
    - Tier-2 microstructure: order book imbalance, spread, proximity to liquidity zone, sweeps
    - Mean reversion alignment for swing (distance to 1H EMA50)
    - Minimal volatility for scalps (5m ATR/price)
    """
    indicators = getattr(snapshot, "indicators", {}) or {}
    tier2 = getattr(snapshot, "tier2", None)

    price = _safe(getattr(snapshot, "price", 0.0))
    vwap_5m = _safe(indicators.get("vwap_5m", price))
    # Timeframe trends (read-only; missing values default to 'neutral')
    trend_1d = indicators.get("trend_1d", "neutral")
    trend_4h = indicators.get("trend_4h", "neutral")
    trend_1h = indicators.get("trend_1h", indicators.get("trend_1h", "neutral"))
    trend_15m = indicators.get("trend_15m", "neutral")
    trend_5m = indicators.get("trend_5m", "neutral")
    trend_1m = indicators.get("trend_1m", "neutral")
    obv_trend = indicators.get("obv_trend_1h", "neutral")
    atr_5m = _safe(indicators.get("atr_14_5m", indicators.get("atr_14", 0.0)))
    ema50_1h = _safe(indicators.get("ema_50", 0.0))

    # 1) VWAP alignment (priority for scalps)
    vwap_ok = (price >= vwap_5m) if direction == "long" else (price <= vwap_5m)
    vwap_score = 0.25 if (vwap_ok and position_type == "scalp") else (0.15 if vwap_ok else 0.0)

    # 2) Momentum by required timeframes (prevents hallucination by enforcing TF discipline)
    mtf_score = 0.0
    if position_type == "scalp":
        # Required stack: 15m -> 5m -> 1m
        if (direction == "long" and trend_15m == "bullish") or (direction == "short" and trend_15m == "bearish"):
            mtf_score += 0.10
        if (direction == "long" and trend_5m == "bullish") or (direction == "short" and trend_5m == "bearish"):
            mtf_score += 0.10
        if (direction == "long" and trend_1m == "bullish") or (direction == "short" and trend_1m == "bearish"):
            mtf_score += 0.10
    else:
        # SWING required stack: 1D -> 4H -> 1H -> 15M
        if (direction == "long" and trend_1d == "bullish") or (direction == "short" and trend_1d == "bearish"):
            mtf_score += 0.10
        if (direction == "long" and trend_4h == "bullish") or (direction == "short" and trend_4h == "bearish"):
            mtf_score += 0.08
        if (direction == "long" and trend_1h == "bullish") or (direction == "short" and trend_1h == "bearish"):
            mtf_score += 0.06
        if (direction == "long" and trend_15m == "bullish") or (direction == "short" and trend_15m == "bearish"):
            mtf_score += 0.04

    # 3) OBV money flow supportive
    obv_ok = (obv_trend == ("up" if direction == "long" else "down"))
    obv_score = 0.10 if obv_ok else 0.0

    # 4) Tier-2 microstructure
    t2_score = 0.0
    if tier2:
        imbalance = _safe(getattr(tier2, "order_book_imbalance", 0.0))
        spread_bp = _safe(getattr(tier2, "spread_bp", 10.0))
        zone_dist = _safe(getattr(tier2, "distance_to_liquidity_zone_pct", 5.0))
        sweep_dir = getattr(tier2, "sweep_direction", None)

        # Imbalance supportive
        if direction == "long" and imbalance > 0.15:
            t2_score += 0.15
        if direction == "short" and imbalance < -0.15:
            t2_score += 0.15

        # Tight spreads help fills
        if spread_bp <= 5.0:
            t2_score += 0.05

        # Reasonable proximity to liquidity zone improves timing
        if 0.3 <= zone_dist <= 2.0:
            t2_score += 0.05

        # Sweep in trade direction is strong
        if sweep_dir and ((sweep_dir == "bullish" and direction == "long") or (sweep_dir == "bearish" and direction == "short")):
            t2_score += 0.10

    # 5) Mean distance for swing (prefer near 1H mean)
    ema_align = 0.0
    if position_type == "swing" and ema50_1h > 0 and price > 0:
        dist = abs(price - ema50_1h) / price
        if dist <= 0.02:  # within 2%
            ema_align = 0.05

    # 6) Minimal volatility for scalp
    vol_score = 0.0
    if position_type == "scalp" and price > 0:
        atr_pct = atr_5m / price
        if atr_pct >= 0.0003:  # 0.03%
            vol_score = 0.05

    score = vwap_score + mtf_score + obv_score + t2_score + ema_align + vol_score
    final_score = max(0.0, min(1.0, score))
    
    # Debug logging for low scores
    if final_score < 0.50:
        logger.debug(
            f"EntryQualifier breakdown for {position_type.upper()} {direction.upper()}: "
            f"VWAP={vwap_score:.2f}, MTF={mtf_score:.2f}, OBV={obv_score:.2f}, "
            f"Tier2={t2_score:.2f}, EMA={ema_align:.2f}, Vol={vol_score:.2f} → Total={final_score:.2f}"
        )
    
    return final_score


