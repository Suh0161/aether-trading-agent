"""Liquidity analyzer for detecting liquidity zones and sweeps."""

import logging
from typing import Dict, Optional, List
import pandas as pd

logger = logging.getLogger(__name__)


class LiquidityAnalyzer:
    """
    Analyzes liquidity zones, sweeps, and order blocks.
    
    Liquidity zones are areas where many stop-losses accumulate:
    - Above swing highs (sell-side liquidity for SHORT entries)
    - Below swing lows (buy-side liquidity for LONG entries)
    - Equal highs/lows (clustered orders)
    """
    
    def __init__(self):
        """Initialize liquidity analyzer."""
        pass
    
    def find_nearest_liquidity_zone(
        self,
        price: float,
        swing_high: float,
        swing_low: float,
        resistance_1: float,
        support_1: float
    ) -> Dict:
        """
        Find nearest significant liquidity zone.
        
        Prioritizes:
        1. Swing high/low (stronger levels)
        2. Resistance/Support levels (pivot-based)
        
        Args:
            price: Current price
            swing_high: Recent swing high
            swing_low: Recent swing low
            resistance_1: R1 resistance level
            support_1: S1 support level
            
        Returns:
            {
                "zone_price": float,
                "zone_type": "swing_high" | "swing_low" | "resistance" | "support",
                "distance_pct": float,  # % distance from current price
                "direction": "above" | "below"  # Zone is above or below price
            }
        """
        zones = []
        
        # Swing high (above price = sell-side liquidity)
        if swing_high > 0 and swing_high > price:
            distance_pct = ((swing_high - price) / price) * 100
            zones.append({
                "zone_price": swing_high,
                "zone_type": "swing_high",
                "distance_pct": distance_pct,
                "direction": "above"
            })
        
        # Swing low (below price = buy-side liquidity)
        if swing_low > 0 and swing_low < price:
            distance_pct = ((price - swing_low) / price) * 100
            zones.append({
                "zone_price": swing_low,
                "zone_type": "swing_low",
                "distance_pct": distance_pct,
                "direction": "below"
            })
        
        # Resistance 1 (above price)
        if resistance_1 > 0 and resistance_1 > price:
            distance_pct = ((resistance_1 - price) / price) * 100
            zones.append({
                "zone_price": resistance_1,
                "zone_type": "resistance",
                "distance_pct": distance_pct,
                "direction": "above"
            })
        
        # Support 1 (below price)
        if support_1 > 0 and support_1 < price:
            distance_pct = ((price - support_1) / price) * 100
            zones.append({
                "zone_price": support_1,
                "zone_type": "support",
                "distance_pct": distance_pct,
                "direction": "below"
            })
        
        if not zones:
            return {
                "zone_price": None,
                "zone_type": None,
                "distance_pct": None,
                "direction": None
            }
        
        # Return nearest zone (smallest distance)
        nearest = min(zones, key=lambda z: z["distance_pct"])
        return nearest
    
    def detect_liquidity_sweep(
        self,
        current_price: float,
        recent_candles: List[List[float]],  # Last 5-10 candles [[timestamp, open, high, low, close, volume], ...]
        liquidity_zone_price: float,
        zone_type: str,
        volume_ratio: float = 1.0
    ) -> Dict:
        """
        Detect if price swept a liquidity zone in recent candles.
        
        Sweep criteria:
        1. Price wick penetrates zone (high > zone for swing_high, low < zone for swing_low)
        2. Price closes back on the "safe side" (below zone for swing_high, above zone for swing_low)
        3. Next candle confirms (doesn't reclaim zone)
        4. Volume spike confirmation (optional but strengthens signal)
        
        Args:
            current_price: Current price
            recent_candles: List of recent candles (1m, 5m, or 15m)
            liquidity_zone_price: Price of liquidity zone
            zone_type: "swing_high" | "swing_low" | "resistance" | "support"
            volume_ratio: Current volume / average volume
            
        Returns:
            {
                "sweep_detected": bool,
                "confidence": float,  # 0.0-1.0
                "direction": "bullish" | "bearish",  # Direction of move AFTER sweep
                "sweep_time": int,  # Timestamp of sweep candle
                "wick_size_pct": float  # How much price wick penetrated zone
            }
        """
        if not liquidity_zone_price or not recent_candles or len(recent_candles) < 2:
            return {
                "sweep_detected": False,
                "confidence": 0.0,
                "direction": None,
                "sweep_time": None,
                "wick_size_pct": 0.0
            }
        
        # Check last 5 candles for sweep (most recent first)
        candles_to_check = min(5, len(recent_candles))
        
        for i in range(candles_to_check - 1, -1, -1):  # Check from oldest to newest
            if i >= len(recent_candles):
                continue
            
            candle = recent_candles[i]
            if len(candle) < 6:
                continue
            
            timestamp = int(candle[0])
            high = float(candle[2])
            low = float(candle[3])
            close = float(candle[4])
            
            if zone_type in ["swing_high", "resistance"]:
                # Sell-side liquidity sweep: wick penetrates above, closes below
                if high > liquidity_zone_price and close < liquidity_zone_price:
                    wick_size = (high - liquidity_zone_price) / liquidity_zone_price
                    wick_size_pct = wick_size * 100
                    
                    # Check if next candle confirms (doesn't reclaim zone)
                    if i < len(recent_candles) - 1:
                        next_candle = recent_candles[i + 1]
                        if len(next_candle) >= 5:
                            next_close = float(next_candle[4])
                            if next_close < liquidity_zone_price:  # Next close still below = confirmed
                                # Calculate confidence based on wick size and volume
                                base_confidence = min(0.8, wick_size_pct / 10.0)  # Larger wick = higher confidence
                                volume_boost = min(0.2, (volume_ratio - 1.0) * 0.1) if volume_ratio > 1.0 else 0.0
                                confidence = min(1.0, base_confidence + volume_boost)
                                
                                return {
                                    "sweep_detected": True,
                                    "confidence": confidence,
                                    "direction": "bearish",  # Sell-side liquidity grabbed, expect down move
                                    "sweep_time": timestamp,
                                    "wick_size_pct": wick_size_pct
                                }
                    
                    # Even without next candle confirmation, if wick is large enough
                    if wick_size_pct > 0.3:  # 0.3% wick = significant
                        base_confidence = min(0.6, wick_size_pct / 10.0)
                        volume_boost = min(0.15, (volume_ratio - 1.0) * 0.1) if volume_ratio > 1.0 else 0.0
                        confidence = min(0.9, base_confidence + volume_boost)
                        
                        return {
                            "sweep_detected": True,
                            "confidence": confidence,
                            "direction": "bearish",
                            "sweep_time": timestamp,
                            "wick_size_pct": wick_size_pct
                        }
            
            elif zone_type in ["swing_low", "support"]:
                # Buy-side liquidity sweep: wick penetrates below, closes above
                if low < liquidity_zone_price and close > liquidity_zone_price:
                    wick_size = (liquidity_zone_price - low) / liquidity_zone_price
                    wick_size_pct = wick_size * 100
                    
                    # Check if next candle confirms (doesn't break below)
                    if i < len(recent_candles) - 1:
                        next_candle = recent_candles[i + 1]
                        if len(next_candle) >= 5:
                            next_close = float(next_candle[4])
                            if next_close > liquidity_zone_price:  # Next close still above = confirmed
                                # Calculate confidence based on wick size and volume
                                base_confidence = min(0.8, wick_size_pct / 10.0)
                                volume_boost = min(0.2, (volume_ratio - 1.0) * 0.1) if volume_ratio > 1.0 else 0.0
                                confidence = min(1.0, base_confidence + volume_boost)
                                
                                return {
                                    "sweep_detected": True,
                                    "confidence": confidence,
                                    "direction": "bullish",  # Buy-side liquidity grabbed, expect up move
                                    "sweep_time": timestamp,
                                    "wick_size_pct": wick_size_pct
                                }
                    
                    # Even without next candle confirmation, if wick is large enough
                    if wick_size_pct > 0.3:  # 0.3% wick = significant
                        base_confidence = min(0.6, wick_size_pct / 10.0)
                        volume_boost = min(0.15, (volume_ratio - 1.0) * 0.1) if volume_ratio > 1.0 else 0.0
                        confidence = min(0.9, base_confidence + volume_boost)
                        
                        return {
                            "sweep_detected": True,
                            "confidence": confidence,
                            "direction": "bullish",
                            "sweep_time": timestamp,
                            "wick_size_pct": wick_size_pct
                        }
        
        # No sweep detected
        return {
            "sweep_detected": False,
            "confidence": 0.0,
            "direction": None,
            "sweep_time": None,
            "wick_size_pct": 0.0
        }
    
    def compute_tier2_liquidity(
        self,
        symbol: str,
        price: float,
        indicators: Dict,
        recent_1m_candles: Optional[List[List[float]]] = None,
        recent_5m_candles: Optional[List[List[float]]] = None,
        recent_15m_candles: Optional[List[List[float]]] = None
    ) -> Dict:
        """
        Compute complete Tier 2 liquidity features.
        
        Args:
            symbol: Trading pair symbol
            price: Current price
            indicators: Dictionary of indicators (from MarketSnapshot)
            recent_1m_candles: Recent 1m candles for sweep detection
            recent_5m_candles: Recent 5m candles for sweep detection
            recent_15m_candles: Recent 15m candles for sweep detection (for swing trading)
            
        Returns:
            Dictionary with liquidity zone fields:
            {
                "distance_pct": float,
                "zone_price": float,
                "zone_type": str,
                "sweep_detected": bool,
                "sweep_confidence": float,
                "sweep_direction": str
            }
        """
        # Get liquidity zone levels from indicators
        swing_high = indicators.get('swing_high', 0)
        swing_low = indicators.get('swing_low', 0)
        resistance_1 = indicators.get('resistance_1', 0)
        support_1 = indicators.get('support_1', 0)
        
        # Find nearest liquidity zone
        nearest_zone = self.find_nearest_liquidity_zone(
            price=price,
            swing_high=swing_high,
            swing_low=swing_low,
            resistance_1=resistance_1,
            support_1=support_1
        )
        
        if not nearest_zone["zone_price"]:
            return {
                "distance_pct": None,
                "zone_price": None,
                "zone_type": None,
                "sweep_detected": False,
                "sweep_confidence": 0.0,
                "sweep_direction": None
            }
        
        # Get volume ratio for sweep detection
        volume_ratio_1m = indicators.get('volume_ratio_1m', 1.0)
        volume_ratio_5m = indicators.get('volume_ratio_5m', 1.0)
        volume_ratio_15m = indicators.get('volume_ratio_15m', indicators.get('volume_ratio', 1.0))
        active_volume_ratio = max(volume_ratio_1m, volume_ratio_5m, volume_ratio_15m)
        
        # Detect sweep using multiple timeframes (prioritize 15m for swing, then 5m, then 1m)
        # 15m sweeps are more significant for swing trading
        # 5m sweeps are good for scalping
        # 1m sweeps are the most granular but can be noisy
        recent_candles_for_sweep = None
        if recent_15m_candles and len(recent_15m_candles) >= 2:
            recent_candles_for_sweep = recent_15m_candles  # Prefer 15m for swing trading
        elif recent_5m_candles and len(recent_5m_candles) >= 2:
            recent_candles_for_sweep = recent_5m_candles  # Fallback to 5m
        elif recent_1m_candles and len(recent_1m_candles) >= 2:
            recent_candles_for_sweep = recent_1m_candles  # Fallback to 1m
        
        sweep_info = self.detect_liquidity_sweep(
            current_price=price,
            recent_candles=recent_candles_for_sweep or [],
            liquidity_zone_price=nearest_zone["zone_price"],
            zone_type=nearest_zone["zone_type"],
            volume_ratio=active_volume_ratio
        )
        
        return {
            "distance_pct": nearest_zone["distance_pct"],
            "zone_price": nearest_zone["zone_price"],
            "zone_type": nearest_zone["zone_type"],
            "sweep_detected": sweep_info["sweep_detected"],
            "sweep_confidence": sweep_info["confidence"],
            "sweep_direction": sweep_info["direction"]
        }

