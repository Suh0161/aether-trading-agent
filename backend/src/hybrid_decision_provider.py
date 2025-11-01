"""Hybrid decision provider: Rule-based strategy + AI filter."""

import logging
from openai import OpenAI
from src.models import MarketSnapshot
from src.strategy import ATRBreakoutStrategy, SimpleEMAStrategy, StrategySignal

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
        
        # Initialize strategy
        if strategy_type == "atr":
            self.strategy = ATRBreakoutStrategy()
            logger.info("Using ATR Breakout Strategy")
        else:
            self.strategy = SimpleEMAStrategy()
            logger.info("Using Simple EMA Strategy")
    
    def get_decision(self, snapshot: MarketSnapshot, position_size: float, equity: float) -> str:
        """
        Get trading decision using hybrid approach.
        
        Args:
            snapshot: Current market snapshot
            position_size: Current position size
            equity: Account equity
            
        Returns:
            JSON string with decision
        """
        # Step 1: Get signal from rule-based strategy
        signal = self.strategy.analyze(snapshot, position_size, equity)
        
        logger.info(f"Strategy signal: {signal.action} (confidence: {signal.confidence:.2f})")
        logger.info(f"Strategy reason: {signal.reason}")
        
        # Step 2: If strategy says hold/close, no need for AI filter
        if signal.action in ["hold", "close"]:
            return self._format_decision(signal)
        
        # Step 3: Strategy wants to enter - ask AI to filter
        if signal.action in ["long", "short"]:
            ai_approved = self._ai_filter(snapshot, signal, position_size, equity)
            
            if not ai_approved:
                # AI vetoed the trade
                logger.warning("AI filter VETOED the trade")
                return '{"action": "hold", "size_pct": 0.0, "reason": "AI filter vetoed: ' + signal.reason + '"}'
            
            logger.info("AI filter APPROVED the trade")
            return self._format_decision(signal)
        
        # Fallback
        return '{"action": "hold", "size_pct": 0.0, "reason": "Unknown signal"}'
    
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
            
            ai_response = response.choices[0].message.content.strip().lower()
            
            # Parse AI response (looking for "approve" or "veto")
            if "veto" in ai_response or "reject" in ai_response or "no" in ai_response[:10]:
                logger.info(f"AI response: {ai_response[:200]}")
                return False
            
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

MARKET CONTEXT:
- Current price: ${snapshot.price:,.2f}
- EMA20: ${indicators.get('ema_20', 0):,.2f}
- EMA50: ${indicators.get('ema_50', 0):,.2f}
- RSI(14): {indicators.get('rsi_14', 50):.1f}
- ATR(14): ${indicators.get('atr_14', 0):,.2f}
- Keltner Upper: ${indicators.get('keltner_upper', 0):,.2f}

YOUR JOB:
Decide if this trade setup is likely to FAIL or succeed.

VETO if:
- Fake breakout / bull trap likely
- Market regime changed (news, funding, etc.)
- Extreme volatility / rug risk
- Overbought conditions
- Insufficient available cash (if required_cash > available_cash)
- Leverage too high (if leverage_used > 2.0x)

APPROVE if:
- Clean breakout with follow-through
- Trend is strong
- Risk/reward is favorable
- Enough available cash to execute trade
- Account can afford the position size

OUTPUT FORMAT:
First word must be either "APPROVE" or "VETO", then brief reason.

Example: "APPROVE - clean breakout with strong momentum"
Example: "VETO - likely fake breakout, RSI overbought"

Your decision:"""
        
        return prompt
    
    def _format_decision(self, signal: StrategySignal) -> str:
        """Format strategy signal as JSON decision."""
        import json
        
        decision = {
            "action": signal.action,
            "size_pct": signal.size_pct,
            "reason": signal.reason
        }
        
        # Include stop loss and take profit if available
        if signal.stop_loss is not None:
            decision["stop_loss"] = signal.stop_loss
        if signal.take_profit is not None:
            decision["take_profit"] = signal.take_profit
        
        return json.dumps(decision)
