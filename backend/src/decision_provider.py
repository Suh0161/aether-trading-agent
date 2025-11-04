"""Decision provider interface and implementations for the Autonomous Trading Agent."""

import os
from typing import Dict, Optional
from abc import ABC, abstractmethod
from openai import OpenAI
from dotenv import load_dotenv
from src.models import MarketSnapshot
from src.tiered_data import EnhancedMarketSnapshot
from src.prompt_optimizer import PromptOptimizer

# Load .env file
load_dotenv()


def get_max_equity_usage():
    """
    Get MAX_EQUITY_USAGE_PCT from environment, default to 0.30 (30%).
    
    This allows easy configuration via .env file without code changes.
    """
    return float(os.getenv("MAX_EQUITY_USAGE_PCT", "0.30"))


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
    
    def __init__(self, api_key: str, use_tiered_data: bool = True):
        """
        Initialize DeepSeek decision provider.
        
        Args:
            api_key: DeepSeek API key
            use_tiered_data: Whether to use tiered data system (default: True)
        """
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.use_tiered_data = use_tiered_data
        self.prompt_optimizer = PromptOptimizer() if use_tiered_data else None
    
    def _build_prompt(self, snapshot: MarketSnapshot, position_size: float, equity: float) -> str:
        """
        Build the prompt for DeepSeek API with full multi-timeframe indicators.
        
        Args:
            snapshot: Current market snapshot
            position_size: Current position size
            equity: Current account equity
            
        Returns:
            str: Formatted prompt string
        """
        indicators = snapshot.indicators
        
        # Extract ALL indicators (multi-timeframe)
        # Daily timeframe
        trend_1d = indicators.get("trend_1d", "unknown")
        ema_50_1d = indicators.get("ema_50_1d", 0)
        
        # 4h timeframe
        trend_4h = indicators.get("trend_4h", "unknown")
        ema_50_4h = indicators.get("ema_50_4h", 0)
        rsi_4h = indicators.get("rsi_14_4h", 50)
        
        # 1h timeframe (primary)
        ema_20 = indicators.get("ema_20", 0)
        ema_50 = indicators.get("ema_50", 0)
        rsi_14 = indicators.get("rsi_14", 50)
        atr_14 = indicators.get("atr_14", 0)
        keltner_upper = indicators.get("keltner_upper", 0)
        keltner_lower = indicators.get("keltner_lower", 0)
        
        # 15m timeframe
        trend_15m = indicators.get("trend_15m", "unknown")
        ema_50_15m = indicators.get("ema_50_15m", 0)
        keltner_upper_15m = indicators.get("keltner_upper_15m", 0)
        rsi_15m = indicators.get("rsi_14_15m", 50)
        
        # 5m timeframe
        trend_5m = indicators.get("trend_5m", "unknown")
        ema_50_5m = indicators.get("ema_50_5m", 0)
        keltner_upper_5m = indicators.get("keltner_upper_5m", 0)
        rsi_5m = indicators.get("rsi_14_5m", 50)
        
        # 1m timeframe
        trend_1m = indicators.get("trend_1m", "unknown")
        ema_50_1m = indicators.get("ema_50_1m", 0)
        keltner_upper_1m = indicators.get("keltner_upper_1m", 0)
        rsi_1m = indicators.get("rsi_14_1m", 50)
        
        # Calculate position value and available cash
        position_value = position_size * snapshot.price
        available_cash = equity - position_value
        
        # Calculate what you can afford
        max_affordable_btc = available_cash / snapshot.price if snapshot.price > 0 else 0
        
        # Calculate leverage being used
        leverage_used = (position_value / equity) if equity > 0 else 0
        
        # Calculate smart max leverage (matches risk_manager logic)
        if equity < 500:
            smart_max_leverage = 1.0
        elif equity < 1000:
            smart_max_leverage = 1.5
        elif equity < 5000:
            smart_max_leverage = 2.0
        elif equity < 10000:
            smart_max_leverage = 2.5
        else:
            smart_max_leverage = 3.0
        
        # Get max equity usage from .env
        max_equity_pct = get_max_equity_usage()
        
        prompt = f"""You are an automated trading agent for {snapshot.symbol} with FULL multi-timeframe analysis.

CURRENT MARKET:
- Price: ${snapshot.price:,.2f}
- Bid: ${snapshot.bid:,.2f}, Ask: ${snapshot.ask:,.2f}

MULTI-TIMEFRAME ANALYSIS (Professional Approach):

HIGHER TIMEFRAMES (Trend Confirmation):
- Daily (1d): Trend={trend_1d}, EMA50=${ema_50_1d:,.2f}
- 4-Hour (4h): Trend={trend_4h}, EMA50=${ema_50_4h:,.2f}, RSI={rsi_4h:.1f}

PRIMARY TIMEFRAME (1h - Main Analysis):
- EMA20: ${ema_20:,.2f}, EMA50: ${ema_50:,.2f}
- RSI(14): {rsi_14:.1f}
- ATR(14): ${atr_14:,.2f}
- Keltner Upper: ${keltner_upper:,.2f}, Lower: ${keltner_lower:,.2f}

SUPPORT/RESISTANCE LEVELS (Key Price Zones):
- Pivot Point: ${indicators.get('pivot', 0):,.2f}
- Resistance Levels: R1=${indicators.get('resistance_1', 0):,.2f}, R2=${indicators.get('resistance_2', 0):,.2f}, R3=${indicators.get('resistance_3', 0):,.2f}
- Support Levels: S1=${indicators.get('support_1', 0):,.2f}, S2=${indicators.get('support_2', 0):,.2f}, S3=${indicators.get('support_3', 0):,.2f}
- Recent Swing High: ${indicators.get('swing_high', 0):,.2f} (resistance from price action)
- Recent Swing Low: ${indicators.get('swing_low', 0):,.2f} (support from price action)

ENTRY TIMING TIMEFRAMES (Precision):
- 15-Minute: Trend={trend_15m}, Keltner Upper=${keltner_upper_15m:,.2f}, RSI={rsi_15m:.1f}, VWAP=${indicators.get('vwap_15m', 0):,.2f}
- 5-Minute: Trend={trend_5m}, Keltner Upper=${keltner_upper_5m:,.2f}, RSI={rsi_5m:.1f}, VWAP=${indicators.get('vwap_5m', 0):,.2f}
- 1-Minute: Trend={trend_1m}, Keltner Upper=${keltner_upper_1m:,.2f}, RSI={rsi_1m:.1f}, VWAP=${indicators.get('vwap_1m', 0):,.2f}

YOUR ACCOUNT:
- Total equity: ${equity:,.2f}
- Current position: {position_size:.6f} BTC (worth ${position_value:,.2f})
- Available cash: ${available_cash:,.2f}
- Current leverage: {leverage_used:.2f}x
- Smart max leverage (adaptive): {smart_max_leverage:.1f}x
- Max you can buy: {max_affordable_btc:.6f} BTC

TRADING STRATEGIES YOU CAN USE:

1. SWING TRADING (Preferred - Higher Timeframes):
   - Use 1d/4h for trend confirmation
   - Use 1h for main analysis
   - Use 15m for precise entry timing
   - Look for: Multi-TF alignment + Keltner breakout
   - Position size: 3-10% of equity
   - Hold time: Hours to days
   - Stop: 2x ATR below entry

2. SCALPING (Fallback - Lower Timeframes):
   - Use 15m for bias confirmation
   - Use 5m for trend and signal generation
   - Use 1m for precise entry timing
   - **VWAP FILTER (CRITICAL):**
     * For LONGS: Price MUST be above VWAP (confirms bullish intraday bias)
     * For SHORTS: Price MUST be below VWAP (confirms bearish intraday bias)
   - Look for: Quick momentum + Keltner breakout on 1m/5m
   - **PULLBACK STRATEGY (Alternative):**
     * Wait for pullback TO VWAP (not away from it)
     * Enter when price bounces FROM VWAP back in trend direction
   - Position size: 1-3% of equity
   - Hold time: 1-5 minutes
   - Stop: 0.3% of price (increased to account for fees/wiggles)
   - Target: 0.5% profit (gives ~0.4% after fees)
   - **EXCHANGE FEES (CRITICAL):**
     * Binance Futures: ~0.045-0.05% per side (taker)
     * Round trip: ~0.1% (enter + exit)
     * Scalping needs moves > 0.6% to be profitable after fees
     * TP of 0.5% = ~0.4% net profit (after ~0.1% fees)

MONEY MANAGEMENT RULES:
1. ONLY trade with AVAILABLE CASH - don't exceed what you can afford
2. If available_cash < $100: You CANNOT open new positions
3. Max position size per trade: {max_equity_pct*100:.0f}% of equity (${equity * max_equity_pct:,.2f})
4. Respect smart max leverage: {smart_max_leverage:.1f}x (adaptive based on account size)
5. Smaller accounts = more conservative leverage
6. For swing trades: Use 3-10% position size
7. For scalp trades: Use 1-3% position size

DECISION LOGIC:
- Check multi-timeframe alignment for BOTH longs and shorts
- **CHECK SUPPORT/RESISTANCE FIRST** - Don't fight key levels!
  * For LONGS: Avoid entering near resistance (R1, R2, R3, swing high)
  * For SHORTS: Avoid entering near support (S1, S2, S3, swing low)
  * BEST LONGS: Enter at support levels (bounce from S1/S2/swing low)
  * BEST SHORTS: Enter at resistance levels (rejection from R1/R2/swing high)
- For SWING LONGS: 1d/4h bullish + breakout on 15m or 1h Keltner upper + NOT at resistance
- For SWING SHORTS: 1d/4h bearish + breakdown on 15m or 1h Keltner lower + NOT at support
- For SCALP LONGS: 15m bullish bias + 5m bullish + price > VWAP + 1m breakout + NOT at resistance
- For SCALP SHORTS: 15m bearish bias + 5m bearish + price < VWAP + 1m breakdown + NOT at support
- **VWAP PULLBACK (Alternative Scalp):**
  * LONG: Price above VWAP → pulls back TO VWAP → bounces up
  * SHORT: Price below VWAP → pulls back TO VWAP → rejects down
- Always verify you have enough available cash
- Don't exceed smart max leverage for your account size
- Consider both swing and scalp opportunities
- Consider both long and short opportunities - don't be long-biased

REASONING REQUIREMENTS (CRITICAL):
- **EXPLAIN CURRENT MARKET CONDITIONS**: What are trends, RSI, volume, key levels?
- **WHY THIS ACTION**: Why hold/long/short now? What signals triggered this?
- **WHAT WOULD CHANGE YOUR MIND**: What would make you go the opposite direction?
- **RISK MANAGEMENT**: Stop levels, reward targets, risk-reward ratio
- **KEY PRICE LEVELS**: Support/resistance, stops, targets
- **STRATEGY SPECIFIC ANALYSIS**: Different reasoning for swing vs scalp

ALLOWED ACTIONS:
- "long": BUY (swing or scalp - specify in reason)
- "short": SELL/SHORT (if trend is bearish on multiple TFs)
- "close": Close entire position
- "hold": Do nothing (when no clear setup)

OUTPUT FORMAT (strict JSON):
{{
  "action": "long|short|close|hold",
  "size_pct": 0.0-0.10,
  "reason": "DETAILED market analysis: current conditions, why this action, what would trigger trades, key levels, risk factors",
  "position_type": "swing|scalp"
}}

Example outputs:

LONG examples:

SWING LONG (Multi-timeframe bullish setup):
{{"action": "long", "size_pct": 0.05, "reason": "SWING LONG opportunity at S1 support. 1D trend bullish with EMA50 support, 4H showing consolidation above EMA20, 1H RSI oversold at 35, price bounced from S1 $109.7k with volume confirmation. 15M showing bullish breakout above Keltner upper. Would go SHORT if 1D trend turns bearish or price rejects at R1 $110.5k. Risk: 2x ATR stop below S1, Reward: 3x risk to R2 $111.5k. Key levels: Stop $108.5k, Target $111.5k", "position_type": "swing"}}

SCALP LONG (Quick momentum setup):
{{"action": "long", "size_pct": 0.02, "reason": "SCALP LONG at VWAP bounce. 15M bias bullish with EMA50 support, 5M trend up above VWAP $109.8k, RSI 45 showing room for upside, OBV increasing. Price above VWAP confirms intraday bullish bias. Would go SHORT if 5M trend reverses below VWAP or price drops below swing low $109.4k. Risk: 0.3% stop below VWAP, Reward: 0.5% target to R1. Key levels: Stop $109.5k, Target $110.2k", "position_type": "scalp"}}

SHORT examples:

SWING SHORT (Multi-timeframe bearish setup):
{{"action": "short", "size_pct": 0.05, "reason": "SWING SHORT opportunity at R1 resistance. 1D trend bearish below EMA50, 4H showing rejection at resistance, 1H RSI overbought at 72, price rejected at R1 $110.5k with volume spike. 15M showing bearish breakdown below Keltner lower. Would go LONG if 1D trend turns bullish or price breaks above swing high $111.2k. Risk: 2x ATR stop above R1, Reward: 3x risk to S2 $108.8k. Key levels: Stop $111.2k, Target $108.8k", "position_type": "swing"}}

SCALP SHORT (Quick momentum setup):
{{"action": "short", "size_pct": 0.02, "reason": "SCALP SHORT at VWAP rejection. 15M bias bearish below EMA50, 5M trend down below VWAP $110.2k, RSI 58 showing downward momentum, OBV decreasing. Price below VWAP confirms intraday bearish bias. Would go LONG if 5M trend reverses above VWAP or price bounces from swing low $109.8k. Risk: 0.3% stop above VWAP, Reward: 0.5% target to S1. Key levels: Stop $110.5k, Target $109.8k", "position_type": "scalp"}}

HOLD examples (detailed market analysis):
{{"action": "hold", "size_pct": 0.0, "reason": "HOLD: Price testing R1 $110.5k resistance with 1D bearish trend intact. 4H showing rejection candles, 1H RSI at 68 (overbought), volume declining. Would go SHORT on confirmed rejection below 15M EMA20, or LONG on breakout above swing high $111.2k with volume. Key resistance $110.5k-$111.2k zone, support at $109.7k S1. Waiting for clearer directional bias before entering", "position_type": "swing"}}
{{"action": "hold", "size_pct": 0.0, "reason": "HOLD: Price in no-man's land between S1 $109.7k and R1 $110.5k. 1D trend neutral, 4H consolidating, 1H RSI 52 (neutral). No strong momentum in either direction, volume low. Would go LONG on bounce from S1 with bullish volume, or SHORT on rejection from R1. Risk of whipsaw in range-bound market - better to wait for breakout", "position_type": "swing"}}
{{"action": "close", "size_pct": 1.0, "reason": "CLOSE LONG: Hit R2 $111.5k target with 3:1 reward-to-risk ratio achieved. 1D trend still bullish, 4H showing profit-taking, 1H RSI overbought at 75. Would consider re-entry on pullback to R1 $110.5k if trend remains intact. Profit locked in at +2.3% position", "position_type": "swing"}}

Output your decision now:"""
        
        return prompt
    
    def get_decision(self, snapshot: MarketSnapshot, position_size: float, equity: float) -> str:
        """
        Get trading decision from DeepSeek API.
        
        Supports both regular MarketSnapshot and EnhancedMarketSnapshot.
        If EnhancedMarketSnapshot is provided, uses tiered data system.
        
        Args:
            snapshot: Current market snapshot (can be MarketSnapshot or EnhancedMarketSnapshot)
            position_size: Current position size
            equity: Current account equity
            
        Returns:
            str: Raw LLM response (JSON string or error message)
        """
        try:
            # Check if snapshot is EnhancedMarketSnapshot
            if isinstance(snapshot, EnhancedMarketSnapshot) and self.use_tiered_data:
                prompt = self._build_tiered_prompt(snapshot, equity)
            else:
                # Fallback to regular prompt (backwards compatibility)
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
    
    def get_multi_symbol_decision(
        self,
        enhanced_snapshots: Dict[str, EnhancedMarketSnapshot],
        equity: float
    ) -> Dict[str, str]:
        """
        Get trading decisions for multiple symbols in one LLM call.
        
        This is more efficient than calling get_decision() multiple times,
        as it sends all symbols in one prompt and gets all decisions at once.
        
        Args:
            enhanced_snapshots: Dictionary mapping symbol to EnhancedMarketSnapshot
            equity: Current account equity
            
        Returns:
            Dictionary mapping symbol to LLM response (JSON string or error message)
        """
        if not self.use_tiered_data:
            # Fallback: process one by one
            results = {}
            for symbol, enhanced_snapshot in enhanced_snapshots.items():
                position_size = enhanced_snapshot.tier1.position_size
                results[symbol] = self.get_decision(enhanced_snapshot.original, position_size, equity)
            return results
        
        try:
            # Build multi-symbol prompt with tiered data
            prompt = self.prompt_optimizer.build_multi_symbol_prompt(
                enhanced_snapshots,
                equity
            )
            
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                timeout=15.0  # Slightly longer timeout for multi-symbol
            )
            
            raw_response = response.choices[0].message.content
            
            # Parse multi-symbol response
            # For now, return the full response - parsing can be handled by the caller
            # The response should contain decisions for all symbols
            return {"_multi_symbol": raw_response}
            
        except Exception as e:
            error_msg = f"DeepSeek API error (multi-symbol): {str(e)}"
            return {"_error": error_msg}
    
    def _build_tiered_prompt(self, enhanced_snapshot: EnhancedMarketSnapshot, equity: float) -> str:
        """
        Build optimized prompt using tiered data system.
        
        Args:
            enhanced_snapshot: EnhancedMarketSnapshot with tiered data
            equity: Current account equity
            
        Returns:
            Optimized prompt string
        """
        import os
        from src.strategy import get_max_equity_usage
        
        max_equity_pct = get_max_equity_usage()
        
        # Calculate smart max leverage
        if equity < 500:
            smart_max_leverage = 1.0
        elif equity < 1000:
            smart_max_leverage = 1.5
        elif equity < 5000:
            smart_max_leverage = 2.0
        elif equity < 10000:
            smart_max_leverage = 2.5
        else:
            smart_max_leverage = 3.0
        
        # Use prompt optimizer for single symbol
        return self.prompt_optimizer.build_single_symbol_prompt(
            enhanced_snapshot,
            equity,
            max_equity_pct,
            smart_max_leverage
        )
