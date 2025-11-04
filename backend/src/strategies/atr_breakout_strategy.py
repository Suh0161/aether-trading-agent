"""ATR-filtered Trend/Breakout Strategy."""

import logging
from typing import Any, Optional

from src.indicators.technical_indicators import (
    analyze_trend_alignment,
    check_support_resistance_levels,
    validate_keltner_bands,
    analyze_volume_confirmation,
    check_breakout_conditions,
    check_near_band_conditions
)
from src.strategy_utils.confidence_calculators import calculate_swing_confidence, get_volume_description
from src.strategy_utils.position_sizing import (
    calculate_position_size,
    calculate_leverage,
    calculate_dynamic_sl_tp
)
from src.strategy import StrategySignal

logger = logging.getLogger(__name__)


class ATRBreakoutStrategy:
    """
    ATR-filtered Trend/Breakout Strategy

    Rules:
    1. Trend filter: only long when price > EMA50
    2. Entry: price breaks above Keltner upper band (ATR-based)
    3. Stop: ATR×2 below entry
    4. Take profit: 2R (risk-reward ratio)
    5. Position size: 1% risk per trade
    """

    def __init__(self, atr_multiplier: float = 1.5, stop_atr_multiplier: float = 2.0):
        """
        Initialize ATR breakout strategy.

        Args:
            atr_multiplier: Multiplier for Keltner band width
            stop_atr_multiplier: Multiplier for stop loss distance
        """
        self.atr_multiplier = atr_multiplier
        self.stop_atr_multiplier = stop_atr_multiplier
        self.last_signal_price = None

    def analyze(self, snapshot: Any, position_size: float, equity: float, suppress_logs: bool = False) -> StrategySignal:
        """
        Analyze market using multi-timeframe analysis and generate trading signal.

        Multi-timeframe swing approach:
        - 1D: Long-term trend direction
        - 4H: Intermediate trend confirmation
        - 1H: Entry signal generation (breakout conditions)
        - 15M: Precise entry timing

        Args:
            snapshot: Market snapshot with price and multi-timeframe indicators
            position_size: Current position size
            equity: Account equity

        Returns:
            StrategySignal with action and parameters
        """
        price = snapshot.price
        indicators = snapshot.indicators

        # Calculate available cash for money management
        position_value = position_size * price if position_size > 0 else 0.0
        available_cash = equity - position_value

        # If we don't have required indicators, hold
        ema_50 = indicators.get("ema_50", 0)
        atr_14 = indicators.get("atr_14", 0)

        if not all([ema_50, atr_14]):
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason="Missing required indicators (EMA50, ATR14)",
                confidence=0.0,
                symbol=snapshot.symbol,
                position_type="swing"
            )

        # Analyze trend alignment
        trend_alignment, timeframe_info = analyze_trend_alignment(indicators, "long" if position_size >= 0 else "short")

        # Check support/resistance levels first (Priority 1)
        near_support, near_resistance, sr_level = check_support_resistance_levels(indicators, price)

        # If we have a LONG position, check exit conditions
        if position_size > 0:
            # Exit if trend reverses
            if trend_alignment in ["neutral", "weak"] or price < ema_50:
                return StrategySignal(
                    action="close",
                    size_pct=1.0,
                    reason=f"Long exit: Trend reversal (price ${price:.2f}, EMA50 ${ema_50:.2f}, {timeframe_info})",
                    confidence=0.9,
                    position_type="swing",
                    symbol=snapshot.symbol
                )

            # Otherwise hold long
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=f"In long position, trend intact (price ${price:.2f} > EMA50 ${ema_50:.2f})",
                confidence=0.7,
                position_type="swing",
                symbol=snapshot.symbol
            )

        # If we have a SHORT position, check exit conditions
        elif position_size < 0:
            # Exit if downtrend reverses
            if trend_alignment in ["neutral", "weak"] or price > ema_50:
                return StrategySignal(
                    action="close",
                    size_pct=1.0,
                    reason=f"Short exit: Trend reversal (price ${price:.2f}, EMA50 ${ema_50:.2f}, {timeframe_info})",
                    confidence=0.9,
                    position_type="swing",
                    symbol=snapshot.symbol
                )

            # Otherwise hold short
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=f"In short position, downtrend intact (price ${price:.2f} < EMA50 ${ema_50:.2f})",
                confidence=0.7,
                position_type="swing",
                symbol=snapshot.symbol
            )

        # No position - look for LONG or SHORT entry

        # PRIORITY 1: S/R Logic (Support=Buy, Resistance=Sell)
        if near_support and trend_alignment in ["strong", "partial"]:
            return self._handle_long_at_support(snapshot, indicators, price, atr_14, equity, available_cash, suppress_logs)

        if near_resistance and trend_alignment in ["strong", "partial"]:
            return self._handle_short_at_resistance(snapshot, indicators, price, atr_14, equity, available_cash, suppress_logs)

        # PRIORITY 2: Keltner Band Logic (breakout/breakdown)
        # Check for long entry
        if trend_alignment in ["strong", "partial"] and not near_resistance:
            # Step 1: Check for 1h breakout (signal generation)
            has_breakout_1h, entry_level_1h, breakout_desc_1h = check_breakout_conditions(indicators, price, "long", "1h")
            
            if has_breakout_1h:
                # Step 2: Use 15m for precise entry timing (find pullback or confirmation)
                trend_15m = indicators.get("trend_15m", "neutral")
                ema_50_15m = indicators.get("ema_50_15m", 0)
                keltner_upper_15m = indicators.get("keltner_upper_15m", 0)
                rsi_15m = indicators.get("rsi_14_15m", 50)
                
                # 15m entry timing options:
                # Option A: Pullback to 15m EMA50 (better entry price)
                # Option B: 15m confirms continuation (price above 15m EMA, bullish trend)
                # Option C: Price near 15m Keltner upper (momentum entry)
                
                pullback_entry = ema_50_15m > 0 and price > ema_50_15m and trend_15m == "bullish"
                momentum_entry = keltner_upper_15m > 0 and price > (keltner_upper_15m * 0.995) and rsi_15m < 75
                
                if pullback_entry:
                    entry_reason = f"1h breakout confirmed, 15m pullback entry at EMA50 ${ema_50_15m:.2f}"
                    entry_level = ema_50_15m
                elif momentum_entry:
                    entry_reason = f"1h breakout confirmed, 15m momentum entry {breakout_desc_1h}"
                    entry_level = entry_level_1h
                else:
                    # Entry now but note we're waiting for better 15m setup
                    entry_reason = f"1h breakout {breakout_desc_1h}, entering on 15m confirmation"
                    entry_level = entry_level_1h
                
                return self._create_long_signal(snapshot, indicators, price, atr_14, equity, available_cash,
                                              entry_level, entry_reason)

        # Check for short entry
        elif trend_alignment in ["strong", "partial"] and not near_support:
            # Step 1: Check for 1h breakdown (signal generation)
            has_breakdown_1h, entry_level_1h, breakdown_desc_1h = check_breakout_conditions(indicators, price, "short", "1h")
            
            if has_breakdown_1h:
                # Step 2: Use 15m for precise entry timing (find pullback or confirmation)
                trend_15m = indicators.get("trend_15m", "neutral")
                ema_50_15m = indicators.get("ema_50_15m", 0)
                keltner_lower_15m = indicators.get("keltner_lower_15m", 0)
                rsi_15m = indicators.get("rsi_14_15m", 50)
                
                # 15m entry timing options:
                # Option A: Pullback to 15m EMA50 (better entry price)
                # Option B: 15m confirms continuation (price below 15m EMA, bearish trend)
                # Option C: Price near 15m Keltner lower (momentum entry)
                
                pullback_entry = ema_50_15m > 0 and price < ema_50_15m and trend_15m == "bearish"
                momentum_entry = keltner_lower_15m > 0 and price < (keltner_lower_15m * 1.005) and rsi_15m > 25
                
                if pullback_entry:
                    entry_reason = f"1h breakdown confirmed, 15m pullback entry at EMA50 ${ema_50_15m:.2f}"
                    entry_level = ema_50_15m
                elif momentum_entry:
                    entry_reason = f"1h breakdown confirmed, 15m momentum entry {breakdown_desc_1h}"
                    entry_level = entry_level_1h
                else:
                    # Entry now but note we're waiting for better 15m setup
                    entry_reason = f"1h breakdown {breakdown_desc_1h}, entering on 15m confirmation"
                    entry_level = entry_level_1h
                
                return self._create_short_signal(snapshot, indicators, price, atr_14, equity, available_cash,
                                               entry_level, entry_reason)

        return StrategySignal(
            action="hold",
            size_pct=0.0,
            reason=f"Waiting for entry: {timeframe_info}, SR: {sr_level}",
            confidence=0.0,
            symbol=snapshot.symbol,
            position_type="swing"
        )

    def _handle_long_at_support(self, snapshot: Any, indicators: dict, price: float,
                               atr_14: float, equity: float, available_cash: float, suppress_logs: bool = False) -> StrategySignal:
        """Handle LONG entry at support level."""
        volume_ratio, volume_desc, obv_trend = analyze_volume_confirmation(indicators, "long")

        # Base confidence for support bounce
        base_confidence = 0.85

        # Volume boost
        if volume_ratio >= 1.5:
            volume_confidence_boost = 0.10
        elif volume_ratio >= 1.2:
            volume_confidence_boost = 0.05
        else:
            volume_confidence_boost = 0.0

        # OBV bonus
        obv_bonus = 0.05 if obv_trend == "bullish" else 0.0

        # Multi-TF alignment bonus
        trend_alignment, _ = analyze_trend_alignment(indicators, "long")
        alignment_bonus = 0.05 if trend_alignment == "strong" else 0.0

        base_confidence = max(0.3, min(0.95, base_confidence + volume_confidence_boost + obv_bonus + alignment_bonus))

        if not suppress_logs:
            logger.info(f"  |-- [SWING LONG @ SUPPORT] Confidence: {base_confidence:.2f} | Vol: {volume_ratio:.2f}x | OBV: {obv_trend}")

        # Use nearest support level as entry reference
        s1 = indicators.get("support_1", 0)
        s2 = indicators.get("support_2", 0)
        swing_low = indicators.get("swing_low", 0)
        support_level = min([s for s in [s1, s2, swing_low] if s > 0], default=price)

        return self._create_long_signal(snapshot, indicators, price, atr_14, equity, available_cash,
                                      support_level, f"support bounce at ${support_level:.2f}")

    def _handle_short_at_resistance(self, snapshot: Any, indicators: dict, price: float,
                                   atr_14: float, equity: float, available_cash: float, suppress_logs: bool = False) -> StrategySignal:
        """Handle SHORT entry at resistance level."""
        volume_ratio, volume_desc, obv_trend = analyze_volume_confirmation(indicators, "short")

        # Base confidence for resistance rejection
        base_confidence = 0.85

        # Volume boost
        if volume_ratio >= 1.5:
            volume_confidence_boost = 0.10
        elif volume_ratio >= 1.2:
            volume_confidence_boost = 0.05
        else:
            volume_confidence_boost = 0.0

        # OBV bonus
        obv_bonus = 0.05 if obv_trend == "bearish" else 0.0

        # Multi-TF alignment bonus
        trend_alignment, _ = analyze_trend_alignment(indicators, "short")
        alignment_bonus = 0.05 if trend_alignment == "strong" else 0.0

        base_confidence = max(0.3, min(0.95, base_confidence + volume_confidence_boost + obv_bonus + alignment_bonus))

        if not suppress_logs:
            logger.info(f"  |-- [SWING SHORT @ RESISTANCE] Confidence: {base_confidence:.2f} | Vol: {volume_ratio:.2f}x | OBV: {obv_trend}")

        # Use nearest resistance level as entry reference
        r1 = indicators.get("resistance_1", 0)
        r2 = indicators.get("resistance_2", 0)
        swing_high = indicators.get("swing_high", 0)
        resistance_level = max([r for r in [r1, r2, swing_high] if r > 0], default=price)

        return self._create_short_signal(snapshot, indicators, price, atr_14, equity, available_cash,
                                       resistance_level, f"resistance rejection at ${resistance_level:.2f}")

    def _create_long_signal(self, snapshot: Any, indicators: dict, price: float,
                           atr_14: float, equity: float, available_cash: float,
                           entry_level: float, entry_reason: str) -> StrategySignal:
        """Create a long entry signal."""
        # Calculate confidence
        volume_ratio, _, obv_trend = analyze_volume_confirmation(indicators, "long")
        trend_alignment, timeframe_info = analyze_trend_alignment(indicators, "long")

        confidence = calculate_swing_confidence(
            volume_ratio=volume_ratio,
            obv_trend=obv_trend,
            trend_alignment=trend_alignment
        )

        # Calculate leverage and position size
        leverage = calculate_leverage(confidence, "swing")
        stop_distance = atr_14 * self.stop_atr_multiplier

        position_size_pct, capital_amount, position_notional, risk_amount, reward_amount = calculate_position_size(
            equity, available_cash, confidence, price, stop_distance, "swing", leverage
        )

        if position_size_pct == 0:
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason="Insufficient cash for position",
                confidence=0.0,
                symbol=snapshot.symbol,
                position_type="swing"
            )

        # Calculate SL/TP
        stop_loss, take_profit = calculate_dynamic_sl_tp(price, atr_14, "long")

        # Create reason string
        volume_desc = get_volume_description(volume_ratio)
        reason = f"Long entry: {entry_reason}, {timeframe_info}. {volume_desc}, OBV: {obv_trend}. Capital: {position_size_pct*100:.0f}%, Leverage: {leverage:.1f}x"

        # Avoid re-entering immediately after exit
        if self.last_signal_price and abs(price - self.last_signal_price) / price < 0.005:
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason="Too close to last signal, avoiding chop",
                confidence=0.3,
                symbol=snapshot.symbol,
                position_type="swing"
            )

        self.last_signal_price = price

        return StrategySignal(
            action="long",
            size_pct=position_size_pct,
            reason=reason,
            confidence=confidence,
            symbol=snapshot.symbol,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_type="swing",
            leverage=leverage,
            risk_amount=risk_amount,
            reward_amount=reward_amount
        )

    def _create_short_signal(self, snapshot: Any, indicators: dict, price: float,
                            atr_14: float, equity: float, available_cash: float,
                            entry_level: float, entry_reason: str) -> StrategySignal:
        """Create a short entry signal."""
        # Calculate confidence
        volume_ratio, _, obv_trend = analyze_volume_confirmation(indicators, "short")
        trend_alignment, timeframe_info = analyze_trend_alignment(indicators, "short")

        confidence = calculate_swing_confidence(
            volume_ratio=volume_ratio,
            obv_trend=obv_trend,
            trend_alignment=trend_alignment,
            resistance_bonus=True  # Bonus for resistance shorts
        )

        # Calculate leverage and position size
        leverage = calculate_leverage(confidence, "swing")
        stop_distance = atr_14 * self.stop_atr_multiplier

        position_size_pct, capital_amount, position_notional, risk_amount, reward_amount = calculate_position_size(
            equity, available_cash, confidence, price, stop_distance, "swing", leverage
        )

        if position_size_pct == 0:
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason="Insufficient cash for position",
                confidence=0.0,
                symbol=snapshot.symbol,
                position_type="swing"
            )

        # Calculate SL/TP
        stop_loss, take_profit = calculate_dynamic_sl_tp(price, atr_14, "short")

        # Create reason string
        volume_desc = get_volume_description(volume_ratio)
        reason = f"Short entry: {entry_reason}, {timeframe_info}. {volume_desc}, OBV: {obv_trend}. Capital: {position_size_pct*100:.0f}%, Leverage: {leverage:.1f}x"

        # Avoid re-entering immediately after exit
        if self.last_signal_price and abs(price - self.last_signal_price) / price < 0.005:
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason="Too close to last signal, avoiding chop",
                confidence=0.3,
                symbol=snapshot.symbol,
                position_type="swing"
            )

        self.last_signal_price = price

        return StrategySignal(
            action="short",
            size_pct=position_size_pct,
            reason=reason,
            confidence=confidence,
            symbol=snapshot.symbol,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_type="swing",
            leverage=leverage,
            risk_amount=risk_amount,
            reward_amount=reward_amount
        )
