"""Helper functions for SymbolProcessor.

All functions accept the SymbolProcessor instance as the first argument
so they can access config, managers, executors, and loggers.
"""

import logging
import time
from typing import Any, Optional

from src.utils.snapshot_utils import get_price_from_snapshot

logger = logging.getLogger(__name__)


def should_skip_llm_call(processor, symbol: str, snapshot, position_size: float, cycle_count: int) -> bool:
    try:
        now = int(time.time())
        current_price = get_price_from_snapshot(snapshot)
        rec = processor.last_llm_call.get(symbol)

        if abs(position_size) > 0.0001:
            return False

        if rec and current_price > 0 and rec.get('price'):
            delta = abs(current_price - rec['price']) / current_price
            time_since_last = now - rec.get('timestamp', 0)

            if delta < 0.0015 and time_since_last < 60:
                return True
            if delta < 0.003 and time_since_last < 90:
                return True
            if delta < 0.005 and time_since_last < 120:
                return True

        if not rec or (now - rec.get('timestamp', 0)) > 180:
            return False

        return False
    except Exception:
        return False


def get_strategy_decision(processor, symbol: str, snapshot: Any, position_size: float, equity: float,
                          cycle_count: int, strategy_type: str, current_price: float) -> Optional[Any]:
    try:
        entry_timestamp = None
        entry_price = None

        if abs(position_size) > 0.0001 and symbol in processor.position_manager.position_entry_timestamps:
            entry_timestamp_dict = processor.position_manager.position_entry_timestamps.get(symbol)
            entry_price_dict = processor.position_manager.position_entry_prices.get(symbol, {})

            if isinstance(entry_timestamp_dict, dict):
                entry_timestamp = entry_timestamp_dict.get(strategy_type)
            if isinstance(entry_price_dict, dict):
                entry_price = entry_price_dict.get(strategy_type)

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

        if strategy_type == 'swing':
            from src.strategies.atr_breakout_strategy import ATRBreakoutStrategy
            strategy = ATRBreakoutStrategy()
            decision = strategy.analyze(snapshot, position_size, equity, suppress_logs=True)
            decision.position_type = 'swing'
        elif strategy_type == 'scalp':
            from src.strategies.scalping_strategy import ScalpingStrategy
            fast_mode = False
            try:
                fast_mode = bool(getattr(processor.config, 'scalp_fast_mode', False))
            except Exception:
                fast_mode = False
            strategy = ScalpingStrategy()
            try:
                # Backward compatibility: if strategy supports fast_mode, set it
                setattr(strategy, 'fast_mode', fast_mode)
            except Exception:
                pass
            swing_pos_for_pullback = 0.0
            try:
                swing_pos_for_pullback = processor.position_manager.get_position_by_type(symbol, 'swing')
            except Exception:
                pass
            decision = strategy.analyze(
                snapshot,
                position_size,
                equity,
                suppress_logs=True,
                swing_position=swing_pos_for_pullback,
            )
            decision.position_type = 'scalp'

            if abs(swing_pos_for_pullback) > 0.0001 and decision and decision.action in ['long', 'short']:
                if (swing_pos_for_pullback > 0 and decision.action == 'long') or (
                    swing_pos_for_pullback < 0 and decision.action == 'short'
                ):
                    logger.info(
                        f"  {symbol}: Scalp blocked: same direction as open swing (swing={swing_pos_for_pullback:.6f}). Waiting for opposite pullback"
                    )
                    decision.action = 'hold'
                    decision.size_pct = 0.0
                    decision.reason = 'Blocked: same-direction as swing. Waiting for opposite pullback'
        else:
            return None

        if hasattr(processor.decision_provider, 'ai_filter'):
            try:
                if should_skip_llm_call(processor, symbol, snapshot, position_size, cycle_count):
                    logger.info(f"  {symbol}: Skipping AI filter (stable market / recent analysis)")
                    return decision
            except Exception:
                pass

            total_margin_used = 0.0
            all_symbols = []
            try:
                if hasattr(processor.config, 'symbols'):
                    all_symbols = processor.config.symbols
                else:
                    all_symbols = [symbol]
                for sym in all_symbols:
                    swing_pos = processor.position_manager.get_position_by_type(sym, 'swing')
                    scalp_pos = processor.position_manager.get_position_by_type(sym, 'scalp')
                    if abs(swing_pos) > 0.0001 or abs(scalp_pos) > 0.0001:
                        entry_dict = processor.position_manager.position_entry_prices.get(sym, {})
                        if isinstance(entry_dict, dict):
                            swing_entry = entry_dict.get('swing', snapshot.price)
                            scalp_entry = entry_dict.get('scalp', snapshot.price)
                        else:
                            swing_entry = entry_dict if entry_dict else snapshot.price
                            scalp_entry = snapshot.price
                        if abs(swing_pos) > 0.0001:
                            lev_dict = processor.position_manager.position_leverages.get(sym, {})
                            if isinstance(lev_dict, dict):
                                leverage = lev_dict.get('swing', 1.0)
                            else:
                                leverage = lev_dict if lev_dict else 1.0
                            position_notional = abs(swing_pos) * swing_entry
                            total_margin_used += position_notional / leverage if leverage > 0 else position_notional
                        if abs(scalp_pos) > 0.0001:
                            lev_dict = processor.position_manager.position_leverages.get(sym, {})
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

            logger.info(
                f"  {symbol}: Calling AI filter for {strategy_type.upper()} {decision.action.upper()} (strategy confidence: {decision.confidence:.2f})..."
            )
            approved, ai_suggested_leverage, ai_confidence = processor.decision_provider.ai_filter.filter_signal(
                snapshot, decision, position_size, equity, total_margin_used, all_symbols
            )
            try:
                processor.last_llm_call[symbol] = {
                    'price': get_price_from_snapshot(snapshot),
                    'timestamp': int(time.time()),
                    'cycle': cycle_count,
                }
            except Exception:
                pass

            if ai_confidence is not None:
                original_confidence = decision.confidence
                decision.confidence = ai_confidence
                logger.info(
                    f"  {symbol}: [AI CONFIDENCE OVERRIDE] {ai_confidence:.2f} (strategy had: {original_confidence:.2f})"
                )
            else:
                logger.warning(
                    f"  {symbol}: [WARNING] AI did not provide confidence assessment - using strategy confidence: {decision.confidence:.2f}"
                )

            try:
                if decision.action in ['long', 'short']:
                    from src.decision_filters.entry_qualifier import compute_entry_qualifier
                    direction = 'long' if decision.action == 'long' else 'short'
                    qualifier = compute_entry_qualifier(snapshot, decision.position_type, direction)
                    fused = max(0.0, min(1.0, 0.7 * decision.confidence + 0.3 * qualifier))
                    decision.confidence = fused
                    decision.reason = f"{decision.reason} | EntryQualifier={qualifier:.2f} -> FusedConf={fused:.2f}"
                    setattr(decision, 'entry_qualifier', qualifier)
                    logger.info(f"  {symbol}: PRECISION MODE -> Qualifier={qualifier:.2f}, FusedConf={fused:.2f}")
            except Exception as e:
                logger.debug(f"  {symbol}: Entry qualifier computation failed: {e}")

            if not approved and decision.action in ['long', 'short', 'close']:
                logger.info(f"  {symbol}: AI VETOED {decision.action.upper()} - converting to HOLD")
                decision.action = 'hold'
                decision.size_pct = 0.0
                if ai_confidence is None:
                    decision.confidence = 0.0
                decision.reason = f"AI vetoed setup (confidence: {decision.confidence:.2f})"
            if not approved and decision.action == 'hold' and ai_confidence is not None:
                logger.info(f"  {symbol}: AI found opportunity (conf: {ai_confidence:.2f}) but decision remains HOLD")

        return decision
    except Exception as e:
        logger.error(f"  {symbol}: Error getting {strategy_type} decision: {e}")
        return None


def execute_strategy_decision(processor, decision: Any, symbol: str, snapshot: Any, cycle_count: int,
                              equity: float, api_client: Any, strategy_type: str = None, all_snapshots: dict = None):
    try:
        logger = logging.getLogger(__name__)
        logger.info(f"  {symbol}: Step 4: Parsing decision...")

        leverage = getattr(decision, 'leverage', None)
        if leverage is None:
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

        raw_decision_parts = [
            f'"action": "{decision.action}"',
            f'"size_pct": {decision.size_pct}',
            f'"reason": "{decision.reason}"',
            f'"position_type": "{decision.position_type}"',
            f'"confidence": {getattr(decision, "confidence", 0.0):.2f}',
            f'"leverage": {int(round(leverage))}',
        ]
        if take_profit is not None:
            raw_decision_parts.append(f'"take_profit": {take_profit:.2f}')
        if stop_loss is not None:
            raw_decision_parts.append(f'"stop_loss": {stop_loss:.2f}')

        raw_decision = '{' + ', '.join(raw_decision_parts) + '}'
        parsed_decision = processor.decision_parser.parse(raw_decision)

        try:
            position_type = getattr(parsed_decision, 'position_type', 'swing')
            equity_for_budget = equity
            requested_capital = max(0.0, float(parsed_decision.size_pct) * equity_for_budget)
            capped_capital = processor.portfolio_allocator.cap_capital(position_type, requested_capital, equity_for_budget)
            if capped_capital != requested_capital:
                new_size_pct = capped_capital / equity_for_budget if equity_for_budget > 0 else 0.0
                logger.info(
                    f"  {symbol}: Portfolio/target caps -> size_pct {parsed_decision.size_pct:.3f} -> {new_size_pct:.3f} "
                    f"(req ${requested_capital:.2f} -> cap ${capped_capital:.2f})"
                )
                parsed_decision.size_pct = max(0.0, new_size_pct)
            if parsed_decision.size_pct <= 0.0:
                logger.info(f"  {symbol}: No alloc after caps, converting to HOLD")
                return
        except Exception:
            pass

        logger.info(f"  {symbol}: Step 5: Validating with risk manager...")
        # Pass SIGNED current position to risk manager so it can detect direction correctly
        current_signed_size = 0.0
        try:
            current_signed_size = processor.position_manager.get_position_by_type(symbol, decision.position_type)
        except Exception:
            current_signed_size = 0.0
        risk_approved, risk_reason = processor.risk_manager.validate_decision(
            parsed_decision, snapshot, current_signed_size, equity, symbol, processor.position_manager
        )
        if not risk_approved:
            logger.warning(f"  {symbol}: {decision.position_type.upper()} decision BLOCKED by risk manager: {risk_reason}")
            return

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

        if symbol not in processor.current_cycle_decisions:
            processor.current_cycle_decisions[symbol] = {}

        execution_result = processor.trade_executor.execute(
            parsed_decision,
            snapshot,
            processor.position_manager.get_position_by_type(symbol, decision.position_type),
            equity,
        )

        executed = execution_result.executed
        processor.current_cycle_decisions[symbol]['executed'] = executed

        if executed:
            actual_leverage = getattr(parsed_decision, 'leverage', getattr(decision, 'leverage', 1.0))
            parsed_decision.leverage = actual_leverage

            capital_amount = getattr(parsed_decision, 'capital_amount', None)
            if capital_amount is not None:
                logger.debug(f"  {symbol}: capital_amount on parsed_decision confirmed: ${capital_amount:.2f}")

            # Capture pre-close state for logging before we zero tracking
            prev_size_for_close = None
            prev_entry_for_close = None
            try:
                prev_size_for_close = processor.position_manager.get_position_by_type(symbol, parsed_decision.position_type)
                entry_dict_prev = processor.position_manager.position_entry_prices.get(symbol, {})
                if isinstance(entry_dict_prev, dict):
                    prev_entry_for_close = entry_dict_prev.get(parsed_decision.position_type)
            except Exception:
                pass

            update_position_tracking_after_trade(processor, parsed_decision, snapshot, symbol, cycle_count, execution_result)

            fill_price = getattr(execution_result, 'fill_price', snapshot.price)
            filled_size = getattr(execution_result, 'filled_size', 0.0)
            order_id = getattr(execution_result, 'order_id', 'N/A')
            leverage_used = getattr(parsed_decision, 'leverage', 1.0)

            logger.info(f"  {symbol}: [SUCCESS] {decision.position_type.upper()} {decision.action.upper()} executed")
            logger.info(f"  {symbol}:   Fill Price: ${fill_price:,.2f}, Size: {filled_size:.6f}")
            logger.info(f"  {symbol}:   Order ID: {order_id}, Leverage: {leverage_used:.1f}x")

            # NEW: Emit explicit Agent Chat message for every OPEN (long/short)
            try:
                if api_client and decision.action in ('long', 'short'):
                    side_word = 'long' if decision.action == 'long' else 'short'
                    ptype = getattr(parsed_decision, 'position_type', 'swing').upper()
                    api_client.add_agent_message(
                        f"Opened {ptype} {symbol} {side_word} at ${fill_price:,.2f} (qty {filled_size:g}). Leverage {leverage_used:.1f}x."
                    )
            except Exception:
                pass

            # Persist to AgentMemory
            try:
                from src.memory.agent_memory import get_memory
                mem = get_memory()
                ptype = getattr(parsed_decision, 'position_type', 'swing')
                side = 'long' if decision.action == 'long' else ('short' if decision.action == 'short' else 'flat')
                if decision.action in ('long', 'short'):
                    mem.record_trade(
                        symbol=symbol,
                        position_type=ptype,
                        event='open',
                        side=side,
                        price=fill_price,
                        size=filled_size or 0.0,
                        leverage=leverage_used,
                        reason=getattr(decision, 'reason', None),
                        confidence=getattr(decision, 'confidence', None),
                    )
                elif decision.action == 'close':
                    # Try to compute realized PnL if we captured previous entry
                    pnl_val = None
                    try:
                        prev_entry = prev_entry_for_close if prev_entry_for_close is not None else getattr(snapshot, 'entry_price', None)
                        if prev_entry and prev_size_for_close:
                            if prev_size_for_close > 0:
                                pnl_val = prev_size_for_close * (fill_price - prev_entry)
                            else:
                                pnl_val = abs(prev_size_for_close) * (prev_entry - fill_price)
                    except Exception:
                        pnl_val = None
                    mem.record_trade(
                        symbol=symbol,
                        position_type=ptype,
                        event='close',
                        side=side if side in ('long','short') else ('long' if (prev_size_for_close or 0) > 0 else 'short'),
                        price=fill_price,
                        size=abs(prev_size_for_close or 0.0),
                        leverage=leverage_used,
                        reason=getattr(decision, 'reason', None),
                        confidence=getattr(decision, 'confidence', None),
                        pnl=pnl_val,
                    )
            except Exception:
                pass

            if api_client and processor.ai_message_service:
                try:
                    current_position_size = processor.position_manager.get_position_by_type(symbol, parsed_decision.position_type)
                    total_margin_used = 0.0
                    try:
                        if hasattr(processor.position_manager, 'tracked_position_sizes'):
                            for sym in processor.position_manager.tracked_position_sizes:
                                positions = processor.position_manager.tracked_position_sizes.get(sym, {})
                                if isinstance(positions, dict):
                                    swing_pos = positions.get('swing', 0.0)
                                    scalp_pos = positions.get('scalp', 0.0)
                                else:
                                    swing_pos = positions if positions else 0.0
                                    scalp_pos = 0.0

                                entry_dict = processor.position_manager.position_entry_prices.get(sym, {})
                                leverage_dict = processor.position_manager.position_leverages.get(sym, {})

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

                    tracked_equity = getattr(processor.position_manager, 'tracked_equity', equity)
                    available_cash = max(0.0, tracked_equity - total_margin_used)

                    entry_price = fill_price
                    current_price = get_price_from_snapshot(snapshot)
                    if decision.action == 'long':
                        unrealized_pnl = current_position_size * (current_price - entry_price)
                    elif decision.action == 'short':
                        unrealized_pnl = abs(current_position_size) * (entry_price - current_price)
                    else:
                        unrealized_pnl = 0.0

                    if decision.action in ['long', 'short', 'close'] and executed:
                        try:
                            processor.ai_message_service.collect_cycle_decision(
                                parsed_decision, snapshot, current_position_size, equity,
                                available_cash, unrealized_pnl, cycle_count, api_client,
                                all_snapshots, realized_pnl=None if decision.action != 'close' else None,
                            )
                            logger.debug(f"  {symbol}: Agent message sent for {decision.action.upper()} action")
                        except Exception as msg_error:
                            logger.warning(f"  {symbol}: Failed to send agent message: {msg_error}")
                except Exception as e:
                    logger.warning(f"  {symbol}: Failed to send agent message: {e}")

            # Record cooldown timestamp on close regardless of frontend availability
            try:
                if parsed_decision.action == 'close':
                    processor.risk_manager.record_position_close(symbol, getattr(parsed_decision, 'position_type', 'swing'))
                    # Also persist action in memory
                    try:
                        from src.memory.agent_memory import get_memory
                        get_memory().record_action(symbol=symbol, position_type=getattr(parsed_decision, 'position_type', 'swing'), action='close')
                    except Exception:
                        pass
            except Exception:
                pass

            if api_client and decision.action == 'close':
                position_type = getattr(parsed_decision, 'position_type', 'swing')
                log_completed_trade(
                    processor,
                    symbol,
                    parsed_decision,
                    snapshot,
                    execution_result,
                    position_type,
                    api_client,
                    prev_size_for_close,
                    prev_entry_for_close,
                )

            # Record action time to support anti-churn cooldowns (especially for scalp)
            try:
                processor.risk_manager.record_action(symbol, getattr(parsed_decision, 'position_type', 'swing'))
            except Exception:
                pass

            # Auto-flip for scalp reversals: attempt immediate opposite scalp entry
            try:
                # Only attempt auto-flip if enabled via config
                if getattr(processor.config, 'scalp_autoflip_enabled', False) and getattr(parsed_decision, 'position_type', 'swing') == 'scalp' and parsed_decision.action == 'close':
                    import re
                    reason_text = str(getattr(decision, 'reason', '') or '')
                    m = re.search(r"flip_to=(long|short)", reason_text, re.IGNORECASE)
                    if m:
                        flip_to = m.group(1).lower()
                        logger.info(f"  {symbol}: Auto-flip hint detected -> {flip_to.upper()} (scalp)")
                        try:
                            current_price = get_price_from_snapshot(snapshot)
                            # After close, size should be zero; request a fresh scalp decision
                            next_decision = processor._get_strategy_decision(
                                symbol, snapshot, 0.0, equity, cycle_count, 'scalp', current_price
                            )
                            if next_decision and next_decision.action in ['long', 'short']:
                                if next_decision.action != flip_to:
                                    logger.info(f"  {symbol}: Strategy suggests {next_decision.action.upper()} (flip requested {flip_to.upper()})")
                                processor._execute_strategy_decision(
                                    next_decision, symbol, snapshot, cycle_count, equity, api_client, 'scalp', all_snapshots
                                )
                            else:
                                logger.info(f"  {symbol}: Flip requested but no valid scalp entry found this cycle")
                        except Exception as _e:
                            logger.warning(f"  {symbol}: Auto-flip execution failed: {_e}")
            except Exception:
                pass
        else:
            logger.warning(f"  {symbol}: [FAILED] {decision.position_type.upper()} {decision.action.upper()} not executed")
    except Exception as e:
        logger.error(f"  {symbol}: Error executing {strategy_type} decision: {e}")


def update_position_tracking_after_trade(processor, decision, snapshot, symbol: str, cycle_count: int, execution_result=None):
    return processor._update_position_tracking_after_trade(decision, snapshot, symbol, cycle_count, execution_result)


def log_completed_trade(processor, symbol: str, decision, snapshot, execution_result, position_type: str, api_client,
                        prev_size: float = None, prev_entry_price: float = None):
    return processor._log_completed_trade(symbol, decision, snapshot, execution_result, position_type, api_client, prev_size, prev_entry_price)


def emergency_close_all_for_symbol(processor, symbol: str, snapshot):
    return processor._emergency_close_all_for_symbol(symbol, snapshot)


