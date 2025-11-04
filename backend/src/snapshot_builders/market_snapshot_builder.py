"""Builders for creating market snapshot objects."""

import logging
from typing import Dict, List, Optional

from src.models import MarketSnapshot
from src.tiered_data import EnhancedMarketSnapshot, Tier1Data, Tier3Data

logger = logging.getLogger(__name__)


class MarketSnapshotBuilder:
    """Builds MarketSnapshot and EnhancedMarketSnapshot objects."""

    def __init__(self, config, orderbook_analyzer=None, regime_classifier=None, data_fetcher=None):
        """
        Initialize snapshot builder.

        Args:
            config: Configuration object
            orderbook_analyzer: Optional orderbook analyzer for Tier 2 data
            regime_classifier: Optional regime classifier for Tier 3 data
            data_fetcher: Optional data fetcher for fetching candles for sweep detection
        """
        self.config = config
        self.orderbook_analyzer = orderbook_analyzer
        self.regime_classifier = regime_classifier
        self.data_fetcher = data_fetcher

    def build_market_snapshot(self, symbol: str, ticker_data: Dict, ohlcv_data: List[List[float]],
                            indicators: Dict[str, float]) -> MarketSnapshot:
        """
        Build a basic MarketSnapshot object.

        Args:
            symbol: Trading pair symbol
            ticker_data: Ticker data from exchange
            ohlcv_data: OHLCV data (primary timeframe)
            indicators: Computed indicators

        Returns:
            MarketSnapshot object
        """
        return MarketSnapshot(
            timestamp=ticker_data['timestamp'],
            symbol=symbol,
            price=ticker_data['last'],
            bid=ticker_data['bid'],
            ask=ticker_data['ask'],
            ohlcv=ohlcv_data,  # Primary OHLCV for backwards compatibility
            indicators=indicators
        )

    def build_enhanced_snapshot(self, snapshot: MarketSnapshot, position_size: float = 0.0) -> EnhancedMarketSnapshot:
        """
        Build an EnhancedMarketSnapshot with Tier 2 and Tier 3 data.

        Args:
            snapshot: Base MarketSnapshot
            position_size: Current position size

        Returns:
            EnhancedMarketSnapshot with all tiered data
        """
        indicators = snapshot.indicators

        # Extract Tier 1 data
        tier1 = self._build_tier1_data(snapshot, indicators, position_size)

        # Fetch Tier 2 data (order book)
        tier2 = self.orderbook_analyzer.fetch_orderbook_metrics(snapshot.symbol) if self.orderbook_analyzer else None

        # Compute liquidity zone features if tier2 exists
        if tier2:
            liquidity_features = self._compute_liquidity_features(snapshot.symbol, snapshot.price, indicators)
            tier2.distance_to_liquidity_zone_pct = liquidity_features.get("distance_pct")
            tier2.nearest_liquidity_zone_price = liquidity_features.get("zone_price")
            tier2.liquidity_zone_type = liquidity_features.get("zone_type")
            tier2.liquidity_sweep_detected = liquidity_features.get("sweep_detected", False)
            tier2.sweep_confidence = liquidity_features.get("sweep_confidence", 0.0)
            tier2.sweep_direction = liquidity_features.get("sweep_direction")

        # Compute Tier 3 data (regime/context)
        tier3 = self._build_tier3_data(snapshot, indicators)

        return EnhancedMarketSnapshot(
            original=snapshot,
            tier1=tier1,
            tier2=tier2,
            tier3=tier3
        )

    def _build_tier1_data(self, snapshot: MarketSnapshot, indicators: Dict[str, float], position_size: float) -> Tier1Data:
        """Build Tier 1 data from snapshot and indicators."""
        return Tier1Data(
            price=snapshot.price,
            bid=snapshot.bid,
            ask=snapshot.ask,
            ema_1m=indicators.get('ema_20_1m', snapshot.price),
            ema_5m=indicators.get('ema_20_5m', snapshot.price),
            ema_15m=indicators.get('ema_50_15m', snapshot.price),
            ema_1h=indicators.get('ema_50', snapshot.price),
            ema_50_4h=indicators.get('ema_50_4h', snapshot.price),
            ema_50_1d=indicators.get('ema_50_1d', snapshot.price),
            atr_14=indicators.get('atr_14', 0.0),
            volume_1m=indicators.get('volume_1m', 0.0),
            volume_5m=indicators.get('volume_5m', 0.0),
            volume_1h=indicators.get('volume_1h', 0.0),
            position_size=position_size,
            position_side="long" if position_size > 0 else ("short" if position_size < 0 else "none"),
            fees=0.04,  # Binance Futures maker/taker fee (0.02% each, 0.04% total)
            tick_size=0.01  # Default tick size (can be fetched from exchange if needed)
        )

    def _build_tier3_data(self, snapshot: MarketSnapshot, indicators: Dict[str, float]) -> Tier3Data:
        """Build Tier 3 data (regime analysis)."""
        ema_20 = indicators.get('ema_20', snapshot.price)
        ema_50 = indicators.get('ema_50', snapshot.price)
        atr = indicators.get('atr_14', 0.0)

        # Get historical ATR for percentile calculation
        historical_atr = None
        if hasattr(self.regime_classifier, '_atr_history') and snapshot.symbol in self.regime_classifier._atr_history:
            atr_history = self.regime_classifier._atr_history[snapshot.symbol]
            if len(atr_history) > 0:
                historical_atr = sum(atr_history) / len(atr_history)

        return self.regime_classifier.compute_tier3_data(
            symbol=snapshot.symbol,
            price=snapshot.price,
            ema_20=ema_20,
            ema_50=ema_50,
            atr=atr,
            historical_atr=historical_atr
        )

    def _compute_liquidity_features(self, symbol: str, price: float, indicators: Dict[str, float]) -> Dict:
        """Compute liquidity zone features."""
        try:
            # Get recent candles for sweep detection
            ohlcv_1m = []
            ohlcv_5m = []
            
            if self.data_fetcher:
                try:
                    # Fetch last 10 candles for sweep detection (need recent wicks)
                    ohlcv_1m = self.data_fetcher.fetch_ohlcv_data(symbol, '1m', limit=10)
                    ohlcv_5m = self.data_fetcher.fetch_ohlcv_data(symbol, '5m', limit=10)
                    logger.debug(f"Fetched {len(ohlcv_1m)} 1m candles and {len(ohlcv_5m)} 5m candles for sweep detection")
                except Exception as e:
                    logger.warning(f"Failed to fetch candles for sweep detection: {e}")

            # Compute liquidity features using orderbook analyzer
            if self.orderbook_analyzer and hasattr(self.orderbook_analyzer, 'liquidity_analyzer'):
                return self.orderbook_analyzer.liquidity_analyzer.compute_tier2_liquidity(
                    symbol=symbol,
                    price=price,
                    indicators=indicators,
                    recent_1m_candles=ohlcv_1m,
                    recent_5m_candles=ohlcv_5m
                )
        except Exception as e:
            logger.warning(f"Failed to compute liquidity features for {symbol}: {e}")

        return {}
