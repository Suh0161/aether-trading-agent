"""Regime classifier for Tier 3 context features."""

import logging
from datetime import datetime
from typing import Dict, Optional
from src.tiered_data import Tier3Data

logger = logging.getLogger(__name__)


class RegimeClassifier:
    """Classifies market regime and trading session context."""
    
    def __init__(self):
        """Initialize regime classifier."""
        # Historical ATR tracking for percentile calculation
        self._atr_history: Dict[str, list] = {}  # symbol -> [atr_values]
        self._max_history_length = 100  # Keep last 100 ATR values
    
    def classify_vol_regime(
        self, 
        symbol: str, 
        atr: float, 
        price: float,
        historical_atr: Optional[float] = None
    ) -> str:
        """
        Classify volatility regime based on ATR.
        
        Uses percentile-based classification:
        - If ATR < 30th percentile of historical: "low"
        - If ATR > 70th percentile of historical: "high"
        - Otherwise: "normal"
        
        Falls back to percentage-based classification if no history.
        
        Args:
            symbol: Trading pair symbol
            atr: Current ATR value
            price: Current price
            historical_atr: Average historical ATR (for fallback)
            
        Returns:
            "low" | "normal" | "high"
        """
        if not atr or not price or price == 0:
            return "normal"
        
        # Track ATR history for percentile calculation
        if symbol not in self._atr_history:
            self._atr_history[symbol] = []
        
        atr_history = self._atr_history[symbol]
        atr_history.append(atr)
        
        # Keep only last N values
        if len(atr_history) > self._max_history_length:
            atr_history.pop(0)
        
        # Calculate percentile if we have enough history
        if len(atr_history) >= 20:
            sorted_atr = sorted(atr_history)
            current_percentile = (sorted_atr.index(atr) / len(sorted_atr)) * 100 if atr in sorted_atr else 50
            
            if current_percentile < 30:
                return "low"
            elif current_percentile > 70:
                return "high"
            else:
                return "normal"
        
        # Fallback: percentage-based classification
        # Compare current ATR to historical average or price-based threshold
        if historical_atr and historical_atr > 0:
            atr_ratio = atr / historical_atr
            if atr_ratio < 0.7:
                return "low"
            elif atr_ratio > 1.3:
                return "high"
            else:
                return "normal"
        
        # Final fallback: percentage of price
        atr_pct = (atr / price) * 100
        if atr_pct < 0.5:  # Very tight range
            return "low"
        elif atr_pct > 2.0:  # Very wide range
            return "high"
        else:
            return "normal"
    
    def get_session_time(self) -> str:
        """
        Determine current trading session based on UTC time.
        
        Sessions:
        - London Open: 08:00-13:00 UTC
        - NY Overlap: 13:00-16:00 UTC (London + NY both open)
        - Asia: 00:00-08:00 UTC (and 16:00-24:00 UTC)
        
        Returns:
            "london_open" | "ny_overlap" | "asia"
        """
        utc_hour = datetime.utcnow().hour
        
        if 8 <= utc_hour < 13:
            return "london_open"
        elif 13 <= utc_hour < 16:
            return "ny_overlap"
        else:
            return "asia"
    
    def classify_market_condition(
        self,
        price: float,
        ema_20: float,
        ema_50: float,
        atr: float
    ) -> str:
        """
        Classify market condition based on trend and volatility.
        
        Args:
            price: Current price
            ema_20: 20-period EMA
            ema_50: 50-period EMA
            atr: Current ATR value
            
        Returns:
            "trend_up" | "trend_down" | "range"
        """
        if not price or not ema_20 or not ema_50:
            return "range"
        
        # Trend classification
        price_above_ema20 = price > ema_20
        price_above_ema50 = price > ema_50
        ema20_above_ema50 = ema_20 > ema_50
        
        # Strong uptrend: price > EMA20 > EMA50
        if price_above_ema20 and price_above_ema50 and ema20_above_ema50:
            return "trend_up"
        
        # Strong downtrend: price < EMA20 < EMA50
        if not price_above_ema20 and not price_above_ema50 and not ema20_above_ema50:
            return "trend_down"
        
        # Range-bound: mixed signals or price between EMAs
        return "range"
    
    def compute_tier3_data(
        self,
        symbol: str,
        price: float,
        ema_20: float,
        ema_50: float,
        atr: float,
        historical_atr: Optional[float] = None
    ) -> Tier3Data:
        """
        Compute complete Tier 3 data for a symbol.
        
        Args:
            symbol: Trading pair symbol
            price: Current price
            ema_20: 20-period EMA
            ema_50: 50-period EMA
            atr: Current ATR value
            historical_atr: Historical average ATR (optional)
            
        Returns:
            Tier3Data with all regime classifications
        """
        # Calculate ATR percentile
        atr_history = self._atr_history.get(symbol, [])
        atr_percentile = 50.0  # Default
        
        if len(atr_history) >= 10:
            sorted_atr = sorted(atr_history)
            if atr in sorted_atr:
                atr_percentile = (sorted_atr.index(atr) / len(sorted_atr)) * 100
            elif atr > sorted_atr[-1]:
                atr_percentile = 100.0
            elif atr < sorted_atr[0]:
                atr_percentile = 0.0
            else:
                # Interpolate
                for i, val in enumerate(sorted_atr):
                    if val > atr:
                        atr_percentile = (i / len(sorted_atr)) * 100
                        break
        
        return Tier3Data(
            session=self.get_session_time(),
            vol_regime=self.classify_vol_regime(symbol, atr, price, historical_atr),
            market_condition=self.classify_market_condition(price, ema_20, ema_50, atr),
            atr_percentile=atr_percentile
        )

