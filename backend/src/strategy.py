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
        
        # Extract indicators
        ema_50 = indicators.get("ema_50", 0)
        atr_14 = indicators.get("atr_14", 0)
        keltner_upper = indicators.get("keltner_upper", 0)
        keltner_lower = indicators.get("keltner_lower", 0)
        
        # Calculate available cash for money management
        position_value = position_size * price if position_size > 0 else 0.0
        available_cash = equity - position_value
        
        # If we don't have required indicators, hold
        if not all([ema_50, atr_14]):
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason="Missing required indicators (EMA50, ATR14)",
                confidence=0.0
            )
        
        # Rule 1: Trend filter - only long when price > EMA50
        in_uptrend = price > ema_50
        
        # If we have a position, check exit conditions (including stop loss)
        if position_size > 0:
            # Exit if trend reverses (price drops below EMA50)
            if not in_uptrend:
                return StrategySignal(
                    action="close",
                    size_pct=1.0,
                    reason=f"Trend reversal: price ${price:.2f} < EMA50 ${ema_50:.2f}",
                    confidence=0.9
                )
            
            # Otherwise hold
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=f"In position, trend intact (price ${price:.2f} > EMA50 ${ema_50:.2f})",
                confidence=0.7
            )
        
        # No position - look for entry
        if not in_uptrend:
            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason=f"No uptrend: price ${price:.2f} < EMA50 ${ema_50:.2f}",
                confidence=0.0
            )
        
        # Rule 2: Volatility breakout - price breaks above Keltner upper band
        if keltner_upper > 0 and price > keltner_upper:
            # Avoid re-entering immediately after exit
            if self.last_signal_price and abs(price - self.last_signal_price) / price < 0.005:
                return StrategySignal(
                    action="hold",
                    size_pct=0.0,
                    reason="Too close to last signal, avoiding chop",
                    confidence=0.3
                )
            
            # Calculate stop loss and take profit
            stop_distance = atr_14 * self.stop_atr_multiplier
            stop_loss = price - stop_distance
            take_profit = price + (stop_distance * 2)  # 2R
            
            # Calculate position size based on 1% risk
            risk_amount = equity * 0.01
            position_size_pct = min(risk_amount / stop_distance / price, 0.10)  # Cap at 10%
            
            # Money management: Check if we have enough available cash
            required_cash = equity * position_size_pct
            if available_cash < required_cash:
                return StrategySignal(
                    action="hold",
                    size_pct=0.0,
                    reason=f"Insufficient cash: need ${required_cash:,.2f}, have ${available_cash:,.2f}",
                    confidence=0.0
                )
            
            # Additional safety: Don't trade if available cash is too low (less than $100 buffer)
            if available_cash < 100:
                return StrategySignal(
                    action="hold",
                    size_pct=0.0,
                    reason=f"Available cash too low: ${available_cash:,.2f} (need at least $100 buffer)",
                    confidence=0.0
                )
            
            self.last_signal_price = price
            
            return StrategySignal(
                action="long",
                size_pct=position_size_pct,
                reason=f"ATR breakout: price ${price:.2f} > Keltner ${keltner_upper:.2f}, uptrend confirmed. SL: ${stop_loss:.2f}, TP: ${take_profit:.2f}",
                confidence=0.8,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
        
        # No signal
        return StrategySignal(
            action="hold",
            size_pct=0.0,
            reason=f"Waiting for breakout (price ${price:.2f}, Keltner upper ${keltner_upper:.2f})",
            confidence=0.0
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
