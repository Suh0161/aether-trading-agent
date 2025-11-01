"""Loop controller for the Autonomous Trading Agent."""

import logging
import signal
import time
from datetime import datetime, timezone
from typing import Optional

from src.config import Config
from src.data_acquisition import DataAcquisition
from src.decision_provider import DecisionProvider, DeepSeekDecisionProvider
from src.decision_parser import DecisionParser
from src.risk_manager import RiskManager
from src.trade_executor import TradeExecutor
from src.logger import Logger
from src.models import CycleLog


logger = logging.getLogger(__name__)


class LoopController:
    """Orchestrates the agent cycle and handles errors gracefully."""
    
    def __init__(self, config: Config):
        """
        Initialize loop controller with all components.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.running = True
        
        # Initialize all components
        logger.info("Initializing loop controller components...")
        
        self.data_acquisition = DataAcquisition(config)
        self.decision_provider = self._init_decision_provider(config)
        self.decision_parser = DecisionParser()
        self.risk_manager = RiskManager(config)
        self.trade_executor = TradeExecutor(config)
        self.logger = Logger("logs/agent_log.jsonl")
        
        # Initialize API client for frontend updates
        try:
            from src.api_client import APIClient
            self.api_client = APIClient()
            logger.info("API client initialized for frontend updates")
        except Exception as e:
            logger.warning(f"Failed to initialize API client: {e}")
            self.api_client = None
        
        # Initialize OpenAI client for AI-generated messages
        try:
            from openai import OpenAI
            self.openai_client = OpenAI(api_key=config.deepseek_api_key, base_url="https://api.deepseek.com")
            logger.info("OpenAI client initialized for AI message generation")
        except Exception as e:
            logger.warning(f"Failed to initialize OpenAI client for messages: {e}")
            self.openai_client = None
        
        # Track entry prices and timestamps for P&L calculation and trade logging
        self.position_entry_prices = {}  # {symbol: entry_price}
        self.position_entry_timestamps = {}  # {symbol: entry_timestamp} - Unix timestamp in seconds
        # Track stop loss and take profit for automatic monitoring
        self.position_stop_losses = {}  # {symbol: stop_loss_price}
        self.position_take_profits = {}  # {symbol: take_profit_price}
        # Track position type (swing/scalp) for UI display
        self.position_types = {}  # {symbol: 'swing' or 'scalp'}
        # Track leverage and risk/reward for position monitoring
        self.position_leverages = {}  # {symbol: leverage_multiplier}
        self.position_risk_amounts = {}  # {symbol: risk_amount_usd}
        self.position_reward_amounts = {}  # {symbol: reward_amount_usd}
        
        # Track last agent message to avoid spam
        self.last_message_type = None  # Track last message type sent
        self.last_message_cycle = 0  # Track which cycle last message was sent
        
        # Track initial real equity for virtual equity calculation
        self.initial_real_equity: Optional[float] = None
        self.virtual_starting_equity = config.virtual_starting_equity
        
        # Store last snapshot for interactive chat
        self.last_snapshot = None
        
        # Track current position size for interactive chat
        self.current_position_size = 0.0
        
        logger.info("Loop controller initialized successfully")
    
    def _init_decision_provider(self, config: Config) -> DecisionProvider:
        """
        Initialize decision provider based on configuration.
        
        Args:
            config: Configuration object
            
        Returns:
            Configured decision provider instance
            
        Raises:
            ValueError: If decision provider type is not supported
        """
        strategy_mode = config.strategy_mode.lower()
        
        if strategy_mode == "hybrid_atr":
            logger.info("Initializing HYBRID mode: ATR Breakout Strategy + AI Filter")
            from src.hybrid_decision_provider import HybridDecisionProvider
            return HybridDecisionProvider(config.deepseek_api_key, strategy_type="atr")
        elif strategy_mode == "hybrid_ema":
            logger.info("Initializing HYBRID mode: Simple EMA Strategy + AI Filter")
            from src.hybrid_decision_provider import HybridDecisionProvider
            return HybridDecisionProvider(config.deepseek_api_key, strategy_type="ema")
        elif strategy_mode == "ai_only":
            logger.info("Initializing AI-ONLY mode: DeepSeek makes all decisions")
            return DeepSeekDecisionProvider(config.deepseek_api_key)
        else:
            raise ValueError(f"Unsupported strategy mode: {strategy_mode}. Use 'hybrid_atr', 'hybrid_ema', or 'ai_only'")

    def startup(self) -> bool:
        """
        Test exchange and LLM connectivity before starting main loop.
        
        Returns:
            bool: True if all connectivity tests pass, False otherwise
        """
        logger.info("=" * 60)
        logger.info("STARTING AUTONOMOUS TRADING AGENT")
        logger.info("=" * 60)
        logger.info(f"Mode: {self.config.run_mode.upper()}")
        logger.info(f"Symbol: {self.config.symbol}")
        logger.info(f"Exchange: {self.config.exchange_type}")
        logger.info(f"Decision Provider: {self.config.decision_provider}")
        logger.info(f"Loop Interval: {self.config.loop_interval_seconds}s")
        if self.config.virtual_starting_equity:
            logger.info(f"Virtual Equity Mode: ENABLED (Starting at ${self.config.virtual_starting_equity:,.2f})")
        logger.info("=" * 60)
        
        # Test 1: Exchange connectivity
        logger.info("Testing exchange connectivity...")
        try:
            balance = self.trade_executor.exchange.fetch_balance()
            logger.info(f"[OK] Exchange connection successful")
            
            # Log available balance (without exposing exact amounts in production)
            total_balance = balance.get('total', {})
            if total_balance:
                logger.info(f"  Available currencies: {list(total_balance.keys())[:5]}")
        except Exception as e:
            logger.error(f"[ERROR] Exchange connection failed: {e}")
            return False
        
        # Test 2: DeepSeek API connectivity
        logger.info("Testing DeepSeek API connectivity...")
        try:
            # Create a minimal test snapshot
            from src.models import MarketSnapshot
            test_snapshot = MarketSnapshot(
                timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
                symbol=self.config.symbol,
                price=50000.0,
                bid=49999.0,
                ask=50001.0,
                ohlcv=[],
                indicators={"ema_20": 50000.0, "ema_50": 49500.0, "rsi_14": 50.0}
            )
            
            # Make a test call (using $100 for test - actual equity comes from exchange)
            response = self.decision_provider.get_decision(test_snapshot, 0.0, 100.0)
            
            if "error" in response.lower() or "deepseek api error" in response.lower():
                logger.error(f"[ERROR] DeepSeek API test failed: {response}")
                return False
            
            logger.info(f"[OK] DeepSeek API connection successful")
            logger.debug(f"  Test response: {response[:100]}...")
            
        except Exception as e:
            logger.error(f"[ERROR] DeepSeek API connection failed: {e}")
            return False
        
        logger.info("=" * 60)
        logger.info("All connectivity tests passed. Starting main loop...")
        logger.info("=" * 60)
        
        return True

    def run(self) -> None:
        """
        Execute agent cycles in a continuous loop.
        
        Handles errors gracefully and continues operation.
        Logs all cycle data for analysis.
        """
        cycle_count = 0
        
        while self.running:
            cycle_count += 1
            cycle_start_time = time.time()
            
            logger.info(f"\n{'=' * 60}")
            logger.info(f"CYCLE {cycle_count} - {datetime.now(timezone.utc).isoformat()}")
            logger.info(f"{'=' * 60}")
            
            try:
                # Check if agent is paused
                import os
                pause_flag = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agent_paused.flag")
                if os.path.exists(pause_flag):
                    logger.info("Agent is PAUSED - skipping cycle")
                    self._sleep_until_next_cycle(cycle_start_time)
                    continue
                
                # Step 1: Fetch market snapshot
                logger.info("Step 1: Fetching market snapshot...")
                try:
                    snapshot = self.data_acquisition.fetch_market_snapshot(self.config.symbol)
                    self.last_snapshot = snapshot  # Store for interactive chat
                    logger.info(f"  Price: {snapshot.price}, Bid: {snapshot.bid}, Ask: {snapshot.ask}")
                except Exception as e:
                    logger.error(f"Failed to fetch market snapshot: {e}")
                    logger.info("Skipping this cycle due to data acquisition failure")
                    self._sleep_until_next_cycle(cycle_start_time)
                    continue
                
                # Step 2: Fetch current position and equity
                logger.info("Step 2: Fetching position and equity...")
                try:
                    balance = self.trade_executor.exchange.fetch_balance()
                    
                    # Get equity (total USDT or quote currency)
                    quote_currency = self.config.symbol.split('/')[1]
                    real_equity = balance['total'].get(quote_currency, 0.0)
                    
                    # Get position size (base currency) - needed for initial equity calculation
                    base_currency = self.config.symbol.split('/')[0]
                    position_size = balance['total'].get(base_currency, 0.0)
                    
                    # Track initial real equity on first fetch (for virtual equity calculation)
                    if self.initial_real_equity is None:
                        # If there's a pre-existing position, we need to wait until it's closed
                        # before we can accurately track virtual equity changes
                        if position_size != 0 and self.virtual_starting_equity:
                            position_value = abs(position_size) * snapshot.price
                            logger.warning(f"  Pre-existing position detected: {position_size} {base_currency} (${position_value:,.2f})")
                            logger.warning(f"  Virtual equity tracking will start AFTER this position is closed")
                            logger.warning(f"  Reason: We don't know the entry price of pre-existing positions")
                            # Don't set initial_real_equity yet - wait for position to close
                        else:
                            # No pre-existing position, safe to start tracking
                            self.initial_real_equity = real_equity
                            if self.virtual_starting_equity:
                                logger.info(f"  Initial real equity: ${real_equity:,.2f}")
                                logger.info(f"  Virtual starting equity: ${self.virtual_starting_equity:,.2f}")
                                logger.info(f"  Virtual equity mode ENABLED - agent will use virtual equity for calculations")
                    
                    # Calculate virtual equity if enabled
                    # Virtual equity starts at virtual_starting_equity and tracks P&L changes
                    if self.virtual_starting_equity is not None and self.initial_real_equity is not None:
                        equity_change = real_equity - self.initial_real_equity
                        equity = self.virtual_starting_equity + equity_change
                        logger.info(f"  Real equity: ${real_equity:,.2f} | Virtual equity: ${equity:,.2f} (change: ${equity_change:+,.2f})")
                    else:
                        equity = real_equity
                    
                    logger.info(f"  Equity (used for calculations): {equity} {quote_currency}")
                    logger.info(f"  Position: {position_size} {base_currency}")
                    
                    # Store for interactive chat
                    self.current_position_size = position_size
                    
                except Exception as e:
                    logger.error(f"Failed to fetch position/equity: {e}")
                    logger.info("Skipping this cycle due to balance fetch failure")
                    self._sleep_until_next_cycle(cycle_start_time)
                    continue
                
                # Check for stop loss / take profit BEFORE decision provider
                if position_size > 0:
                    stored_stop_loss = self.position_stop_losses.get(self.config.symbol)
                    stored_take_profit = self.position_take_profits.get(self.config.symbol)
                    current_price = snapshot.price
                    
                    if stored_stop_loss and current_price <= stored_stop_loss:
                        logger.warning(f"[WARNING] STOP LOSS HIT! Price ${current_price:.2f} <= Stop Loss ${stored_stop_loss:.2f}")
                        raw_llm_output = f'{{"action": "close", "size_pct": 1.0, "reason": "Stop loss triggered: price ${current_price:.2f} <= ${stored_stop_loss:.2f}"}}'
                        # Clear stored stop loss/take profit
                        if self.config.symbol in self.position_stop_losses:
                            del self.position_stop_losses[self.config.symbol]
                        if self.config.symbol in self.position_take_profits:
                            del self.position_take_profits[self.config.symbol]
                    elif stored_take_profit and current_price >= stored_take_profit:
                        logger.info(f"✅ TAKE PROFIT HIT! Price ${current_price:.2f} >= Take Profit ${stored_take_profit:.2f}")
                        raw_llm_output = f'{{"action": "close", "size_pct": 1.0, "reason": "Take profit triggered: price ${current_price:.2f} >= ${stored_take_profit:.2f}"}}'
                        # Clear stored stop loss/take profit
                        if self.config.symbol in self.position_stop_losses:
                            del self.position_stop_losses[self.config.symbol]
                        if self.config.symbol in self.position_take_profits:
                            del self.position_take_profits[self.config.symbol]
                    else:
                        # No stop/tp hit, proceed with normal decision flow
                        raw_llm_output = None
                else:
                    # No position, proceed with normal decision flow
                    raw_llm_output = None
                
                # Check for emergency close flag (only if stop loss/take profit didn't trigger)
                if raw_llm_output is None:
                    emergency_flag = os.path.join(os.path.dirname(os.path.dirname(__file__)), "emergency_close.flag")
                    if os.path.exists(emergency_flag):
                        logger.warning("[WARNING] EMERGENCY CLOSE TRIGGERED!")
                        os.remove(emergency_flag)
                        if position_size != 0:
                            logger.info("Forcing immediate position close...")
                            raw_llm_output = '{"action": "close", "size_pct": 1.0, "reason": "Emergency close triggered by user"}'
                        else:
                            logger.info("No position to close")
                            raw_llm_output = '{"action": "hold", "size_pct": 0.0, "reason": "Emergency close triggered but no position"}'
                
                # Step 3: Call decision provider (only if no stop loss/take profit/emergency close)
                if raw_llm_output is None:
                    # Step 3: Call decision provider
                    logger.info("Step 3: Getting decision from LLM...")
                    try:
                        raw_llm_output = self.decision_provider.get_decision(
                            snapshot, position_size, equity
                        )
                        logger.info(f"  Raw LLM output: {raw_llm_output[:200]}...")
                    except Exception as e:
                        logger.error(f"Decision provider failed: {e}")
                        raw_llm_output = f"Error: {str(e)}"
                        logger.info("Forcing action to 'hold' due to LLM failure")
                
                # Step 4: Parse decision
                logger.info("Step 4: Parsing decision...")
                decision = self.decision_parser.parse(raw_llm_output)
                logger.info(f"  Action: {decision.action}, Size: {decision.size_pct*100}%, Reason: {decision.reason}")
                
                # Step 5: Validate with risk manager
                logger.info("Step 5: Validating with risk manager...")
                risk_result = self.risk_manager.validate(
                    decision, snapshot, position_size, equity
                )
                logger.info(f"  Approved: {risk_result.approved}")
                if not risk_result.approved:
                    logger.info(f"  Denial reason: {risk_result.reason}")
                
                # Step 6: Execute trade if approved
                execution_result = None
                if risk_result.approved:
                    logger.info("Step 6: Executing trade...")
                    execution_result = self.trade_executor.execute(
                        decision, snapshot, position_size, equity
                    )
                    logger.info(f"  Executed: {execution_result.executed}")
                    if execution_result.executed:
                        logger.info(f"  Order ID: {execution_result.order_id}")
                        logger.info(f"  Filled: {execution_result.filled_size} @ {execution_result.fill_price}")
                    elif execution_result.error:
                        logger.warning(f"  Execution error: {execution_result.error}")
                else:
                    logger.info("Step 6: Trade not executed (risk denial)")
                    # Create a dummy execution result for logging
                    from src.models import ExecutionResult
                    execution_result = ExecutionResult(
                        executed=False,
                        order_id=None,
                        filled_size=None,
                        fill_price=None,
                        error=None
                    )
                
                # Step 7: Log full cycle data
                logger.info("Step 7: Logging cycle data...")
                cycle_log = CycleLog(
                    timestamp=snapshot.timestamp,
                    symbol=snapshot.symbol,
                    market_price=snapshot.price,
                    position_before=position_size,
                    llm_raw_output=raw_llm_output,
                    parsed_action=decision.action,
                    parsed_size_pct=decision.size_pct,
                    parsed_reason=decision.reason,
                    risk_approved=risk_result.approved,
                    risk_reason=risk_result.reason,
                    executed=execution_result.executed,
                    order_id=execution_result.order_id,
                    filled_size=execution_result.filled_size,
                    fill_price=execution_result.fill_price,
                    mode=self.config.run_mode
                )
                
                self.logger.log_cycle(cycle_log)
                logger.info("  Cycle logged successfully")
                
                # Update frontend via API
                if self.api_client:
                    try:
                        # Save original position_size BEFORE closing (needed to determine LONG vs SHORT for trade logging)
                        original_position_size = position_size
                        
                        # Capture entry price BEFORE closing positions (needed for trade logging)
                        entry_price_for_closed_trade = None
                        if execution_result.executed and execution_result.filled_size:
                            if decision.action in ['sell', 'close']:
                                # Save entry price before deletion for trade logging
                                entry_price_for_closed_trade = self.position_entry_prices.get(self.config.symbol)
                        
                        # Track entry price, timestamp, stop loss, take profit, and position type when position is opened
                        if execution_result.executed and execution_result.filled_size:
                            if decision.action in ['long', 'short'] and execution_result.fill_price:
                                self.position_entry_prices[self.config.symbol] = execution_result.fill_price
                                self.position_entry_timestamps[self.config.symbol] = int(time.time())
                                logger.info(f"  Recorded entry price: ${execution_result.fill_price:.2f}")
                                
                                # Store position type (swing or scalp)
                                position_type = getattr(decision, 'position_type', 'swing')
                                self.position_types[self.config.symbol] = position_type
                                logger.info(f"  Position type: {position_type.upper()}")
                                
                                # Store stop loss and take profit if provided
                                if decision.stop_loss is not None:
                                    self.position_stop_losses[self.config.symbol] = decision.stop_loss
                                    logger.info(f"  Set stop loss: ${decision.stop_loss:.2f}")
                                if decision.take_profit is not None:
                                    self.position_take_profits[self.config.symbol] = decision.take_profit
                                    logger.info(f"  Set take profit: ${decision.take_profit:.2f}")
                                
                                # Store leverage, risk amount, and reward amount if provided
                                leverage = getattr(decision, 'leverage', 1.0)
                                risk_amount = getattr(decision, 'risk_amount', None)
                                reward_amount = getattr(decision, 'reward_amount', None)
                                
                                self.position_leverages[self.config.symbol] = leverage
                                logger.info(f"  Leverage: {leverage:.1f}x")
                                
                                if risk_amount is not None:
                                    self.position_risk_amounts[self.config.symbol] = risk_amount
                                    logger.info(f"  Risk amount (if SL hits): ${risk_amount:.2f}")
                                
                                if reward_amount is not None:
                                    self.position_reward_amounts[self.config.symbol] = reward_amount
                                    logger.info(f"  Reward amount (if TP hits): ${reward_amount:.2f}")
                            elif decision.action in ['sell', 'close']:
                                # Clear entry price, timestamp, stop loss, take profit, position type, leverage, and risk/reward when position is closed
                                if self.config.symbol in self.position_entry_prices:
                                    del self.position_entry_prices[self.config.symbol]
                                if self.config.symbol in self.position_entry_timestamps:
                                    del self.position_entry_timestamps[self.config.symbol]
                                if self.config.symbol in self.position_stop_losses:
                                    del self.position_stop_losses[self.config.symbol]
                                if self.config.symbol in self.position_take_profits:
                                    del self.position_take_profits[self.config.symbol]
                                if self.config.symbol in self.position_types:
                                    del self.position_types[self.config.symbol]
                                if self.config.symbol in self.position_leverages:
                                    del self.position_leverages[self.config.symbol]
                                if self.config.symbol in self.position_risk_amounts:
                                    del self.position_risk_amounts[self.config.symbol]
                                if self.config.symbol in self.position_reward_amounts:
                                    del self.position_reward_amounts[self.config.symbol]
                        
                        # Adjust position_size if we just closed the position
                        # This ensures accurate position tracking in the same cycle
                        if execution_result.executed and decision.action in ['sell', 'close']:
                            # Position was closed, so set to 0 for current calculations
                            position_size = 0.0
                            logger.info("  Position closed - adjusted position_size to 0 for current cycle")
                        
                        # Calculate P&L and available cash
                        total_unrealized_pnl = 0.0
                        position_value = 0.0
                        positions_list = []
                        
                        # Build position data if exists (both LONG and SHORT)
                        if position_size != 0:
                            base_currency = self.config.symbol.split('/')[0]
                            notional = abs(position_size) * snapshot.price
                            position_value = notional
                            
                            # Calculate unrealized P&L
                            entry_price = self.position_entry_prices.get(self.config.symbol)
                            if not entry_price:
                                # For pre-existing positions, use current price as entry
                                # This starts P&L tracking from $0 at the moment agent starts
                                self.position_entry_prices[self.config.symbol] = snapshot.price
                                entry_price = snapshot.price
                                logger.warning(f"  Pre-existing position detected. Using current price ${entry_price:.2f} as entry (P&L will track from now)")
                            
                            # Calculate P&L based on position direction
                            if position_size > 0:  # LONG position
                                unreal_pnl = (snapshot.price - entry_price) * position_size
                            else:  # SHORT position (position_size < 0)
                                unreal_pnl = (entry_price - snapshot.price) * abs(position_size)
                            
                            total_unrealized_pnl += unreal_pnl
                            logger.info(f"  P&L calculation: Entry=${entry_price:.2f}, Current=${snapshot.price:.2f}, Size={position_size:.6f}, P&L=${unreal_pnl:.2f}")
                            
                            # Calculate P&L percentage
                            if position_size > 0:  # LONG
                                pnl_percentage = ((snapshot.price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
                            else:  # SHORT
                                pnl_percentage = ((entry_price - snapshot.price) / entry_price) * 100 if entry_price > 0 else 0
                            
                            # Get stop loss and take profit for this position
                            stop_loss = self.position_stop_losses.get(self.config.symbol)
                            take_profit = self.position_take_profits.get(self.config.symbol)
                            
                            # Calculate actual leverage used (position value / equity)
                            actual_leverage = (position_value / equity) if equity > 0 else 0.0
                            leverage_str = f"{actual_leverage:.2f}X" if actual_leverage > 0 else "0X"
                            
                            # Determine position direction (LONG or SHORT)
                            side_label = 'LONG' if position_size > 0 else 'SHORT'
                            
                            positions_list.append({
                                'side': side_label,
                                'coin': base_currency,
                                'leverage': leverage_str,
                                'notional': notional,
                                'unrealPnL': unreal_pnl,
                                'entryPrice': entry_price,
                                'currentPrice': snapshot.price,
                                'pnlPercentage': pnl_percentage,
                                'quantity': position_size,
                                'stopLoss': stop_loss,
                                'takeProfit': take_profit,
                                'invalidCondition': None  # Can be set by strategy in the future
                            })
                        
                        # Sync all positions at once (replaces old data)
                        self.api_client.sync_positions(positions_list)
                        
                        # Available cash is the equity (which already accounts for open positions)
                        # In virtual equity mode, equity = starting_equity + realized_pnl
                        # Position value is shown separately in the positions tab
                        available_cash = equity
                        
                        # Update balance with correct cash and P&L
                        self.api_client.update_balance(available_cash, total_unrealized_pnl)
                        
                        # Send smart agent messages (only useful info, no spam)
                        self._send_smart_agent_message(
                            decision, snapshot, position_size, equity, 
                            available_cash, total_unrealized_pnl, cycle_count
                        )
                        
                        # If trade was executed AND it's a CLOSE/SELL action, log the completed trade
                        if execution_result.executed and execution_result.filled_size and decision.action in ['close', 'sell']:
                            # Determine trade direction (LONG/SHORT) based on original position size
                            # original_position_size > 0 means LONG position, < 0 means SHORT position
                            trade_side = 'LONG' if original_position_size > 0 else 'SHORT'
                            
                            # Calculate P&L for completed trades
                            trade_pnl = 0.0
                            # Use the captured entry price (saved before deletion) for both sell and close actions
                            entry_price_for_trade = entry_price_for_closed_trade
                            
                            # Calculate P&L if we have entry and exit prices
                            if entry_price_for_trade and execution_result.fill_price:
                                if original_position_size > 0:  # Closing a LONG position
                                    trade_pnl = (execution_result.fill_price - entry_price_for_trade) * execution_result.filled_size
                                elif original_position_size < 0:  # Closing a SHORT position
                                    trade_pnl = (entry_price_for_trade - execution_result.fill_price) * abs(execution_result.filled_size)
                            
                            # Use entry_price_for_trade or fallback to exit_price if not available
                            final_entry_price = entry_price_for_trade if entry_price_for_trade else execution_result.fill_price
                            
                            # Get entry and exit timestamps
                            entry_timestamp = None
                            if decision.action in ['sell', 'close']:
                                entry_timestamp = self.position_entry_timestamps.get(self.config.symbol)
                            exit_timestamp = int(time.time())
                            
                            # If we don't have entry timestamp, use current time as fallback
                            if entry_timestamp is None:
                                entry_timestamp = exit_timestamp
                            
                            # Calculate holding time from timestamps (format: "19H 7M" or "4H 53M")
                            holding_time = self._calculate_holding_time(entry_timestamp, exit_timestamp)
                            
                            # Quantity: use actual filled size (keep precision for small amounts)
                            quantity_value = abs(execution_result.filled_size)
                            
                            self.api_client.add_trade(
                                coin=self.config.symbol.split('/')[0],
                                side=trade_side,  # Use determined side (LONG/SHORT, not CLOSE)
                                entry_price=final_entry_price,
                                exit_price=execution_result.fill_price,
                                quantity=quantity_value,  # Negative for SHORT, positive for LONG
                                entry_notional=abs(execution_result.filled_size) * final_entry_price,
                                exit_notional=abs(execution_result.filled_size) * execution_result.fill_price,
                                holding_time=holding_time,
                                pnl=trade_pnl,
                                entry_timestamp=entry_timestamp,
                                exit_timestamp=exit_timestamp
                            )
                            
                            # Send execution confirmation using AI's reasoning
                            trade_msg = f"EXECUTED {decision.action.upper()}: {execution_result.filled_size:.6f} BTC @ ${execution_result.fill_price:,.2f}"
                            if trade_pnl != 0:
                                trade_msg += f" | P&L: ${trade_pnl:,.2f}"
                            if decision.reason:
                                trade_msg += f" | {decision.reason}"
                            self.api_client.add_agent_message(trade_msg)
                        
                        logger.info(f"  Frontend updated: Cash=${available_cash:.2f}, P&L=${total_unrealized_pnl:.2f}")
                    except Exception as e:
                        logger.warning(f"Failed to update frontend: {e}")
                
                logger.info(f"{'=' * 60}")
                logger.info(f"CYCLE {cycle_count} COMPLETE")
                logger.info(f"{'=' * 60}\n")
                
            except Exception as e:
                logger.error(f"Unexpected error in cycle {cycle_count}: {e}", exc_info=True)
                logger.info("Continuing to next cycle...")
            
            # Step 8: Sleep for configured interval
            self._sleep_until_next_cycle(cycle_start_time)
        
        logger.info("Loop controller stopped")
    
    def _sleep_until_next_cycle(self, cycle_start_time: float) -> None:
        """
        Sleep until the next cycle should start.
        
        Args:
            cycle_start_time: Time when the current cycle started (from time.time())
        """
        elapsed = time.time() - cycle_start_time
        sleep_time = max(0, self.config.loop_interval_seconds - elapsed)
        
        if sleep_time > 0:
            logger.info(f"Sleeping for {sleep_time:.1f} seconds until next cycle...")
            time.sleep(sleep_time)
        else:
            logger.warning(f"Cycle took {elapsed:.1f}s, longer than interval {self.config.loop_interval_seconds}s")
    
    def _generate_ai_message(
        self, decision, snapshot, position_size: float, equity: float,
        available_cash: float, unrealized_pnl: float
    ) -> str:
        """
        Use AI to generate natural, conversational trading messages.
        
        Args:
            decision: Trading decision
            snapshot: Market snapshot
            position_size: Current position size
            equity: Account equity
            available_cash: Available cash
            unrealized_pnl: Unrealized P&L
            
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
            indicators = snapshot.indicators
            price = snapshot.price
            
            # Build prompt for AI message generation
            prompt = f"""You are a professional crypto trader explaining your decision to your client in a casual, conversational way.

CURRENT SITUATION:
- Action: {decision.action.upper()}
- Position Type: {position_type} (swing = multi-day hold, scalp = quick in/out)
- BTC Price: ${price:,.2f}
- Your Equity: ${equity:,.2f}
- Available Cash: ${available_cash:,.2f}
- Current Position Size: {position_size:.6f} BTC
- Unrealized P&L: ${unrealized_pnl:,.2f}

DECISION DETAILS:
- Reason: {decision.reason}
- Position Size: {decision.size_pct*100:.1f}% of equity
{f"- Stop Loss: ${decision.stop_loss:,.2f}" if decision.stop_loss else ""}
{f"- Take Profit: ${decision.take_profit:,.2f}" if decision.take_profit else ""}

MARKET CONTEXT:
- Daily Trend: {indicators.get('trend_1d', 'unknown')}
- 4H Trend: {indicators.get('trend_4h', 'unknown')}
- 1H RSI: {indicators.get('rsi_14', 50):.1f}
- Support/Resistance: S1=${indicators.get('support_1', 0)/1000:.1f}k, R1=${indicators.get('resistance_1', 0)/1000:.1f}k, Pivot=${indicators.get('pivot', 0)/1000:.1f}k
- VWAP 5m: ${indicators.get('vwap_5m', 0)/1000:.1f}k (price is {'above' if price > indicators.get('vwap_5m', price) else 'below'})
- Swing High: ${indicators.get('swing_high', 0)/1000:.1f}k, Swing Low: ${indicators.get('swing_low', 0)/1000:.1f}k
- Volume (1h): {indicators.get('volume_ratio_1h', 1.0):.2f}x average ({'STRONG' if indicators.get('volume_ratio_1h', 1.0) >= 1.5 else 'MODERATE' if indicators.get('volume_ratio_1h', 1.0) >= 1.2 else 'WEAK'})
- Volume Trend: {indicators.get('volume_trend_1h', 'stable')} | OBV: {indicators.get('obv_trend_1h', 'neutral')}

YOUR TASK:
Write a brief, natural message (1-3 sentences) explaining what you're doing and why, like you're updating a friend. Be conversational, confident, and VARY your phrasing. Use first person ("I'm buying", "I'll wait", "watching for").

IMPORTANT - Include market context in your reasoning:
- Mention S/R levels (e.g., "bounced from support at $109.7k", "testing R1 resistance")
- Mention VWAP position (e.g., "price above VWAP", "below VWAP so bearish bias")
- Mention multi-timeframe alignment (e.g., "1d/4h bullish", "5m bearish")
- Mention key price action (e.g., "rejected at swing high", "broke above pivot")
- Mention VOLUME when relevant (e.g., "strong volume confirms breakout", "weak volume, waiting for confirmation", "volume spike at support")

VARY YOUR PHRASING - Don't repeat the same words. Use different expressions:

BUYING/ENTERING (vary these):
- "Going long at $67.2k - bounced perfectly from S1 support with strong volume. Price above VWAP, target R1 at $68.5k."
- "Taking a scalp here at $67.1k. 5m momentum strong, volume spiking, price above VWAP, aiming for quick $200."
- "Entering swing position at $67.4k. 1d/4h trends aligned bullish, broke above pivot with conviction (1.6x volume)."
- "Buying the dip at $66.8k - swing low support held with volume spike, good risk/reward to R2."

HOLDING (vary these):
- "Holding my long from $67.2k, now at $67.8k (+$600 unrealized). Still below R1 resistance so room to run."
- "Staying in this swing trade. Price testing R1 but 4h trend still bullish, I'll hold for R2."
- "Position down $150 but support at S1 is holding. Giving it room to work."
- "Up $340 on this trade. Price between pivot and R1, trend intact, holding."

SELLING/CLOSING (vary these):
- "Closing at $68.5k for +$1,265 profit. Hit R1 resistance perfectly, taking the win."
- "Out at $67.9k with +$665. Price rejected at swing high, smart to exit here."
- "Stop hit at $66.5k, -$734 loss. Broke below S1 support, capital preservation mode."
- "Exiting at $67.1k for small +$85 gain. Trend reversed below VWAP, not worth the risk."

WAITING/NO POSITION (vary these - BE CREATIVE):
- "Watching from sidelines. Price at R1 resistance $110.5k - need to see breakout or rejection before entering."
- "No position. Price below VWAP and 5m bearish, but at S1 support - waiting to see if it bounces or breaks."
- "Staying patient. Price between pivot and R1, no clear setup yet. Want to see which way it breaks."
- "Holding cash. 1d/4h trends mixed, price chopping between S1 and R1. Need cleaner structure."
- "Waiting for better entry. Price testing swing high resistance - if it breaks I'll go long, if rejects I'll short."
- "No trade yet. Below VWAP but near swing low support - watching for bounce or breakdown."

BE CREATIVE - Don't copy these examples exactly. Mix and match concepts. Explain your actual market analysis.

Write ONLY the message, nothing else:"""
            
            # Call AI
            response = self.openai_client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.7,
                timeout=5.0
            )
            
            message = response.choices[0].message.content.strip()
            
            # Remove quotes if AI added them
            if message.startswith('"') and message.endswith('"'):
                message = message[1:-1]
            if message.startswith("'") and message.endswith("'"):
                message = message[1:-1]
            
            return message
            
        except Exception as e:
            logger.warning(f"Failed to generate AI message: {e}")
            # Fallback to simple message
            return f"{decision.action.upper()}: {decision.reason}"
    
    def _send_smart_agent_message(
        self, decision, snapshot, position_size: float, equity: float,
        available_cash: float, unrealized_pnl: float, cycle_count: int
    ) -> None:
        """
        Send AI-generated natural messages to users.
        
        Rules:
        - Always send: BUY, SELL, CLOSE actions
        - Send hold messages every 10 cycles to avoid spam
        """
        if not self.api_client:
            return
        
        # === ALWAYS SEND: Important actions ===
        if decision.action in ["long", "sell", "close"]:
            message = self._generate_ai_message(
                decision, snapshot, position_size, equity, 
                available_cash, unrealized_pnl
            )
            self.api_client.add_agent_message(message)
            self.last_message_type = decision.action
            self.last_message_cycle = cycle_count
            return
        
        # === HOLD MESSAGES: Send periodically to avoid spam ===
        elif decision.action == "hold":
            if cycle_count == 1 or (cycle_count - self.last_message_cycle) >= 10:
                message = self._generate_ai_message(
                    decision, snapshot, position_size, equity,
                    available_cash, unrealized_pnl
                )
                self.api_client.add_agent_message(message)
                self.last_message_type = "hold"
                self.last_message_cycle = cycle_count
    
    def _calculate_holding_time(self, entry_timestamp: int, exit_timestamp: int) -> str:
        """
        Calculate holding time from timestamps and format as "19H 7M" or "4H 53M".
        
        Args:
            entry_timestamp: Unix timestamp when position was opened (seconds)
            exit_timestamp: Unix timestamp when position was closed (seconds)
            
        Returns:
            Formatted holding time string (e.g., "19H 7M", "4H 53M", "2D 5H")
        """
        if entry_timestamp is None or exit_timestamp is None:
            return "N/A"
        
        duration_seconds = exit_timestamp - entry_timestamp
        
        if duration_seconds < 0:
            return "N/A"
        
        # Calculate days, hours, and minutes
        days = duration_seconds // 86400
        hours = (duration_seconds % 86400) // 3600
        minutes = (duration_seconds % 3600) // 60
        
        # Format based on duration
        if days > 0:
            return f"{days}D {hours}H {minutes}M" if minutes > 0 else f"{days}D {hours}H"
        elif hours > 0:
            return f"{hours}H {minutes}M" if minutes > 0 else f"{hours}H"
        elif minutes > 0:
            return f"{minutes}M"
        else:
            return "<1M"

    def shutdown(self) -> None:
        """
        Gracefully shutdown the agent.
        
        Sets running flag to false, allowing current iteration to complete.
        """
        logger.info("\n" + "=" * 60)
        logger.info("SHUTDOWN SIGNAL RECEIVED")
        logger.info("=" * 60)
        logger.info("Completing current iteration before shutdown...")
        self.running = False
    
    def register_signal_handlers(self) -> None:
        """
        Register signal handlers for graceful shutdown.
        
        Handles SIGINT (Ctrl+C) and SIGTERM (kill command).
        """
        def signal_handler(signum, frame):
            signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
            logger.info(f"\nReceived {signal_name}")
            self.shutdown()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        logger.info("Signal handlers registered (SIGINT, SIGTERM)")
