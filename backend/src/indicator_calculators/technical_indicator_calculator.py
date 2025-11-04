"""Technical indicator calculations from OHLCV data."""

import logging
from typing import Dict, List
import pandas as pd

logger = logging.getLogger(__name__)


class TechnicalIndicatorCalculator:
    """Calculates technical indicators from OHLCV data."""

    def compute_indicators(self, ohlcv: List[List[float]]) -> Dict[str, float]:
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
                logger.warning(f"ATR capped: raw ATR=${current_atr:.2f} ({current_atr/current_price*100:.2f}%), capped to ${capped_atr:.2f} ({max_atr_percentage*100:.2f}%)")

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
