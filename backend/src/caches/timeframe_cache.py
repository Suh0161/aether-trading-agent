"""Caching system for multi-timeframe market data."""

import logging
import time
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class TimeframeCache:
    """Manages caching of indicator data across different timeframes and symbols."""

    def __init__(self):
        """Initialize timeframe cache with TTL settings."""
        # Per-symbol cache structure: {symbol: {timeframe: {'indicators': Dict, 'timestamp': float}}}
        self._cache: Dict[str, Dict[str, Dict[str, Any]]] = {}

        # Cache TTL: Higher TFs update less frequently
        self._cache_ttl_1d = 3600  # Daily: update every 1 hour
        self._cache_ttl_4h = 900   # 4h: update every 15 minutes
        self._cache_ttl_1h = 300   # 1h: update every 5 minutes
        self._cache_ttl_15m = 180  # 15m: update every 3 minutes
        self._cache_ttl_5m = 60    # 5m: update every 1 minute
        self._cache_ttl_1m = 30    # 1m: update every 30 seconds

    def _get_cache_ttl(self, timeframe: str) -> float:
        """Get TTL for a timeframe."""
        ttl_map = {
            '1d': self._cache_ttl_1d,
            '4h': self._cache_ttl_4h,
            '1h': self._cache_ttl_1h,
            '15m': self._cache_ttl_15m,
            '5m': self._cache_ttl_5m,
            '1m': self._cache_ttl_1m
        }
        return ttl_map.get(timeframe, 60)  # Default 60 seconds

    def get_cached_indicators(self, symbol: str, timeframe: str) -> Optional[Dict[str, float]]:
        """
        Get cached indicators for a symbol and timeframe if still valid.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")
            timeframe: Timeframe string ("1d", "4h", "1h", "15m", "5m", "1m")

        Returns:
            Cached indicators dict or None if cache expired/missing
        """
        current_time = time.time()

        # Check if symbol exists in cache
        if symbol not in self._cache:
            return None

        symbol_cache = self._cache[symbol]

        # Check if timeframe exists for this symbol
        if timeframe not in symbol_cache:
            return None

        timeframe_data = symbol_cache[timeframe]
        cache_timestamp = timeframe_data.get('timestamp', 0)
        cache_ttl = self._get_cache_ttl(timeframe)

        # Check if cache is still valid
        if (current_time - cache_timestamp) < cache_ttl:
            logger.debug(f"Using cached {timeframe} timeframe for {symbol}")
            return timeframe_data.get('indicators')
        else:
            # Cache expired, remove it
            del symbol_cache[timeframe]
            if not symbol_cache:
                del self._cache[symbol]
            return None

    def update_cache(self, symbol: str, timeframe: str, indicators: Dict[str, float]):
        """
        Update cache with new indicators for a symbol and timeframe.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")
            timeframe: Timeframe string ("1d", "4h", "1h", "15m", "5m", "1m")
            indicators: Indicator values to cache
        """
        current_time = time.time()

        # Initialize symbol cache if it doesn't exist
        if symbol not in self._cache:
            self._cache[symbol] = {}

        # Update cache for this symbol and timeframe
        self._cache[symbol][timeframe] = {
            'indicators': indicators,
            'timestamp': current_time
        }

        logger.debug(f"Updated {timeframe} timeframe cache for {symbol}")

    def is_cache_expired(self, symbol: str, timeframe: str) -> bool:
        """
        Check if cache for a symbol and timeframe is expired.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")
            timeframe: Timeframe string ("1d", "4h", "1h", "15m", "5m", "1m")

        Returns:
            True if cache is expired or missing
        """
        cached_data = self.get_cached_indicators(symbol, timeframe)
        return cached_data is None
