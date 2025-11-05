"""Scalping strategy for quick trades."""

import logging
import time as time_module
from typing import Any, Optional

from src.indicators.technical_indicators import (
    check_support_resistance_levels,
    get_scalp_trend_bias,
    check_volatility_filter,
    check_breakout_conditions,
    check_near_band_conditions
)
from src.strategy_utils.confidence_calculators import calculate_scalp_confidence, get_volume_description
from src.strategy_utils.position_sizing import (
    calculate_position_size,
    calculate_leverage,
    calculate_dynamic_scalp_sl_tp
)
from src.strategy import StrategySignal

logger = logging.getLogger(__name__)


class ScalpingStrategy:
    """
    Scalping strategy for quick trades when no swing setup is available.

    Rules (Updated to account for Binance fees):
    1. Entry: Price momentum on 15m/5m/1m timeframes (multi-timeframe scalping)
    2. Stop: 0.3% of price (increased from 0.2% to allow for normal wiggles)
    3. Target: 0.5% profit (increased from 0.3% to give ~0.4% after fees)
    4. Hold time: 10 minutes max (increased from 5 min to allow moves to develop)
    5. Exit: Less sensitive - only exit on strong reversal (not just VWAP cross)
    6. Volatility filter: Only scalp when 5m ATR/price >= 0.15% (prevents low-vol scratches)
    
    Timeframes: 15M → 5M → 1M (15m for bias, 5m for signal, 1m for entry timing)
    """

    def __init__(self, profit_target_pct: float = 0.005, stop_loss_pct: float = 0.003):
        """
        Initialize scalping strategy.

        Args:
            profit_target_pct: Target profit as percentage of price (default 0.5%)
            stop_loss_pct: Stop loss as percentage of price (default 0.3%)

        Note: Updated to account for Binance fees (~0.1% round trip).
        - TP 0.5% gives ~0.4% after fees (better margin above fees)
        - SL 0.3% provides room for normal market wiggles
        """
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct = stop_loss_pct
        self.max_hold_seconds = 600  # 10 minutes max (increased from 5 min)

    def analyze(self, snapshot: Any, position_size: float, equity: float, suppress_logs: bool = False) -> StrategySignal:
        """
        Analyze market using 15m/5m/1m timeframes for quick scalping opportunities.
        
        Multi-timeframe scalping approach:
        - 15m: Trend bias confirmation
        - 5m: Signal generation (VWAP, trend, volume)
        - 1m: Precise entry timing

        Args:
            snapshot: Market snapshot with price and multi-timeframe indicators
            position_size: Current position size
            equity: Account equity

        Returns:
            StrategySignal with action and parameters
        """
        price = snapshot.price
        indicators = snapshot.indicators

        # Calculate available cash
        position_value = position_size * price if position_size > 0 else 0.0
        available_cash = equity - position_value

        # VOLATILITY FILTER: Only scalp in high volatility (prevents death by a thousand scratches)
        if not check_volatility_filter(indicators, price):
            # Use 5m timeframe ATR (atr_14_5m) for scalping, fallback to 1h ATR (atr_14) if not available
            atr_5m = indicators.get("atr_14_5m", indicators.get("atr_14", 0.0))
            price_for_calc = indicators.get("price", price)
            atr_to_price_ratio = atr_5m / price_for_calc if price_for_calc > 0 else 0
            min_vol_threshold = 0.03
            comparison = "<" if atr_to_price_ratio * 100 < min_vol_threshold else ">="
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=f"Scalp: Low volatility (5m ATR/price={atr_to_price_ratio*100:.2f}% {comparison} {min_vol_threshold}%), waiting for higher volatility",
                confidence=0.0,
                symbol=snapshot.symbol,
                position_type="scalp"
            )

        # Check higher timeframe bias to avoid scalping against strong trends
        strong_htf_up = indicators.get("trend_4h") == "bullish" or indicators.get("trend_1h") == "bullish"
        strong_htf_down = indicators.get("trend_4h") == "bearish" or indicators.get("trend_1h") == "bearish"

        # Extract timeframe indicators
        trend_5m = indicators.get("trend_5m", "bearish")
        trend_1m = indicators.get("trend_1m", "bearish")
        vwap_5m = indicators.get("vwap_5m", price)

        # If we have a LONG position, check exit conditions
        if position_size > 0:
            # Check "no move" exit logic
            exit_signal = self._check_long_exit_conditions(snapshot, indicators, price, position_size)
            if exit_signal:
                return exit_signal

            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=f"In scalp long, trend intact",
                confidence=0.6,
                symbol=snapshot.symbol,
                position_type="scalp"
            )

        # If we have a SHORT position, check exit conditions
        elif position_size < 0:
            # Check "no move" exit logic
            exit_signal = self._check_short_exit_conditions(snapshot, indicators, price, position_size)
            if exit_signal:
                return exit_signal

            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=f"In scalp short, downtrend intact",
                confidence=0.6,
                symbol=snapshot.symbol,
                position_type="scalp"
            )

        # No position - look for LONG or SHORT scalping entry

        # Check support/resistance levels first (Priority 1)
        near_support, near_resistance, sr_level = check_support_resistance_levels(indicators, price)

        # PRIORITY 1: S/R Logic for Scalping
        if near_support:
            bias_aligned, bias_desc = get_scalp_trend_bias(indicators, "long")
            if bias_aligned and trend_5m == "bullish" and price > vwap_5m:
                return self._handle_scalp_long_at_support(snapshot, indicators, price, equity, available_cash, suppress_logs=suppress_logs)

        if near_resistance:
            bias_aligned, bias_desc = get_scalp_trend_bias(indicators, "short")
            if bias_aligned and trend_5m == "bearish" and price < vwap_5m:
                return self._handle_scalp_short_at_resistance(snapshot, indicators, price, equity, available_cash, suppress_logs=suppress_logs)

        # PRIORITY 2: Keltner Band Logic for Scalping
        # Check for long scalp entry
        if trend_5m == "bullish" and price > vwap_5m and not strong_htf_down:
            bias_aligned, _ = get_scalp_trend_bias(indicators, "long")
            if bias_aligned:
                entry_signal = self._check_long_scalp_entry(snapshot, indicators, price, equity, available_cash)
                if entry_signal:
                    return entry_signal

        # Check for short scalp entry
        if trend_5m == "bearish" and price < vwap_5m and not strong_htf_up:
            bias_aligned, _ = get_scalp_trend_bias(indicators, "short")
            if bias_aligned:
                entry_signal = self._check_short_scalp_entry(snapshot, indicators, price, equity, available_cash)
                if entry_signal:
                    return entry_signal

        # No clear scalp setup
        return StrategySignal(
            action="hold",
            size_pct=0.0,
            reason=f"Scalp: Waiting for entry (5m trend={trend_5m}, no breakout yet)",
            confidence=0.0,
            symbol=snapshot.symbol,
            position_type="scalp"
        )

    def _check_long_exit_conditions(self, snapshot: Any, indicators: dict, price: float, position_size: float) -> Optional[StrategySignal]:
        """Check exit conditions for long scalp positions."""
        # "No move" exit - if held > 5 minutes AND profit < 0.3%, exit
        entry_timestamp = getattr(snapshot, 'entry_timestamp', None)
        if entry_timestamp is None:
            entry_timestamp = indicators.get('position_entry_timestamp', None)

        if entry_timestamp:
            current_timestamp = snapshot.timestamp if hasattr(snapshot, 'timestamp') else int(time_module.time())

            if isinstance(entry_timestamp, (int, float)) and entry_timestamp > 0:
                time_held_seconds = current_timestamp - entry_timestamp
                entry_price = indicators.get('position_entry_price', price)

                if entry_price > 0:
                    profit_pct = ((price - entry_price) / entry_price) * 100
                    min_hold_seconds = 300  # 5 minutes
                    min_profit_threshold_pct = 0.3

                    # Exit if time held is reasonable AND profit is below threshold
                    if 0 <= time_held_seconds <= 3600 and time_held_seconds >= min_hold_seconds and profit_pct < min_profit_threshold_pct:
                        return StrategySignal(
                            action="close",
                            size_pct=1.0,
                            reason=f"Scalp long exit: No move after {time_held_seconds/60:.1f}min (profit {profit_pct:.2f}% < {min_profit_threshold_pct}% threshold)",
                            confidence=0.7,
                            position_type="scalp",
                            symbol=snapshot.symbol
                        )

        # Strong reversal exit
        vwap_5m = indicators.get("vwap_5m", price)
        trend_5m = indicators.get("trend_5m", "bearish")
        trend_1m = indicators.get("trend_1m", "bearish")

        price_below_vwap_significant = price < (vwap_5m * 0.998)  # At least 0.2% below VWAP
        strong_reversal = (trend_5m == "bearish" and trend_1m == "bearish") and price_below_vwap_significant

        if strong_reversal:
            return StrategySignal(
                action="close",
                size_pct=1.0,
                reason=f"Scalp long exit: Strong reversal signal (5m={trend_5m}, 1m={trend_1m}, price ${price:.2f} below VWAP ${vwap_5m:.2f})",
                confidence=0.8,
                position_type="scalp",
                symbol=snapshot.symbol
            )

        return None

    def _check_short_exit_conditions(self, snapshot: Any, indicators: dict, price: float, position_size: float) -> Optional[StrategySignal]:
        """Check exit conditions for short scalp positions."""
        # "No move" exit - if held > 5 minutes AND profit < 0.3%, exit
        entry_timestamp = getattr(snapshot, 'entry_timestamp', None)
        if entry_timestamp is None:
            entry_timestamp = indicators.get('position_entry_timestamp', None)

        if entry_timestamp:
            current_timestamp = snapshot.timestamp if hasattr(snapshot, 'timestamp') else int(time_module.time())

            if isinstance(entry_timestamp, (int, float)) and entry_timestamp > 0:
                time_held_seconds = current_timestamp - entry_timestamp
                entry_price = indicators.get('position_entry_price', price)

                if entry_price > 0:
                    profit_pct = ((entry_price - price) / entry_price) * 100  # For short: profit = entry - current
                    min_hold_seconds = 300  # 5 minutes
                    min_profit_threshold_pct = 0.3

                    # Exit if time held is reasonable AND profit is below threshold
                    if 0 <= time_held_seconds <= 3600 and time_held_seconds >= min_hold_seconds and profit_pct < min_profit_threshold_pct:
                        return StrategySignal(
                            action="close",
                            size_pct=1.0,
                            reason=f"Scalp short exit: No move after {time_held_seconds/60:.1f}min (profit {profit_pct:.2f}% < {min_profit_threshold_pct}% threshold)",
                            confidence=0.7,
                            position_type="scalp",
                            symbol=snapshot.symbol
                        )

        # Strong reversal exit
        vwap_5m = indicators.get("vwap_5m", price)
        trend_5m = indicators.get("trend_5m", "bearish")
        trend_1m = indicators.get("trend_1m", "bearish")

        price_above_vwap_significant = price > (vwap_5m * 1.002)  # At least 0.2% above VWAP
        strong_reversal = (trend_5m == "bullish" and trend_1m == "bullish") and price_above_vwap_significant

        if strong_reversal:
            return StrategySignal(
                action="close",
                size_pct=1.0,
                reason=f"Scalp short exit: Strong reversal signal (5m={trend_5m}, 1m={trend_1m}, price ${price:.2f} above VWAP ${vwap_5m:.2f})",
                confidence=0.8,
                position_type="scalp",
                symbol=snapshot.symbol
            )

        return None

    def _handle_scalp_long_at_support(self, snapshot: Any, indicators: dict, price: float,
                                     equity: float, available_cash: float, suppress_logs: bool = False) -> StrategySignal:
        """Handle LONG scalp entry at support level."""
        volume_ratio_5m = indicators.get("volume_ratio_5m", 1.0)
        volume_ratio_1m = indicators.get("volume_ratio_1m", 1.0)
        obv_trend_5m = indicators.get("obv_trend_5m", "neutral")
        vwap_5m = indicators.get("vwap_5m", price)

        # Base confidence for scalp at support
        base_confidence = 0.75

        # Volume boost
        active_volume_ratio = max(volume_ratio_5m, volume_ratio_1m)
        if active_volume_ratio >= 1.5:
            volume_confidence_boost = 0.10
        elif active_volume_ratio >= 1.3:
            volume_confidence_boost = 0.08
        elif active_volume_ratio >= 1.1:
            volume_confidence_boost = 0.05
        else:
            volume_confidence_boost = 0.0

        # OBV bonus
        obv_bonus = 0.03 if obv_trend_5m == "bullish" else 0.0

        # VWAP and S/R alignment bonus
        vwap_bonus = 0.03 if price > vwap_5m else 0.0
        sr_bonus = 0.03  # At support level

        base_confidence = max(0.4, min(0.85, base_confidence + volume_confidence_boost + obv_bonus + vwap_bonus + sr_bonus))

        if not suppress_logs:
            logger.info(f"  |-- [SCALP LONG @ SUPPORT] Confidence: {base_confidence:.2f} | Vol: {active_volume_ratio:.2f}x | OBV: {obv_trend_5m}")

        # Use support level as entry reference
        s1 = indicators.get("support_1", 0)
        s2 = indicators.get("support_2", 0)
        swing_low = indicators.get("swing_low", 0)
        support_level = min([s for s in [s1, s2, swing_low] if s > 0], default=price)

        return self._create_scalp_long_signal(snapshot, indicators, price, equity, available_cash,
                                            support_level, f"support bounce at ${support_level:.2f}")

    def _handle_scalp_short_at_resistance(self, snapshot: Any, indicators: dict, price: float,
                                         equity: float, available_cash: float, suppress_logs: bool = False) -> StrategySignal:
        """Handle SHORT scalp entry at resistance level."""
        volume_ratio_5m = indicators.get("volume_ratio_5m", 1.0)
        volume_ratio_1m = indicators.get("volume_ratio_1m", 1.0)
        obv_trend_5m = indicators.get("obv_trend_5m", "neutral")
        vwap_5m = indicators.get("vwap_5m", price)

        # Base confidence for scalp at resistance
        base_confidence = 0.75

        # Volume boost
        active_volume_ratio = max(volume_ratio_5m, volume_ratio_1m)
        if active_volume_ratio >= 1.5:
            volume_confidence_boost = 0.10
        elif active_volume_ratio >= 1.3:
            volume_confidence_boost = 0.08
        elif active_volume_ratio >= 1.1:
            volume_confidence_boost = 0.05
        else:
            volume_confidence_boost = 0.0

        # OBV bonus
        obv_bonus = 0.03 if obv_trend_5m == "bearish" else 0.0

        # VWAP and S/R alignment bonus
        vwap_bonus = 0.03 if price < vwap_5m else 0.0
        sr_bonus = 0.03  # At resistance level

        base_confidence = max(0.4, min(0.85, base_confidence + volume_confidence_boost + obv_bonus + vwap_bonus + sr_bonus))

        if not suppress_logs:
            logger.info(f"  |-- [SCALP SHORT @ RESISTANCE] Confidence: {base_confidence:.2f} | Vol: {active_volume_ratio:.2f}x | OBV: {obv_trend_5m}")

        # Use resistance level as entry reference
        r1 = indicators.get("resistance_1", 0)
        r2 = indicators.get("resistance_2", 0)
        swing_high = indicators.get("swing_high", 0)
        resistance_level = max([r for r in [r1, r2, swing_high] if r > 0], default=price)

        return self._create_scalp_short_signal(snapshot, indicators, price, equity, available_cash,
                                             resistance_level, f"resistance rejection at ${resistance_level:.2f}")

    def _check_long_scalp_entry(self, snapshot: Any, indicators: dict, price: float,
                               equity: float, available_cash: float) -> Optional[StrategySignal]:
        """Check for long scalp entry conditions."""
        # Multi-timeframe scalping: 15m → 5m → 1m
        bias_15m_bullish, _ = get_scalp_trend_bias(indicators, "long")
        trend_5m = indicators.get("trend_5m", "bearish")

        if not (bias_15m_bullish and trend_5m == "bullish"):
            return None

        # 1m entry timing (precise entry)
        ema_20_1m = indicators.get("ema_20_1m", 0)
        rsi_1m = indicators.get("rsi_14_1m", 50)
        long_momentum_1m = price > ema_20_1m and rsi_1m < 75  # Not overbought

        # Check breakout conditions
        has_breakout_1m, _, _ = check_breakout_conditions(indicators, price, "long", "1m")
        has_breakout_5m, _, _ = check_breakout_conditions(indicators, price, "long", "5m")
        has_near_upper_1m, _, _ = check_near_band_conditions(indicators, price, "long", "1m")

        # Entry conditions
        has_breakout = has_breakout_1m or (has_breakout_5m and has_breakout_1m)
        has_momentum_entry = has_near_upper_1m and long_momentum_1m

        if (has_breakout or has_momentum_entry) and long_momentum_1m:
            entry_type = "breakout" if has_breakout_1m or has_breakout_5m else "momentum"
            entry_tf = "1m" if has_breakout_1m else "5m"
            return self._create_scalp_long_signal(snapshot, indicators, price, equity, available_cash,
                                                price, f"{entry_tf} {entry_type}")

        return None

    def _check_short_scalp_entry(self, snapshot: Any, indicators: dict, price: float,
                                equity: float, available_cash: float) -> Optional[StrategySignal]:
        """Check for short scalp entry conditions."""
        # Multi-timeframe scalping: 15m → 5m → 1m
        bias_15m_bearish, _ = get_scalp_trend_bias(indicators, "short")
        trend_5m = indicators.get("trend_5m", "bearish")

        if not (bias_15m_bearish and trend_5m == "bearish"):
            return None

        # 1m entry timing (precise entry)
        ema_20_1m = indicators.get("ema_20_1m", 0)
        rsi_1m = indicators.get("rsi_14_1m", 50)
        short_momentum_1m = price < ema_20_1m and rsi_1m > 25  # Not oversold

        # Check breakdown conditions
        has_breakdown_1m, _, _ = check_breakout_conditions(indicators, price, "short", "1m")
        has_breakdown_5m, _, _ = check_breakout_conditions(indicators, price, "short", "5m")
        has_near_lower_1m, _, _ = check_near_band_conditions(indicators, price, "short", "1m")

        # Entry conditions
        has_breakdown = has_breakdown_1m or (has_breakdown_5m and has_breakdown_1m)
        has_momentum_entry = has_near_lower_1m and short_momentum_1m

        if (has_breakdown or has_momentum_entry) and short_momentum_1m:
            entry_type = "breakdown" if has_breakdown_1m or has_breakdown_5m else "momentum"
            entry_tf = "1m" if has_breakdown_1m else "5m"
            return self._create_scalp_short_signal(snapshot, indicators, price, equity, available_cash,
                                                 price, f"{entry_tf} {entry_type}")

        return None

    def _create_scalp_long_signal(self, snapshot: Any, indicators: dict, price: float,
                                 equity: float, available_cash: float,
                                 entry_level: float, entry_reason: str) -> StrategySignal:
        """Create a long scalp entry signal."""
        # Calculate confidence
        volume_ratio_5m = indicators.get("volume_ratio_5m", 1.0)
        volume_ratio_1m = indicators.get("volume_ratio_1m", 1.0)
        obv_trend_5m = indicators.get("obv_trend_5m", "neutral")
        vwap_5m = indicators.get("vwap_5m", price)

        active_volume_ratio = max(volume_ratio_5m, volume_ratio_1m)
        vwap_alignment = price > vwap_5m
        sr_alignment = "support" in entry_reason.lower()

        confidence = calculate_scalp_confidence(
            volume_ratio_5m=volume_ratio_5m,
            volume_ratio_1m=volume_ratio_1m,
            obv_trend=obv_trend_5m,
            vwap_alignment=vwap_alignment,
            support_resistance_bonus=sr_alignment
        )

        # Calculate leverage and position size
        leverage = calculate_leverage(confidence, "scalp")

        # ATR-based dynamic SL/TP
        # Use 5m timeframe ATR (atr_14_5m) for scalping, fallback to 1h ATR (atr_14) if not available
        atr_5m = indicators.get("atr_14_5m", indicators.get("atr_14", price * 0.002))
        stop_loss, take_profit = calculate_dynamic_scalp_sl_tp(price, atr_5m, "long")

        stop_distance = abs(price - stop_loss)
        position_size_pct, capital_amount, position_notional, risk_amount, reward_amount = calculate_position_size(
            equity, available_cash, confidence, price, stop_distance, "scalp", leverage
        )

        if position_size_pct == 0:
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason="Insufficient cash for scalp position",
                confidence=0.0,
                symbol=snapshot.symbol,
                position_type="scalp"
            )

        # Volume description
        volume_desc = get_volume_description(active_volume_ratio)

        reason = f"Scalp long: {entry_reason}, price ${price:.2f} > VWAP ${vwap_5m:.2f}, {volume_desc}. Capital: {position_size_pct*100:.0f}%, Leverage: {int(round(leverage))}x"

        return StrategySignal(
            action="long",
            size_pct=position_size_pct,
            reason=reason,
            confidence=confidence,
            symbol=snapshot.symbol,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_type="scalp",
            leverage=leverage,
            risk_amount=risk_amount,
            reward_amount=reward_amount
        )

    def _create_scalp_short_signal(self, snapshot: Any, indicators: dict, price: float,
                                  equity: float, available_cash: float,
                                  entry_level: float, entry_reason: str) -> StrategySignal:
        """Create a short scalp entry signal."""
        # Calculate confidence
        volume_ratio_5m = indicators.get("volume_ratio_5m", 1.0)
        volume_ratio_1m = indicators.get("volume_ratio_1m", 1.0)
        obv_trend_5m = indicators.get("obv_trend_5m", "neutral")
        vwap_5m = indicators.get("vwap_5m", price)

        active_volume_ratio = max(volume_ratio_5m, volume_ratio_1m)
        vwap_alignment = price < vwap_5m
        sr_alignment = "resistance" in entry_reason.lower()

        confidence = calculate_scalp_confidence(
            volume_ratio_5m=volume_ratio_5m,
            volume_ratio_1m=volume_ratio_1m,
            obv_trend=obv_trend_5m,
            vwap_alignment=vwap_alignment,
            support_resistance_bonus=sr_alignment
        )

        # Calculate leverage and position size
        leverage = calculate_leverage(confidence, "scalp")

        # ATR-based dynamic SL/TP
        # Use 5m timeframe ATR (atr_14_5m) for scalping, fallback to 1h ATR (atr_14) if not available
        atr_5m = indicators.get("atr_14_5m", indicators.get("atr_14", price * 0.002))
        stop_loss, take_profit = calculate_dynamic_scalp_sl_tp(price, atr_5m, "short")

        stop_distance = abs(price - stop_loss)
        position_size_pct, capital_amount, position_notional, risk_amount, reward_amount = calculate_position_size(
            equity, available_cash, confidence, price, stop_distance, "scalp", leverage
        )

        if position_size_pct == 0:
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason="Insufficient cash for scalp position",
                confidence=0.0,
                symbol=snapshot.symbol,
                position_type="scalp"
            )

        # Volume description
        volume_desc = get_volume_description(active_volume_ratio)

        reason = f"Scalp short: {entry_reason}, price ${price:.2f} < VWAP ${vwap_5m:.2f}, {volume_desc}. Capital: {position_size_pct*100:.0f}%, Leverage: {int(round(leverage))}x"

        return StrategySignal(
            action="short",
            size_pct=position_size_pct,
            reason=reason,
            confidence=confidence,
            symbol=snapshot.symbol,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_type="scalp",
            leverage=leverage,
            risk_amount=risk_amount,
            reward_amount=reward_amount
        )
