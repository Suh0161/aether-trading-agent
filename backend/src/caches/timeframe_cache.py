"""Caching system for multi-timeframe market data."""

import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class TimeframeCache:
    """Manages caching of indicator data across different timeframes."""

    def __init__(self):
        """Initialize timeframe cache with TTL settings."""
        # Cache for higher timeframes (they don't change as frequently)
        self._cached_indicators_1d: Optional[Dict[str, float]] = None
        self._cached_indicators_4h: Optional[Dict[str, float]] = None
        self._cache_timestamp_1d: float = 0
        self._cache_timestamp_4h: float = 0

        # Cache TTL: Higher TFs update less frequently
        self._cache_ttl_1d = 3600  # Daily: update every 1 hour
        self._cache_ttl_4h = 900   # 4h: update every 15 minutes

        # Cache for scalping timeframes (update frequently but still cache to reduce API calls)
        self._cached_indicators_5m: Optional[Dict[str, float]] = None
        self._cached_indicators_1m: Optional[Dict[str, float]] = None
        self._cache_timestamp_5m: float = 0
        self._cache_timestamp_1m: float = 0

        # Scalping TF cache TTL: Update more frequently than higher TFs but still cache
        self._cache_ttl_5m = 60    # 5m: update every 1 minute
        self._cache_ttl_1m = 30    # 1m: update every 30 seconds

    def get_cached_indicators(self, timeframe: str) -> Optional[Dict[str, float]]:
        """
        Get cached indicators for a timeframe if still valid.

        Args:
            timeframe: Timeframe string ("1d", "4h", "5m", "1m")

        Returns:
            Cached indicators dict or None if cache expired/missing
        """
        current_time = time.time()

        if timeframe == "1d":
            if (self._cached_indicators_1d and
                (current_time - self._cache_timestamp_1d) < self._cache_ttl_1d):
                logger.debug("Using cached daily timeframe")
                return self._cached_indicators_1d
        elif timeframe == "4h":
            if (self._cached_indicators_4h and
                (current_time - self._cache_timestamp_4h) < self._cache_ttl_4h):
                logger.debug("Using cached 4h timeframe")
                return self._cached_indicators_4h
        elif timeframe == "5m":
            if (self._cached_indicators_5m and
                (current_time - self._cache_timestamp_5m) < self._cache_ttl_5m):
                logger.debug("Using cached 5m timeframe")
                return self._cached_indicators_5m
        elif timeframe == "1m":
            if (self._cached_indicators_1m and
                (current_time - self._cache_timestamp_1m) < self._cache_ttl_1m):
                logger.debug("Using cached 1m timeframe")
                return self._cached_indicators_1m

        return None

    def update_cache(self, timeframe: str, indicators: Dict[str, float]):
        """
        Update cache with new indicators for a timeframe.

        Args:
            timeframe: Timeframe string ("1d", "4h", "5m", "1m")
            indicators: Indicator values to cache
        """
        current_time = time.time()

        if timeframe == "1d":
            self._cached_indicators_1d = indicators
            self._cache_timestamp_1d = current_time
            logger.debug("Updated daily timeframe cache")
        elif timeframe == "4h":
            self._cached_indicators_4h = indicators
            self._cache_timestamp_4h = current_time
            logger.debug("Updated 4h timeframe cache")
        elif timeframe == "5m":
            self._cached_indicators_5m = indicators
            self._cache_timestamp_5m = current_time
            logger.debug("Updated 5m timeframe cache")
        elif timeframe == "1m":
            self._cached_indicators_1m = indicators
            self._cache_timestamp_1m = current_time
            logger.debug("Updated 1m timeframe cache")

    def is_cache_expired(self, timeframe: str) -> bool:
        """
        Check if cache for a timeframe is expired.

        Args:
            timeframe: Timeframe string ("1d", "4h", "5m", "1m")

        Returns:
            True if cache is expired or missing
        """
        cached_data = self.get_cached_indicators(timeframe)
        return cached_data is None
