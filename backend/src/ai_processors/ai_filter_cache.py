"""Caching layer for AI filter responses to reduce API costs."""

import logging
import time
import hashlib
import json
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class CachedResponse:
    """Cached AI filter response."""
    approved: bool
    suggested_leverage: Optional[float]
    ai_confidence: Optional[float]
    timestamp: float
    cache_key: str
    price: float = 0.0  # Store price for validation


class AIFilterCache:
    """Cache for AI filter responses to reduce API calls."""
    
    def __init__(self, ttl_seconds: int = 90, price_tolerance_pct: float = 0.001):
        """
        Initialize AI filter cache.
        
        Args:
            ttl_seconds: Time-to-live for cache entries (default: 90 seconds)
            price_tolerance_pct: Price change tolerance for cache hits (default: 0.1%)
        """
        self.cache: Dict[str, CachedResponse] = {}
        self.ttl_seconds = ttl_seconds
        self.price_tolerance_pct = price_tolerance_pct
        self.hits = 0
        self.misses = 0
        self.cleanup_interval = 300  # Clean up every 5 minutes
        self.last_cleanup = time.time()
    
    def _generate_cache_key(
        self, 
        symbol: str, 
        action: str, 
        position_type: str,
        confidence: float,
        price: float,
        position_size: float,
        indicators_hash: str
    ) -> str:
        """
        Generate cache key from decision parameters.
        
        Args:
            symbol: Trading symbol
            action: Decision action (long/short/hold/close)
            position_type: Position type (swing/scalp)
            confidence: Strategy confidence
            price: Current price
            position_size: Current position size
            indicators_hash: Hash of key indicators
            
        Returns:
            Cache key string
        """
        # Round confidence to 0.1 precision for better cache hits
        confidence_rounded = round(confidence, 1)
        
        # Round price to 0.01% precision for cache matching
        price_rounded = round(price * (1.0 / (1.0 + self.price_tolerance_pct)))
        
        # Create key from decision parameters
        key_parts = [
            symbol,
            action,
            position_type,
            f"{confidence_rounded:.1f}",
            f"{price_rounded:.2f}",
            f"{position_size:.6f}",
            indicators_hash[:16]  # Use first 16 chars of hash
        ]
        
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _extract_key_indicators(self, snapshot) -> str:
        """
        Extract key indicators for cache key generation.
        
        Args:
            snapshot: Market snapshot
            
        Returns:
            Hash of key indicators
        """
        indicators = snapshot.indicators if hasattr(snapshot, 'indicators') else {}
        
        # Extract key indicators that affect decisions
        key_data = {
            'trend_1d': indicators.get('trend_1d', 'unknown'),
            'trend_4h': indicators.get('trend_4h', 'unknown'),
            'trend_1h': indicators.get('trend_1h', 'unknown'),
            'rsi_14': round(indicators.get('rsi_14', 50), 0),
            'ema_50': round(indicators.get('ema_50', 0), -2),  # Round to nearest 100
            'volume_ratio_1h': round(indicators.get('volume_ratio_1h', 1.0), 1),
        }
        
        key_json = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_json.encode()).hexdigest()
    
    def get(
        self,
        symbol: str,
        snapshot,
        signal,
        position_size: float
    ) -> Optional[Tuple[bool, Optional[float], Optional[float]]]:
        """
        Get cached response if available and valid.
        
        Args:
            symbol: Trading symbol
            snapshot: Market snapshot
            signal: Strategy signal
            position_size: Current position size
            
        Returns:
            Tuple of (approved, suggested_leverage, ai_confidence) or None if cache miss
        """
        try:
            # Clean up old entries periodically
            self._cleanup_expired()
            
            # Extract key indicators
            indicators_hash = self._extract_key_indicators(snapshot)
            
            # Get current price
            price = snapshot.price if hasattr(snapshot, 'price') else 0.0
            
            # Generate cache key
            cache_key = self._generate_cache_key(
                symbol=symbol,
                action=signal.action,
                position_type=getattr(signal, 'position_type', 'swing'),
                confidence=signal.confidence,
                price=price,
                position_size=position_size,
                indicators_hash=indicators_hash
            )
            
            # Check cache
            cached = self.cache.get(cache_key)
            if cached:
                # Check if cache entry is still valid
                age = time.time() - cached.timestamp
                if age < self.ttl_seconds:
                    # Verify price hasn't changed too much (if price was stored)
                    if cached.price > 0 and price > 0:
                        price_change_pct = abs(price - cached.price) / price
                        if price_change_pct > self.price_tolerance_pct:
                            logger.debug(
                                f"AI filter cache MISS (price changed {price_change_pct*100:.3f}% > {self.price_tolerance_pct*100:.3f}%)"
                            )
                            self.misses += 1
                            return None
                    
                    self.hits += 1
                    logger.debug(
                        f"AI filter cache HIT for {symbol} {signal.action} "
                        f"(age: {age:.1f}s)"
                    )
                    return (cached.approved, cached.suggested_leverage, cached.ai_confidence)
                else:
                    logger.debug(f"AI filter cache MISS (expired, age: {age:.1f}s)")
            
            self.misses += 1
            return None
            
        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")
            return None
    
    def put(
        self,
        symbol: str,
        snapshot,
        signal,
        position_size: float,
        approved: bool,
        suggested_leverage: Optional[float],
        ai_confidence: Optional[float]
    ) -> None:
        """
        Store response in cache.
        
        Args:
            symbol: Trading symbol
            snapshot: Market snapshot
            signal: Strategy signal
            position_size: Current position size
            approved: AI approval decision
            suggested_leverage: AI-suggested leverage
            ai_confidence: AI-assessed confidence
        """
        try:
            # Extract key indicators
            indicators_hash = self._extract_key_indicators(snapshot)
            
            # Get current price
            price = snapshot.price if hasattr(snapshot, 'price') else 0.0
            
            # Generate cache key
            cache_key = self._generate_cache_key(
                symbol=symbol,
                action=signal.action,
                position_type=getattr(signal, 'position_type', 'swing'),
                confidence=signal.confidence,
                price=price,
                position_size=position_size,
                indicators_hash=indicators_hash
            )
            
            # Store in cache
            cached = CachedResponse(
                approved=approved,
                suggested_leverage=suggested_leverage,
                ai_confidence=ai_confidence,
                timestamp=time.time(),
                cache_key=cache_key,
                price=price  # Store price for validation
            )
            
            self.cache[cache_key] = cached
            
            logger.debug(f"AI filter cache STORED for {symbol} {signal.action} (key: {cache_key[:8]}...)")
            
        except Exception as e:
            logger.warning(f"Cache store failed: {e}")
    
    def _cleanup_expired(self) -> None:
        """Remove expired cache entries."""
        now = time.time()
        if now - self.last_cleanup < self.cleanup_interval:
            return
        
        expired_keys = [
            key for key, cached in self.cache.items()
            if now - cached.timestamp > self.ttl_seconds
        ]
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
        
        self.last_cleanup = now
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0.0
        
        return {
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate_pct': hit_rate,
            'cache_size': len(self.cache),
            'ttl_seconds': self.ttl_seconds
        }
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        logger.info("AI filter cache cleared")

