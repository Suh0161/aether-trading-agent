"""AI message generation service for trading agent."""

import logging
from typing import Dict, Optional

from src.utils.snapshot_utils import get_price_from_snapshot, get_base_snapshot

logger = logging.getLogger(__name__)


class AIMessageService:
    """Service for generating AI-powered trading messages."""

    def __init__(self, openai_client=None):
        """
        Initialize AI message service.

        Args:
            openai_client: OpenAI client for AI message generation
        """
        self.openai_client = openai_client

        # Track last agent message to avoid spam
        self.last_message_type = None  # Track last message type sent
        self.last_message_cycle = 0  # Track which cycle last message was sent
        self.sent_welcome_message = False  # Track if welcome message was sent (once per session)
        self.last_hold_message_cycle = {}  # Track per-symbol hold messages: {symbol: cycle}

        # New: Collect cycle decisions for consolidated messaging
        self.current_cycle_decisions = {}  # {symbol: decision_data} for current cycle
        self.cycle_api_client = None  # Store API client for cycle-end messaging
        self.cycles_since_last_summary = 0  # Track cycles since last summary message

    def generate_ai_message(
        self, decision, snapshot, position_size: float, equity: float,
        available_cash: float, unrealized_pnl: float, all_snapshots: dict = None,
        realized_pnl: float = None
    ) -> str:
        """
        Use AI to generate natural, conversational trading messages.

        Args:
            decision: Trading decision
            snapshot: Market snapshot for the trading symbol
            position_size: Current position size
            equity: Account equity
            available_cash: Available cash
            unrealized_pnl: Unrealized P&L
            all_snapshots: Dict of {symbol: snapshot} for all monitored coins

        Returns:
            Natural language message from AI
        """
        if not self.openai_client:
            # Fallback to simple message if AI not available
            return f"{decision.action.upper()}: {decision.reason}"

        try:
            # Get position type
            position_type = getattr(decision, 'position_type', 'swing')

            # Build context for AI
            base_snapshot = get_base_snapshot(snapshot)
            indicators = base_snapshot.indicators
            price = get_price_from_snapshot(snapshot)
            symbol = base_snapshot.symbol
            base_currency = symbol.split('/')[0]

            # Build ALL COINS market overview (COMPREHENSIVE - ALL INDICATORS)
            all_coins_context = ""
            if all_snapshots:
                all_coins_context = "\n\nALL 6 COINS MARKET OVERVIEW (COMPLETE DATA):\n"
                for coin_symbol, coin_snap in all_snapshots.items():
                    coin_name = coin_symbol.split('/')[0]
                    coin_price = get_price_from_snapshot(coin_snap)
                    coin_base = get_base_snapshot(coin_snap)
                    coin_ind = coin_base.indicators

                    # Multi-timeframe trends
                    coin_trend_1d = coin_ind.get('trend_1d', 'unknown')
                    coin_trend_4h = coin_ind.get('trend_4h', 'unknown')
                    coin_trend_1h = 'bullish' if coin_price > coin_ind.get('ema_50', 0) else 'bearish'
                    coin_trend_15m = coin_ind.get('trend_15m', 'unknown')
                    coin_trend_5m = coin_ind.get('trend_5m', 'unknown')
                    coin_trend_1m = coin_ind.get('trend_1m', 'unknown')

                    # Key indicators
                    coin_ema_50 = coin_ind.get('ema_50', 0)
                    coin_rsi = coin_ind.get('rsi_14', 50)
                    coin_atr = coin_ind.get('atr_14', 0)
                    coin_vwap_1h = coin_ind.get('vwap_1h', coin_price)
                    coin_vwap_5m = coin_ind.get('vwap_5m', coin_price)
                    vwap_pos_1h = 'above' if coin_price > coin_vwap_1h else 'below'
                    vwap_pos_5m = 'above' if coin_price > coin_vwap_5m else 'below'

                    # Keltner Channels
                    coin_keltner_upper_1h = coin_ind.get('keltner_upper', 0)
                    coin_keltner_lower_1h = coin_ind.get('keltner_lower', 0)
                    coin_keltner_upper_5m = coin_ind.get('keltner_upper_5m', 0)
                    coin_keltner_lower_5m = coin_ind.get('keltner_lower_5m', 0)

                    # Support/Resistance
                    coin_r1 = coin_ind.get('resistance_1', 0)
                    coin_r2 = coin_ind.get('resistance_2', 0)
                    coin_r3 = coin_ind.get('resistance_3', 0)
                    coin_s1 = coin_ind.get('support_1', 0)
                    coin_s2 = coin_ind.get('support_2', 0)
                    coin_s3 = coin_ind.get('support_3', 0)
                    coin_swing_high = coin_ind.get('swing_high', 0)
                    coin_swing_low = coin_ind.get('swing_low', 0)

                    # Volume analysis
                    coin_vol_1h = coin_ind.get('volume_ratio_1h', 1.0)
                    coin_vol_5m = coin_ind.get('volume_ratio_5m', 1.0)
                    coin_obv_1h = coin_ind.get('obv_trend_1h', 'neutral')
                    coin_obv_5m = coin_ind.get('obv_trend_5m', 'neutral')
                    vol_str_1h = 'STRONG' if coin_vol_1h >= 1.5 else 'MODERATE' if coin_vol_1h >= 1.2 else 'WEAK'
                    vol_str_5m = 'STRONG' if coin_vol_5m >= 1.5 else 'MODERATE' if coin_vol_5m >= 1.2 else 'WEAK'

                    # Format price based on magnitude
                    if coin_price >= 1000:
                        price_str = f"${coin_price:,.2f}"
                    elif coin_price >= 1:
                        price_str = f"${coin_price:,.2f}"
                    else:
                        price_str = f"${coin_price:.4f}"

                    all_coins_context += f"""
{coin_name}/{coin_symbol.split('/')[1]}:
  Price: {price_str}
  Trends: 1D={coin_trend_1d}, 4H={coin_trend_4h}, 1H={coin_trend_1h}, 15m={coin_trend_15m}, 5m={coin_trend_5m}, 1m={coin_trend_1m}
  Indicators: EMA50=${coin_ema_50:,.2f}, RSI={coin_rsi:.1f}, ATR=${coin_atr:.2f}
  VWAP: 1h=${coin_vwap_1h:,.2f} ({vwap_pos_1h}), 5m=${coin_vwap_5m:,.2f} ({vwap_pos_5m})
  Keltner 1h: Upper=${coin_keltner_upper_1h:,.2f}, Lower=${coin_keltner_lower_1h:,.2f}
  Keltner 5m: Upper=${coin_keltner_upper_5m:,.2f}, Lower=${coin_keltner_lower_5m:,.2f}
  S/R: R1=${coin_r1:,.2f}, R2=${coin_r2:,.2f}, R3=${coin_r3:,.2f} | S1=${coin_s1:,.2f}, S2=${coin_s2:,.2f}, S3=${coin_s3:,.2f}
  Swing: High=${coin_swing_high:,.2f}, Low=${coin_swing_low:,.2f}
  Volume: 1h={coin_vol_1h:.2f}x ({vol_str_1h}, OBV={coin_obv_1h}), 5m={coin_vol_5m:.2f}x ({vol_str_5m}, OBV={coin_obv_5m})
"""

            # Build prompt for AI message generation
            prompt = f"""You are Aether, an autonomous trading assistant. You're fully aware of your capabilities:

YOUR CAPABILITIES:
- You monitor 6 cryptocurrencies (BTC, ETH, SOL, DOGE, BNB, XRP) every 30 seconds
- You analyze technical indicators across multiple timeframes (1D, 4H, 1H, 15M, 5M, 1M)
- You make trading decisions based on market conditions, risk management, and strategy
- You execute trades automatically when conditions are met
- You communicate with users about your actions and market observations

CURRENT SITUATION:
- Symbol: {symbol}
- Current Price: ${price:,.2f}
- Position Size: {position_size:.6f} ({position_type})
- Account Equity: ${equity:,.2f}
- Available Cash: ${available_cash:,.2f}
- Unrealized P&L: ${unrealized_pnl:+,.2f}
{"- Realized P&L: $" + f"{realized_pnl:+,.2f}" if realized_pnl is not None else ""}

DECISION MADE:
- Action: {decision.action.upper()}
- Position Type: {position_type}
- Reason: {decision.reason}

{all_coins_context}

INSTRUCTIONS FOR YOUR RESPONSE:
- Be conversational and natural, like you're chatting with a friend about trading
- Explain your decision in simple terms that anyone can understand
- Keep it concise but informative (2-3 sentences max)
- Show personality - be confident but not arrogant
- For BUY/SELL actions: Briefly explain the technical setup that triggered the trade
- For CLOSE actions: Explain why you're taking profits or cutting losses
- For HOLD actions: Give a quick market update on why you're waiting
- Reference specific indicators when relevant (RSI, EMA, support/resistance, volume, trends)
- Use the current market context to support your explanation

Remember: You're Aether, the autonomous trading assistant. Sound professional but approachable."""

            # Call OpenAI API
            response = self.openai_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "You are Aether, an autonomous trading assistant who communicates naturally about trading decisions."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.7
            )

            message = response.choices[0].message.content.strip()

            # Clean up message (remove quotes if present)
            if message.startswith('"') and message.endswith('"'):
                message = message[1:-1]
            if message.startswith("'") and message.endswith("'"):
                message = message[1:-1]

            return message

        except Exception as e:
            logger.warning(f"Failed to generate AI message: {e}")
            # Fallback to simple message
            return f"{decision.action.upper()}: {decision.reason}"

    def send_smart_agent_message(
        self, decision, snapshot, position_size: float, equity: float,
        available_cash: float, unrealized_pnl: float, cycle_count: int,
        api_client, all_snapshots: dict = None, realized_pnl: float = None
    ) -> None:
        """
        Legacy method - now delegates to collect_cycle_decision for backward compatibility.
        """
        self.collect_cycle_decision(
            decision, snapshot, position_size, equity,
            available_cash, unrealized_pnl, cycle_count,
            api_client, all_snapshots, realized_pnl
        )

    def send_welcome_message(
        self, equity: float, all_snapshots: dict, api_client, cycle_count: int
    ) -> None:
        """
        Send a single welcome message on startup with overview of all coins.
        
        Args:
            equity: Account equity
            all_snapshots: Dict of {symbol: snapshot} for all monitored coins
            api_client: API client for sending messages
            cycle_count: Current cycle count
        """
        if not api_client or not self.openai_client or self.sent_welcome_message:
            return
        
        try:
            # Build comprehensive market overview for all coins
            all_coins_summary = []
            for coin_symbol, coin_snap in all_snapshots.items():
                coin_name = coin_symbol.split('/')[0]
                coin_price = get_price_from_snapshot(coin_snap)
                coin_base = get_base_snapshot(coin_snap)
                coin_ind = coin_base.indicators
                
                # Get key indicators
                coin_trend_1d = coin_ind.get('trend_1d', 'unknown')
                coin_trend_4h = coin_ind.get('trend_4h', 'unknown')
                coin_rsi = coin_ind.get('rsi_14', 50)
                coin_s1 = coin_ind.get('support_1', 0)
                
                # Format price
                if coin_price >= 1000:
                    price_str = f"${coin_price:,.2f}"
                elif coin_price >= 1:
                    price_str = f"${coin_price:,.2f}"
                else:
                    price_str = f"${coin_price:.4f}"
                
                all_coins_summary.append(f"{coin_name}: {price_str} (1D: {coin_trend_1d}, 4H: {coin_trend_4h}, RSI: {coin_rsi:.1f}, Support: ${coin_s1:,.2f})")
            
            coins_text = "\n".join(all_coins_summary)
            
            # Generate welcome message with AI
            prompt = f"""You are Aether, an autonomous trading assistant. This is your FIRST message to the user after starting up.

CURRENT STATUS:
- Account Equity: ${equity:,.2f}
- Monitoring 6 cryptocurrencies: BTC, ETH, SOL, DOGE, BNB, XRP
- Analysis frequency: Every 30 seconds
- All coins currently: HOLD (waiting for entry signals)

ALL COINS OVERVIEW:
{coins_text}

INSTRUCTIONS:
- Write a brief, friendly welcome message (2-3 sentences max)
- Give a quick summary of the overall market sentiment (bullish/bearish/mixed)
- Mention that you're monitoring all 6 coins and waiting for good entry opportunities
- Be conversational and confident, but not overly technical
- Don't list individual coins - just give overall market vibe

Remember: This is your introduction. Be warm but professional."""

            response = self.openai_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "You are Aether, a friendly autonomous trading assistant introducing yourself."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.7
            )
            
            message = response.choices[0].message.content.strip()
            
            # Clean up message
            if message.startswith('"') and message.endswith('"'):
                message = message[1:-1]
            if message.startswith("'") and message.endswith("'"):
                message = message[1:-1]
            
            api_client.add_agent_message(message)
            self.sent_welcome_message = True
            logger.info("Welcome message sent to user")
            
        except Exception as e:
            logger.warning(f"Failed to send welcome message: {e}")

    def collect_cycle_decision(
        self, decision, snapshot, position_size: float, equity: float,
        available_cash: float, unrealized_pnl: float, cycle_count: int,
        api_client, all_snapshots: dict = None, realized_pnl: float = None
    ) -> None:
        """
        Collect decision data for consolidated cycle messaging.
        Individual messages are sent for trades, but hold decisions are collected.

        Args:
            decision: Parsed trading decision
            snapshot: Market snapshot
            position_size: Current position size
            equity: Account equity
            available_cash: Available cash for trading
            unrealized_pnl: Unrealized P&L
            cycle_count: Current cycle count
            api_client: API client for sending messages
            all_snapshots: All market snapshots
            realized_pnl: Realized P&L
        """
        # Get symbol from snapshot
        base_snapshot = get_base_snapshot(snapshot)
        symbol = base_snapshot.symbol

        # Store API client for cycle-end messaging
        self.cycle_api_client = api_client

        # === ALWAYS SEND: Important actions (trades) ===
        if decision.action in ["long", "short", "close"]:
            message = self.generate_ai_message(
                decision, snapshot, position_size, equity,
                available_cash, unrealized_pnl, all_snapshots, realized_pnl=realized_pnl
            )
            api_client.add_agent_message(message)
            self.last_message_type = decision.action
            self.last_message_cycle = cycle_count
            return

        # === COLLECT: Hold decisions for consolidated messaging ===
        elif decision.action == "hold":
            # Store decision data for cycle summary
            self.current_cycle_decisions[symbol] = {
                'decision': decision,
                'snapshot': snapshot,
                'position_size': position_size,
                'equity': equity,
                'available_cash': available_cash,
                'unrealized_pnl': unrealized_pnl,
                'all_snapshots': all_snapshots,
                'cycle_count': cycle_count
            }

    def send_cycle_summary_message(self, cycle_count: int) -> None:
        """
        Send a consolidated summary of all hold decisions for this cycle.
        Only sends every 7 cycles when idle to prevent spam.

        Args:
            cycle_count: Current cycle count
        """
        # Always increment counter (whether we send or not)
        self.cycles_since_last_summary += 1

        if not self.current_cycle_decisions or not self.cycle_api_client:
            return

        try:
            # Only send summary every 7 cycles when all coins are idle
            should_send_summary = (self.cycles_since_last_summary >= 7)

            if should_send_summary:
                # Generate consolidated message for all coins
                message = self._generate_cycle_summary_message(cycle_count)

                if message:
                    self.cycle_api_client.add_agent_message(message)
                    self.last_message_type = "cycle_summary"
                    self.last_message_cycle = cycle_count
                    self.cycles_since_last_summary = 0  # Reset counter

                    # Update hold message cycles for all symbols in this summary
                    for symbol in self.current_cycle_decisions.keys():
                        self.last_hold_message_cycle[symbol] = cycle_count

        except Exception as e:
            logger.warning(f"Failed to send cycle summary message: {e}")

        # Clear collected decisions for next cycle
        self.current_cycle_decisions.clear()

    def _generate_cycle_summary_message(self, cycle_count: int) -> str:
        """
        Generate a consolidated summary message for all coins in the cycle.

        Args:
            cycle_count: Current cycle count

        Returns:
            Consolidated message string
        """
        if not self.current_cycle_decisions:
            return None

        try:
            # Get equity from first decision (should be same for all)
            first_symbol = next(iter(self.current_cycle_decisions.keys()))
            equity = self.current_cycle_decisions[first_symbol]['equity']

            coin_count = len(self.current_cycle_decisions)

            # Check if we need AI analysis or just a simple idle message
            needs_ai_analysis = self._check_if_needs_ai_analysis()

            if not needs_ai_analysis:
                # Simple friendly idle message (no AI call needed) - rotate through 3 different messages
                idle_messages = [
                    f"Hey there! All {coin_count} coins still holding position. Market's quiet right now, but I'm keeping an eye out for good opportunities!",
                    f"Status update: All {coin_count} coins remain in holding mode. Market conditions are stable - monitoring for the next move!",
                    f"Quick check-in: {coin_count} coins staying put for now. The market's taking a breather, but I'm ready when it picks up steam!"
                ]

                # Rotate through messages based on cycle count
                message_index = cycle_count % len(idle_messages)
                return idle_messages[message_index]

            # AI analysis needed - proceed with full analysis
            all_snapshots = self.current_cycle_decisions[first_symbol]['all_snapshots']

            # Build market overview for all coins
            coin_summaries = []
            for symbol, data in self.current_cycle_decisions.items():
                decision = data['decision']
                snapshot = data['snapshot']

                # Get price and indicators
                price = get_price_from_snapshot(snapshot)
                base_snap = get_base_snapshot(snapshot)
                ind = base_snap.indicators

                # Format price
                if price >= 1000:
                    price_str = f"${price:,.0f}"
                else:
                    price_str = f"${price:.3f}"

                # Get key indicators for summary
                trend_1d = ind.get('trend_1d', 'unknown')
                trend_4h = ind.get('trend_4h', 'unknown')
                rsi = ind.get('rsi_14', 50)

                coin_name = symbol.split('/')[0]
                coin_summaries.append(f"{coin_name}: {price_str} (1D: {trend_1d}, 4H: {trend_4h}, RSI: {rsi:.0f})")

            coins_text = "\n".join(coin_summaries)

            # Generate AI summary message
            prompt = f"""You are Aether, an autonomous trading assistant. This is a cycle summary message.

CURRENT STATUS:
- Account Equity: ${equity:,.2f}
- Cycle: {cycle_count}
- All coins currently: HOLD (waiting for entry signals)

CYCLE SUMMARY - ALL COINS:
{coins_text}

INSTRUCTIONS:
- Write a brief summary (2-3 sentences max)
- Focus on overall market sentiment (bullish/bearish/mixed)
- Mention if any coins show interesting setups
- Be conversational but professional
- Don't list every individual coin - give overall market vibe
- Keep it concise since this is a cycle update

Remember: This is a routine cycle summary. Keep it brief."""

            response = self.openai_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "You are Aether, giving a brief cycle summary."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                temperature=0.6
            )

            message = response.choices[0].message.content.strip()

            # Clean up message
            if message.startswith('"') and message.endswith('"'):
                message = message[1:-1]
            if message.startswith("'") and message.endswith("'"):
                message = message[1:-1]

            return message

        except Exception as e:
            logger.warning(f"Failed to generate cycle summary: {e}")
            # Fallback to varied simple summaries
            coin_count = len(self.current_cycle_decisions)
            fallback_messages = [
                f"Cycle {cycle_count}: All {coin_count} coins idle - monitoring for entry signals.",
                f"Update {cycle_count}: {coin_count} coins holding steady - waiting for market clarity.",
                f"Status {cycle_count}: {coin_count} positions unchanged - scanning for opportunities."
            ]

            message_index = cycle_count % len(fallback_messages)
            return fallback_messages[message_index]

    def _check_if_needs_ai_analysis(self) -> bool:
        """
        Check if we need AI analysis or just a simple idle message.

        Returns:
            True if AI analysis needed, False for simple idle message
        """
        # For now, always use simple idle message to save costs
        # Later we can add logic to check for:
        # - Interesting setups (RSI oversold, support levels, etc.)
        # - Market changes (trend changes, volatility spikes)
        # - Position changes (partial fills, etc.)

        return False  # Always use simple idle message for now
