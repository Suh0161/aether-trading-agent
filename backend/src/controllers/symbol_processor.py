"""Symbol processing controller for individual trading symbols."""

import logging
import os
import time
from datetime import datetime
from typing import Any, Optional

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
        """
        Get decision for a specific strategy type (swing or scalp).
        """
        try:
            # Inject position-specific data for the strategy
            entry_timestamp = None
            entry_price = None

            if abs(position_size) > 0.0001 and symbol in self.position_manager.position_entry_timestamps:
                entry_timestamp_dict = self.position_manager.position_entry_timestamps.get(symbol)
                entry_price_dict = self.position_manager.position_entry_prices.get(symbol, {})

                if isinstance(entry_timestamp_dict, dict):
                    entry_timestamp = entry_timestamp_dict.get(strategy_type)
                if isinstance(entry_price_dict, dict):
                    entry_price = entry_price_dict.get(strategy_type)

            # Inject into snapshot
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

            # Get decision based on strategy type
            if strategy_type == 'swing':
                # For swing, use ATR strategy directly
                from src.strategies.atr_breakout_strategy import ATRBreakoutStrategy
                strategy = ATRBreakoutStrategy()
                decision = strategy.analyze(snapshot, position_size, equity, suppress_logs=True)
                decision.position_type = 'swing'
            elif strategy_type == 'scalp':
                # For scalp, use scalping strategy directly
                from src.strategies.scalping_strategy import ScalpingStrategy
                strategy = ScalpingStrategy()
                decision = strategy.analyze(snapshot, position_size, equity, suppress_logs=True)
                decision.position_type = 'scalp'
            else:
                return None

            # Apply AI filter if using HybridDecisionProvider (has AI filter for confidence assessment)
            if hasattr(self.decision_provider, 'ai_filter'):
                # Optional: skip AI call if market is stable to meet cycle budget
                try:
                    if self._should_skip_llm_call(symbol, snapshot, position_size, cycle_count):
                        logger.info(f"  {symbol}: Skipping AI filter (stable market / recent analysis)")
                        return decision
                except Exception:
                    pass
                # Calculate total margin used for capital awareness
                total_margin_used = 0.0
                all_symbols = []
                try:
                    if hasattr(self.config, 'symbols'):
                        all_symbols = self.config.symbols
                    else:
                        all_symbols = [symbol]
                    
                    # Calculate total margin used across all positions
                    for sym in all_symbols:
                        swing_pos = self.position_manager.get_position_by_type(sym, 'swing')
                        scalp_pos = self.position_manager.get_position_by_type(sym, 'scalp')
                        if abs(swing_pos) > 0.0001 or abs(scalp_pos) > 0.0001:
                            entry_dict = self.position_manager.position_entry_prices.get(sym, {})
                            if isinstance(entry_dict, dict):
                                swing_entry = entry_dict.get('swing', snapshot.price)
                                scalp_entry = entry_dict.get('scalp', snapshot.price)
                            else:
                                swing_entry = entry_dict if entry_dict else snapshot.price
                                scalp_entry = snapshot.price
                            
                            if abs(swing_pos) > 0.0001:
                                lev_dict = self.position_manager.position_leverages.get(sym, {})
                                if isinstance(lev_dict, dict):
                                    leverage = lev_dict.get('swing', 1.0)
                                else:
                                    leverage = lev_dict if lev_dict else 1.0
                                position_notional = abs(swing_pos) * swing_entry
                                total_margin_used += position_notional / leverage if leverage > 0 else position_notional
                            
                            if abs(scalp_pos) > 0.0001:
                                lev_dict = self.position_manager.position_leverages.get(sym, {})
                                if isinstance(lev_dict, dict):
                                    leverage = lev_dict.get('scalp', 1.0)
                                else:
                                    leverage = 1.0
                                position_notional = abs(scalp_pos) * scalp_entry
                                total_margin_used += position_notional / leverage if leverage > 0 else position_notional
                except Exception as e:
                    logger.debug(f"Could not calculate total margin: {e}")
                    all_symbols = [symbol]
                    total_margin_used = abs(position_size) * snapshot.price if position_size != 0 else 0.0
                
                # Apply AI filter (from HybridDecisionProvider) - AI assesses confidence dynamically!
                logger.info(f"  {symbol}: Calling AI filter for {strategy_type.upper()} {decision.action.upper()} (strategy confidence: {decision.confidence:.2f})...")
                approved, ai_suggested_leverage, ai_confidence = self.decision_provider.ai_filter.filter_signal(
                    snapshot, decision, position_size, equity, total_margin_used, all_symbols
                )
                # Record last LLM call snapshot for budget control
                try:
                    self.last_llm_call[symbol] = {
                        'price': get_price_from_snapshot(snapshot),
                        'timestamp': int(time.time()),
                        'cycle': cycle_count
                    }
                except Exception:
                    pass
                
                logger.debug(f"  {symbol}: AI filter returned: approved={approved}, leverage={ai_suggested_leverage}, confidence={ai_confidence}")
                
                # Use AI confidence if provided (AI overrides hardcoded strategy confidence)
                # IMPORTANT: Apply confidence BEFORE checking veto status
                if ai_confidence is not None:
                    original_confidence = decision.confidence
                    decision.confidence = ai_confidence
                    logger.info(f"  {symbol}: [AI CONFIDENCE OVERRIDE] {ai_confidence:.2f} (strategy had: {original_confidence:.2f})")
                else:
                    logger.warning(f"  {symbol}: [WARNING] AI did not provide confidence assessment - using strategy confidence: {decision.confidence:.2f}")

                # Precision Mode: compute objective entry qualifier and fuse with confidence
                try:
                    if decision.action in ["long", "short"]:
                        from src.decision_filters.entry_qualifier import compute_entry_qualifier
                        direction = "long" if decision.action == "long" else "short"
                        qualifier = compute_entry_qualifier(snapshot, decision.position_type, direction)
                        fused = max(0.0, min(1.0, 0.7 * decision.confidence + 0.3 * qualifier))
                        decision.confidence = fused
                        decision.reason = f"{decision.reason} | EntryQualifier={qualifier:.2f} -> FusedConf={fused:.2f}"
                        # Attach for downstream risk checks (optional)
                        setattr(decision, 'entry_qualifier', qualifier)
                        logger.info(f"  {symbol}: PRECISION MODE -> Qualifier={qualifier:.2f}, FusedConf={fused:.2f}")
                except Exception as e:
                    logger.debug(f"  {symbol}: Entry qualifier computation failed: {e}")
                
                # If AI vetoed and it's a trade decision, convert to hold (but keep AI confidence if provided)
                if not approved and decision.action in ["long", "short", "close"]:
                    logger.info(f"  {symbol}: AI VETOED {decision.action.upper()} - converting to HOLD")
                    decision.action = "hold"
                    decision.size_pct = 0.0
                    # Keep AI confidence if provided, otherwise set to 0.0
                    if ai_confidence is None:
                        decision.confidence = 0.0
                    decision.reason = f"AI vetoed setup (confidence: {decision.confidence:.2f})"
                
                # For HOLD decisions that AI vetoed: AI found opportunity, keep confidence but stay HOLD for now
                # (Future: Could convert to trade if AI approves with high confidence)
                if not approved and decision.action == "hold" and ai_confidence is not None:
                    logger.info(f"  {symbol}: AI found opportunity (conf: {ai_confidence:.2f}) but decision remains HOLD")

            return decision

        except Exception as e:
            logger.error(f"  {symbol}: Error getting {strategy_type} decision: {e}")
            return None

    def _execute_strategy_decision(self, decision: Any, symbol: str, snapshot: Any, cycle_count: int,
                                   equity: float, api_client: Any, strategy_type: str = None, all_snapshots: dict = None):
        """
        Execute a strategy decision (long/short/close).
        """
        try:
            # Parse decision to get proper format
            logger.info(f"  {symbol}: Step 4: Parsing decision...")
            # Include leverage, take_profit, and stop_loss in the JSON string so they're preserved
            # CRITICAL: Get leverage from decision - check multiple possible attributes
            leverage = getattr(decision, 'leverage', None)
            if leverage is None:
                # Try to extract from reason string as fallback (format: "Leverage: 2.4x")
                import re
                leverage_match = re.search(r'Leverage:\s*([\d.]+)\s*x', decision.reason)
                if leverage_match:
                    leverage = float(leverage_match.group(1))
                    logger.debug(f"  {symbol}: Extracted leverage {leverage:.1f}x from reason string")
                else:
                    leverage = 1.0
                    logger.warning(f"  {symbol}: No leverage found in decision, defaulting to 1.0x")
            else:
                logger.debug(f"  {symbol}: Using leverage {leverage:.1f}x from decision object")
            
            take_profit = getattr(decision, 'take_profit', None)
            stop_loss = getattr(decision, 'stop_loss', None)
            
            # Build JSON string with all fields
            raw_decision_parts = [
                f'"action": "{decision.action}"',
                f'"size_pct": {decision.size_pct}',
                f'"reason": "{decision.reason}"',
                f'"position_type": "{decision.position_type}"',
                f'"confidence": {getattr(decision, "confidence", 0.0):.2f}',
                f'"leverage": {int(round(leverage))}'
            ]
            
            # Add TP/SL if they exist
            if take_profit is not None:
                raw_decision_parts.append(f'"take_profit": {take_profit:.2f}')
            if stop_loss is not None:
                raw_decision_parts.append(f'"stop_loss": {stop_loss:.2f}')
            
            raw_decision = '{' + ', '.join(raw_decision_parts) + '}'
            parsed_decision = self.decision_parser.parse(raw_decision)

            # Step 5: Validating with risk manager
            logger.info(f"  {symbol}: Step 5: Validating with risk manager...")
            risk_approved, risk_reason = self.risk_manager.validate_decision(
                parsed_decision, snapshot, abs(self.position_manager.get_position_by_type(symbol, decision.position_type)), equity, symbol, self.position_manager
            )

            if not risk_approved:
                logger.warning(f"  {symbol}: {decision.position_type.upper()} decision BLOCKED by risk manager: {risk_reason}")
                return

            # Step 6: Executing trade
            logger.info(f"  {symbol}: Step 6: Executing trade...")
            confidence = getattr(decision, 'confidence', 0.0)
            confidence_str = f"{confidence:.2f}" if isinstance(confidence, (int, float)) else str(confidence)
            reason = getattr(decision, 'reason', 'N/A')
            logger.info(f"  {symbol}: ========================================")
            logger.info(f"  {symbol}: SYMBOL: {symbol}")
            logger.info(f"  {symbol}: STRATEGY: {decision.position_type.upper()}")
            logger.info(f"  {symbol}: ACTION: {decision.action.upper()}")
            logger.info(f"  {symbol}: CONFIDENCE: {confidence_str}")
            logger.info(f"  {symbol}: PRICE: ${snapshot.price:,.2f}")
            logger.info(f"  {symbol}: AI REASONING: {reason}")
            logger.info(f"  {symbol}: ========================================")

            # Ensure per-symbol decision record exists for this cycle before execution
            if symbol not in self.current_cycle_decisions:
                self.current_cycle_decisions[symbol] = {}

            execution_result = self.trade_executor.execute(parsed_decision, snapshot,
                                                         self.position_manager.get_position_by_type(symbol, decision.position_type),
                                                         equity)

            executed = execution_result.executed
            self.current_cycle_decisions[symbol]['executed'] = executed

            if executed:
                    # Update parsed_decision with actual leverage used (may have been adjusted by order_sizer)
                    # This ensures leverage stored in position tracking matches what was actually used
                    actual_leverage = getattr(parsed_decision, 'leverage', getattr(decision, 'leverage', 1.0))
                    parsed_decision.leverage = actual_leverage
                    
                    # Update position tracking
                    self._update_position_tracking_after_trade(parsed_decision, snapshot, symbol, cycle_count, execution_result)

                    # Log success with detailed information
                    fill_price = getattr(execution_result, 'fill_price', snapshot.price)
                    filled_size = getattr(execution_result, 'filled_size', 0.0)
                    order_id = getattr(execution_result, 'order_id', 'N/A')
                    leverage_used = getattr(parsed_decision, 'leverage', 1.0)

                    logger.info(f"  {symbol}: [SUCCESS] {decision.position_type.upper()} {decision.action.upper()} executed")
                    logger.info(f"  {symbol}:   Fill Price: ${fill_price:,.2f}, Size: {filled_size:.6f}")
                    logger.info(f"  {symbol}:   Order ID: {order_id}, Leverage: {leverage_used:.1f}x")

                    # Send agent message to frontend when positions are opened (long/short) or closed
                    if api_client and self.ai_message_service:
                        try:
                            # Calculate available cash and unrealized P&L for messaging
                            # Get current position size after update
                            current_position_size = self.position_manager.get_position_by_type(symbol, parsed_decision.position_type)
                        
                            # Calculate total margin used across all positions
                            total_margin_used = 0.0
                            try:
                                if hasattr(self.position_manager, 'tracked_position_sizes'):
                                    for sym in self.position_manager.tracked_position_sizes:
                                        positions = self.position_manager.tracked_position_sizes.get(sym, {})
                                        if isinstance(positions, dict):
                                            swing_pos = positions.get('swing', 0.0)
                                            scalp_pos = positions.get('scalp', 0.0)
                                        else:
                                            swing_pos = positions if positions else 0.0
                                            scalp_pos = 0.0
                                        
                                        entry_dict = self.position_manager.position_entry_prices.get(sym, {})
                                        leverage_dict = self.position_manager.position_leverages.get(sym, {})
                                        
                                        if abs(swing_pos) > 0.0001:
                                            if isinstance(entry_dict, dict):
                                                swing_entry = entry_dict.get('swing', fill_price)
                                            else:
                                                swing_entry = entry_dict if entry_dict else fill_price
                                            if isinstance(leverage_dict, dict):
                                                lev = leverage_dict.get('swing', 1.0)
                                            else:
                                                lev = leverage_dict if leverage_dict else 1.0
                                            swing_notional = abs(swing_pos) * swing_entry
                                            total_margin_used += swing_notional / lev if lev > 0 else swing_notional
                                        
                                        if abs(scalp_pos) > 0.0001:
                                            if isinstance(entry_dict, dict):
                                                scalp_entry = entry_dict.get('scalp', fill_price)
                                            else:
                                                scalp_entry = fill_price
                                            if isinstance(leverage_dict, dict):
                                                lev = leverage_dict.get('scalp', 1.0)
                                            else:
                                                lev = 1.0
                                            scalp_notional = abs(scalp_pos) * scalp_entry
                                            total_margin_used += scalp_notional / lev if lev > 0 else scalp_notional
                            except Exception:
                                total_margin_used = 0.0
                            
                            tracked_equity = getattr(self.position_manager, 'tracked_equity', equity)
                            available_cash = max(0.0, tracked_equity - total_margin_used)
                            
                            # Calculate unrealized P&L for this position
                            entry_price = fill_price  # Use fill price as entry
                            current_price = get_price_from_snapshot(snapshot)
                            if decision.action == "long":
                                unrealized_pnl = current_position_size * (current_price - entry_price)
                            elif decision.action == "short":
                                unrealized_pnl = abs(current_position_size) * (entry_price - current_price)
                            else:
                                unrealized_pnl = 0.0
                            
                            # Send agent message ONLY for successfully executed trades (long/short/close)
                            # Skip messages for failed executions to prevent spam
                            if decision.action in ["long", "short", "close"] and executed:
                                try:
                                    self.ai_message_service.collect_cycle_decision(
                                        parsed_decision, snapshot, current_position_size, equity,
                                        available_cash, unrealized_pnl, cycle_count, api_client,
                                        all_snapshots, realized_pnl=None if decision.action != "close" else None
                                    )
                                    logger.debug(f"  {symbol}: Agent message sent for {decision.action.upper()} action")
                                except Exception as msg_error:
                                    logger.warning(f"  {symbol}: Failed to send agent message: {msg_error}")
                        except Exception as e:
                            logger.warning(f"  {symbol}: Failed to send agent message: {e}")

                    # Send completed trade to frontend (for close actions only)
                    if api_client and decision.action == "close":
                        position_type = getattr(parsed_decision, 'position_type', 'swing')
                        self._log_completed_trade(symbol, parsed_decision, snapshot, execution_result, position_type, api_client)
            else:
                logger.warning(f"  {symbol}: [FAILED] {decision.position_type.upper()} {decision.action.upper()} not executed")

        except Exception as e:
            logger.error(f"  {symbol}: Error executing {strategy_type} decision: {e}")

    def _should_skip_llm_call(self, symbol: str, snapshot, position_size: float, cycle_count: int) -> bool:
        """Check if LLM call should be skipped to reduce cycle time and cost.

        Skip when:
        - Price change vs last AI call < 0.2%
        - And last AI call was < 45s ago
        """
        try:
            now = int(time.time())
            current_price = get_price_from_snapshot(snapshot)
            rec = self.last_llm_call.get(symbol)
            if rec and current_price > 0 and rec.get('price'):
                delta = abs(current_price - rec['price']) / current_price
                recent = (now - rec.get('timestamp', 0)) < 45
                if delta < 0.002 and recent:
                    return True
            # Update record only when we truly call AI (handled at call site)
            return False
        except Exception:
            return False

    def _update_position_tracking_after_trade(self, decision, snapshot, symbol: str, cycle_count: int, execution_result=None):
        """Update position tracking after a successful trade."""
        try:
            position_type = getattr(decision, 'position_type', 'swing')  # Default to swing if not specified
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
                    equity = getattr(self.position_manager, 'tracked_equity', 100.0)
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

            elif decision.action == "short":
                # For short trades, subtract from position size (negative size)
                # CRITICAL: Use filled_size from execution_result, not decision.size_pct!
                # decision.size_pct is a PERCENTAGE (0.25 = 25%), not a quantity!
                filled_size = getattr(execution_result, 'filled_size', 0.0) if execution_result else 0.0
                if filled_size == 0.0:
                    # Fallback: calculate from size_pct if execution_result is missing
                    # This should never happen, but handle gracefully
                    equity = getattr(self.position_manager, 'tracked_equity', 100.0)
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

            elif decision.action == "close":
                # For close trades, set position to zero
                self.position_manager.set_position_by_type(symbol, position_type, 0.0)
                # Clear entry tracking, SL/TP, confidence, and trailing stop data
                self.position_manager._clear_position_tracking(symbol, position_type)

            logger.info(f"  {symbol}: Position updated - {position_type} position: {self.position_manager.get_position_by_type(symbol, position_type):.6f}")

        except Exception as e:
            logger.error(f"  {symbol}: Failed to update position tracking: {e}")

    def _log_completed_trade(self, symbol: str, decision, snapshot, execution_result, position_type: str, api_client):
        """Log completed trades to frontend."""
        try:
            # Calculate PnL for the trade
            entry_price = getattr(execution_result, 'entry_price', get_price_from_snapshot(snapshot))
            exit_price = getattr(execution_result, 'fill_price', get_price_from_snapshot(snapshot))
            quantity = getattr(execution_result, 'filled_size', abs(decision.size_pct))
            
            if decision.action == "close":
                # Calculate realized PnL
                if position_type == "long":
                    realized_pnl = (exit_price - entry_price) * quantity
                else:  # short
                    realized_pnl = (entry_price - exit_price) * quantity
                
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
                trade_data = {
                    "symbol": symbol,
                    "position_type": position_type,
                    "action": decision.action,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "quantity": quantity,
                    "pnl": realized_pnl,
                    "holding_time": holding_time,
                    "timestamp": datetime.now().isoformat()
                }
                
                if api_client:
                    api_client.add_trade(trade_data)
                    logger.debug(f"  {symbol}: Completed trade logged to frontend")
                
        except Exception as e:
            logger.warning(f"Failed to log completed trade: {e}")
