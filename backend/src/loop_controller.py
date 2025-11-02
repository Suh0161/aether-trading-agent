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
        
        # Track decisions per symbol for status messages
        self.current_cycle_decisions = {}  # {symbol: decision} for current cycle
        
        # Track initial real equity for virtual equity calculation
        self.initial_real_equity: Optional[float] = None
        self.virtual_starting_equity = config.virtual_starting_equity
        
        # Store snapshots for interactive chat (multi-coin support)
        self.all_snapshots = {}  # {symbol: snapshot} - all 6 coins
        self.last_snapshot = None  # Backward compatibility (first symbol)
        
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
        logger.info(f"Symbols: {', '.join(self.config.symbols)}")
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
            # Create a minimal test snapshot (use first symbol for test)
            from src.models import MarketSnapshot
            test_snapshot = MarketSnapshot(
                timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
                symbol=self.config.symbols[0],
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
                
                # Step 1: Fetch market snapshots for all symbols
                logger.info("Step 1: Fetching market snapshots for all symbols...")
                try:
                    snapshots = self.data_acquisition.fetch_multi_symbol_snapshots(self.config.symbols)
                    # Store all snapshots for interactive chat (multi-coin support)
                    self.all_snapshots = snapshots
                    # Store first snapshot for interactive chat (backward compatibility)
                    self.last_snapshot = list(snapshots.values())[0] if snapshots else None
                    logger.info(f"  Fetched {len(snapshots)} symbols:")
                    for sym, snap in snapshots.items():
                        logger.info(f"    {sym}: ${snap.price:,.2f}")
                except Exception as e:
                    logger.error(f"Failed to fetch market snapshots: {e}")
                    logger.info("Skipping this cycle due to data acquisition failure")
                    self._sleep_until_next_cycle(cycle_start_time)
                    continue
                
                # Step 2: Fetch current positions and equity for all symbols
                logger.info("Step 2: Fetching positions and equity...")
                try:
                    balance = self.trade_executor.exchange.fetch_balance()
                    
                    # Get equity (total USDT or quote currency) - assume all pairs use USDT
                    quote_currency = 'USDT'
                    real_equity = balance['total'].get(quote_currency, 0.0)
                    
                    # Get position sizes for all symbols
                    positions = {}  # {symbol: position_size}
                    total_position_value = 0.0
                    for symbol in self.config.symbols:
                        base_currency = symbol.split('/')[0]
                        pos_size = balance['total'].get(base_currency, 0.0)
                        positions[symbol] = pos_size
                        if pos_size != 0 and symbol in snapshots:
                            total_position_value += abs(pos_size) * snapshots[symbol].price
                    
                    # For backward compatibility, use first symbol's position as "position_size"
                    position_size = positions.get(self.config.symbols[0], 0.0)
                    
                    # Track initial real equity on first fetch (for virtual equity calculation)
                    if self.initial_real_equity is None:
                        # If there are pre-existing positions, wait until they're all closed
                        has_preexisting = any(pos != 0 for pos in positions.values())
                        if has_preexisting and self.virtual_starting_equity:
                            logger.warning(f"  Pre-existing positions detected (total value: ${total_position_value:,.2f})")
                            logger.warning(f"  Virtual equity tracking will start AFTER all positions are closed")
                            logger.warning(f"  Reason: We don't know the entry prices of pre-existing positions")
                        else:
                            # No pre-existing positions, safe to start tracking
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
                    # Log all positions
                    position_strs = [f"{s.split('/')[0]}={positions[s]:.8f}" for s in positions if positions[s] != 0]
                    logger.info(f"  Positions: {', '.join(position_strs) if position_strs else 'None'}")
                    
                    # Store total position size for interactive chat (backward compatibility)
                    self.current_position_size = sum(abs(p) for p in positions.values())
                    
                except Exception as e:
                    logger.error(f"Failed to fetch position/equity: {e}")
                    logger.info("Skipping this cycle due to balance fetch failure")
                    self._sleep_until_next_cycle(cycle_start_time)
                    continue
                
                # Multi-coin strategy: Process ALL symbols independently each cycle
                # Each symbol: 1) Manage existing positions, 2) Evaluate new opportunities
                
                logger.info("  Processing all symbols for multi-coin trading...")
                
                # Reset decisions tracking for this cycle
                self.current_cycle_decisions = {}
                
                # Process each symbol independently
                for symbol in self.config.symbols:
                    try:
                        self._process_symbol(
                            symbol=symbol,
                            snapshots=snapshots,
                            positions=positions,
                            equity=equity,
                            cycle_count=cycle_count
                        )
                    except Exception as e:
                        logger.error(f"  {symbol}: Error processing symbol - {e}")
                        continue
                        
                # After processing all symbols, refresh positions and update frontend
                try:
                    # Refresh positions after all processing
                    balance = self.trade_executor.exchange.fetch_balance()
                    quote_currency = 'USDT'
                    for symbol in self.config.symbols:
                        base_currency = symbol.split('/')[0]
                        positions[symbol] = balance['total'].get(base_currency, 0.0)
                    
                    # Update frontend with all positions
                    self._update_frontend_all_positions(
                        snapshots=snapshots,
                        positions=positions,
                        equity=equity,
                        cycle_count=cycle_count
                    )
                except Exception as e:
                    logger.warning(f"Failed to refresh positions/update frontend: {e}")
                
                logger.info(f"{'=' * 60}")
                logger.info(f"CYCLE {cycle_count} COMPLETE")
                logger.info(f"{'=' * 60}\n")
                
            except Exception as e:
                logger.error(f"Unexpected error in cycle {cycle_count}: {e}", exc_info=True)
                logger.info("Continuing to next cycle...")
            
            # Step 8: Sleep for configured interval
            self._sleep_until_next_cycle(cycle_start_time)
        
        logger.info("Loop controller stopped")
    
    def _process_symbol(
        self,
        symbol: str,
        snapshots: dict,
        positions: dict,
        equity: float,
        cycle_count: int
    ) -> None:
        """
        Process a single symbol: check stop loss/take profit, get decision, execute trade.
        
        Args:
            symbol: Trading symbol to process
            snapshots: Dict of {symbol: snapshot}
            positions: Dict of {symbol: position_size}
            equity: Current account equity
            cycle_count: Current cycle number
        """
        snapshot = snapshots.get(symbol)
        if not snapshot:
            logger.warning(f"  {symbol}: No snapshot available, skipping")
            return
        
        position_size = positions.get(symbol, 0.0)
        
        # ====================================================================
        # STEP 1: Check stop loss / take profit for existing positions
        # ====================================================================
        raw_llm_output = None
        import os
        
        if position_size != 0:
            stored_stop_loss = self.position_stop_losses.get(symbol)
            stored_take_profit = self.position_take_profits.get(symbol)
            current_price = snapshot.price
            
            # LONG position: SL below entry, TP above entry
            if position_size > 0:
                if stored_stop_loss and current_price <= stored_stop_loss:
                    logger.warning(f"[WARNING] {symbol} LONG STOP LOSS HIT! Price ${current_price:.2f} <= Stop Loss ${stored_stop_loss:.2f}")
                    raw_llm_output = f'{{"action": "close", "size_pct": 1.0, "reason": "Long stop loss triggered: price ${current_price:.2f} <= ${stored_stop_loss:.2f}"}}'
                    # Clear stored stop loss/take profit
                    if symbol in self.position_stop_losses:
                        del self.position_stop_losses[symbol]
                    if symbol in self.position_take_profits:
                        del self.position_take_profits[symbol]
                elif stored_take_profit and current_price >= stored_take_profit:
                    logger.info(f"[OK] {symbol} LONG TAKE PROFIT HIT! Price ${current_price:.2f} >= Take Profit ${stored_take_profit:.2f}")
                    raw_llm_output = f'{{"action": "close", "size_pct": 1.0, "reason": "Long take profit triggered: price ${current_price:.2f} >= ${stored_take_profit:.2f}"}}'
                    # Clear stored stop loss/take profit
                    if symbol in self.position_stop_losses:
                        del self.position_stop_losses[symbol]
                    if symbol in self.position_take_profits:
                        del self.position_take_profits[symbol]
            
            # SHORT position: SL above entry, TP below entry
            else:  # position_size < 0
                if stored_stop_loss and current_price >= stored_stop_loss:
                    logger.warning(f"[WARNING] {symbol} SHORT STOP LOSS HIT! Price ${current_price:.2f} >= Stop Loss ${stored_stop_loss:.2f}")
                    raw_llm_output = f'{{"action": "close", "size_pct": 1.0, "reason": "Short stop loss triggered: price ${current_price:.2f} >= ${stored_stop_loss:.2f}"}}'
                    # Clear stored stop loss/take profit
                    if symbol in self.position_stop_losses:
                        del self.position_stop_losses[symbol]
                    if symbol in self.position_take_profits:
                        del self.position_take_profits[symbol]
                elif stored_take_profit and current_price <= stored_take_profit:
                    logger.info(f"[OK] {symbol} SHORT TAKE PROFIT HIT! Price ${current_price:.2f} <= Take Profit ${stored_take_profit:.2f}")
                    raw_llm_output = f'{{"action": "close", "size_pct": 1.0, "reason": "Short take profit triggered: price ${current_price:.2f} <= ${stored_take_profit:.2f}"}}'
                    # Clear stored stop loss/take profit
                    if symbol in self.position_stop_losses:
                        del self.position_stop_losses[symbol]
                    if symbol in self.position_take_profits:
                        del self.position_take_profits[symbol]
        
        # ====================================================================
        # STEP 2: Check for emergency close flag
        # ====================================================================
        if raw_llm_output is None:
            emergency_flag = os.path.join(os.path.dirname(os.path.dirname(__file__)), "emergency_close.flag")
            if os.path.exists(emergency_flag):
                logger.warning(f"[WARNING] {symbol}: EMERGENCY CLOSE TRIGGERED!")
                if position_size != 0:
                    logger.info(f"  {symbol}: Forcing immediate position close...")
                    raw_llm_output = '{"action": "close", "size_pct": 1.0, "reason": "Emergency close triggered by user - closing all positions immediately"}'
                else:
                    raw_llm_output = '{"action": "hold", "size_pct": 0.0, "reason": "Emergency close triggered but no position"}'
                    
                    # If no position on this symbol, check if all symbols have no positions, then clear flag
                    # We'll clear the flag in the main loop after processing all symbols
                
        # ====================================================================
        # STEP 3: Get decision from decision provider (if no SL/TP/emergency)
        # ====================================================================
        if raw_llm_output is None:
            try:
                raw_llm_output = self.decision_provider.get_decision(
                    snapshot, position_size, equity
                )
                if position_size == 0:
                    # Log decision for new entry evaluation
                    temp_parsed = self.decision_parser.parse(raw_llm_output)
                    temp_confidence = getattr(temp_parsed, 'confidence', 0.0)
                    logger.info(f"    {symbol}: {temp_parsed.action} (confidence: {temp_confidence:.2f})")
            except Exception as e:
                logger.error(f"  {symbol}: Decision provider failed: {e}")
                raw_llm_output = f"Error: {str(e)}"
                
        # ====================================================================
        # STEP 4: Parse decision
        # ====================================================================
        decision = self.decision_parser.parse(raw_llm_output)
        
        # ====================================================================
        # STEP 5: Validate with risk manager
        # ====================================================================
        risk_result = self.risk_manager.validate(
            decision, snapshot, position_size, equity
        )
        
        if not risk_result.approved and decision.action in ['long', 'short', 'close', 'sell']:
            logger.info(f"    {symbol}: Risk manager denied: {risk_result.reason}")
        
        # ====================================================================
        # STEP 6: Execute trade if approved
        # ====================================================================
        execution_result = None
        if risk_result.approved:
            try:
                execution_result = self.trade_executor.execute(
                    decision, snapshot, position_size, equity
                )
                if execution_result.executed:
                    logger.info(f"    {symbol}: EXECUTED - {decision.action} @ ${execution_result.fill_price:.2f}")
                elif execution_result.error:
                    logger.warning(f"    {symbol}: Execution error: {execution_result.error}")
            except Exception as e:
                logger.error(f"    {symbol}: Execution failed: {e}")
                from src.models import ExecutionResult
                execution_result = ExecutionResult(
                    executed=False, order_id=None, filled_size=None,
                    fill_price=None, error=str(e)
                )
        else:
            from src.models import ExecutionResult
            execution_result = ExecutionResult(
                executed=False, order_id=None, filled_size=None,
                fill_price=None, error=None
            )
        
        # ====================================================================
        # STEP 7: Update position tracking
        # ====================================================================
        if execution_result and execution_result.executed and execution_result.filled_size:
            # Handle position opening
            if decision.action in ['long', 'short'] and execution_result.fill_price:
                self.position_entry_prices[symbol] = execution_result.fill_price
                self.position_entry_timestamps[symbol] = int(time.time())
                
                position_type = getattr(decision, 'position_type', 'swing')
                self.position_types[symbol] = position_type
                
                if decision.stop_loss is not None:
                    self.position_stop_losses[symbol] = decision.stop_loss
                if decision.take_profit is not None:
                    self.position_take_profits[symbol] = decision.take_profit
                
                leverage = getattr(decision, 'leverage', 1.0)
                self.position_leverages[symbol] = leverage
                
                risk_amount = getattr(decision, 'risk_amount', None)
                reward_amount = getattr(decision, 'reward_amount', None)
                if risk_amount is not None:
                    self.position_risk_amounts[symbol] = risk_amount
                if reward_amount is not None:
                    self.position_reward_amounts[symbol] = reward_amount
            
            # Handle position closing
            elif decision.action in ['sell', 'close']:
                # Save entry price before deletion for trade logging
                entry_price_for_closed_trade = self.position_entry_prices.get(symbol)
                entry_timestamp = self.position_entry_timestamps.get(symbol)
                
                # Calculate P&L if we have entry price
                if entry_price_for_closed_trade and execution_result.fill_price:
                    # Determine LONG vs SHORT from original position size
                    was_long = position_size > 0
                    if was_long:
                        pnl_pct = ((execution_result.fill_price - entry_price_for_closed_trade) / entry_price_for_closed_trade) * 100
                        trade_pnl = (execution_result.fill_price - entry_price_for_closed_trade) * execution_result.filled_size
                    else:
                        pnl_pct = ((entry_price_for_closed_trade - execution_result.fill_price) / entry_price_for_closed_trade) * 100
                        trade_pnl = (entry_price_for_closed_trade - execution_result.fill_price) * abs(execution_result.filled_size)
                    
                    # Log trade to frontend
                    if self.api_client:
                        base_currency = symbol.split('/')[0]
                        entry_notional = abs(position_size) * entry_price_for_closed_trade
                        exit_notional = abs(execution_result.filled_size) * execution_result.fill_price
                        
                        # Calculate holding time
                        holding_time = "N/A"
                        if entry_timestamp:
                            holding_time = self._calculate_holding_time(entry_timestamp, int(time.time()))
                        
                        self.api_client.add_trade(
                            coin=base_currency,
                            side="LONG" if was_long else "SHORT",
                            entry_price=entry_price_for_closed_trade,
                            exit_price=execution_result.fill_price,
                            quantity=abs(execution_result.filled_size),
                            entry_notional=entry_notional,
                            exit_notional=exit_notional,
                            holding_time=holding_time,
                            pnl=trade_pnl,
                            entry_timestamp=entry_timestamp,
                            exit_timestamp=int(time.time())
                        )
                
                # Send agent message for close actions (including emergency close)
                if self.api_client:
                    # Get all snapshots from the parameter (passed from parent run method)
                    all_snapshots_for_msg = snapshots  # Use snapshots dict from _process_symbol parameter
                    
                    # Calculate available cash and unrealized P&L (position is closed, so P&L is now 0)
                    available_cash_for_msg = equity  # Position closed, all equity is available
                    unrealized_pnl_for_msg = 0.0  # Position closed, no unrealized P&L
                    
                    self._send_smart_agent_message(
                        decision=decision,
                        snapshot=snapshot,
                        position_size=0.0,  # Position is closed
                        equity=equity,
                        available_cash=available_cash_for_msg,
                        unrealized_pnl=unrealized_pnl_for_msg,
                        cycle_count=cycle_count,
                        all_snapshots=all_snapshots_for_msg
                    )
                
                # Clear all position tracking
                for tracking_dict in [
                    self.position_entry_prices,
                    self.position_entry_timestamps,
                    self.position_stop_losses,
                    self.position_take_profits,
                    self.position_types,
                    self.position_leverages,
                    self.position_risk_amounts,
                    self.position_reward_amounts
                ]:
                    if symbol in tracking_dict:
                        del tracking_dict[symbol]
        
        # ====================================================================
        # STEP 8: Store decision for status message
        # ====================================================================
        # Store decision for this symbol to generate comprehensive status message
        self.current_cycle_decisions[symbol] = {
            'decision': decision,
            'snapshot': snapshot,
            'position_size': position_size,
            'executed': execution_result.executed if execution_result else False,
            'risk_approved': risk_result.approved,
            'risk_reason': risk_result.reason
        }
        
        # ====================================================================
        # STEP 9: Log cycle data for this symbol
        # ====================================================================
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
            executed=execution_result.executed if execution_result else False,
            order_id=execution_result.order_id if execution_result else None,
            filled_size=execution_result.filled_size if execution_result else None,
            fill_price=execution_result.fill_price if execution_result else None,
            mode=self.config.run_mode
        )
        self.logger.log_cycle(cycle_log)
    
    def _update_frontend_all_positions(
        self,
        snapshots: dict,
        positions: dict,
        equity: float,
        cycle_count: int
    ) -> None:
        """
        Update frontend with all positions aggregated from all symbols.
        
        Args:
            snapshots: Dict of {symbol: snapshot}
            positions: Dict of {symbol: position_size}
            equity: Current account equity
            cycle_count: Current cycle number
        """
        if not self.api_client:
            return
        
        try:
            total_unrealized_pnl = 0.0
            positions_list = []
            
            # Process all positions
            for symbol in self.config.symbols:
                position_size = positions.get(symbol, 0.0)
                if position_size != 0:
                    snapshot = snapshots.get(symbol)
                    if snapshot:
                        entry_price = self.position_entry_prices.get(symbol, snapshot.price)
                        
                        # Calculate unrealized P&L
                        was_long = position_size > 0
                        if was_long:
                            unrealized_pnl = position_size * (snapshot.price - entry_price)
                            pnl_percentage = ((snapshot.price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
                        else:
                            unrealized_pnl = abs(position_size) * (entry_price - snapshot.price)
                            pnl_percentage = ((entry_price - snapshot.price) / entry_price) * 100 if entry_price > 0 else 0
                        
                        total_unrealized_pnl += unrealized_pnl
                        
                        base_currency = symbol.split('/')[0]
                        stop_loss = self.position_stop_losses.get(symbol)
                        take_profit = self.position_take_profits.get(symbol)
                        leverage = self.position_leverages.get(symbol, 1.0)
                        
                        positions_list.append({
                            "side": "LONG" if was_long else "SHORT",
                            "coin": base_currency,
                            "leverage": f"{leverage:.1f}X",
                            "notional": abs(position_size) * snapshot.price,
                            "unrealPnL": unrealized_pnl,
                            "entryPrice": entry_price,
                            "currentPrice": snapshot.price,
                            "pnlPercent": pnl_percentage,
                            "stopLoss": stop_loss,
                            "takeProfit": take_profit
                        })
            
            # Sync all positions
            self.api_client.sync_positions(positions_list)
            
            # Update balance (available cash = equity - total unrealized P&L)
            available_cash = equity - total_unrealized_pnl
            self.api_client.update_balance(available_cash, total_unrealized_pnl)
            
            logger.info(f"  Frontend updated: Cash=${available_cash:.2f}, P&L=${total_unrealized_pnl:.2f} (positions: {len(positions_list)})")
            
            #  Send status message when needed OR smart idle check-ins
            # Send messages for important events + intelligent periodic check-ins (when meaningful)
            should_send_status = False
            is_idle_message = False
            
            # Check if there's something meaningful to report
            if cycle_count == 1:
                # Always send welcome message on first cycle
                should_send_status = True
            elif self.current_cycle_decisions:
                # Check if any trades were executed or important events occurred
                for symbol, decision_data in self.current_cycle_decisions.items():
                    executed = decision_data.get('executed', False)
                    decision = decision_data.get('decision')
                    action = decision.action if decision else 'hold'
                    
                    # Send if: trades executed, emergency close, stop loss hit, take profit hit
                    if executed or action in ['close', 'emergency'] or 'stop loss' in str(decision.reason).lower() or 'take profit' in str(decision.reason).lower():
                        should_send_status = True
                        break
            
            # Smart idle check-in: Only send when it's been a while AND there's something mildly interesting
            # OR if it's been a very long time (50+ cycles) regardless
            cycles_since_last_message = cycle_count - self.last_message_cycle
            
            if not should_send_status and cycles_since_last_message >= 30:
                # Check if there's anything mildly interesting (not trade-worthy, but worth mentioning)
                has_interesting_activity = False
                if self.current_cycle_decisions:
                    for symbol, decision_data in self.current_cycle_decisions.items():
                        decision = decision_data.get('decision')
                        if decision:
                            reason = decision.reason.lower()
                            # Interesting but not trade-worthy: volume spikes, testing levels, reversals forming
                            interesting_keywords = ['volume', 'testing', 'support', 'resistance', 'reversal', 'breakout', 'breakdown', 'forming']
                            if any(keyword in reason for keyword in interesting_keywords):
                                has_interesting_activity = True
                                break
                
                # Send if: been 30+ cycles AND something interesting, OR been 50+ cycles regardless
                if (has_interesting_activity and cycles_since_last_message >= 30) or cycles_since_last_message >= 50:
                    should_send_status = True
                    is_idle_message = True
            
            if should_send_status and self.current_cycle_decisions and self.api_client:
                # Build comprehensive status message based on all symbol decisions
                self._send_comprehensive_status_message(
                    cycle_decisions=self.current_cycle_decisions,
                    snapshots=snapshots,
                    positions=positions,
                    equity=equity,
                    available_cash=available_cash,
                    unrealized_pnl=total_unrealized_pnl,
                    cycle_count=cycle_count,
                    is_idle_message=is_idle_message
                )
            
            # Reset decisions for next cycle
            self.current_cycle_decisions = {}
            
        except Exception as e:
            logger.warning(f"Failed to update frontend: {e}")
    
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
        available_cash: float, unrealized_pnl: float, all_snapshots: dict = None
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
            indicators = snapshot.indicators
            price = snapshot.price
            symbol = snapshot.symbol
            base_currency = symbol.split('/')[0]
            
            # Build ALL COINS market overview (COMPREHENSIVE - ALL INDICATORS)
            all_coins_context = ""
            if all_snapshots:
                all_coins_context = "\n\nALL 6 COINS MARKET OVERVIEW (COMPLETE DATA):\n"
                for coin_symbol, coin_snap in all_snapshots.items():
                    coin_name = coin_symbol.split('/')[0]
                    coin_price = coin_snap.price
                    coin_ind = coin_snap.indicators
                    
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
            prompt = f"""You are a professional crypto trader explaining your decision to your client in a casual, conversational way.

CURRENT SITUATION:
- Action: {decision.action.upper()}
- Position Type: {position_type} (swing = multi-day hold, scalp = quick in/out)
- {symbol} Price: ${price:,.2f}
- Your Equity: ${equity:,.2f}
- Available Cash: ${available_cash:,.2f}
- Current Position Size: {position_size:.6f} {base_currency}
- Unrealized P&L: ${unrealized_pnl:,.2f}

DECISION DETAILS:
- Reason: {decision.reason}
- Position Size: {decision.size_pct*100:.1f}% of equity
{f"- Stop Loss: ${decision.stop_loss:,.2f}" if decision.stop_loss else ""}
{f"- Take Profit: ${decision.take_profit:,.2f}" if decision.take_profit else ""}

**CRITICAL - CLOSE REASON IDENTIFICATION:**
{"**EMERGENCY CLOSE** - User manually triggered emergency close via 'CLOSE ALL' button. This is NOT a stop loss or take profit. Explain that you're closing all positions immediately at market price as requested." if 'emergency' in decision.reason.lower() else ""}
{"**STOP LOSS TRIGGERED** - Price hit stop loss level, closing position to limit losses. Explain this was a risk management exit, not a manual close." if 'stop loss' in decision.reason.lower() and 'emergency' not in decision.reason.lower() else ""}
{"**TAKE PROFIT TRIGGERED** - Price hit take profit level, closing position to lock in gains. Explain this was a profit target hit." if 'take profit' in decision.reason.lower() and 'emergency' not in decision.reason.lower() else ""}

MARKET CONTEXT ({symbol}):
- Daily Trend: {indicators.get('trend_1d', 'unknown')}
- 4H Trend: {indicators.get('trend_4h', 'unknown')}
- 1H RSI: {indicators.get('rsi_14', 50):.1f}
- Support/Resistance: S1=${indicators.get('support_1', 0)/1000:.1f}k, R1=${indicators.get('resistance_1', 0)/1000:.1f}k, Pivot=${indicators.get('pivot', 0)/1000:.1f}k
- VWAP 5m: ${indicators.get('vwap_5m', 0)/1000:.1f}k (price is {'above' if price > indicators.get('vwap_5m', price) else 'below'})
- Swing High: ${indicators.get('swing_high', 0)/1000:.1f}k, Swing Low: ${indicators.get('swing_low', 0)/1000:.1f}k
- Volume (1h): {indicators.get('volume_ratio_1h', 1.0):.2f}x average ({'STRONG' if indicators.get('volume_ratio_1h', 1.0) >= 1.5 else 'MODERATE' if indicators.get('volume_ratio_1h', 1.0) >= 1.2 else 'WEAK'})
- Volume Trend: {indicators.get('volume_trend_1h', 'stable')} | OBV: {indicators.get('obv_trend_1h', 'neutral')}{all_coins_context}

YOUR TASK:
Write a DETAILED, natural message (3-5 sentences) explaining what you're doing and why, like you're updating a friend. Include:
1. What action you're taking (or why you're waiting)
2. Key market context (S/R levels, VWAP, trends, volume)
3. Your reasoning and what you're watching for next
4. **CRITICAL**: Mention other coins from the ALL 6 COINS overview when relevant (e.g., "ETH looks weak", "SOL has strong volume", "XRP at support")
Be conversational, confident, and VARY your phrasing. Use first person ("I'm buying", "I'll wait", "watching for").

IMPORTANT - Include market context in your reasoning:
- Mention S/R levels (e.g., "bounced from support at $109.7k", "testing R1 resistance")
- Mention VWAP position (e.g., "price above VWAP", "below VWAP so bearish bias")
- Mention multi-timeframe alignment (e.g., "1d/4h bullish", "5m bearish")
- Mention key price action (e.g., "rejected at swing high", "broke above pivot")
- Mention VOLUME when relevant (e.g., "strong volume confirms breakout", "weak volume, waiting for confirmation", "volume spike at support")
- **Mention other coins** when explaining why you're choosing (or not choosing) to trade (e.g., "BTC is the cleanest setup - ETH below VWAP, SOL weak volume")

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
- **EMERGENCY CLOSE ONLY**: "Emergency closing all positions at market price as requested. Closing immediately at current market price ${price:,.2f} to exit all positions."
- **STOP LOSS ONLY**: "Stop loss triggered at $66.5k, closing position to limit losses. Price broke below S1 support, capital preservation activated."
- **TAKE PROFIT ONLY**: "Take profit hit at $68.5k, closing position to lock in gains. Hit R1 resistance perfectly, taking the win."

WAITING/NO POSITION (vary these - BE CREATIVE AND DETAILED):
- "Watching from sidelines right now. Price is testing R1 resistance at $110.5k with weak volume (0.8x average), and the 1-hour trend just flipped bearish. I'm waiting to see if we get a clean breakout above R1 with volume confirmation, or if we reject and head back to support. Daily trend is still bearish, so I'm cautious about longs here. If we break and hold above $110.5k with strong volume, I'll consider a scalp to R2."
- "No position yet - just monitoring all 6 coins. BTC is at $110.2k testing pivot resistance with mixed trends (daily bearish, 1h bullish). ETH and SOL both look weak below their VWAPs. DOGE is at support but volume is too low. BNB had a volume spike but got rejected at R1. XRP is the most interesting - sitting at S1 support with OBV trending up, but I want to see price reclaim VWAP first. Overall, no clear high-probability setups across any coins yet, so I'm staying patient and waiting for a strong signal."
- "Staying patient. Price is chopping between S1 support at $109.2k and pivot at $109.8k with weak volume (0.7x average), which tells me neither bulls nor bears have conviction yet. Daily trend is bearish but 4-hour is bullish - mixed signals. I'm waiting for a clear break of this range with volume confirmation before entering. If we break below S1 with volume, I'll look for shorts to S2. If we reclaim pivot with strong volume (>1.5x), I'll consider longs to R1."
- "Holding cash and being selective. Price rejected at swing high $110.9k twice in the past hour, which is a strong resistance level. The 5-minute chart is bearish and we're below VWAP at $110.3k, but the 1-hour trend is still bullish so I don't want to short blindly. I'm watching to see if we get a third rejection (strong short signal) or if bulls can push through with volume. Volume is currently moderate (1.1x), need to see it spike above 1.5x for a breakout trade."
- "Patience mode activated. Volume completely dried up (0.5x average) and price is just drifting sideways between $109.5k and $110.0k. The daily and 4-hour trends are both bearish, but we're sitting right on S1 support at $109.5k which has held three times today. I'm waiting for a volume spike - if we get strong volume at this support level and price bounces, that's a great long entry to pivot. If volume comes in and we break below S1, that's a short signal to S2. Right now, it's just noise."

BE CREATIVE - Don't copy these examples exactly. Mix and match concepts. Explain your actual market analysis in detail (3-5 sentences).

Write ONLY the message, nothing else:"""
            
            # Call AI
            response = self.openai_client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,  # Increased for longer, more detailed messages
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
        available_cash: float, unrealized_pnl: float, cycle_count: int, all_snapshots: dict = None
    ) -> None:
        """
        Send AI-generated natural messages to users.
        
        Args:
            all_snapshots: Dict of {symbol: snapshot} for all monitored coins
        
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
                available_cash, unrealized_pnl, all_snapshots
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
                    available_cash, unrealized_pnl, all_snapshots
                )
                self.api_client.add_agent_message(message)
                self.last_message_type = "hold"
                self.last_message_cycle = cycle_count
    
    def _send_comprehensive_status_message(
        self, cycle_decisions: dict, snapshots: dict, positions: dict,
        equity: float, available_cash: float, unrealized_pnl: float, cycle_count: int,
        is_idle_message: bool = False
    ) -> None:
        """
        Send comprehensive status message based on all symbol decisions made in this cycle.
        Tells user what the agent is actually doing: checking coins, waiting, monitoring, etc.
        
        Args:
            cycle_decisions: Dict of {symbol: {decision, snapshot, position_size, executed, risk_approved, risk_reason}}
            snapshots: Dict of {symbol: snapshot} for all coins
            positions: Dict of {symbol: position_size}
            equity: Current account equity
            available_cash: Available cash
            unrealized_pnl: Total unrealized P&L
            cycle_count: Current cycle number
        """
        if not self.api_client or not self.openai_client:
            return
        
        try:
            # Build detailed status summary for all symbols
            symbol_statuses = []
            has_active_position = False
            has_executed_trade = False
            
            for symbol in self.config.symbols:
                if symbol in cycle_decisions:
                    decision_data = cycle_decisions[symbol]
                    decision = decision_data['decision']
                    snapshot = decision_data['snapshot']
                    position_size = decision_data['position_size']
                    executed = decision_data.get('executed', False)
                    risk_approved = decision_data.get('risk_approved', True)
                    risk_reason = decision_data.get('risk_reason', '')
                    
                    if position_size != 0:
                        has_active_position = True
                    if executed:
                        has_executed_trade = True
                    
                    # Build status for this symbol
                    coin_name = symbol.split('/')[0]
                    price = snapshot.price
                    indicators = snapshot.indicators
                    
                    # Get decision details
                    action = decision.action
                    reason = decision.reason
                    confidence = getattr(decision, 'confidence', 0.0)
                    
                    # Format status
                    if action == 'hold':
                        status_text = f"{coin_name} ({symbol}): Waiting - {reason}"
                    elif action in ['long', 'short']:
                        if executed:
                            status_text = f"{coin_name} ({symbol}):  EXECUTED {action.upper()} at ${price:,.2f}"
                        elif not risk_approved:
                            status_text = f"{coin_name} ({symbol}):  {action.upper()} signal denied ({risk_reason})"
                        else:
                            status_text = f"{coin_name} ({symbol}): {action.upper()} signal ({confidence:.0%} confidence) - {reason}"
                    elif action in ['close', 'sell']:
                        if executed:
                            status_text = f"{coin_name} ({symbol}): ✅ CLOSED position at ${price:,.2f}"
                        else:
                            status_text = f"{coin_name} ({symbol}): Closing - {reason}"
                    else:
                        status_text = f"{coin_name} ({symbol}): {action.upper()} - {reason}"
                    
                    symbol_statuses.append(status_text)
            
            # Build comprehensive prompt for AI
            active_positions_summary = ""
            if has_active_position:
                pos_summary = []
                for symbol, pos_size in positions.items():
                    if pos_size != 0:
                        coin = symbol.split('/')[0]
                        pos_type = "LONG" if pos_size > 0 else "SHORT"
                        pos_summary.append(f"{coin} {pos_type}")
                active_positions_summary = f"\nCurrent Positions: {', '.join(pos_summary)}" if pos_summary else ""
            
            status_summary = "\n".join(symbol_statuses) if symbol_statuses else "No decisions made this cycle"
            
            # Determine message type based on what happened
            has_executed_trades = any(d.get('executed', False) for d in cycle_decisions.values())
            has_emergency_close = any('emergency' in str(d.get('decision', {}).reason).lower() for d in cycle_decisions.values())
            
            if cycle_count == 1:
                prompt_type = "FIRST_CYCLE_WELCOME"
                prompt_context = "This is the first cycle. Give a brief welcome message explaining you're starting up and monitoring all 6 coins."
            elif has_executed_trades:
                prompt_type = "TRADE_EXECUTED"
                prompt_context = "You just executed trades. Summarize what you did and why."
            elif has_emergency_close:
                prompt_type = "EMERGENCY_CLOSE"
                prompt_context = "Emergency close was triggered. Explain that you're closing all positions immediately."
            elif is_idle_message:
                prompt_type = "IDLE_CHECK_IN"
                prompt_context = "This is a periodic check-in message. Write a natural, human-like update as if you're a real person watching the market. Be conversational and brief."
            else:
                prompt_type = "STATUS_UPDATE"
                prompt_context = "Send a brief summary of current market status. Keep it concise - only mention notable observations."
            
            if is_idle_message:
                # Idle check-in message - natural, human-like, brief
                prompt = f"""You are a professional crypto trading agent giving a natural, periodic check-in to your client.

CURRENT MARKET STATUS:
- Monitoring {len(snapshots)} coins: {', '.join([s.split('/')[0] for s in snapshots.keys()])}
{active_positions_summary if active_positions_summary else ""}
- Available Cash: ${available_cash:,.2f}
- Unrealized P&L: ${unrealized_pnl:,.2f}

YOUR TASK:
Write a NATURAL, CONVERSATIONAL message (2-3 sentences) as if you're a real person checking in. It should feel human, not robotic.

Examples:
- "Just checking in - I'm actively watching the market across all 6 coins, scanning for the best setup. Nothing compelling yet, staying patient and waiting for a clean signal with good volume confirmation."
- "Hi there - currently monitoring the markets and watching for opportunities. All coins are showing mixed signals right now, so I'm being selective and waiting for a clear setup before entering any trades."
- "Checking in: I'm watching all coins closely and scanning for setups. Market is consolidating at the moment, so I'm staying patient and waiting for a strong signal to appear."
- "Still here, actively watching the market for the best opportunities. Nothing exciting yet - staying disciplined and waiting for a clean entry with proper volume confirmation."

IMPORTANT:
- Keep it SHORT (2-3 sentences max)
- Use natural, conversational language (like a real person)
- Mention you're watching/monitoring the market
- Be brief - don't list every detail
- Use first person ("I'm watching", "I'm waiting", "I'm checking")

Write ONLY the message, nothing else:"""
            else:
                # Important event message (trades, emergency, etc.)
                prompt = f"""You are a professional crypto trading agent updating your client with a BRIEF, CONCISE summary.

CURRENT STATUS ({len(snapshots)} coins monitored):
{status_summary}
{active_positions_summary}

ACCOUNT STATUS:
- Equity: ${equity:,.2f}
- Available Cash: ${available_cash:,.2f}
- Unrealized P&L: ${unrealized_pnl:,.2f}

CONTEXT: {prompt_context}

YOUR TASK:
Write a BRIEF, NATURAL message (2-3 sentences MAX) summarizing what happened:
- If trades executed: Say what you did and why
- If emergency close: Explain you're closing all positions immediately
- If first cycle: Brief welcome message
- Otherwise: Brief status update (only mention notable observations, not every coin)

IMPORTANT:
- Keep it SHORT and CONCISE (2-3 sentences max)
- Only mention IMPORTANT events or notable observations
- Don't list every coin if nothing special happened
- Use first person ("I executed", "I'm waiting", "I found")

Examples:
- Trade executed: "Just opened a LONG position in SOL at $185.12. Strong bearish alignment across timeframes, clean breakdown signal. Monitoring for stop loss at $184.43."
- Emergency close: "Emergency closing all positions immediately at market price as requested. Closing all positions now."
- First cycle: "Starting up and monitoring all 6 coins: BTC, ETH, SOL, DOGE, BNB, XRP. Checking for trading opportunities..."
- Status update (only if something notable): "ETH is testing support at $3,862 with decent volume - watching closely. Other coins showing weak signals, staying patient."

Write ONLY the message, nothing else (2-3 sentences max):"""
            
            # Call AI to generate natural status message
            response = self.openai_client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.7,
                timeout=5.0
            )
            
            message = response.choices[0].message.content.strip()
            
            # Remove quotes if AI added them
            if message.startswith('"') and message.endswith('"'):
                message = message[1:-1]
            if message.startswith("'") and message.endswith("'"):
                message = message[1:-1]
            
            # Send message
            self.api_client.add_agent_message(message)
            self.last_message_type = "hold"
            self.last_message_cycle = cycle_count
            
        except Exception as e:
            logger.warning(f"Failed to generate comprehensive status message: {e}")
            # Fallback to simple message
            if snapshots:
                coins_list = ', '.join([s.split('/')[0] for s in snapshots.keys()])
                fallback_msg = f"Monitoring {len(snapshots)} coins: {coins_list}. Checking for trading opportunities..."
                self.api_client.add_agent_message(fallback_msg)
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
