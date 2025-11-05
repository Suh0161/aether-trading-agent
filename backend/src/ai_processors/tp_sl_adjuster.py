"""AI-powered TP/SL adjustment logic."""

import logging
import json
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class TPSLAdjuster:
    """AI-powered take profit and stop loss adjustments."""

    def __init__(self, client):
        """
        Initialize TP/SL adjuster.

        Args:
            client: OpenAI client for API calls
        """
        self.client = client

    def adjust_tp_sl(self, snapshot, signal, position_size: float, equity: float) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Use AI to optionally adjust TP/SL and trailing stop percentage when confidence is high.

        Only called when:
        1. AI has already approved the trade
        2. Signal confidence >= 0.7 (high confidence)

        Args:
            snapshot: Market snapshot
            signal: Strategy signal (already approved)
            position_size: Current position
            equity: Account equity

        Returns:
            Tuple of (adjusted_tp, adjusted_sl, trailing_stop_pct) or (None, None, None) if no adjustment
        """
        # Only adjust if confidence is high (>= 0.7)
        if signal.confidence < 0.7:
            return (None, None, None)

        ai_response = None  # Initialize to avoid scoping issues
        try:
            # Build prompt for TP/SL adjustment
            prompt = self._build_tp_sl_adjustment_prompt(snapshot, signal, position_size, equity)

            # Call AI with sufficient timeout for TP/SL analysis
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                timeout=15.0  # Increased timeout for TP/SL analysis
            )

            ai_response = response.choices[0].message.content.strip()

            # Parse AI response for adjusted TP/SL and trailing stop percentage
            adjusted_tp, adjusted_sl, trailing_pct = self._parse_tp_sl_adjustment(ai_response, signal, snapshot.price)

            if adjusted_tp is not None or adjusted_sl is not None or trailing_pct is not None:
                logger.info(
                    f"AI adjusted TP/SL/Trailing for {signal.action.upper()} "
                    f"(conf: {signal.confidence:.2f}): "
                    f"TP={f'${adjusted_tp:,.2f}' if adjusted_tp else 'None'}, "
                    f"SL={f'${adjusted_sl:,.2f}' if adjusted_sl else 'None'}, "
                    f"Trailing={f'{trailing_pct*100:.1f}%' if trailing_pct else 'None'}"
                )

            return (adjusted_tp, adjusted_sl, trailing_pct)

        except Exception as e:
            logger.warning(f"AI TP/SL adjustment failed: {e}")
            # Safely log AI response if it exists
            try:
                if ai_response:
                    # Safely log AI response without format specifier issues (escape braces)
                    safe_response = str(ai_response[:500]).replace('{', '{{').replace('}', '}}')
                    logger.debug(f"AI Response that caused error: {safe_response}")
            except Exception:
                pass  # Don't fail if logging fails
            logger.info("Using strategy defaults for TP/SL/Trailing")
            return (None, None, None)

    def _parse_tp_sl_adjustment(self, ai_response: str, signal, entry_price: float) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Parse AI response for TP/SL and trailing stop adjustments.

        Expected format:
        - "TP: $108000" or "TP: 108000" or "take_profit: 108000"
        - "SL: $96000" or "SL: 96000" or "stop_loss: 96000"
        - "Trailing: 10%" or "trailing_stop: 0.10" or "trail: 0.12"
        - Or JSON format: {"take_profit": 108000, "stop_loss": 96000, "trailing_stop_pct": 0.10}
        - Or "NO_ADJUSTMENT" to keep strategy defaults

        Args:
            ai_response: AI response text
            signal: Strategy signal (for validation)
            entry_price: Entry price for validation

        Returns:
            Tuple of (adjusted_tp, adjusted_sl, trailing_stop_pct) or (None, None, None)
        """
        adjusted_tp = None
        adjusted_sl = None
        trailing_pct = None

        ai_response_lower = ai_response.lower()

        # Check for "NO_ADJUSTMENT" response
        if "no_adjustment" in ai_response_lower or "no adjustment" in ai_response_lower:
            logger.debug("AI chose NO_ADJUSTMENT - using strategy defaults")
            return (None, None, None)

        # Try to parse as JSON first
        try:
            # Look for JSON block in response - improved regex to handle various formats
            json_patterns = [
                r'\{[^}]*"take_profit"[^}]*"stop_loss"[^}]*\}',  # Original pattern
                r'\{[^}]*"stop_loss"[^}]*"take_profit"[^}]*\}',  # Reversed order
                r'\{"take_profit"\s*:\s*([0-9.]+)[^}]*"stop_loss"\s*:\s*([0-9.]+)[^}]*\}',  # More specific
                r'\{"stop_loss"\s*:\s*([0-9.]+)[^}]*"take_profit"\s*:\s*([0-9.]+)[^}]*\}'   # Reversed
            ]
            
            for pattern in json_patterns:
                json_match = re.search(pattern, ai_response, re.IGNORECASE)
                if json_match:
                    json_str = json_match.group()
                    try:
                        # Try to parse as-is first
                        parsed = json.loads(json_str)
                        adjusted_tp = parsed.get('take_profit')
                        adjusted_sl = parsed.get('stop_loss')
                        trailing_pct = parsed.get('trailing_stop_pct') or parsed.get('trailing_stop') or parsed.get('trailing')
                        # Convert trailing percentage from 0.10 format to float if it's a number
                        if trailing_pct is not None:
                            if isinstance(trailing_pct, str) and trailing_pct.endswith('%'):
                                trailing_pct = float(trailing_pct.rstrip('%')) / 100.0
                            elif isinstance(trailing_pct, (int, float)):
                                trailing_pct = float(trailing_pct)
                                # If it's > 1, assume it's a percentage (e.g., 10 means 10%)
                                if trailing_pct > 1:
                                    trailing_pct = trailing_pct / 100.0
                        if adjusted_tp is not None or adjusted_sl is not None or trailing_pct is not None:
                            logger.debug(f"Parsed TP/SL/Trailing from JSON: TP={adjusted_tp}, SL={adjusted_sl}, Trailing={trailing_pct}")
                            break
                    except json.JSONDecodeError:
                        # If parsing fails, try to extract numbers directly from regex groups
                        if len(json_match.groups()) >= 2:
                            try:
                                # Pattern with capture groups
                                if 'take_profit' in json_str.lower()[:50]:
                                    adjusted_tp = float(json_match.group(1))
                                    adjusted_sl = float(json_match.group(2))
                                else:
                                    adjusted_sl = float(json_match.group(1))
                                    adjusted_tp = float(json_match.group(2))
                                logger.debug(f"Extracted TP/SL from JSON-like text: TP={adjusted_tp}, SL={adjusted_sl}")
                                break
                            except (IndexError, ValueError):
                                continue
        except (json.JSONDecodeError, KeyError, ValueError, AttributeError) as e:
            logger.debug(f"JSON parsing failed: {e}, trying text parsing")
            pass

        # If JSON parsing failed, try text parsing
        if adjusted_tp is None and adjusted_sl is None and trailing_pct is None:
            # Parse TP
            tp_patterns = [
                r'take[_ ]profit[:=]\s*\$?([0-9,]+\.?[0-9]*)',
                r'tp[:=]\s*\$?([0-9,]+\.?[0-9]*)',
                r'profit[_ ]target[:=]\s*\$?([0-9,]+\.?[0-9]*)'
            ]

            for pattern in tp_patterns:
                tp_match = re.search(pattern, ai_response_lower, re.IGNORECASE)
                if tp_match:
                    try:
                        adjusted_tp = float(tp_match.group(1).replace(',', ''))
                        break
                    except ValueError:
                        continue

            # Parse SL
            sl_patterns = [
                r'stop[_ ]loss[:=]\s*\$?([0-9,]+\.?[0-9]*)',
                r'sl[:=]\s*\$?([0-9,]+\.?[0-9]*)',
                r'stop[:=]\s*\$?([0-9,]+\.?[0-9]*)'
            ]

            for pattern in sl_patterns:
                sl_match = re.search(pattern, ai_response_lower, re.IGNORECASE)
                if sl_match:
                    try:
                        adjusted_sl = float(sl_match.group(1).replace(',', ''))
                        break
                    except ValueError:
                        continue

            # Parse trailing stop percentage
            trailing_patterns = [
                r'trailing[_ ]stop[_ ]pct[:=]\s*([0-9.]+)%?',
                r'trailing[_ ]stop[:=]\s*([0-9.]+)%?',
                r'trailing[:=]\s*([0-9.]+)%?',
                r'trail[:=]\s*([0-9.]+)%?'
            ]

            for pattern in trailing_patterns:
                trailing_match = re.search(pattern, ai_response_lower, re.IGNORECASE)
                if trailing_match:
                    try:
                        trailing_value = float(trailing_match.group(1))
                        # If value > 1, assume it's a percentage (e.g., 10 means 10%)
                        if trailing_value > 1:
                            trailing_pct = trailing_value / 100.0
                        else:
                            trailing_pct = trailing_value
                        # Validate trailing percentage is reasonable (5% to 20%)
                        if 0.05 <= trailing_pct <= 0.20:
                            break
                        else:
                            logger.warning(f"Trailing percentage {trailing_pct*100:.1f}% out of range (5-20%), ignoring")
                            trailing_pct = None
                    except ValueError:
                        continue

        # Validate adjustments make sense
        if adjusted_tp is not None:
            # For LONG: TP should be above entry price
            # For SHORT: TP should be below entry price
            if signal.action == "long" and adjusted_tp <= entry_price:
                logger.warning(f"Invalid TP adjustment for LONG: ${adjusted_tp:.2f} <= entry ${entry_price:.2f}")
                adjusted_tp = None
            elif signal.action == "short" and adjusted_tp >= entry_price:
                logger.warning(f"Invalid TP adjustment for SHORT: ${adjusted_tp:.2f} >= entry ${entry_price:.2f}")
                adjusted_tp = None

        if adjusted_sl is not None:
            # For LONG: SL should be below entry price
            # For SHORT: SL should be above entry price
            if signal.action == "long" and adjusted_sl >= entry_price:
                logger.warning(f"Invalid SL adjustment for LONG: ${adjusted_sl:.2f} >= entry ${entry_price:.2f}")
                adjusted_sl = None
            elif signal.action == "short" and adjusted_sl <= entry_price:
                logger.warning(f"Invalid SL adjustment for SHORT: ${adjusted_sl:.2f} <= entry ${entry_price:.2f}")
                adjusted_sl = None

        # Validate trailing percentage if provided
        if trailing_pct is not None:
            # Validate trailing percentage is reasonable (5% to 20%)
            if trailing_pct < 0.05 or trailing_pct > 0.20:
                logger.warning(f"Trailing percentage {trailing_pct*100:.1f}% out of range (5-20%), ignoring")
                trailing_pct = None

        return adjusted_tp, adjusted_sl, trailing_pct

    def _build_tp_sl_adjustment_prompt(self, snapshot, signal, position_size: float, equity: float) -> str:
        """Build prompt for TP/SL adjustment."""
        indicators = snapshot.indicators
        entry_price = snapshot.price  # Assuming current price is entry

        # Get risk/reward info if available
        risk_amount = getattr(signal, 'risk_amount', None)
        reward_amount = getattr(signal, 'reward_amount', None)

        prompt = f"""You are a professional trader optimizing take profit, stop loss, AND trailing stop levels.

CRITICAL: You have FULL CONTROL over THREE risk management parameters:
1. TAKE PROFIT (TP) - Price level to exit with profit
2. STOP LOSS (SL) - Price level to exit with loss protection  
3. TRAILING STOP PERCENTAGE - Percentage to trail behind price (for swing trades only, 5-20% range)

You can adjust ANY or ALL of these parameters based on market conditions. Your adjustments will override the strategy defaults.

TRADE DETAILS:
- Action: {signal.action.upper()}
- Symbol: {snapshot.symbol}
- Entry Price: ${entry_price:,.2f}
- Confidence: {signal.confidence:.2f}
- Position Type: {signal.position_type.upper()} ({'Swing trades use trailing stops' if signal.position_type == 'swing' else 'Scalp trades do not use trailing stops'})
- Strategy TP: ${signal.take_profit:,.2f} ({((signal.take_profit - entry_price)/entry_price*100):+.1f}% from entry)
- Strategy SL: ${signal.stop_loss:,.2f} ({((signal.stop_loss - entry_price)/entry_price*100):+.1f}% from entry)
- Default Trailing: {'10-15% (based on confidence)' if signal.position_type == 'swing' else 'N/A (scalps do not trail)'}
{f"- Risk Amount: ${risk_amount:,.2f}" if risk_amount else ""}
{f"- Reward Amount: ${reward_amount:,.2f}" if reward_amount else ""}

MARKET CONTEXT:
- Daily Trend: {indicators.get('trend_1d', 'unknown')}
- 4H Trend: {indicators.get('trend_4h', 'unknown')}
- 1H Trend: {indicators.get('trend_1h', 'unknown')}
- RSI 14: {indicators.get('rsi_14', 50):.1f}
- Volatility (ATR): ${indicators.get('atr_14', 0):,.2f} ({indicators.get('atr_14', 0)/entry_price*100:.2f}% of price)
- Support/Resistance: S1=${indicators.get('support_1', 0):,.2f}, R1=${indicators.get('resistance_1', 0):,.2f}, S2=${indicators.get('support_2', 0):,.2f}, R2=${indicators.get('resistance_2', 0):,.2f}
- Swing Levels: High=${indicators.get('swing_high', 0):,.2f}, Low=${indicators.get('swing_low', 0):,.2f}
- Volume: 1H={indicators.get('volume_ratio_1h', 1.0):.2f}x, OBV={indicators.get('obv_trend_1h', 'neutral')}

TASK: Optimize TP/SL levels AND trailing stop percentage for maximum profit potential while managing risk.

CONSIDERATIONS FOR TP/SL:
1. Support/Resistance Levels: Use S/R as natural TP/SL targets
2. Trend Strength: Extend TP in strong trends, tighten SL in weak trends
3. Volume Confirmation: Strong volume supports larger targets
4. Risk/Reward: Aim for at least 2:1 reward-to-risk ratio
5. Market Structure: Respect swing highs/lows and key levels

CONSIDERATIONS FOR TRAILING STOP PERCENTAGE (Swing trades only):
1. High Volatility: Use wider trailing (12-15%) to avoid premature exits
2. Low Volatility: Use tighter trailing (8-10%) to lock in profits faster
3. Strong Trends: Use tighter trailing (8-10%) as trend is strong
4. Weak Trends: Use wider trailing (12-15%) to give price room
5. Confidence Level: Higher confidence trades can use tighter trailing
6. Valid Range: 5% to 20% (recommended: 8-15%)

RESPONSE FORMAT: Provide adjusted levels in one of these formats:

Option 1 - Text format:
TP: $108000
SL: $96000
Trailing: 10%  (or Trailing: 0.10)

Option 2 - JSON format:
{{"take_profit": 108000, "stop_loss": 96000, "trailing_stop_pct": 0.10}}

IMPORTANT NOTES:
- You can provide TP, SL, trailing, or any combination
- If you don't want to adjust a parameter, omit it (strategy default will be used)
- For trailing stop: Use decimal (0.10 = 10%) or percentage (10% = 10%)
- Trailing stops only apply to SWING trades (scalps don't use trailing)
- If all strategy levels are optimal, respond with "NO_ADJUSTMENT"
- REMEMBER: You control TP, SL, AND trailing stop percentage!"""

        return prompt
