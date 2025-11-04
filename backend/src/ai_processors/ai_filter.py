"""AI filtering logic for trading decisions."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AIFilter:
    """AI-powered filtering of trading signals."""

    def __init__(self, client):
        """
        Initialize AI filter.

        Args:
            client: OpenAI client for API calls
        """
        self.client = client

    def filter_signal(self, snapshot, signal, position_size: float, equity: float) -> bool:
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

            # Call AI
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                timeout=10.0
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

    def _build_filter_prompt(self, snapshot, signal, position_size: float, equity: float) -> str:
        """Build prompt for AI filter."""
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

        prompt = f"""You are a risk filter for a crypto trading bot.

YOUR ROLE: Act as a CRITICAL THINKER and risk manager. The strategy just generated a signal, but you must question it critically before approving.

STRATEGY SIGNAL TO EVALUATE:
- Action: {signal.action.upper()}
- Symbol: {snapshot.symbol}
- Size: {signal.size_pct*100:.1f}% of equity
- Confidence: {signal.confidence:.2f}
- Reason: {signal.reason}

CURRENT MARKET SITUATION:
- Price: ${snapshot.price:,.2f}
- Position: {position_size:.6f} {snapshot.symbol.split('/')[0]} ({'LONG' if position_size > 0 else 'SHORT' if position_size < 0 else 'NONE'})
- Account: ${equity:,.2f} equity, ${available_cash:,.2f} available, ${position_value:,.2f} position value
- Required cash: ${required_cash:,.2f} ({'OK' if available_cash >= required_cash else 'INSUFFICIENT'})

TECHNICAL ANALYSIS:
- Daily Trend: {indicators.get('trend_1d', 'unknown')}
- 4H Trend: {indicators.get('trend_4h', 'unknown')}
- 1H Trend: {indicators.get('trend_1h', 'unknown')}
- RSI 14: {indicators.get('rsi_14', 50):.1f}
- EMA 50: ${indicators.get('ema_50', 0):,.2f}
- ATR 14: ${indicators.get('atr_14', 0):.2f}
- Support/Resistance: S1=${indicators.get('support_1', 0):,.2f}, R1=${indicators.get('resistance_1', 0):,.2f}
- VWAP 5m: ${indicators.get('vwap_5m', 0):,.2f} (price is {'above' if snapshot.price > indicators.get('vwap_5m', snapshot.price) else 'below'})
- Volume Ratio 1H: {indicators.get('volume_ratio_1h', 1.0):.2f}x ({'HIGH' if indicators.get('volume_ratio_1h', 1.0) >= 1.5 else 'MODERATE' if indicators.get('volume_ratio_1h', 1.0) >= 1.2 else 'LOW'})
- OBV Trend 1H: {indicators.get('obv_trend_1h', 'neutral')}
{tier2_info}

YOUR DECISION FRAMEWORK:

1. OPPOSITE CHECK: Force yourself to argue AGAINST this trade. What could go wrong?
   - Question the strategy's logic: Is this setup really as good as claimed?
   - Check for counter-signals: Are there opposing indicators?
   - Consider market context: Is this the right environment for this trade?

2. RISK ASSESSMENT:
   - Position sizing: Is {signal.size_pct*100:.1f}% too aggressive?
   - Leverage: Will this create excessive risk?
   - Account impact: What % of equity is at risk?
   - Cash availability: Can we afford this trade?

3. MARKET CONTEXT:
   - Trend alignment: Does this trade align with higher timeframes?
   - Volume confirmation: Is there sufficient volume to support the move?
   - Support/Resistance: Are we trading near key levels?
   - Momentum: Is the market showing conviction in this direction?

4. STRATEGY VALIDATION:
   - Entry logic: Does the setup meet the strategy's criteria?
   - Timing: Is this the right moment to enter?
   - Alternatives: Are there better opportunities elsewhere?

DECISION: Respond with ONLY ONE WORD on the first line: "APPROVE" or "VETO"

Then provide structured reasoning in this exact format:
OPPOSITE CHECK: [Your critical analysis questioning the trade]
REASONING: [Your balanced assessment]
CONCERNS: [Any remaining concerns or conditions]

Be rigorous - you're protecting capital, not trying to be liked by the strategy."""

        return prompt
