"""Trading strategies for the Autonomous Trading Agent."""

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class StrategySignal:
    """Signal from a trading strategy."""
    action: str  # "long" | "short" | "close" | "hold"
    size_pct: float  # 0.0 to 1.0 (percentage of equity to allocate as capital)
    reason: str
    confidence: float  # 0.0 to 1.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_type: str = "swing"  # "swing" | "scalp" - indicates trade duration style
    leverage: float = 1.0  # Leverage multiplier (1.0 = no leverage, 2.0 = 2x, 3.0 = 3x)
    risk_amount: Optional[float] = None  # Dollar amount at risk if SL hits
    reward_amount: Optional[float] = None  # Dollar amount if TP hits


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
    
    def analyze(self, snapshot: Any, position_size: float, equity: float) -> StrategySignal:
        """
        Analyze market using multi-timeframe analysis and generate trading signal.
        
        Professional approach:
        - Higher TFs (1d, 4h): Confirm trend direction
        - Lower TF (15m): Find precise entry timing
        
        Args:
            snapshot: Market snapshot with price and multi-timeframe indicators
            position_size: Current position size
            equity: Account equity
            
        Returns:
            StrategySignal with action and parameters
        """
        price = snapshot.price
        indicators = snapshot.indicators
        
        # Extract multi-timeframe indicators
        # Higher timeframes for trend confirmation
        trend_1d = indicators.get("trend_1d", "bearish")
        trend_4h = indicators.get("trend_4h", "bearish")
        ema_50_4h = indicators.get("ema_50_4h", 0)
        ema_50_1d = indicators.get("ema_50_1d", 0)
        
        # Primary timeframe (1h) for main analysis
        ema_50 = indicators.get("ema_50", 0)
        atr_14 = indicators.get("atr_14", 0)
        keltner_upper = indicators.get("keltner_upper", 0)
        keltner_lower = indicators.get("keltner_lower", 0)
        
        # Lower timeframe (15m) for entry timing
        keltner_upper_15m = indicators.get("keltner_upper_15m", 0)
        keltner_lower_15m = indicators.get("keltner_lower_15m", 0)
        ema_50_15m = indicators.get("ema_50_15m", 0)
        rsi_15m = indicators.get("rsi_14_15m", 50)
        trend_15m = indicators.get("trend_15m", "bearish")
        
        # Validate Keltner Channel values are reasonable
        if keltner_upper > 0 and price > 0:
            price_deviation = abs(keltner_upper - price) / price
            if price_deviation > 0.15:  # More than 15% away seems unreasonable
                logger.warning(
                    f"Keltner upper band seems too far: price=${price:.2f}, "
                    f"upper=${keltner_upper:.2f}, deviation={price_deviation*100:.1f}%"
                )
                # Fallback: use a dynamic calculation based on price and EMA
                ema_20 = indicators.get("ema_20", price)
                # Calculate reasonable upper band: EMA20 + 3% of price
                keltner_upper = ema_20 + (price * 0.03)
                logger.info(f"Using fallback Keltner upper: ${keltner_upper:.2f}")
        
        # Calculate available cash for money management
        position_value = position_size * price if position_size > 0 else 0.0
        available_cash = equity - position_value
        
        # If we don't have required indicators, hold
        if not all([ema_50, atr_14]):
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason="Missing required indicators (EMA50, ATR14)",
                confidence=0.0,
                position_type="swing"
            )
        
        # Multi-timeframe trend confirmation for BOTH longs and shorts
        # LONG setup: Higher timeframes bullish
        higher_tf_bullish = trend_1d == "bullish" and trend_4h == "bullish"
        primary_uptrend = price > ema_50
        in_uptrend = higher_tf_bullish and primary_uptrend
        
        # SHORT setup: Higher timeframes bearish
        higher_tf_bearish = trend_1d == "bearish" and trend_4h == "bearish"
        primary_downtrend = price < ema_50
        in_downtrend = higher_tf_bearish and primary_downtrend
        
        # If we have a LONG position, check exit conditions
        if position_size > 0:
            # Exit if trend reverses (price drops below EMA50 or higher TFs turn bearish)
            if not in_uptrend:
                return StrategySignal(
                    action="close",
                    size_pct=1.0,
                    reason=f"Long exit: Trend reversal (price ${price:.2f}, EMA50 ${ema_50:.2f}, 1D={trend_1d}, 4H={trend_4h})",
                    confidence=0.9,
                    position_type="swing"
                )
            
            # Otherwise hold long
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=f"In long position, trend intact (price ${price:.2f} > EMA50 ${ema_50:.2f})",
                confidence=0.7,
                position_type="swing"
            )
        
        # If we have a SHORT position (position_size < 0), check exit conditions
        elif position_size < 0:
            # Exit if downtrend reverses (price rises above EMA50 or higher TFs turn bullish)
            if not in_downtrend:
                return StrategySignal(
                    action="close",
                    size_pct=1.0,
                    reason=f"Short exit: Trend reversal (price ${price:.2f}, EMA50 ${ema_50:.2f}, 1D={trend_1d}, 4H={trend_4h})",
                    confidence=0.9,
                    position_type="swing"
                )
            
            # Otherwise hold short
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=f"In short position, downtrend intact (price ${price:.2f} < EMA50 ${ema_50:.2f})",
                confidence=0.7,
                position_type="swing"
            )
        
        # No position - look for LONG or SHORT entry
        # Priority: Check for strong directional bias first
        
        # === LONG ENTRY LOGIC ===
        if in_uptrend:
            # Extract volume indicators for confirmation
            volume_ratio_1h = indicators.get("volume_ratio_1h", 1.0)
            volume_trend_1h = indicators.get("volume_trend_1h", "stable")
            obv_trend_1h = indicators.get("obv_trend_1h", "neutral")
            
            # Check entry on 15m timeframe (precise timing)
            # More reasonable conditions: breakout OR near upper band with momentum
            long_breakout_15m = keltner_upper_15m > 0 and price > keltner_upper_15m
            long_near_upper_15m = keltner_upper_15m > 0 and price > (keltner_upper_15m * 0.995)
            long_trend_15m = trend_15m == "bullish"
            
            # Also check primary timeframe
            long_primary_breakout = keltner_upper > 0 and price > keltner_upper
            long_near_upper_1h = keltner_upper > 0 and price > (keltner_upper * 0.995)
            
            # Volume confirmation (GOAT-level addition)
            # Strong volume: ratio > 1.5 (50% above average)
            # Moderate volume: ratio > 1.2 (20% above average)
            # Weak volume: ratio < 1.0 (below average)
            volume_confirmed = volume_ratio_1h >= 1.2  # At least 20% above average
            volume_strong = volume_ratio_1h >= 1.5  # 50% above average = strong conviction
            
            # OBV confirmation (money flow)
            obv_bullish = obv_trend_1h == "bullish"
            
            # Entry condition: Higher TF bullish + (breakout OR near band) + VOLUME CONFIRMATION
            entry_timeframe = None
            entry_keltner = 0
            
            if (long_breakout_15m or long_near_upper_15m) and long_trend_15m:
                # Check volume confirmation for 15m entries
                if volume_confirmed:
                    # Use 15m for precise entry timing (preferred method)
                    entry_keltner = keltner_upper_15m
                    entry_timeframe = "15m"
                else:
                    logger.info(f"15m long setup found but VOLUME TOO LOW (ratio={volume_ratio_1h:.2f}, need ≥1.2) - waiting for confirmation")
            elif long_primary_breakout or long_near_upper_1h:
                # Check volume confirmation for 1h entries
                if volume_confirmed:
                    # Fallback to primary timeframe
                    entry_keltner = keltner_upper
                    entry_timeframe = "1h"
                else:
                    logger.info(f"1h long setup found but VOLUME TOO LOW (ratio={volume_ratio_1h:.2f}, need ≥1.2) - waiting for confirmation")
            
            if entry_timeframe:
                # LONG entry confirmed with VOLUME - proceed with trade setup
                # Boost confidence if volume is STRONG
                base_confidence = 0.8
                if volume_strong and obv_bullish:
                    base_confidence = 0.95  # Very high confidence with strong volume + bullish OBV
                    logger.info(f"[STRONG VOLUME] Confirmation: ratio={volume_ratio_1h:.2f}, OBV={obv_trend_1h}")
                
                return self._build_entry_signal(
                    action="long",
                    price=price,
                    atr_14=atr_14,
                    equity=equity,
                    available_cash=available_cash,
                    entry_timeframe=entry_timeframe,
                    entry_keltner=entry_keltner,
                    trend_1d=trend_1d,
                    trend_4h=trend_4h,
                    position_type="swing",
                    volume_ratio=volume_ratio_1h,
                    obv_trend=obv_trend_1h,
                    base_confidence=base_confidence
                )
        
        # === SHORT ENTRY LOGIC ===
        elif in_downtrend:
            # Extract volume indicators for confirmation
            volume_ratio_1h = indicators.get("volume_ratio_1h", 1.0)
            volume_trend_1h = indicators.get("volume_trend_1h", "stable")
            obv_trend_1h = indicators.get("obv_trend_1h", "neutral")
            
            # Check entry on 15m timeframe (precise timing for shorts)
            # More reasonable conditions: breakdown OR near lower band with momentum
            short_breakdown_15m = keltner_lower_15m > 0 and price < keltner_lower_15m
            short_near_lower_15m = keltner_lower_15m > 0 and price < (keltner_lower_15m * 1.005)
            short_trend_15m = trend_15m == "bearish"
            
            # Also check primary timeframe
            short_primary_breakdown = keltner_lower > 0 and price < keltner_lower
            short_near_lower_1h = keltner_lower > 0 and price < (keltner_lower * 1.005)
            
            # Volume confirmation (GOAT-level addition)
            volume_confirmed = volume_ratio_1h >= 1.2  # At least 20% above average
            volume_strong = volume_ratio_1h >= 1.5  # 50% above average = strong conviction
            
            # OBV confirmation (money flow)
            obv_bearish = obv_trend_1h == "bearish"
            
            # Entry condition: Higher TF bearish + (breakdown OR near band) + VOLUME CONFIRMATION
            entry_timeframe = None
            entry_keltner = 0
            
            if (short_breakdown_15m or short_near_lower_15m) and short_trend_15m:
                # Check volume confirmation for 15m entries
                if volume_confirmed:
                    # Use 15m for precise entry timing (preferred method)
                    entry_keltner = keltner_lower_15m
                    entry_timeframe = "15m"
                else:
                    logger.info(f"15m short setup found but VOLUME TOO LOW (ratio={volume_ratio_1h:.2f}, need ≥1.2) - waiting for confirmation")
            elif short_primary_breakdown or short_near_lower_1h:
                # Check volume confirmation for 1h entries
                if volume_confirmed:
                    # Fallback to primary timeframe
                    entry_keltner = keltner_lower
                    entry_timeframe = "1h"
                else:
                    logger.info(f"1h short setup found but VOLUME TOO LOW (ratio={volume_ratio_1h:.2f}, need ≥1.2) - waiting for confirmation")
            
            if entry_timeframe:
                # SHORT entry confirmed with VOLUME - proceed with trade setup
                # Boost confidence if volume is STRONG
                base_confidence = 0.8
                if volume_strong and obv_bearish:
                    base_confidence = 0.95  # Very high confidence with strong volume + bearish OBV
                    logger.info(f"[STRONG VOLUME] Confirmation: ratio={volume_ratio_1h:.2f}, OBV={obv_trend_1h}")
                
                return self._build_entry_signal(
                    action="short",
                    price=price,
                    atr_14=atr_14,
                    equity=equity,
                    available_cash=available_cash,
                    entry_timeframe=entry_timeframe,
                    entry_keltner=entry_keltner,
                    trend_1d=trend_1d,
                    trend_4h=trend_4h,
                    position_type="swing",
                    volume_ratio=volume_ratio_1h,
                    obv_trend=obv_trend_1h,
                    base_confidence=base_confidence
                )
        
        # No clear trend or no entry signal yet
        return StrategySignal(
            action="hold",
            size_pct=0.0,
            reason=f"Waiting for entry: 1D={trend_1d}, 4H={trend_4h}, 1H={'up' if primary_uptrend else 'down' if primary_downtrend else 'neutral'}",
            confidence=0.0,
            position_type="swing"
        )
    
    def _build_entry_signal(self, action: str, price: float, atr_14: float, equity: float, 
                           available_cash: float, entry_timeframe: str, entry_keltner: float,
                           trend_1d: str, trend_4h: str, position_type: str,
                           volume_ratio: float = 1.0, obv_trend: str = "neutral",
                           base_confidence: float = 0.8) -> StrategySignal:
        """
        Build entry signal for long or short trades.
        
        Args:
            action: "long" or "short"
            price: Current price
            atr_14: ATR value
            equity: Account equity
            available_cash: Available cash
            entry_timeframe: Entry timeframe (e.g., "15m", "1h")
            entry_keltner: Keltner band value at entry
            trend_1d: Daily trend
            trend_4h: 4h trend
            position_type: "swing" or "scalp"
            volume_ratio: Volume ratio (current / average)
            obv_trend: On-Balance Volume trend ("bullish", "bearish", "neutral")
            base_confidence: Base confidence level (adjusted for volume strength)
            
        Returns:
            StrategySignal with entry parameters
        """
        # Avoid re-entering immediately after exit
        if self.last_signal_price and abs(price - self.last_signal_price) / price < 0.005:
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason="Too close to last signal, avoiding chop",
                confidence=0.3,
                position_type=position_type
            )
            
        # Calculate stop loss and take profit based on direction
        stop_distance = atr_14 * self.stop_atr_multiplier
        
        if action == "long":
            stop_loss = price - stop_distance
            take_profit = price + (stop_distance * 2)  # 2R
            direction_desc = "breakout"
            keltner_comparison = ">"
        else:  # short
            stop_loss = price + stop_distance
            take_profit = price - (stop_distance * 2)  # 2R
            direction_desc = "breakdown"
            keltner_comparison = "<"
        
        # === TWO-LAYER POSITION SIZING SYSTEM ===
        
        # LAYER 1: Capital Allocation (how much $ to use from account)
        # Based on confidence level
        if base_confidence >= 0.8:
            # High confidence: allocate 20-30% of equity
            capital_allocation_pct = 0.25  # 25% of equity
        elif base_confidence >= 0.6:
            # Medium confidence: allocate 10-15% of equity
            capital_allocation_pct = 0.12  # 12% of equity
        else:
            # Low confidence: allocate 5-8% of equity
            capital_allocation_pct = 0.06  # 6% of equity
        
        # LAYER 2: Leverage Multiplier (how much to amplify with leverage)
        # Based on confidence + setup quality
        if base_confidence >= 0.9:
            # Very high confidence (strong volume + perfect setup): 2.5-3X leverage
            leverage = 3.0
        elif base_confidence >= 0.8:
            # High confidence: 2-2.5X leverage
            leverage = 2.0
        elif base_confidence >= 0.7:
            # Medium-high confidence: 1.5-2X leverage
            leverage = 1.5
        elif base_confidence >= 0.6:
            # Medium confidence: 1-1.5X leverage
            leverage = 1.2
        else:
            # Low confidence: 0.5-1X leverage (conservative)
            leverage = 1.0
        
        # Calculate final position size
        # position_size_pct = capital allocation (what % of equity to use)
        # This will be multiplied by leverage in the trade executor
        position_size_pct = capital_allocation_pct
        
        # Calculate risk and reward amounts
        capital_amount = equity * capital_allocation_pct
        position_notional = capital_amount * leverage  # Total position size with leverage
        position_btc = position_notional / price
        
        # Risk: if SL hits, how much $ do we lose?
        risk_amount = abs(price - (stop_loss if action == "long" else stop_loss)) * position_btc
        
        # Reward: if TP hits, how much $ do we gain?
        reward_amount = abs((take_profit if action == "long" else take_profit) - price) * position_btc
        
        # Ensure minimum position size (at least $5 notional after leverage)
        min_notional = 15.0  # Binance minimum is ~$10, add buffer
        if position_notional < min_notional:
            # Adjust capital allocation to meet minimum
            required_capital = min_notional / leverage
            position_size_pct = required_capital / equity
            logger.info(f"Adjusted position size to meet minimum notional: {position_size_pct*100:.2f}% capital")
        
        # Cap maximum position size at 30% of equity (safety limit)
        position_size_pct = min(position_size_pct, 0.30)
        
        # Money management: Check if we have enough available cash
        required_cash = equity * position_size_pct
        if available_cash < required_cash:
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=f"Insufficient cash: need ${required_cash:,.2f}, have ${available_cash:,.2f}",
                confidence=0.0,
                position_type=position_type
            )
        
        # Additional safety: Don't trade if available cash is too low
        if available_cash < 100:
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=f"Available cash too low: ${available_cash:,.2f} (need at least $100 buffer)",
                confidence=0.0,
                position_type=position_type
            )
        
        self.last_signal_price = price
        
        # Multi-timeframe confirmation in reason
        timeframe_info = f"Trend: 1D={trend_1d}, 4H={trend_4h}, Entry: {entry_timeframe}"
        
        # Volume confirmation info (GOAT-level addition)
        volume_info = f"Vol: {volume_ratio:.2f}x avg"
        if volume_ratio >= 1.5:
            volume_info += " [STRONG]"
        elif volume_ratio >= 1.2:
            volume_info += " OK"
        obv_info = f"OBV: {obv_trend}"
        
        # Position sizing summary for logging
        logger.info(
            f"Position sizing: Capital={capital_allocation_pct*100:.1f}% (${capital_amount:.2f}), "
            f"Leverage={leverage:.1f}x, Notional=${position_notional:.2f}, "
            f"Risk=${risk_amount:.2f}, Reward=${reward_amount:.2f}, R:R={reward_amount/risk_amount:.2f}"
        )
        
        return StrategySignal(
            action=action,
            size_pct=position_size_pct,
            reason=f"Multi-TF {direction_desc}: price ${price:.2f} {keltner_comparison} {entry_timeframe} Keltner ${entry_keltner:.2f}. {timeframe_info}. {volume_info}, {obv_info}. Capital: {capital_allocation_pct*100:.0f}%, Leverage: {leverage:.1f}x, Risk: ${risk_amount:.2f}, Reward: ${reward_amount:.2f}",
            confidence=base_confidence,  # Use volume-adjusted confidence
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_type=position_type,
            leverage=leverage,
            risk_amount=risk_amount,
            reward_amount=reward_amount
        )


class ScalpingStrategy:
    """
    Scalping strategy for quick trades when no swing setup is available.
    
    Rules:
    1. Entry: Price momentum on 1m/5m timeframes
    2. Stop: Very tight (0.1-0.3% of price)
    3. Target: Quick 0.2-0.5% profit
    4. Hold time: 1-5 minutes max
    5. Exit: Quick profit or tight stop
    """
    
    def __init__(self, profit_target_pct: float = 0.003, stop_loss_pct: float = 0.002):
        """
        Initialize scalping strategy.
        
        Args:
            profit_target_pct: Target profit as percentage of price (default 0.3%)
            stop_loss_pct: Stop loss as percentage of price (default 0.2%)
        """
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct = stop_loss_pct
        self.max_hold_seconds = 300  # 5 minutes max
    
    def analyze(self, snapshot: Any, position_size: float, equity: float) -> StrategySignal:
        """
        Analyze market using 1m/5m timeframes for quick scalping opportunities.
        
        Args:
            snapshot: Market snapshot with price and multi-timeframe indicators
            position_size: Current position size
            equity: Account equity
            
        Returns:
            StrategySignal with action and parameters
        """
        price = snapshot.price
        indicators = snapshot.indicators
        
        # Extract scalping timeframes
        ema_20_5m = indicators.get("ema_20_5m", 0)
        ema_50_5m = indicators.get("ema_50_5m", 0)
        rsi_5m = indicators.get("rsi_14_5m", 50)
        trend_5m = indicators.get("trend_5m", "bearish")
        keltner_upper_5m = indicators.get("keltner_upper_5m", 0)
        keltner_lower_5m = indicators.get("keltner_lower_5m", 0)
        
        ema_20_1m = indicators.get("ema_20_1m", 0)
        ema_50_1m = indicators.get("ema_50_1m", 0)
        rsi_1m = indicators.get("rsi_14_1m", 50)
        trend_1m = indicators.get("trend_1m", "bearish")
        keltner_upper_1m = indicators.get("keltner_upper_1m", 0)
        keltner_lower_1m = indicators.get("keltner_lower_1m", 0)
        
        # VWAP for intraday scalping (primary filter for direction)
        vwap_5m = indicators.get("vwap_5m", price)
        vwap_1m = indicators.get("vwap_1m", price)
        
        # Calculate available cash
        position_value = position_size * price if position_size > 0 else 0.0
        available_cash = equity - position_value
        
        # If we have a LONG position, check exit conditions
        if position_size > 0:
            # Exit if BOTH 5m AND 1m trends turn bearish (more conservative)
            # OR if price drops below VWAP (losing momentum)
            if (trend_5m == "bearish" and trend_1m == "bearish") or price < vwap_5m:
                return StrategySignal(
                    action="close",
                    size_pct=1.0,
                    reason=f"Scalp long exit: Momentum lost (5m={trend_5m}, 1m={trend_1m}, price ${price:.2f} vs VWAP ${vwap_5m:.2f})",
                    confidence=0.8,
                    position_type="scalp"
                )
            
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=f"In scalp long, trend intact",
                confidence=0.6,
                position_type="scalp"
            )
        
        # If we have a SHORT position, check exit conditions
        elif position_size < 0:
            # Exit if BOTH 5m AND 1m trends turn bullish (more conservative)
            # OR if price rises above VWAP (losing momentum)
            if (trend_5m == "bullish" and trend_1m == "bullish") or price > vwap_5m:
                return StrategySignal(
                    action="close",
                    size_pct=1.0,
                    reason=f"Scalp short exit: Momentum lost (5m={trend_5m}, 1m={trend_1m}, price ${price:.2f} vs VWAP ${vwap_5m:.2f})",
                    confidence=0.8,
                    position_type="scalp"
                )
            
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=f"In scalp short, downtrend intact",
                confidence=0.6,
                position_type="scalp"
            )
        
        # No position - look for LONG or SHORT scalping entry
        
        # === LONG SCALP ENTRY ===
        # VWAP Filter: Only long if price is above VWAP (confirms bullish intraday bias)
        if trend_5m == "bullish" and price > vwap_5m:
            # Extract volume indicators for scalping confirmation
            volume_ratio_5m = indicators.get("volume_ratio_5m", 1.0)
            volume_ratio_1m = indicators.get("volume_ratio_1m", 1.0)
            obv_trend_5m = indicators.get("obv_trend_5m", "neutral")
            
            # Volume confirmation for scalping (use 5m or 1m volume)
            # For scalps, we want at least 1.3x average volume (higher threshold than swings)
            volume_confirmed_5m = volume_ratio_5m >= 1.3
            volume_confirmed_1m = volume_ratio_1m >= 1.3
            volume_confirmed = volume_confirmed_5m or volume_confirmed_1m
            
            # Check 1m momentum for longs
            long_momentum_1m = price > ema_20_1m and rsi_1m < 75  # Not overbought
            
            # More reasonable entry conditions:
            # 1. Strong breakout: price > Keltner upper (original aggressive condition)
            # 2. Momentum entry: price near upper band (within 0.5%) with strong momentum
            long_breakout_1m = keltner_upper_1m > 0 and price > keltner_upper_1m
            long_breakout_5m = keltner_upper_5m > 0 and price > keltner_upper_5m
            
            # Near upper band = within 0.5% of upper band
            near_upper_1m = keltner_upper_1m > 0 and price > (keltner_upper_1m * 0.995)
            near_upper_5m = keltner_upper_5m > 0 and price > (keltner_upper_5m * 0.995)
            
            # Entry: 5m bullish trend + price above VWAP + (breakout OR near band with momentum) + VOLUME
            has_breakout = long_breakout_1m or long_breakout_5m
            has_momentum_entry = (near_upper_1m or near_upper_5m) and long_momentum_1m
            
            if (has_breakout or has_momentum_entry) and long_momentum_1m and volume_confirmed:
                # Calculate position size using TWO-LAYER SYSTEM for scalps
                stop_distance = price * self.stop_loss_pct
                
                # Base confidence for scalps (lower than swings)
                base_confidence = 0.7
                
                # Boost confidence if volume is VERY strong
                if volume_ratio_5m >= 1.5 or volume_ratio_1m >= 1.5:
                    base_confidence = 0.8
                
                # LAYER 1: Capital Allocation (scalps are smaller than swings)
                if base_confidence >= 0.8:
                    capital_allocation_pct = 0.15  # 15% for high-confidence scalps
                elif base_confidence >= 0.6:
                    capital_allocation_pct = 0.10  # 10% for medium-confidence scalps
                else:
                    capital_allocation_pct = 0.05  # 5% for low-confidence scalps
                
                # LAYER 2: Leverage (scalps use less leverage than swings)
                if base_confidence >= 0.8:
                    leverage = 2.0  # 2X for high-confidence scalps
                elif base_confidence >= 0.7:
                    leverage = 1.5  # 1.5X for medium-confidence scalps
                else:
                    leverage = 1.0  # 1X for low-confidence scalps
                
                position_size_pct = capital_allocation_pct
                
                # Calculate risk and reward
                capital_amount = equity * capital_allocation_pct
                position_notional = capital_amount * leverage
                position_btc = position_notional / price
                risk_amount = stop_distance * position_btc
                reward_amount = (price * self.profit_target_pct) * position_btc
                
                # Ensure minimum notional
                min_notional = 15.0
                if position_notional < min_notional:
                    required_capital = min_notional / leverage
                    position_size_pct = required_capital / equity
                
                # Cap at 20% for scalps (safety)
                position_size_pct = min(position_size_pct, 0.20)
                
                # Check available cash
                required_cash = equity * position_size_pct
                if available_cash < required_cash:
                    return StrategySignal(
                        action="hold",
                        size_pct=0.0,
                        reason=f"Scalp long: Insufficient cash (need ${required_cash:,.2f}, have ${available_cash:,.2f})",
                        confidence=0.0,
                        position_type="scalp"
                    )
                
                # Calculate stop loss and take profit for long
                stop_loss = price - stop_distance
                take_profit = price + (price * self.profit_target_pct)
                
                # Determine entry type for message
                if long_breakout_1m or long_breakout_5m:
                    entry_type = "breakout"
                    entry_tf = "1m" if long_breakout_1m else "5m"
                else:
                    entry_type = "momentum"
                    entry_tf = "1m" if near_upper_1m else "5m"
                
                # Volume info for scalp
                active_volume_ratio = volume_ratio_1m if volume_confirmed_1m else volume_ratio_5m
                volume_info = f"Vol: {active_volume_ratio:.2f}x"
                if active_volume_ratio >= 1.5:
                    volume_info += " [STRONG]"  # Changed from emoji for Windows compatibility
                
                # Position sizing summary for logging
                logger.info(
                    f"Scalp position sizing: Capital={capital_allocation_pct*100:.1f}% (${capital_amount:.2f}), "
                    f"Leverage={leverage:.1f}x, Notional=${position_notional:.2f}, "
                    f"Risk=${risk_amount:.2f}, Reward=${reward_amount:.2f}"
                )
                
                return StrategySignal(
                    action="long",
                    size_pct=position_size_pct,
                    reason=f"Scalp long: {entry_tf} {entry_type}, price ${price:.2f} > VWAP ${vwap_5m:.2f}, {volume_info}. Capital: {capital_allocation_pct*100:.0f}%, Leverage: {leverage:.1f}x, Risk: ${risk_amount:.2f}",
                    confidence=base_confidence,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    position_type="scalp",
                    leverage=leverage,
                    risk_amount=risk_amount,
                    reward_amount=reward_amount
                )
        
        # === SHORT SCALP ENTRY ===
        # VWAP Filter: Only short if price is below VWAP (confirms bearish intraday bias)
        elif trend_5m == "bearish" and price < vwap_5m:
            # Extract volume indicators for scalping confirmation
            volume_ratio_5m = indicators.get("volume_ratio_5m", 1.0)
            volume_ratio_1m = indicators.get("volume_ratio_1m", 1.0)
            obv_trend_5m = indicators.get("obv_trend_5m", "neutral")
            
            # Volume confirmation for scalping (use 5m or 1m volume)
            # For scalps, we want at least 1.3x average volume (higher threshold than swings)
            volume_confirmed_5m = volume_ratio_5m >= 1.3
            volume_confirmed_1m = volume_ratio_1m >= 1.3
            volume_confirmed = volume_confirmed_5m or volume_confirmed_1m
            
            # Check 1m momentum for shorts
            short_momentum_1m = price < ema_20_1m and rsi_1m > 25  # Not oversold
            
            # More reasonable entry conditions:
            # 1. Strong breakdown: price < Keltner lower (original aggressive condition)
            # 2. Momentum entry: price near lower band (within 0.5%) with strong momentum
            short_breakdown_1m = keltner_lower_1m > 0 and price < keltner_lower_1m
            short_breakdown_5m = keltner_lower_5m > 0 and price < keltner_lower_5m
            
            # Near lower band = within 0.5% of lower band
            near_lower_1m = keltner_lower_1m > 0 and price < (keltner_lower_1m * 1.005)
            near_lower_5m = keltner_lower_5m > 0 and price < (keltner_lower_5m * 1.005)
            
            # Entry: 5m bearish trend + price below VWAP + (breakdown OR near band with momentum) + VOLUME
            has_breakdown = short_breakdown_1m or short_breakdown_5m
            has_momentum_entry = (near_lower_1m or near_lower_5m) and short_momentum_1m
            
            if (has_breakdown or has_momentum_entry) and short_momentum_1m and volume_confirmed:
                # Calculate position size using TWO-LAYER SYSTEM for scalps
                stop_distance = price * self.stop_loss_pct
                
                # Base confidence for scalps (lower than swings)
                base_confidence = 0.7
                
                # Boost confidence if volume is VERY strong
                if volume_ratio_5m >= 1.5 or volume_ratio_1m >= 1.5:
                    base_confidence = 0.8
                
                # LAYER 1: Capital Allocation (scalps are smaller than swings)
                if base_confidence >= 0.8:
                    capital_allocation_pct = 0.15  # 15% for high-confidence scalps
                elif base_confidence >= 0.6:
                    capital_allocation_pct = 0.10  # 10% for medium-confidence scalps
                else:
                    capital_allocation_pct = 0.05  # 5% for low-confidence scalps
                
                # LAYER 2: Leverage (scalps use less leverage than swings)
                if base_confidence >= 0.8:
                    leverage = 2.0  # 2X for high-confidence scalps
                elif base_confidence >= 0.7:
                    leverage = 1.5  # 1.5X for medium-confidence scalps
                else:
                    leverage = 1.0  # 1X for low-confidence scalps
                
                position_size_pct = capital_allocation_pct
                
                # Calculate risk and reward
                capital_amount = equity * capital_allocation_pct
                position_notional = capital_amount * leverage
                position_btc = position_notional / price
                risk_amount = stop_distance * position_btc
                reward_amount = (price * self.profit_target_pct) * position_btc
                
                # Ensure minimum notional
                min_notional = 15.0
                if position_notional < min_notional:
                    required_capital = min_notional / leverage
                    position_size_pct = required_capital / equity
                
                # Cap at 20% for scalps (safety)
                position_size_pct = min(position_size_pct, 0.20)
                
                # Check available cash
                required_cash = equity * position_size_pct
                if available_cash < required_cash:
                    return StrategySignal(
                        action="hold",
                        size_pct=0.0,
                        reason=f"Scalp short: Insufficient cash (need ${required_cash:,.2f}, have ${available_cash:,.2f})",
                        confidence=0.0,
                        position_type="scalp"
                    )
                
                # Calculate stop loss and take profit for short
                stop_loss = price + stop_distance
                take_profit = price - (price * self.profit_target_pct)
                
                # Determine entry type for message
                if short_breakdown_1m or short_breakdown_5m:
                    entry_type = "breakdown"
                    entry_tf = "1m" if short_breakdown_1m else "5m"
                else:
                    entry_type = "momentum"
                    entry_tf = "1m" if near_lower_1m else "5m"
                
                # Volume info for scalp
                active_volume_ratio = volume_ratio_1m if volume_confirmed_1m else volume_ratio_5m
                volume_info = f"Vol: {active_volume_ratio:.2f}x"
                if active_volume_ratio >= 1.5:
                    volume_info += " [STRONG]"  # Changed from emoji for Windows compatibility
                
                # Position sizing summary for logging
                logger.info(
                    f"Scalp position sizing: Capital={capital_allocation_pct*100:.1f}% (${capital_amount:.2f}), "
                    f"Leverage={leverage:.1f}x, Notional=${position_notional:.2f}, "
                    f"Risk=${risk_amount:.2f}, Reward=${reward_amount:.2f}"
                )
                
                return StrategySignal(
                    action="short",
                    size_pct=position_size_pct,
                    reason=f"Scalp short: {entry_tf} {entry_type}, price ${price:.2f} < VWAP ${vwap_5m:.2f}, {volume_info}. Capital: {capital_allocation_pct*100:.0f}%, Leverage: {leverage:.1f}x, Risk: ${risk_amount:.2f}",
                    confidence=base_confidence,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    position_type="scalp",
                    leverage=leverage,
                    risk_amount=risk_amount,
                    reward_amount=reward_amount
                )
        
        # No clear scalp setup
        return StrategySignal(
            action="hold",
            size_pct=0.0,
            reason=f"Scalp: Waiting for entry (5m trend={trend_5m}, no breakout yet)",
            confidence=0.0,
            position_type="scalp"
        )


class SimpleEMAStrategy:
    """
    Simple EMA crossover strategy (supports both longs and shorts).
    
    Rules:
    1. Long when EMA20 > EMA50 and RSI < 70
    2. Short when EMA20 < EMA50 and RSI > 30
    3. Close when trend reverses or extreme RSI
    4. Position size: 5-10% based on signal strength
    """
    
    def analyze(self, snapshot: Any, position_size: float, equity: float) -> StrategySignal:
        """
        Analyze market and generate trading signal for longs or shorts.
        
        Args:
            snapshot: Market snapshot with price and indicators
            position_size: Current position size
            equity: Account equity
            
        Returns:
            StrategySignal with action and parameters
        """
        price = snapshot.price
        indicators = snapshot.indicators
        
        ema_20 = indicators.get("ema_20", 0)
        ema_50 = indicators.get("ema_50", 0)
        rsi_14 = indicators.get("rsi_14", 50)
        
        # If we have a LONG position, check exit
        if position_size > 0:
            # Exit if trend reverses or overbought
            if ema_20 < ema_50 or rsi_14 > 80:
                return StrategySignal(
                    action="close",
                    size_pct=1.0,
                    reason=f"Long exit: EMA20 ${ema_20:.2f} vs EMA50 ${ema_50:.2f}, RSI {rsi_14:.1f}",
                    confidence=0.8
                )
            
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason="In long position, trend intact",
                confidence=0.6
            )
        
        # If we have a SHORT position, check exit
        elif position_size < 0:
            # Exit if downtrend reverses or oversold
            if ema_20 > ema_50 or rsi_14 < 20:
                return StrategySignal(
                    action="close",
                    size_pct=1.0,
                    reason=f"Short exit: EMA20 ${ema_20:.2f} vs EMA50 ${ema_50:.2f}, RSI {rsi_14:.1f}",
                    confidence=0.8
                )
            
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason="In short position, downtrend intact",
                confidence=0.6
            )
        
        # No position - look for LONG or SHORT entry
        
        # LONG entry: EMA20 > EMA50 and RSI not overbought
        if ema_20 > ema_50 and rsi_14 < 70:
            # Calculate position size based on signal strength
            signal_strength = min((ema_20 - ema_50) / ema_50, 0.02)  # Max 2% difference
            size_pct = 0.05 + (signal_strength * 2.5)  # 5-10%
            size_pct = min(size_pct, 0.10)
            
            return StrategySignal(
                action="long",
                size_pct=size_pct,
                reason=f"Bullish: EMA20 ${ema_20:.2f} > EMA50 ${ema_50:.2f}, RSI {rsi_14:.1f}",
                confidence=0.7
            )
        
        # SHORT entry: EMA20 < EMA50 and RSI not oversold
        elif ema_20 < ema_50 and rsi_14 > 30:
            # Calculate position size based on signal strength
            signal_strength = min((ema_50 - ema_20) / ema_50, 0.02)  # Max 2% difference
            size_pct = 0.05 + (signal_strength * 2.5)  # 5-10%
            size_pct = min(size_pct, 0.10)
            
            return StrategySignal(
                action="short",
                size_pct=size_pct,
                reason=f"Bearish: EMA20 ${ema_20:.2f} < EMA50 ${ema_50:.2f}, RSI {rsi_14:.1f}",
                confidence=0.7
            )
        
        return StrategySignal(
            action="hold",
            size_pct=0.0,
            reason=f"No entry signal (EMA20 ${ema_20:.2f}, EMA50 ${ema_50:.2f}, RSI {rsi_14:.1f})",
            confidence=0.0
        )
