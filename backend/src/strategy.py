"""Trading strategies for the Autonomous Trading Agent."""

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class StrategySignal:
    """Signal from a trading strategy."""
    action: str  # "long" | "short" | "close" | "hold"
    size_pct: float  # 0.0 to 1.0
    reason: str
    confidence: float  # 0.0 to 1.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_type: str = "swing"  # "swing" | "scalp" - indicates trade duration style


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
        
        # Multi-timeframe trend confirmation
        # Rule 1: Higher timeframes must be bullish for long trades
        higher_tf_bullish = trend_1d == "bullish" and trend_4h == "bullish"
        # Rule 2: Primary timeframe (1h) trend
        primary_uptrend = price > ema_50
        # Combined trend filter
        in_uptrend = higher_tf_bullish and primary_uptrend
        
        # If we have a position, check exit conditions (including stop loss)
        if position_size > 0:
            # Exit if trend reverses (price drops below EMA50)
            if not in_uptrend:
                return StrategySignal(
                    action="close",
                    size_pct=1.0,
                    reason=f"Trend reversal: price ${price:.2f} < EMA50 ${ema_50:.2f}",
                    confidence=0.9,
                    position_type="swing"
                )
            
            # Otherwise hold
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=f"In position, trend intact (price ${price:.2f} > EMA50 ${ema_50:.2f})",
                confidence=0.7,
                position_type="swing"
            )
        
        # No position - look for entry
        if not in_uptrend:
            reason = f"No uptrend alignment: 1D={trend_1d}, 4H={trend_4h}, 1H={'bullish' if primary_uptrend else 'bearish'}"
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=reason,
                confidence=0.0,
                position_type="swing"
            )
        
        # Rule 2: Multi-timeframe entry confirmation
        # Higher TF confirms trend, lower TF (15m) provides entry timing
        # Entry: Price breaks above 15m Keltner upper (precise timing)
        # AND higher TFs are bullish (trend confirmation)
        
        # Check entry on 15m timeframe (precise timing)
        entry_signal_15m = keltner_upper_15m > 0 and price > keltner_upper_15m
        entry_trend_15m = trend_15m == "bullish"
        
        # Also check primary timeframe breakout for confirmation
        primary_breakout = keltner_upper > 0 and price > keltner_upper
        
        # Entry condition: Higher TF bullish + 15m breakout OR primary breakout
        entry_timeframe = None
        entry_keltner = 0
        
        if entry_signal_15m and entry_trend_15m and higher_tf_bullish:
            # Use 15m for precise entry timing (preferred method)
            entry_keltner = keltner_upper_15m
            entry_timeframe = "15m"
        elif primary_breakout and higher_tf_bullish:
            # Fallback to primary timeframe breakout
            entry_keltner = keltner_upper
            entry_timeframe = "1h"
        else:
            # No entry signal yet - this is a "swing_hold" (could scalp instead)
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=f"Waiting for entry: Higher TFs={trend_1d}/{trend_4h}, 15m breakout={entry_signal_15m}, Primary breakout={primary_breakout}",
                confidence=0.0,
                position_type="swing"
            )
        
        # Entry confirmed - proceed with trade setup
        if entry_timeframe:
            # Avoid re-entering immediately after exit
            if self.last_signal_price and abs(price - self.last_signal_price) / price < 0.005:
                return StrategySignal(
                    action="hold",
                    size_pct=0.0,
                    reason="Too close to last signal, avoiding chop",
                    confidence=0.3,
                    position_type="swing"
                )
            
            # Calculate stop loss and take profit
            stop_distance = atr_14 * self.stop_atr_multiplier
            stop_loss = price - stop_distance
            take_profit = price + (stop_distance * 2)  # 2R
            
            # Smart position sizing: 1% risk per trade
            # This means if stop loss hits, you only lose 1% of equity
            # Formula: risk_amount / stop_distance / price = position_size_pct
            # Example: $10k equity, 1% risk = $100 risk, $500 stop distance, $50k price
            #          = $100 / $500 / $50k = 0.004 = 0.4% position size
            # Cap at 10% to prevent over-concentration (risk manager will also check leverage)
            risk_amount = equity * 0.01
            position_size_pct = min(risk_amount / stop_distance / price, 0.10)  # Cap at 10%
            
            # Money management: Check if we have enough available cash
            required_cash = equity * position_size_pct
            if available_cash < required_cash:
                return StrategySignal(
                    action="hold",
                    size_pct=0.0,
                    reason=f"Insufficient cash: need ${required_cash:,.2f}, have ${available_cash:,.2f}",
                    confidence=0.0,
                    position_type="swing"
                )
            
            # Additional safety: Don't trade if available cash is too low (less than $100 buffer)
            if available_cash < 100:
                return StrategySignal(
                    action="hold",
                    size_pct=0.0,
                    reason=f"Available cash too low: ${available_cash:,.2f} (need at least $100 buffer)",
                    confidence=0.0,
                    position_type="swing"
                )
            
            self.last_signal_price = price
            
            # Multi-timeframe confirmation in reason
            timeframe_info = f"Trend: 1D={trend_1d}, 4H={trend_4h}, Entry: {entry_timeframe}"
            
            return StrategySignal(
                action="long",
                size_pct=position_size_pct,
                reason=f"Multi-TF breakout: price ${price:.2f} > {entry_timeframe} Keltner ${entry_keltner:.2f}. {timeframe_info}. SL: ${stop_loss:.2f}, TP: ${take_profit:.2f}",
                confidence=0.85,  # Higher confidence with multi-TF confirmation
                stop_loss=stop_loss,
                take_profit=take_profit,
                position_type="swing"
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
        
        ema_20_1m = indicators.get("ema_20_1m", 0)
        ema_50_1m = indicators.get("ema_50_1m", 0)
        rsi_1m = indicators.get("rsi_14_1m", 50)
        trend_1m = indicators.get("trend_1m", "bearish")
        keltner_upper_1m = indicators.get("keltner_upper_1m", 0)
        
        # Calculate available cash
        position_value = position_size * price if position_size > 0 else 0.0
        available_cash = equity - position_value
        
        # If we have a position, check exit conditions
        if position_size > 0:
            # Quick exit: Profit target or stop loss
            # Note: Stop loss/take profit monitoring is handled in loop_controller
            # Here we just check if trend reversed
            if trend_5m == "bearish" or trend_1m == "bearish":
                return StrategySignal(
                    action="close",
                    size_pct=1.0,
                    reason=f"Scalp exit: Trend reversed on scalping TF (5m={trend_5m}, 1m={trend_1m})",
                    confidence=0.8,
                    position_type="scalp"
                )
            
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=f"In scalp position, trend intact",
                confidence=0.6,
                position_type="scalp"
            )
        
        # No position - look for scalping entry
        # Entry conditions: Quick momentum breakout on lower TFs
        # 1. 5m trend must be bullish (primary scalping TF)
        # 2. 1m shows momentum (price above EMA20, RSI not overbought)
        # 3. Price breaks above 1m or 5m Keltner upper (quick breakout)
        
        if trend_5m != "bullish":
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=f"No scalp entry: 5m trend={trend_5m}",
                confidence=0.0,
                position_type="scalp"
            )
        
        # Check 1m momentum
        momentum_1m = price > ema_20_1m and rsi_1m < 75  # Not overbought
        breakout_1m = keltner_upper_1m > 0 and price > keltner_upper_1m
        breakout_5m = keltner_upper_5m > 0 and price > keltner_upper_5m
        
        # Entry: 5m bullish trend + (1m breakout OR 5m breakout) + momentum
        if (breakout_1m or breakout_5m) and momentum_1m:
            # Calculate position size (smaller for scalping - max 3% of equity)
            # Risk-based sizing: 1% risk per scalp trade
            stop_distance = price * self.stop_loss_pct
            risk_amount = equity * 0.01
            position_size_pct = min(risk_amount / stop_distance / price, 0.03)  # Cap at 3% for scalps
            
            # Check available cash
            required_cash = equity * position_size_pct
            if available_cash < required_cash:
                return StrategySignal(
                    action="hold",
                    size_pct=0.0,
                    reason=f"Scalp: Insufficient cash (need ${required_cash:,.2f}, have ${available_cash:,.2f})",
                    confidence=0.0,
                    position_type="scalp"
                )
            
            # Calculate stop loss and take profit
            stop_loss = price - stop_distance
            take_profit = price + (price * self.profit_target_pct)
            
            entry_tf = "1m" if breakout_1m else "5m"
            
            return StrategySignal(
                action="long",
                size_pct=position_size_pct,
                reason=f"Scalp entry: {entry_tf} breakout (price ${price:.2f}), momentum confirmed. SL: ${stop_loss:.2f}, TP: ${take_profit:.2f}",
                confidence=0.7,
                stop_loss=stop_loss,
                take_profit=take_profit,
                position_type="scalp"
            )
        
        return StrategySignal(
            action="hold",
            size_pct=0.0,
            reason=f"Scalp: Waiting for breakout (5m trend OK, no 1m/5m breakout yet)",
            confidence=0.0,
            position_type="scalp"
        )


class SimpleEMAStrategy:
    """
    Simple EMA crossover strategy (current system improved).
    
    Rules:
    1. Long when EMA20 > EMA50 and RSI < 70
    2. Close when EMA20 < EMA50 or RSI > 80
    3. Position size: 5-10% based on signal strength
    """
    
    def analyze(self, snapshot: Any, position_size: float, equity: float) -> StrategySignal:
        """
        Analyze market and generate trading signal.
        
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
        
        # If we have a position, check exit
        if position_size > 0:
            # Exit if trend reverses or overbought
            if ema_20 < ema_50 or rsi_14 > 80:
                return StrategySignal(
                    action="close",
                    size_pct=1.0,
                    reason=f"Exit signal: EMA20 ${ema_20:.2f} vs EMA50 ${ema_50:.2f}, RSI {rsi_14:.1f}",
                    confidence=0.8
                )
            
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason="In position, trend intact",
                confidence=0.6
            )
        
        # Look for entry
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
        
        return StrategySignal(
            action="hold",
            size_pct=0.0,
            reason=f"No entry signal (EMA20 ${ema_20:.2f}, EMA50 ${ema_50:.2f}, RSI {rsi_14:.1f})",
            confidence=0.0
        )
