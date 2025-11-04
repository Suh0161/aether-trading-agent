"""Market data fetching logic for ticker and OHLCV data."""

import logging
import time
from typing import Dict, List

logger = logging.getLogger(__name__)


class MarketDataFetcher:
    """Handles fetching of ticker and OHLCV market data."""

    def __init__(self, exchange_adapter, config):
        """
        Initialize market data fetcher.

        Args:
            exchange_adapter: Exchange adapter for API calls
            config: Configuration object
        """
        self.exchange_adapter = exchange_adapter
        self.config = config

    def fetch_ticker_data(self, symbol: str) -> Dict:
        """
        Fetch ticker data from exchange.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")

        Returns:
            Dictionary with ticker data
        """
        # For demo trading, use Futures-specific ticker endpoint
        if self.config.exchange_type.lower() == "binance_demo":
            # Use Futures public ticker endpoints (works on demo-fapi.binance.com)
            # For futures, use Mark Price (same as Binance UI) instead of Last Price
            # Mark Price is used for P&L calculations and is more accurate
            sym = symbol.replace('/', '')

            # Try to get Mark Price first (more accurate for futures)
            try:
                # Use premiumIndex endpoint for Mark Price
                premium_index = self.exchange_adapter.exchange.fapiPublicGetPremiumIndex({'symbol': sym})
                current_price = float(premium_index.get('markPrice', 0))
                if current_price > 0:
                    logger.debug(f"Using Mark Price for {symbol}: ${current_price:.2f}")
            except Exception as e:
                logger.debug(f"Mark Price not available for {symbol}, falling back to Last Price: {e}")
                # Fallback to Last Price if Mark Price fails
                try:
                    ticker_price = self.exchange_adapter.exchange.fapiPublicGetTickerPrice({'symbol': sym})
                    current_price = float(ticker_price['price'])
                except Exception as e2:
                    logger.warning(f"Failed to fetch price for {symbol}: {e2}")
                    current_price = 0.0

            # Get bid/ask from book ticker
            try:
                book_ticker = self.exchange_adapter.exchange.fapiPublicGetTickerBookTicker({'symbol': sym})
                bid = float(book_ticker.get('bidPrice', current_price))
                ask = float(book_ticker.get('askPrice', current_price))
            except:
                bid = current_price
                ask = current_price

            ticker = {
                'last': current_price,
                'bid': bid,
                'ask': ask,
                'high': current_price,  # Demo doesn't provide 24h stats
                'low': current_price,
                'volume': 0.0,
                'timestamp': int(time.time() * 1000),
            }
        else:
            ticker = self.exchange_adapter.exchange.fetch_ticker(symbol)
            current_price = ticker['last']

        return ticker

    def fetch_ohlcv_data(self, symbol: str, timeframe: str, limit: int) -> List[List[float]]:
        """
        Fetch OHLCV data from exchange.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")
            timeframe: Timeframe string (e.g., "1d", "1h", "15m")
            limit: Number of candles to fetch

        Returns:
            List of OHLCV candles in ccxt format [[timestamp, open, high, low, close, volume], ...]
        """
        if self.config.exchange_type.lower() == "binance_demo":
            return self.exchange_adapter.fetch_futures_klines(symbol, timeframe, limit)
        else:
            return self.exchange_adapter.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
