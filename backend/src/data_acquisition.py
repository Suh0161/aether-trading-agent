"""Data acquisition layer for fetching market data from exchanges."""

import ccxt
import logging
import pandas as pd
import time
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
            
            # Get current price for ATR validation
            current_price = df['close'].iloc[-1]
            current_atr = atr_14.iloc[-1]
            
            # Cap ATR to reasonable maximum (5% of price) to prevent extreme Keltner bands
            # This prevents unrealistic bands during high volatility or data issues
            max_atr_percentage = 0.05  # 5% of price
            max_allowed_atr = current_price * max_atr_percentage
            capped_atr = min(current_atr, max_allowed_atr) if pd.notna(current_atr) else max_allowed_atr
            
            # Compute Keltner Channels (EMA20 ± capped_ATR*1.5)
            atr_multiplier = 1.5
            current_ema_20 = ema_20.iloc[-1]
            
            # Use capped ATR for more reasonable bands
            keltner_upper = current_ema_20 + (capped_atr * atr_multiplier)
            keltner_lower = current_ema_20 - (capped_atr * atr_multiplier)
            
            # Log if ATR was capped (for debugging)
            if pd.notna(current_atr) and current_atr > max_allowed_atr:
                logger.warning(f"ATR capped: raw ATR=${current_atr:.2f} ({current_atr/current_price*100:.2f}%), capped to ${capped_atr:.2f} ({max_atr_percentage*100}%)")
            
            # Compute VWAP (Volume Weighted Average Price)
            # VWAP = Cumulative(Typical Price × Volume) / Cumulative(Volume)
            # Typical Price = (High + Low + Close) / 3
            df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
            df['tp_volume'] = df['typical_price'] * df['volume']
            
            # Calculate cumulative sums for VWAP
            cumulative_tp_volume = df['tp_volume'].cumsum()
            cumulative_volume = df['volume'].cumsum()
            
            # VWAP calculation (avoid division by zero)
            vwap = cumulative_tp_volume / cumulative_volume
            current_vwap = float(vwap.iloc[-1]) if cumulative_volume.iloc[-1] > 0 else current_price
            
            # Compute Pivot Points (Classic Daily Pivots)
            # Use recent candles to calculate pivot levels
            # Use the previous completed candle for pivot calculation (standard approach)
            # This prevents using stale/extreme values from old spikes
            if len(df) >= 2:
                recent_high = float(df['high'].iloc[-2])
                recent_low = float(df['low'].iloc[-2])
                recent_close = float(df['close'].iloc[-2])
            else:
                # Fallback if not enough data
                recent_high = float(df['high'].iloc[-1])
                recent_low = float(df['low'].iloc[-1])
                recent_close = float(df['close'].iloc[-1])
            
            pivot = (recent_high + recent_low + recent_close) / 3
            resistance_1 = (2 * pivot) - recent_low
            support_1 = (2 * pivot) - recent_high
            resistance_2 = pivot + (recent_high - recent_low)
            support_2 = pivot - (recent_high - recent_low)
            resistance_3 = recent_high + 2 * (pivot - recent_low)
            support_3 = recent_low - 2 * (recent_high - pivot)
            
            # Detect Swing Highs and Lows (recent support/resistance zones)
            # Look back 50 candles for significant swing points
            lookback = min(50, len(df))
            swing_highs = []
            swing_lows = []
            
            for i in range(lookback - 5, lookback):
                if i >= 2 and i < len(df) - 2:
                    # Swing high: higher than 2 candles on each side
                    if (df['high'].iloc[i] > df['high'].iloc[i-1] and 
                        df['high'].iloc[i] > df['high'].iloc[i-2] and
                        df['high'].iloc[i] > df['high'].iloc[i+1] and
                        df['high'].iloc[i] > df['high'].iloc[i+2]):
                        swing_highs.append(float(df['high'].iloc[i]))
                    
                    # Swing low: lower than 2 candles on each side
                    if (df['low'].iloc[i] < df['low'].iloc[i-1] and 
                        df['low'].iloc[i] < df['low'].iloc[i-2] and
                        df['low'].iloc[i] < df['low'].iloc[i+1] and
                        df['low'].iloc[i] < df['low'].iloc[i+2]):
                        swing_lows.append(float(df['low'].iloc[i]))
            
            # Get most recent swing high/low (closest to current price)
            nearest_swing_high = max(swing_highs) if swing_highs else recent_high
            nearest_swing_low = min(swing_lows) if swing_lows else recent_low
            
            # ========== VOLUME ANALYSIS ==========
            # Calculate volume metrics for confirmation
            current_volume = float(df['volume'].iloc[-1])
            avg_volume_20 = float(df['volume'].rolling(window=20).mean().iloc[-1])
            avg_volume_50 = float(df['volume'].rolling(window=50).mean().iloc[-1])
            
            # Volume spike detection (current volume vs average)
            volume_ratio_20 = current_volume / avg_volume_20 if avg_volume_20 > 0 else 1.0
            volume_ratio_50 = current_volume / avg_volume_50 if avg_volume_50 > 0 else 1.0
            
            # Volume trend (is volume increasing or decreasing?)
            # Compare last 5 candles average vs previous 5 candles average
            if len(df) >= 10:
                recent_volume_avg = float(df['volume'].iloc[-5:].mean())
                previous_volume_avg = float(df['volume'].iloc[-10:-5].mean())
                volume_trend = "increasing" if recent_volume_avg > previous_volume_avg * 1.1 else \
                              "decreasing" if recent_volume_avg < previous_volume_avg * 0.9 else \
                              "stable"
            else:
                volume_trend = "stable"
            
            # On-Balance Volume (OBV) - cumulative volume indicator
            # OBV increases on up days, decreases on down days
            obv = 0.0
            for i in range(1, len(df)):
                if df['close'].iloc[i] > df['close'].iloc[i-1]:
                    obv += df['volume'].iloc[i]
                elif df['close'].iloc[i] < df['close'].iloc[i-1]:
                    obv -= df['volume'].iloc[i]
            
            # OBV trend (is money flowing in or out?)
            obv_sma_10 = 0.0
            if len(df) >= 10:
                obv_values = []
                temp_obv = 0.0
                for i in range(1, len(df)):
                    if df['close'].iloc[i] > df['close'].iloc[i-1]:
                        temp_obv += df['volume'].iloc[i]
                    elif df['close'].iloc[i] < df['close'].iloc[i-1]:
                        temp_obv -= df['volume'].iloc[i]
                    obv_values.append(temp_obv)
                
                if len(obv_values) >= 10:
                    obv_sma_10 = sum(obv_values[-10:]) / 10
            
            obv_trend = "bullish" if obv > obv_sma_10 else "bearish" if obv < obv_sma_10 else "neutral"
            
            indicators = {
                'ema_20': float(current_ema_20),
                'ema_50': float(ema_50.iloc[-1]),
                'rsi_14': float(rsi_14.iloc[-1]),
                'atr_14': float(capped_atr),  # Use capped ATR value
                'keltner_upper': float(keltner_upper),
                'keltner_lower': float(keltner_lower),
                'vwap': current_vwap,  # VWAP for intraday scalping
                
                # Pivot Points (Support/Resistance levels)
                'pivot': float(pivot),
                'resistance_1': float(resistance_1),
                'resistance_2': float(resistance_2),
                'resistance_3': float(resistance_3),
                'support_1': float(support_1),
                'support_2': float(support_2),
                'support_3': float(support_3),
                
                # Swing High/Low (Recent price action S/R)
                'swing_high': float(nearest_swing_high),
                'swing_low': float(nearest_swing_low),
                
                # Volume Analysis (NEW - for breakout confirmation)
                'current_volume': current_volume,
                'avg_volume_20': avg_volume_20,
                'avg_volume_50': avg_volume_50,
                'volume_ratio_20': volume_ratio_20,  # Current vol / 20-period avg
                'volume_ratio_50': volume_ratio_50,  # Current vol / 50-period avg
                'volume_trend': volume_trend,  # "increasing", "decreasing", "stable"
                'obv': obv,  # On-Balance Volume
                'obv_trend': obv_trend,  # "bullish", "bearish", "neutral"
            }
            
            logger.debug(f"Computed indicators: {indicators}")
            
            return indicators
            
        except Exception as e:
            logger.error(f"Failed to compute indicators: {e}")
            # Return empty indicators on failure
            return {}
    
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
            # Fetch ticker data
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            # Fetch multi-timeframe OHLCV data
            # Higher timeframes for trend (daily/4h) - cached and updated less frequently
            # Lower timeframes (1h/15m) - fetched every cycle for precise entries
            
            current_time = time.time()
            
            # 1. Daily timeframe - for major trend (200 candles = ~7 months)
            # Update only every hour (cache TTL)
            if (not self._cached_indicators_1d or 
                (current_time - self._cache_timestamp_1d) > self._cache_ttl_1d):
                ohlcv_1d = self.exchange.fetch_ohlcv(symbol, timeframe='1d', limit=200)
                indicators_1d = self._compute_indicators(ohlcv_1d)
                self._cached_indicators_1d = indicators_1d
                self._cache_timestamp_1d = current_time
                logger.debug("Updated daily timeframe cache")
            else:
                indicators_1d = self._cached_indicators_1d
                logger.debug("Using cached daily timeframe")
            
            # 2. 4-hour timeframe - for medium-term trend (300 candles = ~50 days)
            # Update every 15 minutes (cache TTL)
            if (not self._cached_indicators_4h or 
                (current_time - self._cache_timestamp_4h) > self._cache_ttl_4h):
                ohlcv_4h = self.exchange.fetch_ohlcv(symbol, timeframe='4h', limit=300)
                indicators_4h = self._compute_indicators(ohlcv_4h)
                self._cached_indicators_4h = indicators_4h
                self._cache_timestamp_4h = current_time
                logger.debug("Updated 4h timeframe cache")
            else:
                indicators_4h = self._cached_indicators_4h
                logger.debug("Using cached 4h timeframe")
            
            # 3. 1-hour timeframe - for short-term trend (500 candles = ~21 days)
            # Always fetch fresh (main analysis timeframe)
            ohlcv_1h = self.exchange.fetch_ohlcv(symbol, timeframe='1h', limit=500)
            indicators_1h = self._compute_indicators(ohlcv_1h)
            
            # 4. 15-minute timeframe - for entry timing (200 candles = ~2 days)
            # Always fetch fresh (precise entry signals)
            ohlcv_15m = self.exchange.fetch_ohlcv(symbol, timeframe='15m', limit=200)
            indicators_15m = self._compute_indicators(ohlcv_15m)
            
            # 5. 5-minute timeframe - for scalping fallback (200 candles = ~17 hours)
            # Cached with short TTL (1 minute)
            if (not self._cached_indicators_5m or 
                (current_time - self._cache_timestamp_5m) > self._cache_ttl_5m):
                ohlcv_5m = self.exchange.fetch_ohlcv(symbol, timeframe='5m', limit=200)
                indicators_5m = self._compute_indicators(ohlcv_5m)
                self._cached_indicators_5m = indicators_5m
                self._cache_timestamp_5m = current_time
                logger.debug("Updated 5m timeframe cache")
            else:
                indicators_5m = self._cached_indicators_5m
                logger.debug("Using cached 5m timeframe")
            
            # 6. 1-minute timeframe - for scalping entry timing (200 candles = ~3 hours)
            # Cached with very short TTL (30 seconds)
            if (not self._cached_indicators_1m or 
                (current_time - self._cache_timestamp_1m) > self._cache_ttl_1m):
                ohlcv_1m = self.exchange.fetch_ohlcv(symbol, timeframe='1m', limit=200)
                indicators_1m = self._compute_indicators(ohlcv_1m)
                self._cached_indicators_1m = indicators_1m
                self._cache_timestamp_1m = current_time
                logger.debug("Updated 1m timeframe cache")
            else:
                indicators_1m = self._cached_indicators_1m
                logger.debug("Using cached 1m timeframe")
            
            # Combine indicators with timeframe prefix
            # Primary indicators come from 1h (main analysis)
            # Add higher/lower TF context
            combined_indicators = {
                # Primary (1h) - main analysis timeframe
                'ema_20': indicators_1h.get('ema_20', 0),
                'ema_50': indicators_1h.get('ema_50', 0),
                'rsi_14': indicators_1h.get('rsi_14', 50),
                'atr_14': indicators_1h.get('atr_14', 0),
                'keltner_upper': indicators_1h.get('keltner_upper', 0),
                'keltner_lower': indicators_1h.get('keltner_lower', 0),
                
                # Daily timeframe - major trend
                'ema_20_1d': indicators_1d.get('ema_20', 0),
                'ema_50_1d': indicators_1d.get('ema_50', 0),
                'trend_1d': 'bullish' if current_price > indicators_1d.get('ema_50', 0) else 'bearish',
                
                # 4h timeframe - medium-term trend
                'ema_20_4h': indicators_4h.get('ema_20', 0),
                'ema_50_4h': indicators_4h.get('ema_50', 0),
                'rsi_14_4h': indicators_4h.get('rsi_14', 50),
                'trend_4h': 'bullish' if current_price > indicators_4h.get('ema_50', 0) else 'bearish',
                
                # 15m timeframe - entry timing
                'ema_20_15m': indicators_15m.get('ema_20', 0),
                'ema_50_15m': indicators_15m.get('ema_50', 0),
                'keltner_upper_15m': indicators_15m.get('keltner_upper', 0),
                'keltner_lower_15m': indicators_15m.get('keltner_lower', 0),
                'rsi_14_15m': indicators_15m.get('rsi_14', 50),
                'trend_15m': 'bullish' if current_price > indicators_15m.get('ema_50', 0) else 'bearish',
                
                # 5m timeframe - scalping analysis
                'ema_20_5m': indicators_5m.get('ema_20', 0),
                'ema_50_5m': indicators_5m.get('ema_50', 0),
                'keltner_upper_5m': indicators_5m.get('keltner_upper', 0),
                'keltner_lower_5m': indicators_5m.get('keltner_lower', 0),
                'rsi_14_5m': indicators_5m.get('rsi_14', 50),
                'trend_5m': 'bullish' if current_price > indicators_5m.get('ema_50', 0) else 'bearish',
                
                # 1m timeframe - scalping entry timing
                'ema_20_1m': indicators_1m.get('ema_20', 0),
                'ema_50_1m': indicators_1m.get('ema_50', 0),
                'keltner_upper_1m': indicators_1m.get('keltner_upper', 0),
                'keltner_lower_1m': indicators_1m.get('keltner_lower', 0),
                'rsi_14_1m': indicators_1m.get('rsi_14', 50),
                'trend_1m': 'bullish' if current_price > indicators_1m.get('ema_50', 0) else 'bearish',
                
                # VWAP for intraday scalping (volume-weighted average price)
                'vwap_1h': indicators_1h.get('vwap', current_price),
                'vwap_15m': indicators_15m.get('vwap', current_price),
                'vwap_5m': indicators_5m.get('vwap', current_price),
                'vwap_1m': indicators_1m.get('vwap', current_price),
                
                # Support/Resistance Levels (from 1h timeframe - main analysis)
                'pivot': indicators_1h.get('pivot', current_price),
                'resistance_1': indicators_1h.get('resistance_1', current_price),
                'resistance_2': indicators_1h.get('resistance_2', current_price),
                'resistance_3': indicators_1h.get('resistance_3', current_price),
                'support_1': indicators_1h.get('support_1', current_price),
                'support_2': indicators_1h.get('support_2', current_price),
                'support_3': indicators_1h.get('support_3', current_price),
                'swing_high': indicators_1h.get('swing_high', current_price),
                'swing_low': indicators_1h.get('swing_low', current_price),
                
                # Volume Analysis (NEW - for breakout confirmation)
                # Use 1h volume as primary, with 5m/1m for scalping
                'volume_1h': indicators_1h.get('current_volume', 0),
                'avg_volume_20_1h': indicators_1h.get('avg_volume_20', 0),
                'volume_ratio_1h': indicators_1h.get('volume_ratio_20', 1.0),
                'volume_trend_1h': indicators_1h.get('volume_trend', 'stable'),
                'obv_trend_1h': indicators_1h.get('obv_trend', 'neutral'),
                
                'volume_5m': indicators_5m.get('current_volume', 0),
                'avg_volume_20_5m': indicators_5m.get('avg_volume_20', 0),
                'volume_ratio_5m': indicators_5m.get('volume_ratio_20', 1.0),
                'volume_trend_5m': indicators_5m.get('volume_trend', 'stable'),
                'obv_trend_5m': indicators_5m.get('obv_trend', 'neutral'),
                
                'volume_1m': indicators_1m.get('current_volume', 0),
                'avg_volume_20_1m': indicators_1m.get('avg_volume_20', 0),
                'volume_ratio_1m': indicators_1m.get('volume_ratio_20', 1.0),
                'volume_trend_1m': indicators_1m.get('volume_trend', 'stable'),
                'obv_trend_1m': indicators_1m.get('obv_trend', 'neutral'),
            }
            
            # Create market snapshot with multi-timeframe indicators
            # Use 1h OHLCV as primary (for backwards compatibility)
            snapshot = MarketSnapshot(
                timestamp=ticker['timestamp'],
                symbol=symbol,
                price=current_price,
                bid=ticker['bid'],
                ask=ticker['ask'],
                ohlcv=ohlcv_1h,  # Primary OHLCV for backwards compatibility
                indicators=combined_indicators
            )
            
            # Cache the snapshot for error recovery
            self._cached_snapshot = snapshot
            
            logger.info(f"Fetched multi-timeframe snapshot for {symbol}: price={snapshot.price}")
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
