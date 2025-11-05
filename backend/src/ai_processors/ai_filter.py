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

    def filter_signal(self, snapshot, signal, position_size: float, equity: float, total_margin_used: float = 0.0, all_symbols: list = None) -> tuple[bool, Optional[float], Optional[float]]:
        """
        Use enhanced AI to filter/veto strategy signals with superior critical thinking AND assess confidence dynamically.

        Args:
            snapshot: Market snapshot
            signal: Strategy signal to filter
            position_size: Current position for this symbol
            equity: Account equity
            total_margin_used: Total margin used across ALL symbols (for liquidity awareness)
            all_symbols: List of all symbols being traded (for capital allocation awareness)

        Returns:
            Tuple of (approved: bool, suggested_leverage: Optional[float], ai_confidence: Optional[float])
            - approved: True if AI approves, False if AI vetoes
            - suggested_leverage: AI-suggested leverage (only if confidence >= 0.75), None otherwise
            - ai_confidence: AI-assessed confidence score (0.0-1.0), None if AI doesn't provide one
        """
        # IMPORTANT: AI will assess ALL decisions, including HOLD with 0.00 confidence
        # AI can find trades even when strategy says HOLD, or assess actual confidence
        # We removed auto-approve so AI can dynamically evaluate market conditions
        
        try:
            # Build enhanced prompt for AI filter with capital awareness
            prompt = self._build_enhanced_filter_prompt(snapshot, signal, position_size, equity, total_margin_used, all_symbols)

            # Call AI with timeout and multiple retries with increasing timeout
            base_timeout = 12.0
            max_retries = 3  # Retry up to 3 times (total 4 attempts)
            last_exception = None
            
            for attempt in range(max_retries + 1):  # 0, 1, 2, 3 = 4 attempts total
                timeout = base_timeout + (attempt * 5.0)  # 12s, 17s, 22s, 27s
                try:
                    response = self.client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[{"role": "user", "content": prompt}],
                        timeout=timeout
                    )
                    # Success! Break out of retry loop
                    break
                except Exception as e:
                    last_exception = e
                    msg = str(e).lower()
                    if "timed out" in msg or "timeout" in msg:
                        if attempt < max_retries:
                            logger.warning(f"AI filter timeout (attempt {attempt + 1}/{max_retries + 1}), retrying with {timeout + 5.0:.1f}s timeout...")
                        else:
                            # Last attempt failed - log error but don't auto-approve
                            logger.error(f"AI filter failed after {max_retries + 1} attempts due to timeout. Last timeout: {timeout:.1f}s")
                            logger.error(f"AI filter unavailable - REJECTING trade for safety (cannot assess risk without AI)")
                            # Return VETO instead of auto-approve to be safe
                            return False, None, signal.confidence  # Use strategy confidence as fallback
                    else:
                        # Non-timeout error - raise immediately
                        raise
            
            # If we got here, we have a response
            if 'response' not in locals():
                # This shouldn't happen, but handle it safely
                logger.error("AI filter failed - no response received after all retries")
                return False, None, signal.confidence

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
                logger.debug("AI CRITICAL THINKING:")
                if opposite_check:
                    logger.debug(f"  |-- OPPOSITE CHECK: {sanitize_unicode(opposite_check[:200])}")
                if reasoning:
                    logger.debug(f"  |-- REASONING: {sanitize_unicode(reasoning)}")
                if concerns:
                    logger.debug(f"  |-- CONCERNS: {sanitize_unicode(concerns)}")

            # Parse decision and extract leverage suggestion (if confidence >= 0.75)
            suggested_leverage = None
            ai_confidence = None
            import re
            
            # Extract confidence from AI response (look for "CONFIDENCE: 0.85" or "confidence: 0.7" or "AI assessed confidence: 0.15")
            confidence_patterns = [
                r'confidence[:\s]+(\d+\.?\d*)',  # "CONFIDENCE: 0.85" or "confidence: 0.7"
                r'conf[:\s]+(\d+\.?\d*)',  # "conf: 0.85"
                r'assessed[:\s]+confidence[:\s]+(\d+\.?\d*)',  # "assessed confidence: 0.15"
                r'ai[:\s]+assessed[:\s]+confidence[:\s]+(\d+\.?\d*)',  # "AI assessed confidence: 0.15"
                r'confidence[:\s]+score[:\s]+(\d+\.?\d*)',  # "confidence score: 0.85"
                r'actual[:\s]+confidence[:\s]+(\d+\.?\d*)',  # "actual confidence: 0.85"
                r'real[:\s]+confidence[:\s]+(\d+\.?\d*)',  # "real confidence: 0.85"
                r'assessed[:\s]+(\d+\.?\d*)[:\s]+confidence',  # "assessed 0.15 confidence"
            ]
            for pattern in confidence_patterns:
                match = re.search(pattern, ai_response_lower)
                if match:
                    try:
                        conf_value = float(match.group(1))
                        # Normalize if AI gives percentage (e.g., 85 -> 0.85)
                        if conf_value > 1.0:
                            conf_value = conf_value / 100.0
                        # Validate confidence is reasonable (0.0 to 1.0)
                        if 0.0 <= conf_value <= 1.0:
                            ai_confidence = conf_value
                            logger.info(f"AI assessed confidence: {ai_confidence:.2f} (original strategy: {signal.confidence:.2f}) - MATCHED PATTERN: {pattern}")
                            break
                    except (ValueError, IndexError) as e:
                        logger.debug(f"Confidence parsing error for pattern {pattern}: {e}")
                        pass
            
            # Debug: Log if no confidence found
            if ai_confidence is None:
                logger.warning(f"AI did not provide confidence in response. First 200 chars: {ai_response[:200]}")
            
            if signal.confidence >= 0.75:
                # Try to extract leverage suggestion from AI response
                # Look for patterns like "LEVERAGE: 2.5x" or "suggested leverage: 2.0"
                leverage_patterns = [
                    r'leverage[:\s]+(\d+\.?\d*)\s*x',
                    r'leverage[:\s]+(\d+\.?\d*)',
                    r'suggested[:\s]+leverage[:\s]+(\d+\.?\d*)\s*x',
                    r'use[:\s]+(\d+\.?\d*)\s*x\s+leverage'
                ]
                for pattern in leverage_patterns:
                    match = re.search(pattern, ai_response_lower)
                    if match:
                        try:
                            leverage_value = float(match.group(1))
                            # Validate leverage is whole number (1 or 2 only - Binance doesn't support decimals)
                            leverage_value = int(round(leverage_value))
                            if leverage_value == 1 or leverage_value == 2:
                                suggested_leverage = float(leverage_value)
                                logger.info(f"AI suggested leverage: {int(suggested_leverage)}x (confidence: {ai_confidence or signal.confidence:.2f})")
                                break
                            else:
                                logger.warning(f"AI suggested invalid leverage {leverage_value}x (must be 1x or 2x), ignoring")
                        except (ValueError, IndexError):
                            pass
            
            if first_word in ["veto", "reject", "no"]:
                # Fix Unicode encoding issue: replace ≥ with >= for Windows console
                safe_response = sanitize_unicode(first_line[:150])
                logger.info(f"AI VETOED: {safe_response}")
                if reasoning:
                    logger.info(f"  |-- Full reasoning: {sanitize_unicode(reasoning)}")
                if ai_confidence is not None:
                    logger.info(f"  |-- AI assessed confidence: {ai_confidence:.2f} (strategy had: {signal.confidence:.2f}) - RETURNING CONFIDENCE")
                else:
                    logger.warning(f"  |-- WARNING: ai_confidence is None after parsing! Response snippet: {ai_response[:300]}")
                # Return confidence even when vetoing (for HOLD decisions, this shows AI's assessment)
                logger.debug(f"DEBUG: Returning (False, None, {ai_confidence}) from filter_signal")
                return False, None, ai_confidence
            elif first_word == "approve":
                # Fix Unicode encoding issue: replace ≥ with >= for Windows console
                safe_response = sanitize_unicode(first_line[:150])
                logger.info(f"AI APPROVED: {safe_response}")
                if reasoning:
                    logger.info(f"  |-- Full reasoning: {sanitize_unicode(reasoning)}")
                if suggested_leverage:
                    logger.info(f"  |-- AI leverage suggestion: {int(suggested_leverage)}x")
                if ai_confidence is not None:
                    logger.info(f"  |-- AI confidence override: {ai_confidence:.2f} (strategy had: {signal.confidence:.2f})")
                return True, suggested_leverage, ai_confidence
            else:
                # Fallback: check if veto/reject appears early in response
                if "veto" in ai_response_lower[:100] or "reject" in ai_response_lower[:100]:
                    # Fix Unicode encoding issue: replace ≥ with >= for Windows console
                    safe_response = sanitize_unicode(ai_response[:150])
                    logger.warning(f"AI VETOED (fallback): {safe_response}")
                    if ai_confidence is not None:
                        logger.info(f"  |-- AI assessed confidence: {ai_confidence:.2f} (strategy had: {signal.confidence:.2f})")
                    return False, None, ai_confidence
                # Default to approve if unclear (but log warning)
                logger.warning(f"AI response unclear, defaulting to APPROVE: {sanitize_unicode(first_line[:100])}")
                logger.warning(f"  |-- Full response: {sanitize_unicode(ai_response[:500])}")
                return True, suggested_leverage, ai_confidence

        except Exception as e:
            logger.error(f"AI filter failed: {e}")
            # On error, approve by default (don't block strategy)
            return True, None, None

    def _build_enhanced_filter_prompt(self, snapshot, signal, position_size: float, equity: float, total_margin_used: float = 0.0, all_symbols: list = None) -> str:
        """Build superior prompt for AI filter with enhanced critical thinking framework and capital awareness."""
        indicators = snapshot.indicators

        # Sanitize certain indicator values for AI prompt readability (does not affect core logic)
        price = float(getattr(snapshot, 'price', 0.0) or 0.0)

        def _sanitize_vwap(vwap_value: float, ref_price: float) -> float:
            try:
                v = float(vwap_value)
                if v <= 0 or ref_price <= 0:
                    return ref_price
                ratio = v / ref_price
                if 0.5 <= ratio <= 2.0:
                    return v
                return ref_price
            except Exception:
                return ref_price

        def _keltner_context(upper: float, lower: float, ref_price: float) -> str:
            try:
                u = float(upper)
                l = float(lower)
                if ref_price <= 0 or u <= 0 or l <= 0:
                    return ""
                # Hide if clearly anomalous (>50% away from price)
                if abs(u - ref_price) / ref_price > 0.5 or abs(l - ref_price) / ref_price > 0.5:
                    return ""
                return f" (Keltner: Upper=${u:,.2f}, Lower=${l:,.2f})"
            except Exception:
                return ""

        vwap_5m_prompt = _sanitize_vwap(indicators.get('vwap_5m', price), price)
        vwap_relation_5m = 'ABOVE' if price > vwap_5m_prompt else 'BELOW'

        keltner_prompt_1h = _keltner_context(indicators.get('keltner_upper', 0), indicators.get('keltner_lower', 0), price)
        keltner_prompt_15m = _keltner_context(indicators.get('keltner_upper_15m', 0), indicators.get('keltner_lower_15m', 0), price)
        keltner_prompt_5m = _keltner_context(indicators.get('keltner_upper_5m', 0), indicators.get('keltner_lower_5m', 0), price)
        keltner_prompt_1m = _keltner_context(indicators.get('keltner_upper_1m', 0), indicators.get('keltner_lower_1m', 0), price)

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
        available_cash = equity - total_margin_used  # Use total margin across all symbols
        required_cash = equity * signal.size_pct
        leverage_used = (total_margin_used / equity) if equity > 0 else 0.0

        # Get position breakdown by type (for better AI awareness)
        swing_position = 0.0
        scalp_position = 0.0
        try:
            import api_server
            if hasattr(api_server, 'loop_controller_instance') and api_server.loop_controller_instance:
                loop_controller = api_server.loop_controller_instance
                if hasattr(loop_controller, 'cycle_controller') and loop_controller.cycle_controller:
                    position_manager = loop_controller.cycle_controller.position_manager
                    swing_position = position_manager.get_position_by_type(snapshot.symbol, 'swing')
                    scalp_position = position_manager.get_position_by_type(snapshot.symbol, 'scalp')
        except Exception as e:
            logger.debug(f"Could not get position breakdown for AI: {e}")
        
        # Multi-symbol awareness info
        multi_symbol_info = ""
        if all_symbols:
            multi_symbol_info = f"""
MULTI-SYMBOL & MULTI-POSITION CAPABILITIES:
- Total Symbols Traded: {len(all_symbols)}
- Symbols: {', '.join(all_symbols)}
- SIMULTANEOUS POSITIONS: Can hold BOTH swing AND scalp positions on the SAME symbol!
- Swing positions (1-7 days): Use trailing stops, higher leverage, larger size
- Scalp positions (5-60 min): No trailing stops, lower leverage, smaller size
- CRITICAL: You are trading across MULTIPLE symbols simultaneously. Ensure capital allocation doesn't exceed total equity.
- Total Margin Used (ALL symbols): ${total_margin_used:,.2f}
- Available Cash (remaining): ${available_cash:,.2f}
- Current Leverage (across all positions): {leverage_used:.2f}x
- IMPORTANT: This trade will add to existing positions. Ensure we don't over-leverage the account.
"""

        # Choose timeframe focus based on position type
        position_type = getattr(signal, 'position_type', 'swing').lower()
        if position_type == 'scalp':
            timeframe_section = f"""
INTRADAY MARKET ANALYSIS (SCALP):
15M: {indicators.get('trend_15m', 'unknown')}{keltner_prompt_15m}
5M: {indicators.get('trend_5m', 'unknown')} (EMA50: ${indicators.get('ema_50_5m', 0):,.2f}, RSI: {indicators.get('rsi_5m', 50):.1f}){keltner_prompt_5m}
1M: {indicators.get('trend_1m', 'unknown')} (EMA50: ${indicators.get('ema_50_1m', 0):,.2f}, RSI: {indicators.get('rsi_1m', 50):.1f}){keltner_prompt_1m}
VOLATILITY: ATR(14) ${indicators.get('atr_14', 0):,.2f}
"""
            volume_section = f"""
VOLUME & MOMENTUM CONFIRMATION:
5M Volume: {indicators.get('volume_ratio_5m', 1.0):.2f}x avg ({'STRONG' if indicators.get('volume_ratio_5m', 1.0) >= 1.5 else 'MODERATE' if indicators.get('volume_ratio_5m', 1.0) >= 1.3 else 'WEAK'})
OBV Trend (5m): {indicators.get('obv_trend_5m', 'neutral')} (money flow direction)
VWAP 5M: ${vwap_5m_prompt:,.2f} (price is {vwap_relation_5m})
"""
            wrong_direction_warning = "LONG when 15M/5M bearish, SHORT when 15M/5M bullish"
            tf_harmony_line = "15M/5M/1M trends align with trade direction (ideal, but not required)"
        else:
            timeframe_section = f"""
MULTI-TIMEFRAME MARKET ANALYSIS (SWING):
DAILY: {indicators.get('trend_1d', 'unknown')} (EMA50: ${indicators.get('ema_50_1d', 0):,.2f})
4H: {indicators.get('trend_4h', 'unknown')} (EMA50: ${indicators.get('ema_50_4h', 0):,.2f})
1H: {indicators.get('trend_1h', 'unknown')} (EMA50: ${indicators.get('ema_50', 0):,.2f}, RSI: {indicators.get('rsi_14', 50):.1f}){keltner_prompt_1h}
15M ENTRY: {indicators.get('trend_15m', 'unknown')}{keltner_prompt_15m}
VOLATILITY: ATR(14) ${indicators.get('atr_14', 0):,.2f}
"""
            volume_section = f"""
VOLUME & MOMENTUM CONFIRMATION:
1H Volume: {indicators.get('volume_ratio_1h', 1.0):.2f}x avg ({'STRONG' if indicators.get('volume_ratio_1h', 1.0) >= 1.5 else 'MODERATE' if indicators.get('volume_ratio_1h', 1.0) >= 1.2 else 'WEAK'})
OBV Trend (1h): {indicators.get('obv_trend_1h', 'neutral')} (money flow direction)
"""
            wrong_direction_warning = "LONG when 1D/4H bearish, SHORT when 1D/4H bullish"
            tf_harmony_line = "1D/4H trends align with trade direction (ideal, but not required)"

        prompt = f"""You are a CRYPTO TRADING RISK MANAGER for a professional quantitative trading firm.

YOUR MISSION: Act as the FINAL DEFENSE against catastrophic trading decisions AND DYNAMIC CONFIDENCE ASSESSOR. Every signal that reaches you has already passed technical analysis and strategy validation. Your job is to:
1. APPROVE reasonable trades while preventing catastrophic mistakes
2. ASSESS ACTUAL CONFIDENCE dynamically based on ALL market data (not hardcoded strategy values)
3. FIND trade opportunities even when strategy says HOLD (if market conditions are favorable)

CRITICAL: Even if strategy says HOLD with 0.00 confidence, you MUST assess the market and evaluate:
- Is there actually a trade opportunity the strategy missed?
- What is the REAL confidence for this market setup?
- Should we trade despite strategy saying HOLD?

STRATEGY SIGNAL UNDER REVIEW:
TARGET Action: {signal.action.upper()} {snapshot.symbol}
POSITION TYPE: {getattr(signal, 'position_type', 'swing').upper()} ({'Swing trades hold 1-7 days' if getattr(signal, 'position_type', 'swing') == 'swing' else 'Scalp trades hold 5-60 minutes'})
POSITION Size: {signal.size_pct*100:.1f}% of equity (${equity * signal.size_pct:,.0f})
CONFIDENCE: {signal.confidence:.2f}/1.0 (STRATEGY'S HARDCODED VALUE - YOU MUST ASSESS REAL CONFIDENCE!)
STRATEGY REASON: {signal.reason}

CURRENT PORTFOLIO STATUS:
Account Equity: ${equity:,.2f}
Position Value ({snapshot.symbol}): ${position_value:,.2f} ({'LONG' if position_size > 0 else 'SHORT' if position_size < 0 else 'FLAT'})
SWING Position ({snapshot.symbol}): {swing_position:.4f} ({'LONG' if swing_position > 0 else 'SHORT' if swing_position < 0 else 'FLAT'})
SCALP Position ({snapshot.symbol}): {scalp_position:.4f} ({'LONG' if scalp_position > 0 else 'SHORT' if scalp_position < 0 else 'FLAT'})
Available Cash: ${available_cash:,.2f}
Required Cash: ${required_cash:,.2f} ({'SUFFICIENT' if available_cash >= required_cash else 'INSUFFICIENT'})
{multi_symbol_info}

{timeframe_section}

KEY PRICE LEVELS (SUPPORT/RESISTANCE):
Current Price: ${snapshot.price:,.2f}
Resistance: R1=${indicators.get('resistance_1', 0):,.2f}, R2=${indicators.get('resistance_2', 0):,.2f}
Support: S1=${indicators.get('support_1', 0):,.2f}, S2=${indicators.get('support_2', 0):,.2f}
Swing Points: High=${indicators.get('swing_high', 0):,.2f}, Low=${indicators.get('swing_low', 0):,.2f}

{volume_section}
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
- Wrong direction: {wrong_direction_warning}
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

APPROVAL CRITERIA (LEAN STRONGLY TOWARD APPROVAL):
CRITICAL: The strategy has already analyzed this setup and assigned confidence {signal.confidence:.2f}/1.0. HIGH CONFIDENCE (>=0.75) indicates the strategy sees a strong edge. Your role is to prevent catastrophic mistakes, NOT to second-guess every trade.

APPROVE IF ANY OF THESE ARE TRUE:
- Strategy confidence >=0.80: High-confidence signals should be APPROVED unless there are CRITICAL risk factors (e.g., insufficient cash, extreme RSI >85, or severe liquidity crisis)
- Strategy confidence >=0.70 AND setup is at key support/resistance: Medium-high confidence at important levels warrants approval
- Multi-TF harmony: {tf_harmony_line}
- Volume confirmation: >=1.2x average with supportive OBV flow (ideal, but not required)
- Strategic positioning: LONG near support, SHORT near resistance (ideal, but not required)
- Liquidity comfort: Tight spreads, supporting order book (ideal, but not required)
- No CRITICAL red flags: Cash sufficient, RSI not extreme, spreads reasonable

# Special guidance for HOLD-origin signals (strategy confidence low):
- For SCALP: If YOUR assessed confidence >= 0.55 and no CRITICAL red flags, APPROVE
- For SWING: If YOUR assessed confidence >= 0.60 and no CRITICAL red flags, APPROVE
- Counter-trend is allowed if risk is managed (tight SL, clear invalidation, strong microstructure)

STRATEGY CONFIDENCE WEIGHTING:
- >=0.85: APPROVE unless cash insufficient OR extreme RSI (>85/<15) OR severe liquidity crisis
- >=0.75: APPROVE unless multiple critical warnings converge (e.g., wrong direction + weak volume + opposing order book + insufficient cash)
- >=0.65: APPROVE if setup is reasonable and no critical warnings
- <0.65: Apply standard skepticism - veto if warnings outweigh benefits

REMEMBER: Counter-trend trades CAN be profitable if the strategy has high confidence. The strategy's confidence score reflects its assessment of edge. Don't veto simply because higher timeframes are bearish - that's why we have stop losses.

FINAL DECISION PROTOCOL:

REQUIRED FORMAT - YOU MUST FOLLOW THIS EXACTLY:

First line: ONLY ONE WORD - "APPROVE" or "VETO"

Then provide structured analysis:
OPPOSITE CHECK: [Force critical analysis of why this could fail]
REASONING: [Balanced assessment of risks, rewards, and market context]
CONCERNS: [Any remaining risk factors or conditions for approval]

MANDATORY CONFIDENCE ASSESSMENT (CRITICAL - REQUIRED FOR ALL DECISIONS - DO NOT SKIP THIS):
You MUST include this exact line: "CONFIDENCE: X.XX" where X.XX is your assessed confidence (0.00-1.00)

You MUST assess the ACTUAL confidence for this decision based on ALL available data:
- Strategy suggests confidence: {signal.confidence:.2f}/1.0 (HARDCODED - IGNORE IF WRONG!)
- But YOU must evaluate: market conditions, indicators, volume, liquidity, risk factors
- Assess REAL confidence: 0.0-1.0 (0.0=no edge, 1.0=perfect setup)
- CONSIDER: Multi-TF alignment, volume confirmation, liquidity, order book, support/resistance proximity
- If strategy says HOLD but market is bullish: Assess confidence 0.3-0.6 and consider LONG
- If strategy says HOLD but market is bearish: Assess confidence 0.3-0.6 and consider SHORT
- If market conditions are PERFECT but strategy underrated: INCREASE confidence significantly
- If market conditions are MIXED but strategy overrated: DECREASE confidence
- If setup is MEDIOCRE: confidence 0.3-0.5
- If setup is GOOD: confidence 0.5-0.7
- If setup is EXCELLENT: confidence 0.7-0.9
- If setup is EXCEPTIONAL: confidence 0.9-1.0
- If NO setup exists (confirmed HOLD): confidence 0.00-0.20

CRITICAL FOR HOLD DECISIONS:
- If strategy says HOLD with 0.00 confidence, you MUST still assess the market
- If you find a trade opportunity (LONG/SHORT), you can APPROVE it even if strategy said HOLD
- You MUST assess confidence for ALL decisions, including HOLD
- For HOLD: Assess if there's actually a trade opportunity the strategy missed
- If no opportunity: Assess confidence as 0.00-0.20 (very low) - BUT STILL PROVIDE "CONFIDENCE: 0.XX"
- If opportunity found: Assess confidence 0.3-1.0 and APPROVE the trade

IMPORTANT: Always end your response with "CONFIDENCE: X.XX" on its own line. This is MANDATORY.
- Your confidence assessment will OVERRIDE the strategy's hardcoded confidence
- Use YOUR judgment - you see the full market picture, not just hardcoded rules
- NEVER return 0.00 confidence unless you're CERTAIN there's no opportunity
LEVERAGE SUGGESTION (ONLY if confidence >= 0.75):
If you APPROVE this trade and confidence is >= 0.75, you may suggest optimal leverage by adding:
LEVERAGE: Xx (where X is 1 or 2 ONLY - Binance does NOT support decimal leverage like 1.5x or 2.5x)
- Accounts $100+: Max 2x leverage (use 2x for high confidence, 1x for medium/low)
- Accounts <$100: Max 1x leverage (always use 1x)
- Consider: Higher leverage (2x) for high confidence + strong setups, 1x for medium/low confidence
- Your leverage suggestion will OVERRIDE the calculated leverage if provided
- If you don't suggest leverage, system will use calculated leverage based on confidence (whole numbers only: 1x or 2x)

You are the last line of defense AND DYNAMIC CONFIDENCE ASSESSOR. Assess confidence for ALL decisions. Find trades even when strategy says HOLD. Be professionally skeptical but APPROVE when you find opportunities. Protect capital without being paralyzed by fear."""

        return prompt
