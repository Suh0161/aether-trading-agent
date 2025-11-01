"""Data acquisition layer for fetching market data from exchanges."""

import ccxt
import logging
import pandas as pd
from typing import Optional, Dict, List
from src.config import Config
from src.models import MarketSnapshot


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
        self.exchange = self._init_exchange(config)
        self._cached_snapshot: Optional[MarketSnapshot] = None
    
    def _init_exchange(self, config: Config) -> ccxt.Exchange:
        """
        Initialize ccxt exchange client with proper configuration.
        
        Args:
            config: Configuration object
            
        Returns:
            Configured ccxt exchange instance
        """
        exchange_type = config.exchange_type.lower()
        
        # Map exchange types to ccxt classes
        if exchange_type == "binance_testnet":
            exchange = ccxt.binance({
                'apiKey': config.exchange_api_key,
                'secret': config.exchange_api_secret,
                'enableRateLimit': True,
            })
            # Override API URL for testnet
            exchange.set_sandbox_mode(True)
        elif exchange_type == "binance":
            exchange = ccxt.binance({
                'apiKey': config.exchange_api_key,
                'secret': config.exchange_api_secret,
                'enableRateLimit': True,
            })
        elif exchange_type == "hyperliquid":
            # Placeholder for future Hyperliquid support
            raise NotImplementedError("Hyperliquid exchange not yet implemented")
        else:
            raise ValueError(f"Unsupported exchange type: {exchange_type}")
        
        return exchange
    
    def _compute_indicators(self, ohlcv: List[List[float]]) -> Dict[str, float]:
        """
        Compute technical indicators from OHLCV data.
        
        Args:
            ohlcv: List of OHLCV candles [[timestamp, open, high, low, close, volume], ...]
            
        Returns:
            Dictionary of indicator values
        """
        try:
            # Convert OHLCV to pandas DataFrame
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Compute EMA(20) and EMA(50)
            ema_20 = df['close'].ewm(span=20, adjust=False).mean()
            ema_50 = df['close'].ewm(span=50, adjust=False).mean()
            
            # Compute RSI(14) manually
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi_14 = 100 - (100 / (1 + rs))
            
            # Compute ATR(14) - Average True Range
            high_low = df['high'] - df['low']
            high_close = (df['high'] - df['close'].shift()).abs()
            low_close = (df['low'] - df['close'].shift()).abs()
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr_14 = true_range.rolling(window=14).mean()
            
            # Compute Keltner Channels (EMA20 ± ATR*1.5)
            atr_multiplier = 1.5
            keltner_upper = ema_20 + (atr_14 * atr_multiplier)
            keltner_lower = ema_20 - (atr_14 * atr_multiplier)
            
            indicators = {
                'ema_20': float(ema_20.iloc[-1]),
                'ema_50': float(ema_50.iloc[-1]),
                'rsi_14': float(rsi_14.iloc[-1]),
                'atr_14': float(atr_14.iloc[-1]),
                'keltner_upper': float(keltner_upper.iloc[-1]),
                'keltner_lower': float(keltner_lower.iloc[-1])
            }
            
            logger.debug(f"Computed indicators: {indicators}")
            
            return indicators
            
        except Exception as e:
            logger.error(f"Failed to compute indicators: {e}")
            # Return empty indicators on failure
            return {}
    
    def fetch_market_snapshot(self, symbol: str) -> MarketSnapshot:
        """
        Fetch ticker, OHLCV data and return normalized snapshot.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")
            
        Returns:
            MarketSnapshot with current market data
        """
        try:
            # Fetch ticker data
            ticker = self.exchange.fetch_ticker(symbol)
            
            # Fetch OHLCV data (at least 50 candles for indicators)
            # Using 1h timeframe, fetch 60 candles to have buffer
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='1h', limit=60)
            
            # Compute technical indicators
            indicators = self._compute_indicators(ohlcv)
            
            # Create market snapshot with indicators
            snapshot = MarketSnapshot(
                timestamp=ticker['timestamp'],
                symbol=symbol,
                price=ticker['last'],
                bid=ticker['bid'],
                ask=ticker['ask'],
                ohlcv=ohlcv,
                indicators=indicators
            )
            
            # Cache the snapshot for error recovery
            self._cached_snapshot = snapshot
            
            logger.info(f"Fetched market snapshot for {symbol}: price={snapshot.price}")
            
            return snapshot
            
        except Exception as e:
            logger.error(f"Failed to fetch market data for {symbol}: {e}")
            
            # Return cached snapshot if available
            if self._cached_snapshot is not None:
                logger.warning(f"Returning cached snapshot for {symbol}")
                return self._cached_snapshot
            
            # If no cache available, re-raise the exception
            raise
