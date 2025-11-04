"""Symbol processing controller for individual trading symbols."""

import logging
import os
import time

from src.utils.snapshot_utils import get_price_from_snapshot

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
            emergency_flag = os.path.join(os.path.dirname(os.path.dirname(__file__)), "emergency_close.flag")
            if os.path.exists(emergency_flag):
                logger.warning(f"[WARNING] {symbol}: EMERGENCY CLOSE TRIGGERED!")
                if position_size != 0:
                    logger.info(f"  {symbol}: Forcing immediate position close...")
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

            # COST OPTIMIZATION: Skip LLM call if market hasn't changed significantly
            should_skip_llm = self._should_skip_llm_call(symbol, snapshot, position_size, cycle_count)

            if should_skip_llm:
                # Use cached "hold" decision from last call
                logger.info(f"  {symbol}: Step 3: Skipping LLM call - market unchanged")
                raw_llm_output = '{"action": "hold", "size_pct": 0.0, "reason": "Market unchanged - waiting for significant movement"}'
            else:
                logger.info(f"  {symbol}: Step 3: Getting decision from LLM...")
                try:
                    raw_llm_output = self.decision_provider.get_decision(
                        snapshot, position_size, equity
                    )
                    # Log full raw LLM output (AI reasoning is in the "reason" field)
                    logger.info(f"  {symbol}:   Raw LLM output: {raw_llm_output}")

                    # Check if agent is paused after LLM call
                    if os.path.exists(pause_flag):
                        logger.info(f"  {symbol}: Agent paused - halting after decision provider")
                        return

                    # Track this LLM call for future cost optimization
                    from src.utils.snapshot_utils import get_base_snapshot
                    snapshot_for_tracking = get_base_snapshot(snapshot)
                    self.last_llm_call[symbol] = {
                        'price': get_price_from_snapshot(snapshot),
                        'cycle': cycle_count,
                        'timestamp': snapshot_for_tracking.timestamp,
                        'volume_1h': snapshot_for_tracking.indicators.get('volume_ratio_1h', 1.0),
                        'volume_5m': snapshot_for_tracking.indicators.get('volume_ratio_5m', 1.0)
                    }

                    if position_size == 0:
                        # Log decision for new entry evaluation (only at DEBUG for cleaner output)
                        temp_parsed = self.decision_parser.parse(raw_llm_output)
                        temp_confidence = getattr(temp_parsed, 'confidence', 0.0)
                        logger.debug(f"  {symbol}: {temp_parsed.action} (confidence: {temp_confidence:.2f})")
                except Exception as e:
                    logger.error(f"  {symbol}: Decision provider failed: {e}")
                    raw_llm_output = f"Error: {str(e)}"

        # ====================================================================
        # STEP 4: Parse decision
        # ====================================================================
        logger.info(f"  {symbol}: Step 4: Parsing decision...")
        decision = self.decision_parser.parse(raw_llm_output)
        logger.info(f"  {symbol}:   Action: {decision.action}, Size: {decision.size_pct*100:.1f}%, Confidence: {getattr(decision, 'confidence', 0.0):.2f}")
        logger.info(f"  {symbol}:   AI Reasoning: {decision.reason}")

        # ====================================================================
        # STEP 5: Validate with risk manager
        # ====================================================================
        # Store decision for cycle status messages
        self.current_cycle_decisions[symbol] = {
            'decision': decision,
            'snapshot': snapshot,
            'position_size': position_size,
            'executed': False,
            'risk_approved': False,
            'risk_reason': None
        }

        # Get the actual position size for this decision type (important for risk validation)
        decision_position_size = position_size
        if hasattr(decision, 'position_type') and decision.position_type:
            decision_position_size = self.position_manager.get_position_by_type(symbol, decision.position_type)
        else:
            # Backward compatibility: if no position_type, use total
            decision_position_size = position_size

        # Validate with risk manager
        logger.info(f"  {symbol}: Step 5: Validating with risk manager...")
        risk_approved, risk_reason = self.risk_manager.validate_decision(
            decision, snapshot, decision_position_size, equity, symbol
        )
        logger.info(f"  {symbol}:   Approved: {risk_approved}" + (f" ({risk_reason})" if risk_reason else ""))

        self.current_cycle_decisions[symbol]['risk_approved'] = risk_approved
        self.current_cycle_decisions[symbol]['risk_reason'] = risk_reason

        if not risk_approved:
            logger.info(f"  {symbol}: Risk check FAILED - {risk_reason}")
            logger.info(f"  {symbol}: Decision blocked: {decision.action} -> hold")
            decision.action = "hold"
            decision.size_pct = 0.0
            decision.reason = f"Risk check failed: {risk_reason}"

        # ====================================================================
        # STEP 6: Execute trade if approved
        # ====================================================================
        logger.info(f"  {symbol}: Step 6: Executing trade...")
        if decision.action == "hold":
            logger.info(f"  {symbol}:   Action is 'hold', no execution needed")
            logger.info(f"  {symbol}:   Executed: False")
        elif decision.action in ["long", "short", "close"]:
            logger.info(f"  {symbol}:   Executing {decision.action.upper()}")

            execution_result = None  # Store for JSON logging
            try:
                execution_result = self.trade_executor.execute(decision, snapshot, decision_position_size, equity)
                executed = execution_result.executed
                self.current_cycle_decisions[symbol]['executed'] = executed
                self.current_cycle_decisions[symbol]['execution_result'] = execution_result  # Store for JSON logging

                if executed:
                    # Update position tracking after successful execution
                    self._update_position_tracking_after_trade(decision, snapshot, symbol, cycle_count)

                    logger.info(f"  {symbol}:   Executed: True")
                    logger.info(f"  {symbol}:   ✓ Trade executed successfully")

                    # Log trade to frontend
                    if api_client and hasattr(api_client, 'log_trade'):
                        try:
                            api_client.log_trade({
                                'symbol': symbol,
                                'action': decision.action,
                                'size_pct': decision.size_pct,
                                'reason': decision.reason,
                                'price': get_price_from_snapshot(snapshot),
                                'timestamp': int(time.time()),
                                'position_type': getattr(decision, 'position_type', 'swing')
                            })
                        except Exception as e:
                            logger.debug(f"Failed to log trade to frontend: {e}")
                else:
                    logger.info(f"  {symbol}:   Executed: False")
                    logger.warning(f"  {symbol}:   ✗ Trade execution failed")

            except Exception as e:
                logger.error(f"  {symbol}: Trade execution error: {e}")
                self.current_cycle_decisions[symbol]['executed'] = False
                execution_result = None

        # ====================================================================
        # STEP 7: Send AI message about decision
        # ====================================================================
        logger.info(f"  {symbol}: Step 7: Sending AI message...")
        if api_client and hasattr(decision, 'action'):
            try:
                available_cash = equity  # Simplified - would need proper calculation
                unrealized_pnl = 0.0  # Simplified - would need proper calculation

                self.ai_message_service.send_smart_agent_message(
                    decision, snapshot, position_size, equity,
                    available_cash, unrealized_pnl, cycle_count,
                    api_client, all_snapshots
                )
            except Exception as e:
                logger.debug(f"Failed to send AI message: {e}")

        # ====================================================================
        # STEP 8: Log cycle data to JSON for AI memory and audit trail
        # ====================================================================
        logger.debug(f"  {symbol}: Step 8: Logging cycle data to JSON...")
        try:
            from src.models import CycleLog
            import time

            # Get execution result for detailed logging
            execution_result = self.current_cycle_decisions.get(symbol, {}).get('execution_result')

            # Create comprehensive cycle log
            cycle_log = CycleLog(
                timestamp=int(time.time()),
                symbol=symbol,
                market_price=get_price_from_snapshot(snapshot),
                position_before=position_size,
                llm_raw_output=raw_llm_output if 'raw_llm_output' in locals() else '',
                parsed_action=decision.action if decision else '',
                parsed_size_pct=getattr(decision, 'size_pct', 0.0) if decision else 0.0,
                parsed_reason=getattr(decision, 'reason', '') if decision else '',
                risk_approved=self.current_cycle_decisions.get(symbol, {}).get('risk_approved', False),
                risk_reason=self.current_cycle_decisions.get(symbol, {}).get('risk_reason', ''),
                executed=self.current_cycle_decisions.get(symbol, {}).get('executed', False),
                order_id=execution_result.order_id if execution_result else None,
                filled_size=execution_result.filled_size if execution_result else None,
                fill_price=execution_result.fill_price if execution_result else None,
                mode=self.config.run_mode  # Use actual run mode from config
            )

            # Log to JSON file for AI memory and audit trail
            if hasattr(self, 'logger') and self.logger:
                logger.debug(f"  {symbol}:   Logger available, calling log_cycle...")
                self.logger.log_cycle(cycle_log)
                logger.debug(f"  {symbol}:   JSON logging completed")
            else:
                logger.warning(f"  {symbol}:   Logger not available for JSON logging")

        except Exception as e:
            logger.warning(f"Failed to log cycle data to JSON: {e}")

    def _should_skip_llm_call(self, symbol: str, snapshot, position_size: float, cycle_count: int) -> bool:
        """Check if LLM call should be skipped for cost optimization."""
        # Implementation would go here - simplified for refactoring
        return False

    def _update_position_tracking_after_trade(self, decision, snapshot, symbol: str, cycle_count: int):
        """Update position tracking after a successful trade."""
        try:
            position_type = getattr(decision, 'position_type', 'swing')  # Default to swing if not specified
            entry_price = get_price_from_snapshot(snapshot)
            entry_timestamp = int(time.time())

            # Update position tracking based on action type
            if decision.action == "long":
                # For long trades, add to position size
                current_size = self.position_manager.get_position_by_type(symbol, position_type)
                new_size = current_size + decision.size_pct  # decision.size_pct is already the quantity
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

            elif decision.action == "short":
                # For short trades, subtract from position size (negative size)
                current_size = self.position_manager.get_position_by_type(symbol, position_type)
                new_size = current_size - decision.size_pct  # decision.size_pct is already the quantity
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

            elif decision.action == "close":
                # For close trades, set position to zero
                self.position_manager.set_position_by_type(symbol, position_type, 0.0)
                # Clear entry tracking, SL/TP, confidence, and trailing stop data
                self.position_manager._clear_position_tracking(symbol, position_type)

            logger.info(f"  {symbol}: Position updated - {position_type} position: {self.position_manager.get_position_by_type(symbol, position_type):.6f}")

        except Exception as e:
            logger.error(f"  {symbol}: Failed to update position tracking: {e}")
