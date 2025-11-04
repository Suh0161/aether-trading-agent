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

    def adjust_tp_sl(self, snapshot, signal, position_size: float, equity: float) -> Tuple[Optional[float], Optional[float]]:
        """
        Use AI to optionally adjust TP/SL when confidence is high.

        Only called when:
        1. AI has already approved the trade
        2. Signal confidence >= 0.7 (high confidence)

        Args:
            snapshot: Market snapshot
            signal: Strategy signal (already approved)
            position_size: Current position
            equity: Account equity

        Returns:
            Tuple of (adjusted_tp, adjusted_sl) or (None, None) if no adjustment
        """
        # Only adjust if confidence is high (>= 0.7)
        if signal.confidence < 0.7:
            return (None, None)

        try:
            # Build prompt for TP/SL adjustment
            prompt = self._build_tp_sl_adjustment_prompt(snapshot, signal, position_size, equity)

            # Call AI
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                timeout=10.0
            )

            ai_response = response.choices[0].message.content.strip()

            # Parse AI response for adjusted TP/SL
            adjusted_tp, adjusted_sl = self._parse_tp_sl_adjustment(ai_response, signal, snapshot.price)

            if adjusted_tp is not None or adjusted_sl is not None:
                logger.info(
                    f"AI adjusted TP/SL for {signal.action.upper()} "
                    f"(conf: {signal.confidence:.2f}): "
                    f"TP={f'${adjusted_tp:,.2f}' if adjusted_tp else 'None'}, "
                    f"SL={f'${adjusted_sl:,.2f}' if adjusted_sl else 'None'}"
                )

            return (adjusted_tp, adjusted_sl)

        except Exception as e:
            logger.warning(f"AI TP/SL adjustment failed: {e} - using strategy defaults")
            return (None, None)

    def _parse_tp_sl_adjustment(self, ai_response: str, signal, entry_price: float) -> Tuple[Optional[float], Optional[float]]:
        """
        Parse AI response for TP/SL adjustments.

        Expected format:
        - "TP: $108000" or "TP: 108000" or "take_profit: 108000"
        - "SL: $96000" or "SL: 96000" or "stop_loss: 96000"
        - Or JSON format: {"take_profit": 108000, "stop_loss": 96000}

        Args:
            ai_response: AI response text
            signal: Strategy signal (for validation)
            entry_price: Entry price for validation

        Returns:
            Tuple of (adjusted_tp, adjusted_sl) or (None, None)
        """
        adjusted_tp = None
        adjusted_sl = None

        ai_response_lower = ai_response.lower()

        # Try to parse as JSON first
        try:
            # Look for JSON block in response
            json_match = re.search(r'\{[^}]*"take_profit"[^}]*"stop_loss"[^}]*\}', ai_response, re.IGNORECASE)
            if json_match:
                json_str = json_match.group()
                parsed = json.loads(json_str)
                adjusted_tp = parsed.get('take_profit')
                adjusted_sl = parsed.get('stop_loss')
                logger.debug(f"Parsed TP/SL from JSON: TP={adjusted_tp}, SL={adjusted_sl}")
        except (json.JSONDecodeError, KeyError):
            pass

        # If JSON parsing failed, try text parsing
        if adjusted_tp is None and adjusted_sl is None:
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

        return adjusted_tp, adjusted_sl

    def _build_tp_sl_adjustment_prompt(self, snapshot, signal, position_size: float, equity: float) -> str:
        """Build prompt for TP/SL adjustment."""
        indicators = snapshot.indicators
        entry_price = snapshot.price  # Assuming current price is entry

        # Get risk/reward info if available
        risk_amount = getattr(signal, 'risk_amount', None)
        reward_amount = getattr(signal, 'reward_amount', None)

        prompt = f"""You are a professional trader optimizing take profit and stop loss levels.

TRADE DETAILS:
- Action: {signal.action.upper()}
- Symbol: {snapshot.symbol}
- Entry Price: ${entry_price:,.2f}
- Confidence: {signal.confidence:.2f}
- Strategy TP: ${signal.take_profit:,.2f} ({((signal.take_profit - entry_price)/entry_price*100):+.1f}% from entry)
- Strategy SL: ${signal.stop_loss:,.2f} ({((signal.stop_loss - entry_price)/entry_price*100):+.1f}% from entry)
{f"- Risk Amount: ${risk_amount:,.2f}" if risk_amount else ""}
{f"- Reward Amount: ${reward_amount:,.2f}" if reward_amount else ""}

MARKET CONTEXT:
- Daily Trend: {indicators.get('trend_1d', 'unknown')}
- 4H Trend: {indicators.get('trend_4h', 'unknown')}
- 1H Trend: {indicators.get('trend_1h', 'unknown')}
- RSI 14: {indicators.get('rsi_14', 50):.1f}
- Support/Resistance: S1=${indicators.get('support_1', 0):,.2f}, R1=${indicators.get('resistance_1', 0):,.2f}, S2=${indicators.get('support_2', 0):,.2f}, R2=${indicators.get('resistance_2', 0):,.2f}
- Swing Levels: High=${indicators.get('swing_high', 0):,.2f}, Low=${indicators.get('swing_low', 0):,.2f}
- Volume: 1H={indicators.get('volume_ratio_1h', 1.0):.2f}x, OBV={indicators.get('obv_trend_1h', 'neutral')}

TASK: Optimize TP/SL levels for maximum profit potential while managing risk.

CONSIDERATIONS:
1. Support/Resistance Levels: Use S/R as natural TP/SL targets
2. Trend Strength: Extend TP in strong trends, tighten SL in weak trends
3. Volume Confirmation: Strong volume supports larger targets
4. Risk/Reward: Aim for at least 2:1 reward-to-risk ratio
5. Market Structure: Respect swing highs/lows and key levels

RESPONSE FORMAT: Provide adjusted levels in one of these formats:

Option 1 - Text format:
TP: $108000
SL: $96000

Option 2 - JSON format:
{"take_profit": 108000, "stop_loss": 96000}

Only provide adjustments if you can improve upon the strategy's levels. If the strategy levels are optimal, respond with "NO_ADJUSTMENT"."""

        return prompt
