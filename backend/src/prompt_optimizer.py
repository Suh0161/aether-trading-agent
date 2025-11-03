"""Prompt optimizer for building focused, token-efficient prompts with tiered data."""

import logging
from typing import Dict
from src.tiered_data import EnhancedMarketSnapshot

logger = logging.getLogger(__name__)


class PromptOptimizer:
    """Builds optimized prompts with tiered data for multiple symbols."""
    
    def __init__(self):
        """Initialize prompt optimizer."""
        pass
    
    def _format_imbalance(self, imbalance: float) -> str:
        """Format order book imbalance with interpretation."""
        if imbalance > 0.1:
            sign = "+"
            interpretation = "buyers heavier"
        elif imbalance < -0.1:
            sign = ""
            interpretation = "sellers heavier"
        else:
            sign = ""
            interpretation = "balanced"
        return f"{sign}{imbalance:.3f} ({interpretation})"
    
    def _format_sweep_info(self, tier2) -> str:
        """Format liquidity sweep information."""
        if not tier2.liquidity_sweep_detected:
            distance = tier2.distance_to_liquidity_zone_pct
            if distance < 0.5:
                return f"- Sweep Detected: NO (waiting for liquidity grab)\n  → Very close to zone ({distance:.2f}%), sweep may be imminent"
            elif distance > 2.0:
                return f"- Sweep Detected: NO (waiting for liquidity grab)\n  → Far from zone ({distance:.2f}%), weak entry signal"
            else:
                return f"- Sweep Detected: NO (waiting for liquidity grab)"
        
        sweep_desc = f"{tier2.sweep_direction.upper()} SWEEP DETECTED"
        sweep_info = f"- Sweep Detected: YES ({sweep_desc}, confidence: {tier2.sweep_confidence:.2f})\n"
        
        if tier2.sweep_direction == "bullish":
            sweep_info += "  → Smart money grabbed BUY-side liquidity, expect upward move"
        elif tier2.sweep_direction == "bearish":
            sweep_info += "  → Smart money grabbed SELL-side liquidity, expect downward move"
        
        return sweep_info
    
    def _format_symbol_data(self, symbol: str, snapshot: EnhancedMarketSnapshot) -> str:
        """Format tiered data for a single symbol."""
        tier1 = snapshot.tier1
        tier2 = snapshot.tier2
        tier3 = snapshot.tier3
        
        lines = [
            f"=== {symbol} ===",
            "",
            "TIER 1 - Core State:",
            f"- Price: ${tier1.price:,.2f}",
            f"- EMAs: 1h=${tier1.ema_1h:,.2f}, 15m=${tier1.ema_15m:,.2f}",
            f"- ATR(14): ${tier1.atr_14:,.2f}",
            f"- Volume 1h: {tier1.volume_1h:,.0f}",
            f"- Current: {abs(tier1.position_size):.6f} {'LONG' if tier1.position_size > 0 else 'SHORT' if tier1.position_size < 0 else 'No position'}",
            ""
        ]
        
        if tier2:
            lines.extend([
                "TIER 2 - Order Book:",
                f"- Imbalance: {self._format_imbalance(tier2.order_book_imbalance)}",
                f"- Spread: {tier2.spread_bp:.2f}bp",
                f"- Bid/Ask Vol Ratio: {tier2.bid_ask_vol_ratio:.2f}x",
                ""
            ])
            
            if tier2.liquidity_zone_type:
                lines.extend([
                    "TIER 2 - Liquidity Zones (Smart Money Concept):",
                    f"- Nearest Zone: ${tier2.nearest_liquidity_zone_price:,.2f} ({tier2.liquidity_zone_type})",
                    f"- Distance: {tier2.distance_to_liquidity_zone_pct:.2f}%",
                    self._format_sweep_info(tier2),
                    ""
                ])
        
        lines.extend([
            "TIER 3 - Regime:",
            f"- Session: {tier3.session.upper()}",
            f"- Vol Regime: {tier3.vol_regime.upper()} (ATR at {tier3.atr_percentile:.0f}th percentile)",
            f"- Market Condition: {tier3.market_condition.upper()}",
            ""
        ])
        
        return "\n".join(lines)
    
    def _get_trading_rules(self) -> str:
        """Get trading rules section."""
        return "=" * 50 + """
TRADING RULES WITH REGIME AWARENESS:

1. VOL REGIME RULES:
   - LOW vol: Be conservative, smaller positions, wait for clear setups
   - NORMAL vol: Standard position sizing
   - HIGH vol: Can use larger positions if trend is clear

2. SESSION RULES:
   - LONDON_OPEN (08:00-13:00 UTC): European market activity, good liquidity
   - NY_OVERLAP (13:00-16:00 UTC): Highest liquidity, best trading hours
   - ASIA (00:00-08:00, 16:00-24:00 UTC): Lower liquidity, be cautious

3. MARKET CONDITION RULES:
   - TREND_UP: Focus on LONG positions, avoid SHORTs
   - TREND_DOWN: Focus on SHORT positions, avoid LONGs
   - RANGE: Smaller positions, quick scalps, respect S/R levels

4. TIER 2 (Order Book) USAGE - How to Interpret:
   
   ORDER BOOK IMBALANCE (Range: -1.0 to +1.0):
   - Positive (+0.1 to +1.0) = Buyers heavier than sellers = BULLISH
   - Negative (-0.1 to -1.0) = Sellers heavier than buyers = BEARISH
   - Near zero (-0.1 to +0.1) = Balanced = NEUTRAL
   
   For LONG entries:
   - Imbalance > +0.2: STRONG buy-side pressure → BOOST confidence (+0.05)
   - Imbalance < -0.2: Strong sell-side pressure → REDUCE confidence (-0.15) or consider HOLD
   - Imbalance between -0.2 and +0.2: Neutral, use other signals
   
   For SHORT entries:
   - Imbalance < -0.2: STRONG sell-side pressure → BOOST confidence (+0.05)
   - Imbalance > +0.2: Strong buy-side pressure → REDUCE confidence (-0.15) or consider HOLD
   - Imbalance between -0.2 and +0.2: Neutral, use other signals
   
   SPREAD & BID/ASK RATIO:
   - Spread > 5bp: Thin liquidity → Be CAUTIOUS, reduce position size
   - Bid/Ask Vol Ratio > 2x: Buyers dominating → Favor LONG entries
   - Bid/Ask Vol Ratio < 0.5x: Sellers dominating → Favor SHORT entries

5. LIQUIDITY ZONE RULES (Smart Money Concept) - How to Trade:
   
   WHAT ARE LIQUIDITY ZONES:
   - Swing Highs = Sell-side liquidity (above price) = where stop-losses for SHORTS accumulate
   - Swing Lows = Buy-side liquidity (below price) = where stop-losses for LONGS accumulate
   - "Smart money" targets these zones to trigger stop-losses and then reverse
   
   SWEEP = Liquidity Grab:
   - Price wick penetrates zone → triggers stops → then reverses quickly
   - Bullish sweep (swing_low swept): Buy-side liquidity grabbed → Expect upward move
   - Bearish sweep (swing_high swept): Sell-side liquidity grabbed → Expect downward move
   
   ENTRY LOGIC BY TRADE TYPE:
   
   FOR LONG POSITIONS (Swing or Scalp):
   - BEST: Bullish sweep detected (swing_low swept) → HIGH confidence, BOOST size (+15%)
   - GOOD: Near swing_low (< 0.5% away) + volume spike → MEDIUM confidence
   - AVOID: Too far from zone (> 2.0%) + no sweep → LOW confidence or HOLD
   - NEVER: Bearish sweep detected (swing_high swept) → REDUCE confidence (-0.2)
   
   FOR SHORT POSITIONS (Swing or Scalp):
   - BEST: Bearish sweep detected (swing_high swept) → HIGH confidence, BOOST size (+15%)
   - GOOD: Near swing_high (< 0.5% away) + volume spike → MEDIUM confidence
   - AVOID: Too far from zone (> 2.0%) + no sweep → LOW confidence or HOLD
   - NEVER: Bullish sweep detected (swing_low swept) → REDUCE confidence (-0.2)
   
   DISTANCE INTERPRETATION:
   - distance < 0.5%: Very close to zone → Zone about to be tested → MEDIUM confidence
   - distance 0.5% - 2.0%: Approaching zone → Watch for sweep opportunity
   - distance > 2.0%: Too far → Wait for price to approach zone OR wait for sweep
   
   SWEEP CONFIDENCE SCALING:
   - Sweep confidence 0.7-1.0: High quality sweep → MAX boost
   - Sweep confidence 0.4-0.7: Medium quality → Moderate boost
   - Sweep confidence < 0.4: Weak sweep → Small boost or ignore

6. EXCHANGE FEES (CRITICAL FOR SCALPING):
   - Binance Futures fees: ~0.045-0.05% per side (taker)
   - Round trip cost: ~0.1% (enter + exit)
   - Scalping TP (0.5%) = ~0.4% after fees - account for this!
   - Scalping requires moves > 0.6% to be profitable after fees
   - Swing trades: Fees are less impactful due to larger moves

7. POSITION SIZING:
   - Swing trades: 6-25% of equity (based on confidence)
   - Scalp trades: 5-15% of equity (based on confidence)
   - Reduce size in LOW vol or ASIA session
"""
    
    def _get_output_format(self) -> str:
        """Get output format section."""
        return "=" * 50 + """
OUTPUT FORMAT (JSON):
{"action": "long|short|close|hold",
 "size_pct": 0.0-1.0,
 "reason": "...",
 "confidence": 0.0-1.0,
 "stop_loss": price,
 "take_profit": price}

Analyze all symbols and provide ONE decision per symbol.
Consider regime context (vol regime, session time, market condition) in your decisions.
"""
    
    def build_multi_symbol_prompt(
        self,
        snapshots: Dict[str, EnhancedMarketSnapshot],
        equity: float,
        max_equity_pct: float = 0.30,
        smart_max_leverage: float = 3.0
    ) -> str:
        """
        Build optimized prompt for multiple symbols with tiered data.
        
        Only includes essential information to minimize token usage:
        - Tier 1: Core market state (always included)
        - Tier 2: Order book microstructure (if available)
        - Tier 3: Regime/context (always included, small)
        
        Args:
            snapshots: Dictionary mapping symbol to EnhancedMarketSnapshot
            equity: Current account equity
            max_equity_pct: Maximum equity usage percentage
            smart_max_leverage: Maximum leverage based on account size
            
        Returns:
            Optimized prompt string
        """
        # Header
        header = f"""You are an automated trading agent analyzing multiple symbols with tiered market data.

ACCOUNT INFO:
- Total equity: ${equity:,.2f}
- Max position size: {max_equity_pct*100:.0f}% per symbol (${equity * max_equity_pct:,.2f})
- Max leverage: {smart_max_leverage:.1f}x

"""
        
        # Symbol data sections
        symbol_sections = []
        for symbol, snapshot in snapshots.items():
            symbol_sections.append(self._format_symbol_data(symbol, snapshot))
        
        # Combine all sections
        prompt = header + "\n".join(symbol_sections) + self._get_trading_rules() + self._get_output_format()
        
        return prompt
    
    def build_single_symbol_prompt(
        self,
        snapshot: EnhancedMarketSnapshot,
        equity: float,
        max_equity_pct: float = 0.30,
        smart_max_leverage: float = 3.0
    ) -> str:
        """
        Build optimized prompt for single symbol (fallback for single-symbol analysis).
        
        Args:
            snapshot: EnhancedMarketSnapshot for the symbol
            equity: Current account equity
            max_equity_pct: Maximum equity usage percentage
            smart_max_leverage: Maximum leverage
            
        Returns:
            Optimized prompt string
        """
        return self.build_multi_symbol_prompt(
            {snapshot.original.symbol: snapshot},
            equity,
            max_equity_pct,
            smart_max_leverage
        )

