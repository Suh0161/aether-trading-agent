"""Enhanced AI filtering logic for trading decisions with superior prompt engineering."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AIFilter:
    """Enhanced AI-powered filtering of trading signals with professional risk management."""

    def __init__(self, client):
        """
        Initialize AI filter.

        Args:
            client: OpenAI client for API calls
        """
        self.client = client

    def filter_signal(self, snapshot, signal, position_size: float, equity: float) -> bool:
        """
        Use enhanced AI to filter/veto strategy signals with superior critical thinking.

        Args:
            snapshot: Market snapshot
            signal: Strategy signal to filter
            position_size: Current position
            equity: Account equity

        Returns:
            True if AI approves, False if AI vetoes
        """
        try:
            # Build enhanced prompt for AI filter
            prompt = self._build_enhanced_filter_prompt(snapshot, signal, position_size, equity)

            # Call AI with increased timeout for complex analysis
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                timeout=20.0  # Increased from 10.0 to handle complex prompts
            )

            ai_response = response.choices[0].message.content.strip()
            ai_response_lower = ai_response.lower()

            # Parse AI response (looking for "approve" or "veto")
            # New format: First line is "APPROVE" or "VETO", followed by structured reasoning
            lines = ai_response.split('\n')
            first_line = lines[0].strip() if lines else ""
            first_word = first_line.lower().split()[0] if first_line else ""

            # Extract reasoning sections for logging
            opposite_check = ""
            reasoning = ""
            concerns = ""

            for i, line in enumerate(lines):
                line_lower = line.lower().strip()
                if line_lower.startswith("opposite check:"):
                    opposite_check = line.replace("OPPOSITE CHECK:", "").replace("opposite check:", "").strip()
                elif line_lower.startswith("reasoning:"):
                    reasoning = line.replace("REASONING:", "").replace("reasoning:", "").strip()
                elif line_lower.startswith("concerns:"):
                    concerns = line.replace("CONCERNS:", "").replace("concerns:", "").strip()

            # Helper function to sanitize Unicode for Windows console
            def sanitize_unicode(text):
                """Replace Unicode characters that can't be encoded in cp1252."""
                if not text:
                    return text
                return text.replace('\u2265', '>=').replace('\u2264', '<=').replace('\u2192', '->').replace('\u2260', '!=')

            # Log full reasoning for debugging
            if opposite_check or reasoning or concerns:
                logger.info("AI CRITICAL THINKING:")
                if opposite_check:
                    logger.info(f"  |-- OPPOSITE CHECK: {sanitize_unicode(opposite_check[:200])}")
                if reasoning:
                    logger.info(f"  |-- REASONING: {sanitize_unicode(reasoning)}")
                if concerns:
                    logger.info(f"  |-- CONCERNS: {sanitize_unicode(concerns)}")

            # Parse decision
            if first_word in ["veto", "reject", "no"]:
                # Fix Unicode encoding issue: replace ≥ with >= for Windows console
                safe_response = sanitize_unicode(first_line[:150])
                logger.info(f"AI VETOED: {safe_response}")
                if reasoning:
                    logger.info(f"  |-- Full reasoning: {sanitize_unicode(reasoning)}")
                return False
            elif first_word == "approve":
                # Fix Unicode encoding issue: replace ≥ with >= for Windows console
                safe_response = sanitize_unicode(first_line[:150])
                logger.info(f"AI APPROVED: {safe_response}")
                if reasoning:
                    logger.info(f"  |-- Full reasoning: {sanitize_unicode(reasoning)}")
                return True
            else:
                # Fallback: check if veto/reject appears early in response
                if "veto" in ai_response_lower[:100] or "reject" in ai_response_lower[:100]:
                    # Fix Unicode encoding issue: replace ≥ with >= for Windows console
                    safe_response = sanitize_unicode(ai_response[:150])
                    logger.warning(f"AI VETOED (fallback): {safe_response}")
                    return False
                # Default to approve if unclear (but log warning)
                logger.warning(f"AI response unclear, defaulting to APPROVE: {sanitize_unicode(first_line[:100])}")
                logger.warning(f"  |-- Full response: {sanitize_unicode(ai_response[:500])}")
                return True

        except Exception as e:
            logger.error(f"AI filter failed: {e}")
            # On error, approve by default (don't block strategy)
            return True

    def _build_enhanced_filter_prompt(self, snapshot, signal, position_size: float, equity: float) -> str:
        """Build superior prompt for AI filter with enhanced critical thinking framework."""
        indicators = snapshot.indicators

        # Try to get Tier 2 data (order book + liquidity zones) for better decision making
        tier2_info = ""
        try:
            import api_server
            if hasattr(api_server, 'loop_controller_instance') and api_server.loop_controller_instance:
                loop_controller = api_server.loop_controller_instance
                data_acq = loop_controller.data_acquisition
                enhanced_snapshot = data_acq.fetch_enhanced_snapshot(snapshot.symbol, position_size)

                if enhanced_snapshot and enhanced_snapshot.tier2:
                    tier2 = enhanced_snapshot.tier2
                    tier2_info = f"""
ORDER BOOK & LIQUIDITY ANALYSIS (Tier 2 Data):
- Order Book Imbalance: {tier2.order_book_imbalance:.3f} ({'BUYERS heavier' if tier2.order_book_imbalance > 0.1 else 'SELLERS heavier' if tier2.order_book_imbalance < -0.1 else 'balanced'})
  → For LONG: {'SUPPORTS' if tier2.order_book_imbalance > 0.2 else 'OPPOSES' if tier2.order_book_imbalance < -0.2 else 'neutral'}
  → For SHORT: {'SUPPORTS' if tier2.order_book_imbalance < -0.2 else 'OPPOSES' if tier2.order_book_imbalance > 0.2 else 'neutral'}
- Spread: {tier2.spread_bp:.2f}bp ({'WIDE - thin liquidity, be cautious' if tier2.spread_bp > 5.0 else 'normal'})
- Bid/Ask Vol Ratio: {tier2.bid_ask_vol_ratio:.2f}x

"""
                    if tier2.liquidity_zone_type:
                        tier2_info += f"""- Liquidity Zone: ${tier2.nearest_liquidity_zone_price:,.2f} ({tier2.liquidity_zone_type})
- Distance to Zone: {tier2.distance_to_liquidity_zone_pct:.2f}%
"""
                        if tier2.liquidity_sweep_detected:
                            tier2_info += f"""- SWEEP DETECTED: YES ({tier2.sweep_direction.upper()}, confidence: {tier2.sweep_confidence:.2f})
  → For LONG: {'STRONG CONFIRMATION - smart money grabbed buy-side liquidity' if tier2.sweep_direction == 'bullish' else 'OPPOSES - bearish sweep detected, reduce confidence'}
  → For SHORT: {'STRONG CONFIRMATION - smart money grabbed sell-side liquidity' if tier2.sweep_direction == 'bearish' else 'OPPOSES - bullish sweep detected, reduce confidence'}
"""
                        else:
                            if tier2.distance_to_liquidity_zone_pct > 2.0:
                                tier2_info += f"""- SWEEP DETECTED: NO - Too far from zone ({tier2.distance_to_liquidity_zone_pct:.2f}%) - WEAK signal
"""
                            elif tier2.distance_to_liquidity_zone_pct < 0.5:
                                tier2_info += f"""- SWEEP DETECTED: NO - Very close to zone ({tier2.distance_to_liquidity_zone_pct:.2f}%) - sweep may be imminent
"""
                            else:
                                tier2_info += f"""- SWEEP DETECTED: NO - Zone nearby ({tier2.distance_to_liquidity_zone_pct:.2f}%) - watch for sweep
"""
                    tier2_info += "\n"
        except Exception as e:
            logger.debug(f"Could not fetch Tier 2 data for AI filter: {e}")

        # Calculate money management metrics
        position_value = position_size * snapshot.price if position_size > 0 else 0.0
        available_cash = equity - position_value
        required_cash = equity * signal.size_pct
        leverage_used = (position_value / equity) if equity > 0 else 0.0

        prompt = f"""You are a CRYPTO TRADING RISK MANAGER for a professional quantitative trading firm.

YOUR MISSION: Act as the FINAL DEFENSE against catastrophic trading decisions. Every signal that reaches you has already passed technical analysis and strategy validation. Your job is to be the SKEPTIC - the one who asks "what if this is wrong?" and "what could go wrong?"

STRATEGY SIGNAL UNDER REVIEW:
TARGET Action: {signal.action.upper()} {snapshot.symbol}
POSITION Size: {signal.size_pct*100:.1f}% of equity (${equity * signal.size_pct:,.0f})
CONFIDENCE: {signal.confidence:.2f}/1.0
STRATEGY REASON: {signal.reason}

CURRENT PORTFOLIO STATUS:
Account Equity: ${equity:,.2f}
Position Value: ${position_value:,.2f} ({'LONG' if position_size > 0 else 'SHORT' if position_size < 0 else 'FLAT'})
Available Cash: ${available_cash:,.2f}
Required Cash: ${required_cash:,.2f} ({'SUFFICIENT' if available_cash >= required_cash else 'INSUFFICIENT'})

MULTI-TIMEFRAME MARKET ANALYSIS:
DAILY: {indicators.get('trend_1d', 'unknown')} (EMA50: ${indicators.get('ema_50_1d', 0):,.2f})
4H: {indicators.get('trend_4h', 'unknown')} (EMA50: ${indicators.get('ema_50_4h', 0):,.2f})
1H: {indicators.get('trend_1h', 'unknown')} (EMA50: ${indicators.get('ema_50', 0):,.2f}, RSI: {indicators.get('rsi_14', 50):.1f})
15M ENTRY: {indicators.get('trend_15m', 'unknown')} (Keltner: ${indicators.get('keltner_upper_15m', 0):,.2f})
VOLATILITY: ATR(14) ${indicators.get('atr_14', 0):,.2f}

KEY PRICE LEVELS (SUPPORT/RESISTANCE):
Current Price: ${snapshot.price:,.2f}
Resistance: R1=${indicators.get('resistance_1', 0):,.2f}, R2=${indicators.get('resistance_2', 0):,.2f}
Support: S1=${indicators.get('support_1', 0):,.2f}, S2=${indicators.get('support_2', 0):,.2f}
Swing Points: High=${indicators.get('swing_high', 0):,.2f}, Low=${indicators.get('swing_low', 0):,.2f}

VOLUME & MOMENTUM CONFIRMATION:
1H Volume: {indicators.get('volume_ratio_1h', 1.0):.2f}x avg ({'STRONG' if indicators.get('volume_ratio_1h', 1.0) >= 1.5 else 'MODERATE' if indicators.get('volume_ratio_1h', 1.0) >= 1.2 else 'WEAK'})
5M Volume: {indicators.get('volume_ratio_5m', 1.0):.2f}x avg ({'STRONG' if indicators.get('volume_ratio_5m', 1.0) >= 1.5 else 'MODERATE' if indicators.get('volume_ratio_5m', 1.0) >= 1.3 else 'WEAK'})
OBV Trend: {indicators.get('obv_trend_1h', 'neutral')} (money flow direction)
VWAP 5M: ${indicators.get('vwap_5m', 0):,.2f} (price is {'ABOVE' if snapshot.price > indicators.get('vwap_5m', snapshot.price) else 'BELOW'})
{tier2_info}

CRITICAL THINKING RISK ASSESSMENT FRAMEWORK:

1. OPPOSITE PERSPECTIVE - FORCE CRITICAL ANALYSIS:
   - What evidence contradicts this trade? What could prove the strategy wrong?
   - Are there hidden risks or counter-indicators being ignored?
   - What if the market moves against us immediately after entry?

2. RISK EXPOSURE EVALUATION:
   - Position sizing: Does {signal.size_pct*100:.1f}% risk too much of our capital?
   - Leverage impact: How much equity is exposed to this single trade?
   - Cash flow: Can we afford this trade AND potential losses?
   - Portfolio correlation: Does this add unacceptable concentration risk?

3. MARKET CONTEXT VALIDATION:
   - Trend alignment: Do higher timeframes support or contradict this entry?
   - Volume conviction: Is there real institutional participation or just noise?
   - Level significance: Are we trading at meaningful S/R or random levels?
   - Momentum sustainability: Is this a genuine trend or short-lived spike?

4. STRATEGY INTEGRITY CHECK:
   - Setup validity: Does this truly match the strategy's core principles?
   - Timing precision: Is this the optimal entry point or just "good enough"?
   - Alternative opportunities: Are there clearly better setups available?
   - Edge quantification: What's the statistical edge here vs. random chance?

RISK WARNINGS (EVALUATE CAREFULLY - YOU CAN OVERRIDE IF TRULY CONFIDENT):
- Cash insufficient: Need ${required_cash:,.0f}, have ${available_cash:,.0f}
- Extreme RSI: >80 for LONG, <20 for SHORT (overbought/oversold reversal risk)
- Wrong direction: LONG when 1D/4H bearish, SHORT when 1D/4H bullish
- At danger zones: LONG near R1/R2/swing high, SHORT near S1/S2/swing low
- Volume failure: <1.2x avg for swing trades, <1.3x for scalps
- Liquidity crisis: Wide spreads (>5bp) + opposing order book
- Institutional opposition: Heavy sellers for LONG, heavy buyers for SHORT

AI DISCRETION GUIDELINES (WHEN YOU CAN OVERRIDE WARNINGS):
- If you find COMPELLING EVIDENCE that outweighs the warnings (e.g., strong institutional accumulation, clear reversal patterns, exceptional setup quality)
- When market context suggests an imminent trend change despite current warnings
- If the risk/reward ratio remains highly favorable despite red flags
- When you have strong conviction that this is a high-probability setup despite technical warnings
- REMEMBER: You are the FINAL DECISION MAKER - use your judgment when evidence is compelling

APPROVAL CRITERIA (LEAN TOWARD APPROVAL):
- Multi-TF harmony: 1D/4H trends align with trade direction
- Volume confirmation: >=1.2x average with supportive OBV flow
- Strategic positioning: LONG near support, SHORT near resistance
- Liquidity comfort: Tight spreads, supporting order book
- No red flags: Clean setup meeting all basic criteria
- AI Confidence: Your assessment can override technical warnings if evidence is compelling

FINAL DECISION PROTOCOL:

First line: ONLY ONE WORD - "APPROVE" or "VETO"

Then provide structured analysis:
OPPOSITE CHECK: [Force critical analysis of why this could fail]
REASONING: [Balanced assessment of risks, rewards, and market context]
CONCERNS: [Any remaining risk factors or conditions for approval]

You are the last line of defense. Be ruthlessly skeptical but professionally fair. Protect capital without being paralyzed by fear."""

        return prompt
