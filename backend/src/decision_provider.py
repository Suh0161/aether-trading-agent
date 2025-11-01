"""Decision provider interface and implementations for the Autonomous Trading Agent."""

from abc import ABC, abstractmethod
from openai import OpenAI
from src.models import MarketSnapshot


class DecisionProvider(ABC):
    """Abstract base class for LLM decision providers."""
    
    @abstractmethod
    def get_decision(self, snapshot: MarketSnapshot, position_size: float, equity: float) -> str:
        """
        Generate a trading decision based on market data and current position.
        
        Args:
            snapshot: Current market snapshot with price and indicators
            position_size: Current position size (positive for long, negative for short, 0 for flat)
            equity: Current account equity in quote currency
            
        Returns:
            str: Raw LLM response as string (should be JSON format)
        """
        pass


class DeepSeekDecisionProvider(DecisionProvider):
    """DeepSeek LLM decision provider implementation."""
    
    def __init__(self, api_key: str):
        """
        Initialize DeepSeek decision provider.
        
        Args:
            api_key: DeepSeek API key
        """
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    
    def _build_prompt(self, snapshot: MarketSnapshot, position_size: float, equity: float) -> str:
        """
        Build the prompt for DeepSeek API.
        
        Args:
            snapshot: Current market snapshot
            position_size: Current position size
            equity: Current account equity
            
        Returns:
            str: Formatted prompt string
        """
        # Extract indicators
        ema_20 = snapshot.indicators.get("ema_20", 0.0)
        ema_50 = snapshot.indicators.get("ema_50", 0.0)
        rsi_14 = snapshot.indicators.get("rsi_14", 0.0)
        
        # Determine trend
        trend = "bullish" if ema_20 > ema_50 else "bearish"
        
        # Calculate position value and available cash
        position_value = position_size * snapshot.price
        available_cash = equity - position_value
        
        # Calculate what you can afford
        max_affordable_btc = available_cash / snapshot.price if snapshot.price > 0 else 0
        
        # Calculate leverage being used
        leverage_used = (position_value / equity) if equity > 0 else 0
        
        prompt = f"""You are an automated trading agent for {snapshot.symbol}.

MARKET CONTEXT:
- Current price: ${snapshot.price:,.2f}
- Bid: ${snapshot.bid:,.2f}, Ask: ${snapshot.ask:,.2f}
- EMA(20): ${ema_20:,.2f}, EMA(50): ${ema_50:,.2f}
- RSI(14): {rsi_14:.2f}
- Trend: {trend}

YOUR ACCOUNT:
- Total equity: ${equity:,.2f}
- Current position: {position_size:.6f} BTC (worth ${position_value:,.2f})
- Available cash: ${available_cash:,.2f}
- Current leverage: {leverage_used:.2f}x
- Max you can buy: {max_affordable_btc:.6f} BTC (with available cash)

MONEY MANAGEMENT RULES:
1. ONLY trade with AVAILABLE CASH - don't exceed what you can afford
2. If available_cash is negative or low, you CANNOT open new positions
3. Max position size per trade: 10% of TOTAL EQUITY (${equity * 0.10:,.2f})
4. Recommended: Use 3-5% for normal trades, 8-10% only for very strong signals
5. If you already have a large position, consider closing or holding instead of adding
6. NEVER use more than 3x leverage total

ALLOWED ACTIONS:
- "long": BUY more (only if you have available cash!)
- "short": SELL (close long or open short)
- "close": Close entire position
- "hold": Do nothing (safest option when uncertain)

DECISION LOGIC:
- If available_cash < $500: You CANNOT buy more, only hold/close
- If leverage > 2x: Consider reducing position
- If position is already large: Be very cautious about adding more
- Always check if you can AFFORD the trade before deciding

OUTPUT FORMAT (strict JSON):
{{
  "action": "long|short|close|hold",
  "size_pct": 0.0-0.10,
  "reason": "brief explanation including cash/leverage consideration"
}}

Output your decision now:"""
        
        return prompt
    
    def get_decision(self, snapshot: MarketSnapshot, position_size: float, equity: float) -> str:
        """
        Get trading decision from DeepSeek API.
        
        Args:
            snapshot: Current market snapshot
            position_size: Current position size
            equity: Current account equity
            
        Returns:
            str: Raw LLM response (JSON string or error message)
        """
        try:
            prompt = self._build_prompt(snapshot, position_size, equity)
            
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                timeout=10.0
            )
            
            raw_response = response.choices[0].message.content
            return raw_response
            
        except Exception as e:
            # Return error message that will be handled by parser
            error_msg = f"DeepSeek API error: {str(e)}"
            return error_msg
