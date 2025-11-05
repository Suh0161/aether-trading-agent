"""Data acquisition layer for fetching market data from exchanges."""

import logging
import time
from typing import Optional, Dict, List
from src.config import Config
from src.models import MarketSnapshot
from src.orderbook_analyzer import OrderBookAnalyzer
from src.regime_classifier import RegimeClassifier
from src.tiered_data import EnhancedMarketSnapshot
from src.exchange_adapters.exchange_adapter import ExchangeAdapter
from src.data_fetchers.market_data_fetcher import MarketDataFetcher
from src.indicator_calculators.technical_indicator_calculator import TechnicalIndicatorCalculator
from src.caches.timeframe_cache import TimeframeCache
from src.snapshot_builders.market_snapshot_builder import MarketSnapshotBuilder


logger = logging.getLogger(__name__)


class DataAcquisition:
    """Fetches and normalizes market data from exchange APIs."""
    
    def __init__(self, config: Config):
        """
        Initialize data acquisition with exchange client.

        Args:
            config: Configuration object with exchange settings
        """
        self.config = config

        # Initialize modular components
        self.exchange_adapter = ExchangeAdapter(config)
        self.data_fetcher = MarketDataFetcher(self.exchange_adapter, config)
        self.indicator_calculator = TechnicalIndicatorCalculator()
        self.timeframe_cache = TimeframeCache()
        self.snapshot_builder = MarketSnapshotBuilder(config, data_fetcher=self.data_fetcher)

        # Cache for error recovery
        self._cached_snapshot: Optional[MarketSnapshot] = None

        # Initialize tiered data components
        try:
            self.orderbook_analyzer = OrderBookAnalyzer(self.exchange_adapter.exchange)
        except Exception as e:
            self.orderbook_analyzer = None
            logger.warning(f"OrderBookAnalyzer initialization failed: {e}")
        self.regime_classifier = RegimeClassifier()

        # Connect snapshot builder to analyzers
        if self.orderbook_analyzer:
            self.snapshot_builder.orderbook_analyzer = self.orderbook_analyzer
        self.snapshot_builder.regime_classifier = self.regime_classifier

    def _get_limit_for_timeframe(self, timeframe: str) -> int:
        """Get appropriate candle limit for timeframe."""
        limits = {
            '1d': 200,   # ~7 months
            '4h': 300,   # ~50 days
            '1h': 500,   # ~21 days
            '15m': 200,  # ~2 days
            '5m': 200,   # ~17 hours
            '1m': 200    # ~3 hours
        }
        return limits.get(timeframe, 200)
    
    
    def _compute_indicators(self, ohlcv: List[List[float]]) -> Dict[str, float]:
        """Delegate to technical indicator calculator."""
        return self.indicator_calculator.compute_indicators(ohlcv)
    def fetch_market_snapshot(self, symbol: str) -> MarketSnapshot:
        """
        Fetch ticker, OHLCV data from multiple timeframes and return normalized snapshot.

        Professional multi-timeframe analysis:
        - Higher TFs (4h, 1d): For trend confirmation
        - Lower TFs (15m): For entry timing

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")

        Returns:
            MarketSnapshot with current market data and multi-timeframe indicators
        """
        try:
            # Fetch ticker data using data fetcher
            ticker_data = self.data_fetcher.fetch_ticker_data(symbol)
            current_price = ticker_data['last']

            # Fetch multi-timeframe OHLCV data with caching
            timeframes = ['1d', '4h', '1h', '15m', '5m', '1m']
            combined_indicators = {}

            for tf in timeframes:
                # Check cache first
                cached = self.timeframe_cache.get_cached_indicators(tf)
                if cached:
                    indicators = cached
                    logger.debug(f"Using cached {tf} timeframe")
                else:
                    # Fetch fresh data
                    ohlcv_data = self.data_fetcher.fetch_ohlcv_data(symbol, tf, self._get_limit_for_timeframe(tf))
                    indicators = self.indicator_calculator.compute_indicators(ohlcv_data)
                    self.timeframe_cache.update_cache(tf, indicators)
                    logger.debug(f"Updated {tf} timeframe cache")

                # Add timeframe prefix to indicators
                if tf != '1h':  # 1h is primary, no prefix needed
                    prefixed_indicators = {f"{k}_{tf}": v for k, v in indicators.items()}
                    combined_indicators.update(prefixed_indicators)
                else:
                    combined_indicators.update(indicators)

            # Add trend analysis based on EMAs
            combined_indicators['trend_1d'] = 'bullish' if current_price > combined_indicators.get('ema_50_1d', 0) else 'bearish'
            combined_indicators['trend_4h'] = 'bullish' if current_price > combined_indicators.get('ema_50_4h', 0) else 'bearish'
            combined_indicators['trend_15m'] = 'bullish' if current_price > combined_indicators.get('ema_50_15m', 0) else 'bearish'
            combined_indicators['trend_5m'] = 'bullish' if current_price > combined_indicators.get('ema_50_5m', 0) else 'bearish'
            combined_indicators['trend_1m'] = 'bullish' if current_price > combined_indicators.get('ema_50_1m', 0) else 'bearish'

            # Fetch primary OHLCV for backwards compatibility
            ohlcv_1h = self.data_fetcher.fetch_ohlcv_data(symbol, '1h', 500)

            # Create market snapshot
            snapshot = self.snapshot_builder.build_market_snapshot(symbol, ticker_data, ohlcv_1h, combined_indicators)

            # Cache the snapshot for error recovery
            self._cached_snapshot = snapshot

            logger.debug(f"Fetched multi-timeframe snapshot for {symbol}: price={snapshot.price}")
            logger.debug(f"Trend alignment: 1D={combined_indicators['trend_1d']}, 4H={combined_indicators['trend_4h']}, 15M={combined_indicators['trend_15m']}")

            return snapshot

        except Exception as e:
            logger.error(f"Failed to fetch market data for {symbol}: {e}")

            # Return cached snapshot if available
            if self._cached_snapshot is not None:
                logger.warning(f"Returning cached snapshot for {symbol}")
                return self._cached_snapshot

            # If no cache available, re-raise the exception
            raise
    
    def fetch_multi_symbol_snapshots(self, symbols: List[str]) -> Dict[str, MarketSnapshot]:
        """
        Fetch market snapshots for multiple symbols in parallel.
        
        Args:
            symbols: List of trading pair symbols (e.g., ["BTC/USDT", "ETH/USDT"])
            
        Returns:
            Dictionary mapping symbol to MarketSnapshot
        """
        snapshots = {}
        errors = []
        
        for symbol in symbols:
            try:
                snapshot = self.fetch_market_snapshot(symbol)
                snapshots[symbol] = snapshot
                logger.debug(f"Fetched snapshot for {symbol}: price={snapshot.price}")
            except Exception as e:
                logger.error(f"Failed to fetch snapshot for {symbol}: {e}")
                errors.append(symbol)
        
        if errors:
            logger.warning(f"Failed to fetch {len(errors)} symbol(s): {', '.join(errors)}")
        
        if not snapshots:
            raise Exception("Failed to fetch any market snapshots")
        
        logger.info(f"Fetched {len(snapshots)} symbol snapshots successfully")
        return snapshots
    
    def fetch_enhanced_snapshot(
        self,
        symbol: str,
        position_size: float = 0.0
    ) -> EnhancedMarketSnapshot:
        """
        Fetch market snapshot with Tier 2 (order book) and Tier 3 (regime) data.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")
            position_size: Current position size (for Tier 1 data)

        Returns:
            EnhancedMarketSnapshot with all tiered data
        """
        # Fetch base snapshot
        snapshot = self.fetch_market_snapshot(symbol)

        # Build enhanced snapshot with Tier 2 and Tier 3 data
        return self.snapshot_builder.build_enhanced_snapshot(snapshot, position_size)
    
    def fetch_multi_symbol_enhanced_snapshots(
        self,
        symbols: List[str],
        position_sizes: Optional[Dict[str, float]] = None
    ) -> Dict[str, EnhancedMarketSnapshot]:
        """
        Fetch enhanced market snapshots with Tier 2 and Tier 3 data for multiple symbols.
        
        Args:
            symbols: List of trading pair symbols (e.g., ["BTC/USDT", "ETH/USDT"])
            position_sizes: Dictionary mapping symbol to position size (default: all 0)
            
        Returns:
            Dictionary mapping symbol to EnhancedMarketSnapshot
        """
        if position_sizes is None:
            position_sizes = {symbol: 0.0 for symbol in symbols}
        
        enhanced_snapshots = {}
        errors = []
        
        for symbol in symbols:
            try:
                position_size = position_sizes.get(symbol, 0.0)
                enhanced_snapshot = self.fetch_enhanced_snapshot(symbol, position_size)
                enhanced_snapshots[symbol] = enhanced_snapshot
                
                # Log tiered data summary
                tier2_info = ""
                liquidity_info = ""
                if enhanced_snapshot.tier2:
                    tier2_info = f", OB imbalance={enhanced_snapshot.tier2.order_book_imbalance:.3f}"
                    if enhanced_snapshot.tier2.liquidity_zone_type:
                        sweep_info = ""
                        if enhanced_snapshot.tier2.liquidity_sweep_detected:
                            sweep_info = f", SWEEP({enhanced_snapshot.tier2.sweep_direction}, conf:{enhanced_snapshot.tier2.sweep_confidence:.2f})"
                        liquidity_info = f", {enhanced_snapshot.tier2.liquidity_zone_type}@{enhanced_snapshot.tier2.nearest_liquidity_zone_price:,.0f}({enhanced_snapshot.tier2.distance_to_liquidity_zone_pct:.2f}%){sweep_info}"
                
                logger.debug(
                    f"Enhanced snapshot for {symbol}: "
                    f"price=${enhanced_snapshot.tier1.price:,.2f}, "
                    f"session={enhanced_snapshot.tier3.session}, "
                    f"vol_regime={enhanced_snapshot.tier3.vol_regime}, "
                    f"condition={enhanced_snapshot.tier3.market_condition}"
                    f"{tier2_info}"
                    f"{liquidity_info}"
                )
            except Exception as e:
                logger.error(f"Failed to fetch enhanced snapshot for {symbol}: {e}")
                errors.append(symbol)
        
        if errors:
            logger.warning(f"Failed to fetch enhanced snapshots for {len(errors)} symbol(s): {', '.join(errors)}")
        
        if enhanced_snapshots:
            logger.info(f"Fetched {len(enhanced_snapshots)} enhanced snapshots successfully")
        
        return enhanced_snapshots
