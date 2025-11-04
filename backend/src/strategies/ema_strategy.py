"""Simple EMA crossover strategy."""

from typing import Any

from src.strategy import StrategySignal


class SimpleEMAStrategy:
    """
    Simple EMA crossover strategy (supports both longs and shorts).

    Rules:
    1. Long when EMA20 > EMA50 and RSI < 70
    2. Short when EMA20 < EMA50 and RSI > 30
    3. Close when trend reverses or extreme RSI
    4. Position size: 5-10% based on signal strength
    """

    def analyze(self, snapshot: Any, position_size: float, equity: float, suppress_logs: bool = False) -> StrategySignal:
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
                    confidence=0.8,
                    symbol=snapshot.symbol
                )

            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason="In long position, trend intact",
                confidence=0.6,
                symbol=snapshot.symbol
            )

        # If we have a SHORT position, check exit
        elif position_size < 0:
            # Exit if downtrend reverses or oversold
            if ema_20 > ema_50 or rsi_14 < 20:
                return StrategySignal(
                    action="close",
                    size_pct=1.0,
                    reason=f"Short exit: EMA20 ${ema_20:.2f} vs EMA50 ${ema_50:.2f}, RSI {rsi_14:.1f}",
                    confidence=0.8,
                    symbol=snapshot.symbol
                )

            return StrategySignal(
                action="hold",
                size_pct=0.0,
                reason="In short position, downtrend intact",
                confidence=0.6,
                symbol=snapshot.symbol
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
                confidence=0.7,
                symbol=snapshot.symbol
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
                confidence=0.7,
                symbol=snapshot.symbol
            )

        return StrategySignal(
            action="hold",
            size_pct=0.0,
            reason=f"No entry signal (EMA20 ${ema_20:.2f}, EMA50 ${ema_50:.2f}, RSI {rsi_14:.1f})",
            confidence=0.0,
            symbol=snapshot.symbol
        )
