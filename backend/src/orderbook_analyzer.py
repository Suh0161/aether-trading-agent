"""Order book analyzer for Tier 2 microstructure data."""

try:
    import ccxt
except ImportError:
    # Fallback for CCXT installation issues
    ccxt = None
import logging
from typing import Dict, Optional, List
from src.tiered_data import Tier2Data
from src.liquidity_analyzer import LiquidityAnalyzer

logger = logging.getLogger(__name__)


class OrderBookAnalyzer:
    """Analyzes order book to extract microstructure signals."""
    
    def __init__(self, exchange):
        """
        Initialize order book analyzer.
        
        Args:
            exchange: CCXT exchange instance (can have API keys, but we'll use public endpoint)
        """
        self.exchange = exchange
        self.liquidity_analyzer = LiquidityAnalyzer()
        self._cache: Dict[str, Dict] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._cache_ttl = 5.0  # Cache for 5 seconds (balance between freshness and API cost)
        
        # Create a public-only exchange instance for order book fetching (no API keys needed)
        # Order book is a public endpoint and doesn't require authentication
        self._init_public_exchange(exchange)
    
    def _init_public_exchange(self, exchange):
        """
        Create a public-only exchange instance for order book fetching.
        Order book is a public endpoint and doesn't require API keys.
        
        Args:
            exchange: Original exchange instance (to copy config from)
        """
        try:
            # Check if this is demo trading by inspecting exchange URLs
            exchange_urls = getattr(exchange, 'urls', {})
            api_urls = exchange_urls.get('api', {})
            fapi_public_url = api_urls.get('fapiPublic', '')
            is_demo = 'demo-fapi' in str(fapi_public_url) or 'demo.binance.com' in str(fapi_public_url)
            
            # Create public-only exchange instance (no API keys)
            self.public_exchange = ccxt.binance({
                'apiKey': '',  # No API key needed for public endpoints
                'secret': '',   # No secret needed
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',  # Use USD-M Futures
                    'adjustForTimeDifference': True,
                }
            })
            
            # ALWAYS use LIVE Binance public API for order book data
            # Order book is public data (no authentication needed) and demo API doesn't support it
            # This is safe - we're only READING public market data, not trading
            if is_demo:
                logger.info(
                    "Using LIVE Binance public API for order book data "
                    "(public data, no authentication - safe for demo mode)"
                )
            else:
                logger.debug("Created public exchange instance for order book fetching")
                
        except Exception as e:
            logger.warning(f"Failed to create public exchange instance: {e}, will use original exchange")
            self.public_exchange = exchange
    
    def fetch_orderbook_metrics(self, symbol: str, depth: int = 20) -> Optional[Tier2Data]:
        """
        Fetch order book and compute Tier 2 metrics.
        
        Tier 2 metrics:
        - order_book_imbalance: (bid_vol - ask_vol) / (bid_vol + ask_vol), range -1 to +1
        - spread_bp: (ask - bid) / bid * 10000 (basis points)
        - bid_ask_vol_ratio: best_bid_vol / best_ask_vol
        
        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")
            depth: Order book depth (default 20 levels)
            
        Returns:
            Tier2Data or None if fetch failed
        """
        import time
        
        # Check cache first
        cache_key = symbol
        current_time = time.time()
        if cache_key in self._cache:
            if current_time - self._cache_timestamps[cache_key] < self._cache_ttl:
                logger.debug(f"Using cached order book data for {symbol}")
                return self._cache[cache_key]
        
        try:
            # Fetch order book using public endpoint (no authentication required)
            # Use public_exchange instance which has no API keys
            orderbook = self.public_exchange.fetch_order_book(symbol, depth)
            
            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])
            
            if not bids or not asks:
                logger.warning(f"Empty order book for {symbol}")
                return None
            
            # Best bid/ask (top of book)
            best_bid_price = bids[0][0] if bids else 0.0
            best_ask_price = asks[0][0] if asks else 0.0
            
            if best_bid_price == 0 or best_ask_price == 0:
                logger.warning(f"Invalid bid/ask prices for {symbol}")
                return None
            
            # Calculate spread in basis points
            spread = best_ask_price - best_bid_price
            spread_bp = (spread / best_bid_price) * 10000
            
            # Calculate volume at best bid/ask (first level)
            best_bid_vol = bids[0][1] if len(bids[0]) > 1 else 0.0
            best_ask_vol = asks[0][1] if len(asks[0]) > 1 else 0.0
            
            # Calculate bid/ask volume ratio
            if best_ask_vol > 0:
                bid_ask_vol_ratio = best_bid_vol / best_ask_vol
            else:
                bid_ask_vol_ratio = 10.0 if best_bid_vol > 0 else 1.0  # Default if ask vol is 0
            
            # Calculate order book imbalance
            # Sum volume on bid side (top 5 levels)
            bid_vol_sum = sum(bid[1] for bid in bids[:5] if len(bid) > 1)
            # Sum volume on ask side (top 5 levels)
            ask_vol_sum = sum(ask[1] for ask in asks[:5] if len(ask) > 1)
            
            total_vol = bid_vol_sum + ask_vol_sum
            if total_vol > 0:
                order_book_imbalance = (bid_vol_sum - ask_vol_sum) / total_vol
            else:
                order_book_imbalance = 0.0  # Neutral if no volume
            
            # Clamp imbalance to -1 to +1
            order_book_imbalance = max(-1.0, min(1.0, order_book_imbalance))
            
            tier2_data = Tier2Data(
                order_book_imbalance=order_book_imbalance,
                spread_bp=spread_bp,
                bid_ask_vol_ratio=bid_ask_vol_ratio,
                best_bid_price=best_bid_price,
                best_ask_price=best_ask_price,
                best_bid_vol=best_bid_vol,
                best_ask_vol=best_ask_vol,
            )
            
            # Cache the result
            self._cache[cache_key] = tier2_data
            self._cache_timestamps[cache_key] = current_time
            
            logger.debug(
                f"Order book metrics for {symbol}: "
                f"imbalance={order_book_imbalance:.3f}, "
                f"spread={spread_bp:.2f}bp, "
                f"bid/ask_ratio={bid_ask_vol_ratio:.2f}"
            )
            
            return tier2_data
            
        except Exception as e:
            # Order book fetching can fail in demo mode or due to API limitations
            # This is expected and doesn't affect core trading functionality
            # Only log at DEBUG level to avoid cluttering logs
            logger.debug(f"Failed to fetch order book for {symbol}: {e}")
            return None
    
    def clear_cache(self):
        """Clear order book cache (useful for testing)."""
        self._cache.clear()
        self._cache_timestamps.clear()

