"""Tiered data models for structured, focused market analysis."""

from dataclasses import dataclass
from typing import Optional, Dict, List
from src.models import MarketSnapshot


@dataclass
class Tier1Data:
    """Core market state - must have for every decision."""
    price: float
    bid: float
    ask: float
    ema_1m: float
    ema_5m: float
    ema_15m: float
    ema_1h: float
    ema_50_4h: float
    ema_50_1d: float
    atr_14: float
    volume_1m: float
    volume_5m: float
    volume_1h: float
    position_size: float
    position_side: str  # "long" | "short" | "none"
    fees: float  # Trading fee rate
    tick_size: float


@dataclass
class Tier2Data:
    """Order book microstructure + liquidity zones - very useful for precise timing."""
    order_book_imbalance: float  # -1 to +1, + = buyers heavier, - = sellers heavier
    spread_bp: float  # Spread in basis points
    bid_ask_vol_ratio: float  # best_bid_vol / best_ask_vol
    best_bid_price: float
    best_ask_price: float
    best_bid_vol: float
    best_ask_vol: float
    
    # Liquidity zone fields (extended)
    distance_to_liquidity_zone_pct: Optional[float] = None  # % distance to nearest zone
    nearest_liquidity_zone_price: Optional[float] = None  # Price of nearest zone
    liquidity_zone_type: Optional[str] = None  # "swing_high" | "swing_low" | "resistance" | "support"
    liquidity_sweep_detected: bool = False  # Was there a sweep in last 5 min?
    sweep_confidence: float = 0.0  # 0.0-1.0, based on wick size + volume
    sweep_direction: Optional[str] = None  # "bullish" | "bearish" | None


@dataclass
class Tier3Data:
    """Regime/context features - avoids over-trading."""
    session: str  # "london_open" | "ny_overlap" | "asia"
    vol_regime: str  # "low" | "normal" | "high"
    market_condition: str  # "trend_up" | "trend_down" | "range"
    atr_percentile: float  # 0-100, where current ATR sits vs historical


@dataclass
class EnhancedMarketSnapshot:
    """MarketSnapshot extended with tiered data for optimized AI context."""
    
    # Original snapshot (for backwards compatibility)
    original: MarketSnapshot
    
    # Tiered data
    tier1: Tier1Data
    tier2: Optional[Tier2Data]  # None if order book fetch failed
    tier3: Tier3Data
    
    # Property accessors for backwards compatibility with MarketSnapshot
    @property
    def price(self) -> float:
        """Get current price from tier1 or original snapshot."""
        return self.tier1.price if self.tier1 else self.original.price
    
    @property
    def bid(self) -> float:
        """Get bid price from tier1 or original snapshot."""
        return self.tier1.bid if self.tier1 else self.original.bid
    
    @property
    def ask(self) -> float:
        """Get ask price from tier1 or original snapshot."""
        return self.tier1.ask if self.tier1 else self.original.ask
    
    @property
    def symbol(self) -> str:
        """Get symbol from original snapshot."""
        return self.original.symbol
    
    @property
    def timestamp(self) -> int:
        """Get timestamp from original snapshot."""
        return self.original.timestamp
    
    @property
    def ohlcv(self) -> List[List[float]]:
        """Get OHLCV data from original snapshot."""
        return self.original.ohlcv
    
    @property
    def indicators(self) -> Dict[str, float]:
        """Get indicators from original snapshot."""
        return self.original.indicators
    
    def to_compact_dict(self) -> Dict:
        """
        Convert to compact dictionary for prompt building.
        Only includes essential fields to minimize token usage.
        """
        return {
            "tier1": {
                "price": self.tier1.price,
                "ema_1h": self.tier1.ema_1h,
                "ema_15m": self.tier1.ema_15m,
                "atr_14": self.tier1.atr_14,
                "volume_1h": self.tier1.volume_1h,
                "position_size": self.tier1.position_size,
                "position_side": self.tier1.position_side,
            },
            "tier2": {
                "imbalance": self.tier2.order_book_imbalance if self.tier2 else None,
                "spread_bp": self.tier2.spread_bp if self.tier2 else None,
                "bid_ask_ratio": self.tier2.bid_ask_vol_ratio if self.tier2 else None,
                "liquidity_zone": {
                    "zone_price": self.tier2.nearest_liquidity_zone_price if self.tier2 else None,
                    "zone_type": self.tier2.liquidity_zone_type if self.tier2 else None,
                    "distance_pct": self.tier2.distance_to_liquidity_zone_pct if self.tier2 else None,
                    "sweep_detected": self.tier2.liquidity_sweep_detected if self.tier2 else False,
                    "sweep_confidence": self.tier2.sweep_confidence if self.tier2 else 0.0,
                    "sweep_direction": self.tier2.sweep_direction if self.tier2 else None,
                } if self.tier2 and self.tier2.liquidity_zone_type else None,
            } if self.tier2 else None,
            "tier3": {
                "session": self.tier3.session,
                "vol_regime": self.tier3.vol_regime,
                "market_condition": self.tier3.market_condition,
            },
            "symbol": self.original.symbol,
        }

