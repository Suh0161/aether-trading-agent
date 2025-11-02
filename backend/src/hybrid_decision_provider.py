"""Hybrid decision provider: Rule-based strategy + AI filter."""

import logging
from openai import OpenAI
from src.models import MarketSnapshot
from src.strategy import ATRBreakoutStrategy, SimpleEMAStrategy, ScalpingStrategy, StrategySignal

logger = logging.getLogger(__name__)


class HybridDecisionProvider:
    """
    Hybrid approach: Rule-based strategy generates signals, AI filters them.
    
    This is the "crypto-realistic" approach:
    1. Strategy (ATR breakout) generates trade signals
    2. AI (DeepSeek) acts as risk filter to veto bad setups
    3. Only execute if both strategy AND AI approve
    """
    
    def __init__(self, api_key: str, strategy_type: str = "atr"):
        """
        Initialize hybrid decision provider.
        
        Args:
            api_key: DeepSeek API key
            strategy_type: "atr" for ATR breakout, "ema" for simple EMA
        """
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        
        # Initialize strategies
        if strategy_type == "atr":
            self.strategy = ATRBreakoutStrategy()
            logger.info("Using ATR Breakout Strategy (swing)")
        else:
            self.strategy = SimpleEMAStrategy()
            logger.info("Using Simple EMA Strategy")
        
        # Initialize scalping strategy for fallback
        self.scalping_strategy = ScalpingStrategy()
        logger.info("Scalping strategy initialized (fallback mode)")
    
    def get_decision(self, snapshot: MarketSnapshot, position_size: float, equity: float) -> str:
        """
        Get trading decision using hybrid approach with adaptive fallback.
        
        Adaptive Strategy:
        1. If we have a position, route to the correct strategy based on position type
        2. If no position, try swing trading first, then scalping as fallback
        3. AI filters all entry signals
        
        Args:
            snapshot: Current market snapshot
            position_size: Current position size
            equity: Account equity
            
        Returns:
            JSON string with decision
        """
        # Check if we have an existing position and its type
        position_type = None
        if position_size != 0:
            # Import here to avoid circular dependency
            import api_server
            if hasattr(api_server, 'loop_controller_instance') and api_server.loop_controller_instance:
                position_type = api_server.loop_controller_instance.position_types.get(snapshot.symbol)
        
        # If we have a SCALP position, use scalping strategy for exit logic
        if position_size != 0 and position_type == "scalp":
            logger.info(f"Existing SCALP position detected, using scalping strategy for management")
            return self._check_scalping_fallback(snapshot, position_size, equity)
        
        # Step 1: Get signal from swing strategy (primary)
        swing_signal = self.strategy.analyze(snapshot, position_size, equity)
        
        logger.debug(f"Swing signal: {swing_signal.action} (confidence: {swing_signal.confidence:.2f}, type: {swing_signal.position_type})")
        logger.debug(f"Swing reason: {swing_signal.reason}")
        
        # Step 2: If swing strategy has a position or wants to close, use it directly
        if swing_signal.action in ["close"]:
            # Always respect close signals
            return self._format_decision(swing_signal)
        
        # Step 3: If swing strategy wants to enter, ask AI to filter
        if swing_signal.action in ["long", "short"]:
            ai_approved = self._ai_filter(snapshot, swing_signal, position_size, equity)
            
            if not ai_approved:
                # AI vetoed the swing trade - check scalping as fallback
                logger.debug("AI filter VETOED swing trade, checking scalping fallback")
                return self._check_scalping_fallback(snapshot, position_size, equity)
            
            logger.debug("AI filter APPROVED swing trade")
            return self._format_decision(swing_signal)
        
        # Step 4: Swing strategy says "hold" - check if we should try scalping
        # Only fall back to scalping if:
        # - No current position (position_size == 0)
        # - Swing confidence is very low (0.0) - meaning no swing setup available
        # - This allows scalping when swing has no opportunities
        
        if swing_signal.action == "hold" and position_size == 0 and swing_signal.confidence == 0.0:
            # No swing opportunity - try scalping as fallback
            logger.info("No swing opportunity detected (confidence=0.0), checking scalping fallback")
            return self._check_scalping_fallback(snapshot, position_size, equity)
        
        # Step 5: Swing strategy says "hold" but we're in a swing position
        # Or swing strategy has some confidence but no entry yet
        # In these cases, respect the swing hold signal
        return self._format_decision(swing_signal)
    
    def _check_scalping_fallback(self, snapshot: MarketSnapshot, position_size: float, equity: float) -> str:
        """
        Check scalping strategy as fallback when swing has no opportunities.
        
        Args:
            snapshot: Current market snapshot
            position_size: Current position size
            equity: Account equity
            
        Returns:
            JSON string with decision
        """
        # Get scalping signal
        scalp_signal = self.scalping_strategy.analyze(snapshot, position_size, equity)
        
        logger.debug(f"Scalp signal: {scalp_signal.action} (confidence: {scalp_signal.confidence:.2f})")
        logger.debug(f"Scalp reason: {scalp_signal.reason}")
        
        # If scalping wants to close (we're in a scalp position), use it
        if scalp_signal.action == "close":
            return self._format_decision(scalp_signal)
        
        # If scalping wants to enter, ask AI to filter
        if scalp_signal.action in ["long", "short"]:
            ai_approved = self._ai_filter(snapshot, scalp_signal, position_size, equity)
            
            if not ai_approved:
                logger.warning("AI filter VETOED scalp trade")
                return '{"action": "hold", "size_pct": 0.0, "reason": "AI filter vetoed scalp: ' + scalp_signal.reason + '", "position_type": "scalp"}'
            
            logger.debug("AI filter APPROVED scalp trade")
            return self._format_decision(scalp_signal)
        
        # Scalping also says hold - return hold signal
        return self._format_decision(scalp_signal)
    
    def _get_smart_leverage(self, equity: float) -> float:
        """Get smart max leverage for current equity (matches risk_manager logic)."""
        if equity < 500:
            return 1.0
        elif equity < 1000:
            return 1.5
        elif equity < 5000:
            return 2.0
        elif equity < 10000:
            return 2.5
        else:
            return 3.0
    
    def _ai_filter(self, snapshot: MarketSnapshot, signal: StrategySignal, position_size: float, equity: float) -> bool:
        """
        Use AI to filter/veto strategy signals.
        
        Args:
            snapshot: Market snapshot
            signal: Strategy signal to filter
            position_size: Current position
            equity: Account equity
            
        Returns:
            True if AI approves, False if AI vetoes
        """
        try:
            # Build prompt for AI filter
            prompt = self._build_filter_prompt(snapshot, signal, position_size, equity)
            
            # Call DeepSeek
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                timeout=10.0
            )
            
            ai_response = response.choices[0].message.content.strip()
            ai_response_lower = ai_response.lower()
            
            # Parse AI response (looking for "approve" or "veto")
            # Check first word to avoid false positives
            first_word = ai_response_lower.split()[0] if ai_response_lower else ""
            
            if first_word in ["veto", "reject", "no"]:
                # Fix Unicode encoding issue: replace ≥ with >= for Windows console
                safe_response = ai_response[:150].replace('\u2265', '>=').replace('\u2264', '<=').replace('\u2192', '->')
                logger.debug(f"AI VETOED: {safe_response}")
                return False
            elif first_word == "approve":
                # Fix Unicode encoding issue: replace ≥ with >= for Windows console
                safe_response = ai_response[:150].replace('\u2265', '>=').replace('\u2264', '<=').replace('\u2192', '->')
                logger.debug(f"AI APPROVED: {safe_response}")
                return True
            else:
                # Fallback: check if veto/reject appears early in response
                if "veto" in ai_response_lower[:50] or "reject" in ai_response_lower[:50]:
                    # Fix Unicode encoding issue: replace ≥ with >= for Windows console
                    safe_response = ai_response[:150].replace('\u2265', '>=').replace('\u2264', '<=').replace('\u2192', '->')
                    logger.debug(f"AI VETOED (fallback): {safe_response}")
                    return False
                # Default to approve if unclear
                logger.warning(f"AI response unclear, defaulting to APPROVE: {ai_response[:100]}")
                return True
            
        except Exception as e:
            logger.error(f"AI filter failed: {e}")
            # On error, approve by default (don't block strategy)
            return True
    
    def _build_filter_prompt(self, snapshot: MarketSnapshot, signal: StrategySignal, position_size: float, equity: float) -> str:
        """Build prompt for AI filter."""
        indicators = snapshot.indicators
        
        # Calculate money management metrics
        position_value = position_size * snapshot.price if position_size > 0 else 0.0
        available_cash = equity - position_value
        required_cash = equity * signal.size_pct
        leverage_used = (position_value / equity) if equity > 0 else 0.0
        
        prompt = f"""You are a risk filter for a crypto trading bot.

STRATEGY SIGNAL:
Action: {signal.action.upper()}
Entry price: ${snapshot.price:,.2f}
Position size: {signal.size_pct * 100:.1f}% of equity (${equity * signal.size_pct:,.2f})
{'Stop loss: $' + f'{signal.stop_loss:,.2f}' if signal.stop_loss is not None else 'Stop loss: Not set'}
{'Take profit: $' + f'{signal.take_profit:,.2f}' if signal.take_profit is not None else 'Take profit: Not set'}
Reason: {signal.reason}

ACCOUNT STATUS (MONEY MANAGEMENT):
- Total equity: ${equity:,.2f}
- Current position value: ${position_value:,.2f}
- Available cash: ${available_cash:,.2f}
- Required cash for this trade: ${required_cash:,.2f}
- Current leverage: {leverage_used:.2f}x
- Smart max leverage (adaptive): {self._get_smart_leverage(equity):.2f}x
  (System uses adaptive leverage: smaller accounts = more conservative)

MARKET CONTEXT (Multi-Timeframe Analysis):
- Current price: ${snapshot.price:,.2f}
- Position Type: {signal.position_type.upper()}

SWING TIMEFRAMES (for swing trades):
- Daily trend: {indicators.get('trend_1d', 'unknown')} (EMA50: ${indicators.get('ema_50_1d', 0):,.2f})
- 4h trend: {indicators.get('trend_4h', 'unknown')} (EMA50: ${indicators.get('ema_50_4h', 0):,.2f}, RSI {indicators.get('rsi_14_4h', 50):.1f})
- Primary (1h): EMA20 ${indicators.get('ema_20', 0):,.2f}, EMA50 ${indicators.get('ema_50', 0):,.2f}, RSI {indicators.get('rsi_14', 50):.1f}
- 15m entry: Trend {indicators.get('trend_15m', 'unknown')}, Keltner Upper ${indicators.get('keltner_upper_15m', 0):,.2f}, RSI {indicators.get('rsi_14_15m', 50):.1f}
- ATR(14): ${indicators.get('atr_14', 0):,.2f}
- Primary Keltner Upper: ${indicators.get('keltner_upper', 0):,.2f}

SCALPING TIMEFRAMES (for scalp trades):
- 5m trend: {indicators.get('trend_5m', 'unknown')}, Keltner Upper ${indicators.get('keltner_upper_5m', 0):,.2f}, RSI {indicators.get('rsi_14_5m', 50):.1f}, VWAP ${indicators.get('vwap_5m', 0):,.2f}
- 1m trend: {indicators.get('trend_1m', 'unknown')}, Keltner Upper ${indicators.get('keltner_upper_1m', 0):,.2f}, RSI {indicators.get('rsi_14_1m', 50):.1f}, VWAP ${indicators.get('vwap_1m', 0):,.2f}
- **VWAP Position:** Price ${snapshot.price:,.2f} is {'ABOVE' if snapshot.price > indicators.get('vwap_5m', snapshot.price) else 'BELOW'} 5m VWAP (${indicators.get('vwap_5m', 0):,.2f})

SUPPORT/RESISTANCE LEVELS (Key Price Zones):
- Pivot: ${indicators.get('pivot', 0):,.2f}
- Resistance: R1=${indicators.get('resistance_1', 0):,.2f}, R2=${indicators.get('resistance_2', 0):,.2f}, R3=${indicators.get('resistance_3', 0):,.2f}
- Support: S1=${indicators.get('support_1', 0):,.2f}, S2=${indicators.get('support_2', 0):,.2f}, S3=${indicators.get('support_3', 0):,.2f}
- Swing High: ${indicators.get('swing_high', 0):,.2f} (recent resistance)
- Swing Low: ${indicators.get('swing_low', 0):,.2f} (recent support)

VOLUME ANALYSIS (Breakout Confirmation):
- 1h Volume: {indicators.get('volume_ratio_1h', 1.0):.2f}x average ({'STRONG' if indicators.get('volume_ratio_1h', 1.0) >= 1.5 else 'MODERATE' if indicators.get('volume_ratio_1h', 1.0) >= 1.2 else 'WEAK'})
- 5m Volume: {indicators.get('volume_ratio_5m', 1.0):.2f}x average ({'STRONG' if indicators.get('volume_ratio_5m', 1.0) >= 1.5 else 'MODERATE' if indicators.get('volume_ratio_5m', 1.0) >= 1.3 else 'WEAK'})
- Volume Trend: {indicators.get('volume_trend_1h', 'stable')} (1h), {indicators.get('volume_trend_5m', 'stable')} (5m)
- OBV (Money Flow): {indicators.get('obv_trend_1h', 'neutral')} (1h), {indicators.get('obv_trend_5m', 'neutral')} (5m)

YOUR JOB:
You are a RISK FILTER, not a strategy. The rule-based strategy has already identified this opportunity.
Your job is to VETO only if there are SERIOUS red flags. When in doubt, APPROVE.

CRITICAL VETO CONDITIONS (must veto):
- Insufficient available cash (required_cash > available_cash) - CANNOT execute
- Leverage exceeds smart max leverage - TOO RISKY
- Account too small for position size (< $50 total) - TOO SMALL

STRONG VETO CONDITIONS (should veto):
- For LONGS: Extreme overbought (RSI > 80 on multiple timeframes) - LIKELY REVERSAL
- For SHORTS: Extreme oversold (RSI < 20 on multiple timeframes) - LIKELY REVERSAL
- For SWING LONGS: 1d or 4h trend is bearish (conflicts with long entry) - WRONG DIRECTION
- For SWING SHORTS: 1d or 4h trend is bullish (conflicts with short entry) - WRONG DIRECTION
- For SCALP LONGS: 5m trend is bearish OR price below VWAP (conflicts with long) - WRONG DIRECTION
- For SCALP SHORTS: 5m trend is bullish OR price above VWAP (conflicts with short) - WRONG DIRECTION
- **For LONGS: Price at/near resistance (R1, R2, R3, swing high) - LIKELY REJECTION**
- **For SHORTS: Price at/near support (S1, S2, S3, swing low) - LIKELY BOUNCE**
- **Breakout with WEAK volume (< 1.2x avg for swings, < 1.3x for scalps) - LIKELY FAKE BREAKOUT**
- Obvious fake breakout/breakdown pattern (price just rejected) - TRAP

APPROVE CONDITIONS (default to approve):
- For SWING LONGS: Multi-TF alignment bullish (1d/4h), RSI < 75, NOT at resistance, volume ≥ 1.2x
- For SWING SHORTS: Multi-TF alignment bearish (1d/4h), RSI > 25, NOT at support, volume ≥ 1.2x
- For SCALP LONGS: 5m bullish + price ABOVE VWAP + NOT at resistance + volume ≥ 1.3x
- For SCALP SHORTS: 5m bearish + price BELOW VWAP + NOT at support + volume ≥ 1.3x
- **BEST LONGS: Entry at/near support (S1, S2, swing low) WITH VOLUME SPIKE - HIGH PROBABILITY**
- **BEST SHORTS: Entry at/near resistance (R1, R2, swing high) WITH VOLUME SPIKE - HIGH PROBABILITY**
- **STRONG volume (≥ 1.5x) + bullish OBV = EXTRA CONFIDENCE for longs**
- **STRONG volume (≥ 1.5x) + bearish OBV = EXTRA CONFIDENCE for shorts**
- Available cash is sufficient
- Leverage is within limits
- Position size is reasonable
- Clean breakout/breakdown with follow-through potential
- Even if not perfect, if no critical red flags exist → APPROVE

IMPORTANT:
- The strategy has already done the analysis and found this setup
- You are just a safety check, not the primary decision maker
- APPROVE by default unless you see SERIOUS problems
- Don't be overly conservative - trust the strategy unless there's a real issue

OUTPUT FORMAT:
First word MUST be either "APPROVE" or "VETO", then brief reason (max 10 words).

SWING examples:
Example: "APPROVE - multi-TF bullish, clean breakout, RSI 65, 1.4x volume, cash OK"
Example: "VETO - RSI 85 overbought on 1h/4h, reversal likely"
Example: "APPROVE - strong 1.6x volume, bullish OBV, broke R1, continuation setup"

SCALP examples:
Example: "APPROVE - price above VWAP, bounced from S1, 1.5x volume spike"
Example: "VETO - price at R1 resistance, weak 0.9x volume, likely fake"
Example: "APPROVE - rejected at swing high, below VWAP, 1.4x volume, short valid"

S/R + Volume examples:
Example: "APPROVE - bounced from swing low $109.5k with 1.7x volume, support confirmed"
Example: "VETO - price at R2 $111k resistance, weak volume, likely rejection"
Example: "APPROVE - broke above R1 with strong 1.8x volume, OBV bullish, continuation"

General:
Example: "VETO - insufficient cash, need $500 have $100"

Your decision:"""
        
        return prompt
    
    def _format_decision(self, signal: StrategySignal) -> str:
        """Format strategy signal as JSON decision."""
        import json
        
        decision = {
            "action": signal.action,
            "size_pct": signal.size_pct,
            "reason": signal.reason,
            "position_type": signal.position_type
        }
        
        # Include stop loss and take profit if available
        if signal.stop_loss is not None:
            decision["stop_loss"] = signal.stop_loss
        if signal.take_profit is not None:
            decision["take_profit"] = signal.take_profit
        
        return json.dumps(decision)
