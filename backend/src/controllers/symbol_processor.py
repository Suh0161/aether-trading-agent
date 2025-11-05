"""Symbol processing controller for individual trading symbols."""

import logging
import os
import time
from datetime import datetime
from typing import Any, Optional

from src.utils.snapshot_utils import get_price_from_snapshot
from src.portfolio.allocator import PortfolioAllocator
from src.controllers.symbol_processor_helpers import (
    get_strategy_decision as _sp_get_strategy_decision,
    execute_strategy_decision as _sp_execute_strategy_decision,
    should_skip_llm_call as _sp_should_skip_llm_call,
)

logger = logging.getLogger(__name__)


class SymbolProcessor:
    """Processes individual trading symbols through the trading cycle."""

    def __init__(self, config, position_manager, risk_manager, trade_executor,
                 decision_provider, decision_parser, logger_instance, ai_message_service):
        """
        Initialize symbol processor.

        Args:
            config: Configuration object
            position_manager: PositionManager instance
            risk_manager: RiskManager instance
            trade_executor: TradeExecutor instance
            decision_provider: Decision provider instance
            decision_parser: Decision parser instance
            logger_instance: Logger instance
            ai_message_service: AIMessageService instance
        """
        self.config = config
        self.position_manager = position_manager
        self.risk_manager = risk_manager
        self.trade_executor = trade_executor
        self.decision_provider = decision_provider
        self.decision_parser = decision_parser
        self.logger = logger_instance
        self.ai_message_service = ai_message_service

        # Track decisions per symbol for status messages
        self.current_cycle_decisions = {}  # {symbol: decision} for current cycle

        # Track last LLM call per symbol for cost optimization
        self.last_llm_call = {}  # {symbol: {'price': float, 'cycle': int, 'timestamp': int}}

        # Portfolio allocator
        self.portfolio_allocator = PortfolioAllocator(config, position_manager)

    def process_symbol(
        self,
        symbol: str,
        snapshots: dict,
        positions: dict,
        equity: float,
        cycle_count: int,
        api_client=None,
        all_snapshots: dict = None
    ) -> None:
        """
        Process a single symbol: check stop loss/take profit, get decision, execute trade.

        Args:
            symbol: Trading symbol to process
            snapshots: Dict of {symbol: snapshot}
            positions: Dict of {symbol: position_size}
            equity: Current account equity
            cycle_count: Current cycle number
            api_client: Optional API client for messaging
            all_snapshots: Dict of all snapshots for AI messaging
        """
        snapshot = snapshots.get(symbol)
        if not snapshot:
            logger.warning(f"  {symbol}: No snapshot available, skipping")
            return

        # Get total position size (swing + scalp) for backward compatibility
        position_size = self.position_manager.get_total_position(symbol)

        # ====================================================================
        # STEP 1: Check stop loss / take profit for existing positions (per-type)
        # ====================================================================
        raw_llm_output = None

        # Check if agent is paused - halt immediately
        pause_flag = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agent_paused.flag")
        if os.path.exists(pause_flag):
            logger.info(f"  {symbol}: Agent paused - halting symbol processing")
            return

        # Check both swing and scalp positions separately
        swing_position = self.position_manager.get_position_by_type(symbol, 'swing')
        scalp_position = self.position_manager.get_position_by_type(symbol, 'scalp')
        current_price = get_price_from_snapshot(snapshot)

        # Update trailing stops for existing positions (before SL/TP checks)
        if abs(swing_position) > 0.0001:
            self.position_manager.update_trailing_stops(symbol, 'swing', swing_position, current_price)
        if abs(scalp_position) > 0.0001:
            self.position_manager.update_trailing_stops(symbol, 'scalp', scalp_position, current_price)

        # Check swing position SL/TP
        if abs(swing_position) > 0.0001:
            raw_llm_output = self.position_manager.check_position_sl_tp(
                symbol, snapshot, 'swing', swing_position, current_price
            )

        # Check scalp position SL/TP (only if swing didn't trigger)
        if raw_llm_output is None and abs(scalp_position) > 0.0001:
            raw_llm_output = self.position_manager.check_position_sl_tp(
                symbol, snapshot, 'scalp', scalp_position, current_price
            )

        # Check if agent is paused again (after SL/TP checks)
        if os.path.exists(pause_flag):
            logger.info(f"  {symbol}: Agent paused - halting symbol processing")
            return

        # ====================================================================
        # STEP 2: Check for emergency close flag
        # ====================================================================
        if raw_llm_output is None:
            # Support flag in either backend/src or backend root
            src_dir = os.path.dirname(os.path.dirname(__file__))
            backend_dir = os.path.dirname(src_dir)
            flag_candidates = [
                os.path.join(src_dir, "emergency_close.flag"),
                os.path.join(backend_dir, "emergency_close.flag"),
            ]
            emergency_flag = next((p for p in flag_candidates if os.path.exists(p)), None)
            if emergency_flag:
                logger.warning(f"[WARNING] {symbol}: EMERGENCY CLOSE TRIGGERED!")
                try:
                    # Close both swing and scalp positions immediately in this cycle
                    self._emergency_close_all_for_symbol(symbol, snapshot)
                    # Skip normal processing for this symbol after emergency close
                    return
                except Exception as _e:
                    logger.warning(f"  {symbol}: Emergency close error, falling back to single close path: {_e}")
                if position_size != 0:
                    raw_llm_output = '{"action": "close", "size_pct": 1.0, "reason": "Emergency close triggered by user - closing all positions immediately"}'
                else:
                    raw_llm_output = '{"action": "hold", "size_pct": 0.0, "reason": "Emergency close triggered but no position"}'

        # ====================================================================
        # STEP 3: Get decision from decision provider (if no SL/TP/emergency)
        # ====================================================================
        if raw_llm_output is None:
            # Inject entry timestamp and price into snapshot indicators for scalping "no move" exit logic
            # CRITICAL FIX: Inject position-type-specific timestamp/price (not mixing swing/scalp)
            # The scalping strategy needs the correct entry timestamp for the scalp position
            entry_timestamp = None
            entry_price = None

            # Check if we have a scalp position (scalp strategy needs scalp-specific data)
            if abs(scalp_position) > 0.0001 and symbol in self.position_manager.position_entry_timestamps:
                entry_timestamp_dict = self.position_manager.position_entry_timestamps.get(symbol)
                entry_price_dict = self.position_manager.position_entry_prices.get(symbol, {})

                # Get scalp-specific timestamp and price
                if isinstance(entry_timestamp_dict, dict):
                    entry_timestamp = entry_timestamp_dict.get('scalp')
                else:
                    # Backward compatibility: only use if scalp position exists
                    entry_timestamp = entry_timestamp_dict if abs(scalp_position) > 0.0001 else None

                if isinstance(entry_price_dict, dict):
                    entry_price = entry_price_dict.get('scalp')
                else:
                    # Backward compatibility
                    entry_price = entry_price_dict if entry_price_dict and abs(scalp_position) > 0.0001 else None

            # Fallback: If no scalp position but have swing position, use swing data
            # (This is for backward compatibility, but scalping strategy shouldn't be called if no scalp position)
            if entry_timestamp is None and abs(swing_position) > 0.0001 and symbol in self.position_manager.position_entry_timestamps:
                entry_timestamp_dict = self.position_manager.position_entry_timestamps.get(symbol)
                entry_price_dict = self.position_manager.position_entry_prices.get(symbol, {})

                if isinstance(entry_timestamp_dict, dict):
                    entry_timestamp = entry_timestamp_dict.get('swing')
                else:
                    entry_timestamp = entry_timestamp_dict

                if isinstance(entry_price_dict, dict):
                    entry_price = entry_price_dict.get('swing', get_price_from_snapshot(snapshot))
                else:
                    entry_price = entry_price_dict if entry_price_dict else get_price_from_snapshot(snapshot)

            # Inject into snapshot only if we have valid data
            if entry_timestamp is not None and entry_timestamp > 0:
                from src.tiered_data import EnhancedMarketSnapshot
                if isinstance(snapshot, EnhancedMarketSnapshot):
                    snapshot.original.indicators['position_entry_timestamp'] = entry_timestamp
                    if entry_price is not None:
                        snapshot.original.indicators['position_entry_price'] = entry_price
                else:
                    snapshot.indicators['position_entry_timestamp'] = entry_timestamp
                    if entry_price is not None:
                        snapshot.indicators['position_entry_price'] = entry_price

            # Check if agent is paused before LLM call
            if os.path.exists(pause_flag):
                logger.info(f"  {symbol}: Agent paused - halting before decision provider")
                return

            # ====================================================================
            # NEW APPROACH: Check BOTH strategies independently (no priority!)
            # ====================================================================
            self._process_both_strategies_independently(symbol, snapshot, swing_position, scalp_position, equity, cycle_count, current_price, api_client, all_snapshots)
            return  # Both strategies processed independently
    def _process_both_strategies_independently(self, symbol: str, snapshot: Any, swing_position: float,
                                               scalp_position: float, equity: float, cycle_count: int,
                                               current_price: float, api_client: Any, all_snapshots: dict = None):
        """
        Process both SWING and SCALP strategies independently - no priority, no fallback!
        Both strategies can execute simultaneously if they find opportunities.
        """

        # ====================================================================
        # PROCESS SWING STRATEGY
        # ====================================================================
        swing_decision = self._get_strategy_decision(symbol, snapshot, swing_position, equity,
                                                     cycle_count, 'swing', current_price)
        
        # ALWAYS log decision details (even for HOLD)
        if swing_decision:
            confidence = getattr(swing_decision, 'confidence', 0.0)
            confidence_str = f"{confidence:.2f}" if isinstance(confidence, (int, float)) else str(confidence)
            reason = getattr(swing_decision, 'reason', 'N/A')
            
            if swing_decision.action in ["long", "short", "close"]:
                # Detailed logging for actual trades
                logger.info(f"  {symbol}: Step 3: Getting decision from Strategy...")
                logger.info(f"  {symbol}: ========================================")
                logger.info(f"  {symbol}: SYMBOL: {symbol}")
                logger.info(f"  {symbol}: STRATEGY: SWING")
                logger.info(f"  {symbol}: ACTION: {swing_decision.action.upper()}")
                logger.info(f"  {symbol}: CONFIDENCE: {confidence_str}")
                logger.info(f"  {symbol}: PRICE: ${current_price:,.2f}")
                logger.info(f"  {symbol}: STRATEGY REASONING: {reason}")
                logger.info(f"  {symbol}: ========================================")
                logger.info(f"  {symbol}: SWING opportunity found - executing {swing_decision.action.upper()}")
                self._execute_strategy_decision(swing_decision, symbol, snapshot, cycle_count, equity, api_client, 'swing', all_snapshots)
            else:
                # Compact table format for HOLD decisions
                logger.info(f"  {symbol}: Step 3: {symbol} | SWING | HOLD | Conf: {confidence_str} | Price: ${current_price:,.2f} | {reason[:60]}...")
                logger.info(f"  {symbol}: Step 4: Parsing decision... (HOLD - no parsing needed)")
                logger.info(f"  {symbol}: Step 5: Validating with risk manager... (HOLD - validation skipped)")
                logger.info(f"  {symbol}: Step 6: Executing trade... (HOLD - no execution needed)")
                logger.debug(f"  {symbol}: SWING HOLD Reasoning: {reason}")

        # ====================================================================
        # PROCESS SCALP STRATEGY (independent of swing!)
        # ====================================================================
        scalp_decision = self._get_strategy_decision(symbol, snapshot, scalp_position, equity,
                                                     cycle_count, 'scalp', current_price)
        
        # ALWAYS log decision details (even for HOLD)
        if scalp_decision:
            confidence = getattr(scalp_decision, 'confidence', 0.0)
            confidence_str = f"{confidence:.2f}" if isinstance(confidence, (int, float)) else str(confidence)
            reason = getattr(scalp_decision, 'reason', 'N/A')
            
            if scalp_decision.action in ["long", "short", "close"]:
                # Detailed logging for actual trades
                logger.info(f"  {symbol}: Step 3: Getting decision from Strategy...")
                logger.info(f"  {symbol}: ========================================")
                logger.info(f"  {symbol}: SYMBOL: {symbol}")
                logger.info(f"  {symbol}: STRATEGY: SCALP")
                logger.info(f"  {symbol}: ACTION: {scalp_decision.action.upper()}")
                logger.info(f"  {symbol}: CONFIDENCE: {confidence_str}")
                logger.info(f"  {symbol}: PRICE: ${current_price:,.2f}")
                logger.info(f"  {symbol}: STRATEGY REASONING: {reason}")
                logger.info(f"  {symbol}: ========================================")
                logger.info(f"  {symbol}: SCALP opportunity found - executing {scalp_decision.action.upper()}")
                self._execute_strategy_decision(scalp_decision, symbol, snapshot, cycle_count, equity, api_client, 'scalp', all_snapshots)
            else:
                # Compact table format for HOLD decisions
                logger.info(f"  {symbol}: Step 3: {symbol} | SCALP | HOLD | Conf: {confidence_str} | Price: ${current_price:,.2f} | {reason[:60]}...")
                logger.info(f"  {symbol}: Step 4: Parsing decision... (HOLD - no parsing needed)")
                logger.info(f"  {symbol}: Step 5: Validating with risk manager... (HOLD - validation skipped)")
                logger.info(f"  {symbol}: Step 6: Executing trade... (HOLD - no execution needed)")
                logger.debug(f"  {symbol}: SCALP HOLD Reasoning: {reason}")

        # Log results (only for trades, HOLD is already logged compactly)
        if (swing_decision and swing_decision.action in ["long", "short", "close"]) or \
           (scalp_decision and scalp_decision.action in ["long", "short", "close"]):
            swing_action = swing_decision.action.upper() if swing_decision else "NONE"
            scalp_action = scalp_decision.action.upper() if scalp_decision else "NONE"
            logger.info(f"  {symbol}: Strategy results - SWING: {swing_action}, SCALP: {scalp_action}")

    def _get_strategy_decision(self, symbol: str, snapshot: Any, position_size: float, equity: float,
                               cycle_count: int, strategy_type: str, current_price: float) -> Optional[Any]:
        """Delegate to helper to keep file small."""
        return _sp_get_strategy_decision(self, symbol, snapshot, position_size, equity, cycle_count, strategy_type, current_price)

    def _execute_strategy_decision(self, decision: Any, symbol: str, snapshot: Any, cycle_count: int,
                                   equity: float, api_client: Any, strategy_type: str = None, all_snapshots: dict = None):
        """Delegate to helper to keep file small."""
        return _sp_execute_strategy_decision(self, decision, symbol, snapshot, cycle_count, equity, api_client, strategy_type, all_snapshots)

    def _should_skip_llm_call(self, symbol: str, snapshot, position_size: float, cycle_count: int) -> bool:
        """Delegate skip decision to helper."""
        return _sp_should_skip_llm_call(self, symbol, snapshot, position_size, cycle_count)

    def _update_position_tracking_after_trade(self, decision, snapshot, symbol: str, cycle_count: int, execution_result=None):
        """Update position tracking after a successful trade."""
        try:
            position_type = getattr(decision, 'position_type', 'swing')  # Default to swing if not specified
            # Prefer exchange fill price for accurate PnL; fallback to snapshot price
            entry_price = getattr(execution_result, 'fill_price', None)
            if not isinstance(entry_price, (int, float)) or entry_price <= 0:
                entry_price = get_price_from_snapshot(snapshot)
            entry_timestamp = int(time.time())

            # Update position tracking based on action type
            if decision.action == "long":
                # For long trades, add to position size
                # CRITICAL: Use filled_size from execution_result, not decision.size_pct!
                # decision.size_pct is a PERCENTAGE (0.25 = 25%), not a quantity!
                filled_size = getattr(execution_result, 'filled_size', 0.0) if execution_result else 0.0
                if filled_size == 0.0:
                    # Fallback: calculate from size_pct if execution_result is missing
                    # This should never happen, but handle gracefully
                    # Use config.mock_starting_equity for demo mode, or raise error for live mode
                    equity = getattr(self.position_manager, 'tracked_equity', None)
                    if equity is None:
                        # In live mode, equity should come from exchange
                        if self.config.exchange_type.lower() != "binance_demo":
                            logger.error(f"  {symbol}: CRITICAL - No equity available in live mode! Cannot calculate position size.")
                            raise ValueError("Equity not available - cannot calculate position size without equity")
                        # Demo mode fallback: use config value
                        equity = self.config.mock_starting_equity
                        logger.warning(f"  {symbol}: Using config.mock_starting_equity={equity} as fallback (tracked_equity not available)")
                    capital_amount = equity * decision.size_pct
                    current_price = get_price_from_snapshot(snapshot)
                    filled_size = capital_amount / current_price if current_price > 0 else 0.0
                
                current_size = self.position_manager.get_position_by_type(symbol, position_type)
                new_size = current_size + filled_size  # Use actual filled quantity, not percentage!
                self.position_manager.set_position_by_type(symbol, position_type, new_size)

                # Set entry price, timestamp, and confidence for new positions
                if abs(new_size) > abs(current_size):  # Only update if position increased
                    if symbol not in self.position_manager.position_entry_prices:
                        self.position_manager.position_entry_prices[symbol] = {}
                    self.position_manager.position_entry_prices[symbol][position_type] = entry_price

                    if symbol not in self.position_manager.position_entry_timestamps:
                        self.position_manager.position_entry_timestamps[symbol] = {}
                    self.position_manager.position_entry_timestamps[symbol][position_type] = entry_timestamp

                    # Store confidence for trailing stop calculations
                    if symbol not in self.position_manager.position_confidence:
                        self.position_manager.position_confidence[symbol] = {}
                    self.position_manager.position_confidence[symbol][position_type] = getattr(decision, 'confidence', 0.5)

                    # Initialize highest price tracking for trailing stops (LONG position)
                    if symbol not in self.position_manager.position_highest_prices:
                        self.position_manager.position_highest_prices[symbol] = {}
                    self.position_manager.position_highest_prices[symbol][position_type] = entry_price

                    # Store stop loss and take profit from decision (if provided)
                    stop_loss = getattr(decision, 'stop_loss', None)
                    take_profit = getattr(decision, 'take_profit', None)
                    if stop_loss is not None:
                        if symbol not in self.position_manager.position_stop_losses:
                            self.position_manager.position_stop_losses[symbol] = {}
                        self.position_manager.position_stop_losses[symbol][position_type] = stop_loss
                        logger.info(f"  {symbol}: Stored {position_type} SL: ${stop_loss:.2f}")
                    if take_profit is not None:
                        if symbol not in self.position_manager.position_take_profits:
                            self.position_manager.position_take_profits[symbol] = {}
                        self.position_manager.position_take_profits[symbol][position_type] = take_profit
                        logger.info(f"  {symbol}: Stored {position_type} TP: ${take_profit:.2f}")

                    # Store leverage from decision (if provided)
                    leverage = getattr(decision, 'leverage', 1.0)
                    if symbol not in self.position_manager.position_leverages:
                        self.position_manager.position_leverages[symbol] = {}
                    self.position_manager.position_leverages[symbol][position_type] = leverage
                    logger.info(f"  {symbol}: Stored {position_type} leverage: {leverage:.1f}x")

                    # Store actual capital used for margin calculation
                    capital_amount = getattr(decision, 'capital_amount', None)
                    if capital_amount is None:
                        equity_fallback = getattr(self.position_manager, 'tracked_equity', None)
                        if equity_fallback is None:
                            if self.config.exchange_type.lower() != "binance_demo":
                                logger.error(f"  {symbol}: CRITICAL - No equity available in live mode! Cannot calculate capital amount.")
                                raise ValueError("Equity not available - cannot calculate capital amount without equity")
                            equity_fallback = self.config.mock_starting_equity
                            logger.warning(f"  {symbol}: Using config.mock_starting_equity={equity_fallback} as fallback (tracked_equity not available)")
                        capital_amount = equity_fallback * getattr(decision, 'size_pct', 0.0)
                    if symbol not in self.position_manager.position_capital_used:
                        self.position_manager.position_capital_used[symbol] = {}
                    self.position_manager.position_capital_used[symbol][position_type] = capital_amount
                    logger.debug(f"  {symbol}: Stored {position_type} capital used: ${capital_amount:.2f}")

            elif decision.action == "short":
                # For short trades, subtract from position size (negative size)
                # CRITICAL: Use filled_size from execution_result, not decision.size_pct!
                # decision.size_pct is a PERCENTAGE (0.25 = 25%), not a quantity!
                filled_size = getattr(execution_result, 'filled_size', 0.0) if execution_result else 0.0
                if filled_size == 0.0:
                    # Fallback: calculate from size_pct if execution_result is missing
                    # This should never happen, but handle gracefully
                    # Use config.mock_starting_equity for demo mode, or raise error for live mode
                    equity = getattr(self.position_manager, 'tracked_equity', None)
                    if equity is None:
                        # In live mode, equity should come from exchange
                        if self.config.exchange_type.lower() != "binance_demo":
                            logger.error(f"  {symbol}: CRITICAL - No equity available in live mode! Cannot calculate position size.")
                            raise ValueError("Equity not available - cannot calculate position size without equity")
                        # Demo mode fallback: use config value
                        equity = self.config.mock_starting_equity
                        logger.warning(f"  {symbol}: Using config.mock_starting_equity={equity} as fallback (tracked_equity not available)")
                    capital_amount = equity * decision.size_pct
                    current_price = get_price_from_snapshot(snapshot)
                    filled_size = capital_amount / current_price if current_price > 0 else 0.0
                
                current_size = self.position_manager.get_position_by_type(symbol, position_type)
                new_size = current_size - filled_size  # Use actual filled quantity, not percentage!
                self.position_manager.set_position_by_type(symbol, position_type, new_size)

                # Set entry price, timestamp, and confidence for new positions
                if abs(new_size) > abs(current_size):  # Only update if position increased (more negative)
                    if symbol not in self.position_manager.position_entry_prices:
                        self.position_manager.position_entry_prices[symbol] = {}
                    self.position_manager.position_entry_prices[symbol][position_type] = entry_price

                    if symbol not in self.position_manager.position_entry_timestamps:
                        self.position_manager.position_entry_timestamps[symbol] = {}
                    self.position_manager.position_entry_timestamps[symbol][position_type] = entry_timestamp

                    # Store confidence for trailing stop calculations
                    if symbol not in self.position_manager.position_confidence:
                        self.position_manager.position_confidence[symbol] = {}
                    self.position_manager.position_confidence[symbol][position_type] = getattr(decision, 'confidence', 0.5)

                    # Initialize lowest price tracking for trailing stops (SHORT position)
                    if symbol not in self.position_manager.position_lowest_prices:
                        self.position_manager.position_lowest_prices[symbol] = {}
                    self.position_manager.position_lowest_prices[symbol][position_type] = entry_price

                    # Store stop loss and take profit from decision (if provided)
                    stop_loss = getattr(decision, 'stop_loss', None)
                    take_profit = getattr(decision, 'take_profit', None)
                    if stop_loss is not None:
                        if symbol not in self.position_manager.position_stop_losses:
                            self.position_manager.position_stop_losses[symbol] = {}
                        self.position_manager.position_stop_losses[symbol][position_type] = stop_loss
                        logger.info(f"  {symbol}: Stored {position_type} SL: ${stop_loss:.2f}")
                    if take_profit is not None:
                        if symbol not in self.position_manager.position_take_profits:
                            self.position_manager.position_take_profits[symbol] = {}
                        self.position_manager.position_take_profits[symbol][position_type] = take_profit
                        logger.info(f"  {symbol}: Stored {position_type} TP: ${take_profit:.2f}")

                    # Store leverage from decision (if provided)
                    leverage = getattr(decision, 'leverage', 1.0)
                    if symbol not in self.position_manager.position_leverages:
                        self.position_manager.position_leverages[symbol] = {}
                    self.position_manager.position_leverages[symbol][position_type] = leverage
                    logger.info(f"  {symbol}: Stored {position_type} leverage: {leverage:.1f}x")
                    
                    # Store actual capital used for margin calculation (critical for smart money management)
                    # This is the actual capital allocated, not the inflated notional value
                    capital_amount = getattr(decision, 'capital_amount', None)
                    if capital_amount is None:
                        # Fallback: calculate from equity and size_pct
                        # Use config.mock_starting_equity for demo mode, or raise error for live mode
                        equity = getattr(self.position_manager, 'tracked_equity', None)
                        if equity is None:
                            # In live mode, equity should come from exchange
                            if self.config.exchange_type.lower() != "binance_demo":
                                logger.error(f"  {symbol}: CRITICAL - No equity available in live mode! Cannot calculate capital amount.")
                                raise ValueError("Equity not available - cannot calculate capital amount without equity")
                            # Demo mode fallback: use config value
                            equity = self.config.mock_starting_equity
                            logger.warning(f"  {symbol}: Using config.mock_starting_equity={equity} as fallback (tracked_equity not available)")
                        capital_amount = equity * decision.size_pct
                    if symbol not in self.position_manager.position_capital_used:
                        self.position_manager.position_capital_used[symbol] = {}
                    self.position_manager.position_capital_used[symbol][position_type] = capital_amount
                    logger.debug(f"  {symbol}: Stored {position_type} capital used: ${capital_amount:.2f}")

            elif decision.action == "close":
                # For close trades, set position to zero
                self.position_manager.set_position_by_type(symbol, position_type, 0.0)
                # Clear entry tracking, SL/TP, confidence, and trailing stop data
                self.position_manager._clear_position_tracking(symbol, position_type)

            logger.info(f"  {symbol}: Position updated - {position_type} position: {self.position_manager.get_position_by_type(symbol, position_type):.6f}")

        except Exception as e:
            logger.error(f"  {symbol}: Failed to update position tracking: {e}")

    def _log_completed_trade(self, symbol: str, decision, snapshot, execution_result, position_type: str, api_client,
                             prev_size: float = None, prev_entry_price: float = None):
        """Log completed trades to frontend.

        position_type here is 'swing' or 'scalp'. We infer LONG/SHORT from the
        previous position size (prev_size > 0 => LONG, < 0 => SHORT).
        """
        try:
            # Calculate PnL for the trade
            # Prefer the previously stored entry price if provided
            entry_price = prev_entry_price if isinstance(prev_entry_price, (int, float)) and prev_entry_price > 0 else getattr(execution_result, 'entry_price', get_price_from_snapshot(snapshot))
            exit_price = getattr(execution_result, 'fill_price', get_price_from_snapshot(snapshot))
            quantity = getattr(execution_result, 'filled_size', 0.0)
            if not isinstance(quantity, (int, float)) or quantity <= 0:
                # Fallback to previous absolute position size
                quantity = abs(prev_size) if isinstance(prev_size, (int, float)) else abs(getattr(decision, 'size_pct', 0.0))
            
            if decision.action == "close":
                # Calculate realized PnL
                was_long = True if isinstance(prev_size, (int, float)) and prev_size > 0 else False
                if was_long:
                    realized_pnl = (exit_price - entry_price) * quantity
                    side_str = "LONG"
                else:
                    realized_pnl = (entry_price - exit_price) * quantity
                    side_str = "SHORT"
                # Skip micro-noise trades to avoid cluttering Completed Trades with $0.00
                if abs(realized_pnl) < 0.01:
                    logger.info(f"  {symbol}: Completed trade P&L ${realized_pnl:.4f} < $0.01 - suppressing UI entry")
                    return
                
                # Calculate holding time
                entry_timestamp = None
                if symbol in self.position_manager.position_entry_timestamps:
                    timestamp_dict = self.position_manager.position_entry_timestamps.get(symbol, {})
                    if isinstance(timestamp_dict, dict):
                        entry_timestamp = timestamp_dict.get(position_type)
                
                holding_time = "Unknown"
                if entry_timestamp:
                    holding_seconds = int(time.time()) - entry_timestamp
                    if holding_seconds < 3600:
                        holding_time = f"{holding_seconds // 60}m"
                    else:
                        holding_time = f"{holding_seconds // 3600}h {(holding_seconds % 3600) // 60}m"
                
                # Send to frontend
                # Map trade data to positional arguments for add_trade
                if api_client:
                    # entry_timestamp and exit_timestamp are optional and not tracked here
                    api_client.add_trade(
                        symbol,  # coin
                        side_str,  # side
                        entry_price,  # entry_price
                        exit_price,   # exit_price
                        quantity,     # quantity
                        entry_price * quantity,  # entry_notional
                        exit_price * quantity,   # exit_notional
                        holding_time, # holding_time
                        realized_pnl  # pnl
                        # entry_timestamp and exit_timestamp omitted (default None)
                    )
                    logger.info(f"  {symbol}: Completed trade logged - Duration: {holding_time}, P&L: ${realized_pnl:.2f}")
                
                # CRITICAL: Record position close to enforce cooldown (prevents spam trading)
                self.risk_manager.record_position_close(symbol, position_type)
                
        except Exception as e:
            logger.warning(f"Failed to log completed trade: {e}")

    def _emergency_close_all_for_symbol(self, symbol: str, snapshot):
        """Force-close swing and scalp positions immediately for this symbol.

        Bypasses AI/risk and directly sends close orders for any non-zero
        swing/scalp positions. Uses order executor's precision rounding.
        """
        try:
            price = get_price_from_snapshot(snapshot)
            for position_type in ['swing', 'scalp']:
                size = self.position_manager.get_position_by_type(symbol, position_type)
                if abs(size) > 0.0001:
                    logger.info(f"  {symbol}: [EMERGENCY] Closing {position_type} position size={size:.6f} @ ${price:.2f}")
                    # Capture pre-close entry for correct PnL logging
                    prev_entry = None
                    try:
                        ep_dict = self.position_manager.position_entry_prices.get(symbol, {})
                        if isinstance(ep_dict, dict):
                            prev_entry = ep_dict.get(position_type)
                    except Exception:
                        pass
                    # Execute close via underlying order executor (with emergency flag)
                    try:
                        exec_result = self.trade_executor.order_executor.execute_close(symbol, size, price, is_emergency=True)
                        if exec_result and getattr(exec_result, 'executed', False):
                            # Update tracking
                            self.position_manager.set_position_by_type(symbol, position_type, 0.0)
                            self.position_manager._clear_position_tracking(symbol, position_type)
                            logger.info(f"  {symbol}: [EMERGENCY] {position_type} close sent/cleared")
                            # Log completed trade to frontend so it appears in Completed Trades
                            try:
                                dummy_decision = type('D', (), {'action': 'close', 'position_type': position_type})
                                api_client = None
                                # Best-effort to find api_client from cycle controller
                                try:
                                    import api_server
                                    loop = getattr(api_server, 'loop_controller_instance', None)
                                    if loop and hasattr(loop, 'cycle_controller') and loop.cycle_controller:
                                        api_client = getattr(loop.cycle_controller, 'api_client', None)
                                except Exception:
                                    api_client = None
                                self._log_completed_trade(
                                    symbol,
                                    dummy_decision,
                                    snapshot,
                                    exec_result,
                                    position_type,
                                    api_client,
                                    prev_size=size,
                                    prev_entry_price=prev_entry,
                                )
                            except Exception:
                                pass
                        else:
                            logger.warning(f"  {symbol}: [EMERGENCY] {position_type} close not confirmed: {getattr(exec_result, 'error', 'unknown')}")
                    except Exception as e:
                        logger.warning(f"  {symbol}: [EMERGENCY] {position_type} close failed: {e}")
        except Exception as e:
            logger.warning(f"  {symbol}: [EMERGENCY] close handler error: {e}")
