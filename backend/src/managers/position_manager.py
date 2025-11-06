"""Position management for trading agent."""

import logging
from typing import Dict, Optional

from src.utils.snapshot_utils import get_price_from_snapshot

logger = logging.getLogger(__name__)


class PositionManager:
    """Manages position tracking, entry prices, stop losses, and take profits."""

    def __init__(self, config):
        """
        Initialize position manager.

        Args:
            config: Configuration object with mock_starting_equity
        """
        # Track entry prices and timestamps for P&L calculation and trade logging
        # NEW: Track per position type (swing and scalp can coexist)
        self.position_entry_prices = {}  # {symbol: {'swing': price, 'scalp': price}}
        self.position_entry_timestamps = {}  # {symbol: {'swing': timestamp, 'scalp': timestamp}} - Unix timestamp in seconds

        # Track position sizes internally (for demo mode when exchange doesn't support position queries)
        # NEW: Track swing and scalp positions separately - can coexist!
        self.tracked_position_sizes = {}  # {symbol: {'swing': size, 'scalp': size}} - positive for long, negative for short

        # Retain config and sync/logging knobs
        self.config = config
        # Demo/exchange sync behavior
        self.disable_sync_in_demo = getattr(config, 'disable_position_sync_in_demo', True)
        self.sync_grace_seconds = getattr(config, 'sync_grace_seconds', 900)
        self.sync_confirm_misses = getattr(config, 'sync_confirm_misses', 3)
        self.completed_trades_min_abs_pnl = getattr(config, 'completed_trades_min_abs_pnl', 0.0)

        # Track equity dynamically for demo mode (starts at mock equity from config, updates with realized P&L)
        self.tracked_equity = config.mock_starting_equity  # Starting equity for demo mode (will update with realized P&L)
        self.starting_equity = config.mock_starting_equity  # Track starting equity for daily reset
        self.current_equity = config.mock_starting_equity  # Current equity (tracked_equity + unrealized P&L, or real equity from exchange)

        # Track stop loss and take profit for automatic monitoring
        self.position_stop_losses = {}  # {symbol: {'swing': sl, 'scalp': sl}}
        self.position_take_profits = {}  # {symbol: {'swing': tp, 'scalp': tp}}

        # Track leverage and risk/reward for position monitoring
        self.position_leverages = {}  # {symbol: {'swing': leverage, 'scalp': leverage}}
        self.position_risk_amounts = {}  # {symbol: {'swing': risk, 'scalp': risk}}
        self.position_reward_amounts = {}  # {symbol: {'swing': reward, 'scalp': reward}}
        
        # Track actual capital used for margin calculation (critical for smart money management)
        # This is the actual capital allocated, not the inflated notional value
        self.position_capital_used = {}  # {symbol: {'swing': capital, 'scalp': capital}}

        # Track highest/lowest price for trailing stop (swing trades only)
        self.position_highest_prices = {}  # {symbol: {'swing': highest}} for LONG positions
        self.position_lowest_prices = {}  # {symbol: {'swing': lowest}} for SHORT positions
        self.position_initial_sl = {}  # {symbol: {'swing': initial_sl}} to calculate R multiples

        # Track confidence when position was opened (for adaptive trailing stop)
        self.position_confidence = {}  # {symbol: {'swing': confidence, 'scalp': confidence}}

        # Track AI-suggested trailing stop percentage (if AI adjusted it)
        self.position_trailing_stop_pct = {}  # {symbol: {'swing': trailing_pct}}

        # Track last scalp close time per symbol to prevent immediate re-entry (cooldown)
        self.last_scalp_close_time = {}  # {symbol: timestamp} - Unix timestamp in seconds
        
        # Track last sync time to avoid syncing too frequently
        self.last_position_sync_time = 0
        # Anti-duplicate emission tracker for externally closed trades
        self._last_emitted_close = {}  # key=(symbol, position_type) -> timestamp
        # Debounce clearing: require consecutive exchange 'no position' reports
        self._no_position_miss_count = {}  # key=(symbol, position_type) -> count

    def get_position_by_type(self, symbol: str, position_type: str) -> float:
        """Helper to get position size by type (swing or scalp). Returns 0 if not found."""
        positions = self.tracked_position_sizes.get(symbol, {})
        if isinstance(positions, dict):
            return positions.get(position_type, 0.0)
        # Backward compatibility: if old format (single value), treat as swing
        return positions if position_type == 'swing' else 0.0

    def set_position_by_type(self, symbol: str, position_type: str, size: float):
        """Helper to set position size by type."""
        if symbol not in self.tracked_position_sizes:
            self.tracked_position_sizes[symbol] = {}
        if not isinstance(self.tracked_position_sizes[symbol], dict):
            # Convert old format to new format
            old_size = self.tracked_position_sizes[symbol]
            self.tracked_position_sizes[symbol] = {'swing': old_size, 'scalp': 0.0}
        self.tracked_position_sizes[symbol][position_type] = size
        # Clean up if both are zero
        if self.tracked_position_sizes[symbol].get('swing', 0.0) == 0.0 and self.tracked_position_sizes[symbol].get('scalp', 0.0) == 0.0:
            self.tracked_position_sizes[symbol] = {}

    def get_total_position(self, symbol: str) -> float:
        """Get total position size (swing + scalp) for backward compatibility."""
        positions = self.tracked_position_sizes.get(symbol, {})
        if isinstance(positions, dict):
            return positions.get('swing', 0.0) + positions.get('scalp', 0.0)
        return positions  # Old format

    def update_trailing_stops(self, symbol: str, position_type: str, position_size: float, current_price: float):
        """
        Update trailing stops based on price movement.

        For swing trades only, implements 10-15% trailing based on confidence.
        Higher confidence = tighter trailing (10%), lower confidence = looser (15%).

        Args:
            symbol: Trading symbol
            position_type: 'swing' or 'scalp' (only swing gets trailing)
            position_size: Position size (positive for long, negative for short)
            current_price: Current market price
        """
        # Only implement trailing stops for swing trades
        if position_type != 'swing':
            return

        # Get confidence for this position
        confidence = 0.5  # Default medium confidence
        if symbol in self.position_confidence:
            conf_dict = self.position_confidence[symbol]
            if isinstance(conf_dict, dict):
                confidence = conf_dict.get(position_type, 0.5)
            else:
                confidence = conf_dict if position_type == 'swing' else 0.5

        # Check if AI suggested a trailing stop percentage
        ai_trailing_pct = None
        if symbol in self.position_trailing_stop_pct:
            trailing_dict = self.position_trailing_stop_pct[symbol]
            if isinstance(trailing_dict, dict):
                ai_trailing_pct = trailing_dict.get(position_type)

        # Use AI-suggested trailing percentage if available, otherwise use confidence-based defaults
        if ai_trailing_pct is not None:
            # Validate AI-suggested trailing percentage is reasonable
            if 0.05 <= ai_trailing_pct <= 0.20:
                trail_pct = ai_trailing_pct
                logger.debug(f"Using AI-suggested trailing stop: {trail_pct*100:.1f}% for {symbol} {position_type}")
            else:
                logger.warning(f"AI trailing percentage {ai_trailing_pct*100:.1f}% out of range (5-20%), using confidence-based default")
                # Fall through to confidence-based calculation
                ai_trailing_pct = None

        # Calculate trailing percentage based on confidence (if AI didn't suggest one)
        if ai_trailing_pct is None:
            # Higher confidence = tighter trailing (10%), lower confidence = looser (15%)
            if confidence >= 0.8:
                trail_pct = 0.10  # 10% trailing for high confidence
            elif confidence >= 0.6:
                trail_pct = 0.12  # 12% trailing for medium-high confidence
            else:
                trail_pct = 0.15  # 15% trailing for lower confidence

        # Update highest/lowest prices and trailing stops
        if position_size > 0:  # LONG position
            # Track highest price reached
            current_highest = self.position_highest_prices.get(symbol, {}).get(position_type, current_price)
            if current_price > current_highest:
                # Price went higher - update highest price
                if symbol not in self.position_highest_prices:
                    self.position_highest_prices[symbol] = {}
                self.position_highest_prices[symbol][position_type] = current_price
                current_highest = current_price

                # Update trailing stop: trail behind highest price
                new_sl = current_highest * (1 - trail_pct)
                if symbol not in self.position_stop_losses:
                    self.position_stop_losses[symbol] = {}
                self.position_stop_losses[symbol][position_type] = new_sl

                logger.info(f"[TRAILING] {symbol} {position_type} LONG: New high ${current_highest:.2f}, SL updated to ${new_sl:.2f} ({trail_pct*100:.0f}% trail, conf: {confidence:.2f}, {'AI-suggested' if ai_trailing_pct else 'confidence-based'})")

        elif position_size < 0:  # SHORT position
            # Track lowest price reached
            current_lowest = self.position_lowest_prices.get(symbol, {}).get(position_type, current_price)
            if current_price < current_lowest:
                # Price went lower - update lowest price
                if symbol not in self.position_lowest_prices:
                    self.position_lowest_prices[symbol] = {}
                self.position_lowest_prices[symbol][position_type] = current_price
                current_lowest = current_price

                # Update trailing stop: trail above lowest price
                new_sl = current_lowest * (1 + trail_pct)
                if symbol not in self.position_stop_losses:
                    self.position_stop_losses[symbol] = {}
                self.position_stop_losses[symbol][position_type] = new_sl

                logger.info(f"[TRAILING] {symbol} {position_type} SHORT: New low ${current_lowest:.2f}, SL updated to ${new_sl:.2f} ({trail_pct*100:.0f}% trail, conf: {confidence:.2f}, {'AI-suggested' if ai_trailing_pct else 'confidence-based'})")

    def check_position_sl_tp(self, symbol: str, snapshot, position_type: str, position_size: float, current_price: float) -> Optional[str]:
        """
        Check stop loss and take profit for a specific position type.

        Args:
            symbol: Trading symbol
            snapshot: Market snapshot
            position_type: 'swing' or 'scalp'
            position_size: Position size (positive for long, negative for short)
            current_price: Current market price

        Returns:
            JSON decision string if SL/TP hit, None otherwise
        """
        # Get stored SL/TP for this position type
        stored_stop_loss = None
        stored_take_profit = None
        entry_price = current_price

        if symbol in self.position_stop_losses:
            sl_dict = self.position_stop_losses[symbol]
            if isinstance(sl_dict, dict):
                stored_stop_loss = sl_dict.get(position_type)
            else:
                # Backward compatibility: if old format, only use for swing
                stored_stop_loss = sl_dict if position_type == 'swing' else None

        if symbol in self.position_take_profits:
            tp_dict = self.position_take_profits[symbol]
            if isinstance(tp_dict, dict):
                stored_take_profit = tp_dict.get(position_type)
            else:
                # Backward compatibility: if old format, only use for swing
                stored_take_profit = tp_dict if position_type == 'swing' else None

        if symbol in self.position_entry_prices:
            entry_dict = self.position_entry_prices[symbol]
            if isinstance(entry_dict, dict):
                entry_price = entry_dict.get(position_type, current_price)
            else:
                # Backward compatibility
                entry_price = entry_dict if position_type == 'swing' else current_price

        # Check stop loss
        if stored_stop_loss is not None:
            if position_size > 0:  # Long position
                if current_price <= stored_stop_loss:
                    logger.info(f"[SL] {symbol} {position_type} LONG SL triggered: ${current_price:.2f} <= ${stored_stop_loss:.2f}")
                    decision = f'{{"action": "close", "size_pct": 1.0, "reason": "{position_type.capitalize()} long stop loss triggered: price ${current_price:.2f} <= ${stored_stop_loss:.2f}", "position_type": "{position_type}"}}'
                    # Clear stored stop loss/take profit for this type
                    self._clear_position_tracking(symbol, position_type)
                    return decision
            else:  # Short position
                if current_price >= stored_stop_loss:
                    logger.info(f"[SL] {symbol} {position_type} SHORT SL triggered: ${current_price:.2f} >= ${stored_stop_loss:.2f}")
                    decision = f'{{"action": "close", "size_pct": 1.0, "reason": "{position_type.capitalize()} short stop loss triggered: price ${current_price:.2f} >= ${stored_stop_loss:.2f}", "position_type": "{position_type}"}}'
                    # Clear stored stop loss/take profit for this type
                    self._clear_position_tracking(symbol, position_type)
                    return decision

        # Check take profit
        if stored_take_profit is not None:
            if position_size > 0:  # Long position
                if current_price >= stored_take_profit:
                    logger.info(f"[TP] {symbol} {position_type} LONG TP triggered: ${current_price:.2f} >= ${stored_take_profit:.2f}")
                    decision = f'{{"action": "close", "size_pct": 1.0, "reason": "{position_type.capitalize()} long take profit triggered: price ${current_price:.2f} >= ${stored_take_profit:.2f}", "position_type": "{position_type}"}}'
                    # Clear stored stop loss/take profit for this type
                    self._clear_position_tracking(symbol, position_type)
                    return decision
            else:  # Short position
                if current_price <= stored_take_profit:
                    logger.info(f"[TP] {symbol} {position_type} SHORT TP triggered: ${current_price:.2f} <= ${stored_take_profit:.2f}")
                    decision = f'{{"action": "close", "size_pct": 1.0, "reason": "{position_type.capitalize()} short take profit triggered: price ${current_price:.2f} <= ${stored_take_profit:.2f}", "position_type": "{position_type}"}}'
                    # Clear stored stop loss/take profit for this type
                    self._clear_position_tracking(symbol, position_type)
                    return decision

        return None  # No SL/TP hit

    def _clear_position_tracking(self, symbol: str, position_type: str):
        """Clear position tracking data for a specific position type."""
        # Clear stop loss/take profit
        if symbol in self.position_stop_losses:
            if isinstance(self.position_stop_losses[symbol], dict):
                if position_type in self.position_stop_losses[symbol]:
                    del self.position_stop_losses[symbol][position_type]
            else:
                # Old format: clear entire entry
                del self.position_stop_losses[symbol]

        if symbol in self.position_take_profits:
            if isinstance(self.position_take_profits[symbol], dict):
                if position_type in self.position_take_profits[symbol]:
                    del self.position_take_profits[symbol][position_type]
            else:
                del self.position_take_profits[symbol]

        # Clear confidence
        if symbol in self.position_confidence:
            if isinstance(self.position_confidence[symbol], dict):
                if position_type in self.position_confidence[symbol]:
                    del self.position_confidence[symbol][position_type]
            else:
                del self.position_confidence[symbol]

        # Clear entry prices and timestamps
        if symbol in self.position_entry_prices:
            if isinstance(self.position_entry_prices[symbol], dict):
                if position_type in self.position_entry_prices[symbol]:
                    del self.position_entry_prices[symbol][position_type]
            else:
                del self.position_entry_prices[symbol]

        if symbol in self.position_entry_timestamps:
            if isinstance(self.position_entry_timestamps[symbol], dict):
                if position_type in self.position_entry_timestamps[symbol]:
                    del self.position_entry_timestamps[symbol][position_type]
            else:
                del self.position_entry_timestamps[symbol]

        # Clear trailing stop tracking (highest/lowest prices)
        if symbol in self.position_highest_prices:
            if isinstance(self.position_highest_prices[symbol], dict):
                if position_type in self.position_highest_prices[symbol]:
                    del self.position_highest_prices[symbol][position_type]
            else:
                del self.position_highest_prices[symbol]

        if symbol in self.position_lowest_prices:
            if isinstance(self.position_lowest_prices[symbol], dict):
                if position_type in self.position_lowest_prices[symbol]:
                    del self.position_lowest_prices[symbol][position_type]
            else:
                del self.position_lowest_prices[symbol]

        # Clear AI-suggested trailing stop percentage
        if symbol in self.position_trailing_stop_pct:
            if isinstance(self.position_trailing_stop_pct[symbol], dict):
                if position_type in self.position_trailing_stop_pct[symbol]:
                    del self.position_trailing_stop_pct[symbol][position_type]
            else:
                del self.position_trailing_stop_pct[symbol]

        # Clear leverage and risk/reward tracking
        if symbol in self.position_leverages:
            if isinstance(self.position_leverages[symbol], dict):
                if position_type in self.position_leverages[symbol]:
                    del self.position_leverages[symbol][position_type]
            else:
                del self.position_leverages[symbol]

        if symbol in self.position_risk_amounts:
            if isinstance(self.position_risk_amounts[symbol], dict):
                if position_type in self.position_risk_amounts[symbol]:
                    del self.position_risk_amounts[symbol][position_type]
            else:
                del self.position_risk_amounts[symbol]

        if symbol in self.position_reward_amounts:
            if isinstance(self.position_reward_amounts[symbol], dict):
                if position_type in self.position_reward_amounts[symbol]:
                    del self.position_reward_amounts[symbol][position_type]
            else:
                del self.position_reward_amounts[symbol]
        
        # Clear capital used tracking
        if symbol in self.position_capital_used:
            if isinstance(self.position_capital_used[symbol], dict):
                if position_type in self.position_capital_used[symbol]:
                    del self.position_capital_used[symbol][position_type]
            else:
                del self.position_capital_used[symbol]
    
    def sync_positions_with_exchange(self, exchange_adapter, tracked_symbols: list) -> None:
        """
        Synchronize internal position tracking with actual exchange positions.
        This detects positions that were closed externally (e.g., by hitting SL/TP on exchange).
        
        Args:
            exchange_adapter: ExchangeAdapter instance with fetch_futures_positions() method
            tracked_symbols: List of symbols we're tracking (e.g., ['BTC/USDT', 'ETH/USDT'])
        """
        # If running in demo and configured to disable sync, skip entirely (prevents false external-closes
        # on unsupported alt symbols that demo never returns in account positions)
        try:
            if self.disable_sync_in_demo and getattr(exchange_adapter, 'config', None):
                et = getattr(exchange_adapter.config, 'exchange_type', '').lower()
                rm = getattr(exchange_adapter.config, 'run_mode', '').lower()
                if et == 'binance_demo' or rm == 'demo':
                    return
        except Exception:
            pass
        import time
        current_time = time.time()
        
        # Only sync every 30 seconds to avoid spamming the exchange
        if current_time - self.last_position_sync_time < 30:
            return
        
        self.last_position_sync_time = current_time
        
        try:
            # Fetch actual positions from exchange
            exchange_positions = exchange_adapter.fetch_futures_positions()
            
            # Check each tracked symbol for discrepancies
            for symbol in tracked_symbols:
                # Get our internal tracking
                swing_pos = self.get_position_by_type(symbol, 'swing')
                scalp_pos = self.get_position_by_type(symbol, 'scalp')
                
                # Get actual position from exchange (total, not split by strategy type)
                actual_pos = exchange_positions.get(symbol, None)
                
                if actual_pos:
                    # Exchange has a position
                    actual_size = actual_pos['size']
                    if actual_pos['side'] == 'short':
                        actual_size = -actual_size
                    # Reset miss counters if exchange reports a position
                    self._no_position_miss_count[(symbol, 'swing')] = 0
                    self._no_position_miss_count[(symbol, 'scalp')] = 0
                    
                    # Check if our internal tracking matches
                    internal_total = swing_pos + scalp_pos
                    
                    if abs(internal_total - actual_size) > 0.001:
                        logger.warning(f"[POSITION SYNC] {symbol}: Discrepancy detected!")
                        logger.warning(f"  Internal: swing={swing_pos:.6f}, scalp={scalp_pos:.6f}, total={internal_total:.6f}")
                        logger.warning(f"  Exchange: {actual_pos['side']} {actual_size:.6f}")
                        
                        # For now, just log the discrepancy
                        # In production, you might want to reconcile automatically
                else:
                    # Exchange has NO position for this symbol
                    if abs(swing_pos) > 0.001 or abs(scalp_pos) > 0.001:
                        logger.warning(f"[POSITION SYNC] {symbol}: Position closed externally!")
                        logger.warning(f"  Internal: swing={swing_pos:.6f}, scalp={scalp_pos:.6f}")
                        logger.warning(f"  Exchange: No position")
                        logger.info(f"  -> Debouncing clear to avoid false positives")

                        # Debounce logic (robust): if the position was opened recently, or misses are not confirmed,
                        # do NOT clear yet. Require two consecutive 'no position' syncs and at least 120s since open.
                        def _should_clear(ptype: str, size: float) -> bool:
                            if abs(size) <= 0.001:
                                # Nothing to clear
                                return False
                            # If entry timestamp exists and is recent, skip clearing (likely propagation lag)
                            ts = None
                            try:
                                ts = self.position_entry_timestamps.get(symbol, {}).get(ptype)
                            except Exception:
                                ts = None
                            short_window = int(self.sync_grace_seconds or 120)
                            if ts is not None and current_time - int(ts) < short_window:
                                logger.info(f"  -> Skipping {ptype} clear (opened {int(current_time - int(ts))}s ago < {short_window}s)")
                                # Reset miss counter since we consider it valid
                                self._no_position_miss_count[(symbol, ptype)] = 0
                                return False
                            # Increment consecutive miss count
                            key = (symbol, ptype)
                            self._no_position_miss_count[key] = self._no_position_miss_count.get(key, 0) + 1
                            required_misses = int(self.sync_confirm_misses or 2)
                            if self._no_position_miss_count[key] < required_misses:
                                logger.info(f"  -> {ptype} miss #{self._no_position_miss_count[key]} (waiting for confirmation)")
                                return False
                            # Confirmed by two misses beyond the time window
                            return True

                        # Evaluate for each type independently
                        clear_swing = _should_clear('swing', swing_pos)
                        clear_scalp = _should_clear('scalp', scalp_pos)

                        if not clear_swing and not clear_scalp:
                            # Do not proceed to emit/clear yet this cycle
                            continue
                        try:
                            # Attempt to send completed trade(s) to frontend for visibility
                            import api_server
                            loop = getattr(api_server, 'loop_controller_instance', None)
                            api_client = None
                            if loop and hasattr(loop, 'cycle_controller') and loop.cycle_controller:
                                api_client = getattr(loop.cycle_controller, 'api_client', None)
                            # Helper to fetch last price
                            def _last_price(sym: str, fallback: float = 0.0) -> float:
                                try:
                                    ex = getattr(exchange_adapter, 'exchange', None)
                                    if ex and hasattr(ex, 'fapiPublicGetTickerPrice'):
                                        res = ex.fapiPublicGetTickerPrice({'symbol': sym.replace('/', '')})
                                        p = float(res['price']) if isinstance(res, dict) and 'price' in res else float(res)
                                        return p if p > 0 else fallback
                                    if ex and hasattr(ex, 'fetch_ticker'):
                                        tk = ex.fetch_ticker(sym)
                                        p = float(tk.get('last', fallback))
                                        return p if p > 0 else fallback
                                except Exception:
                                    pass
                                return fallback
                            # Helper to log trade
                            def _emit_trade(ptype: str, size: float):
                                if not api_client or abs(size) <= 0.0:
                                    return
                                # De-dupe: do not emit the same symbol/type more than once within 10s
                                import time as _t
                                key = (symbol, ptype)
                                last_ts = self._last_emitted_close.get(key, 0)
                                now_ts = int(_t.time())
                                if now_ts - last_ts < 10:
                                    return
                                # Entry price from tracking
                                entry_price = None
                                ep_dict = self.position_entry_prices.get(symbol, {})
                                if isinstance(ep_dict, dict):
                                    entry_price = ep_dict.get(ptype)
                                exit_price = _last_price(symbol, entry_price or 0.0)
                                qty = abs(size)
                                if entry_price and exit_price and qty > 0:
                                    side = 'LONG' if size > 0 else 'SHORT'
                                    # Holding time
                                    ts = None
                                    ts_dict = self.position_entry_timestamps.get(symbol, {})
                                    if isinstance(ts_dict, dict):
                                        ts = ts_dict.get(ptype)
                                    holding = 'Unknown'
                                    import time as _t
                                    if ts:
                                        sec = int(_t.time()) - int(ts)
                                        holding = f"{sec // 60}m" if sec < 3600 else f"{sec // 3600}h {(sec % 3600)//60}m"
                                    pnl = (exit_price - entry_price) * qty if size > 0 else (entry_price - exit_price) * qty
                                    # Skip micro-noise trades to avoid spam (configurable)
                                    try:
                                        min_abs = float(self.completed_trades_min_abs_pnl)
                                    except Exception:
                                        min_abs = 0.0
                                    if abs(pnl) < min_abs:
                                        return
                                    try:
                                        api_client.add_trade(
                                            symbol,
                                            side,
                                            entry_price,
                                            exit_price,
                                            qty,
                                            entry_price * qty,
                                            exit_price * qty,
                                            holding,
                                            pnl,
                                        )
                                        self._last_emitted_close[key] = now_ts
                                        # Also notify Agent Chat about the close
                                        try:
                                            agent_side = side.lower()
                                            agent_msg = (
                                                f"Closed {ptype.upper()} {symbol} {agent_side} at ${exit_price:,.2f} "
                                                f"(qty {qty:g}). Duration {holding}. P&L {pnl:+.2f}."
                                            )
                                            api_client.add_agent_message(agent_msg)
                                        except Exception:
                                            pass
                                    except Exception:
                                        pass
                                    # Update tracked equity with realized PnL
                                    try:
                                        self.tracked_equity = (self.tracked_equity or 0.0) + pnl
                                    except Exception:
                                        pass
                            # Emit trades for both types
                            if clear_swing and abs(swing_pos) > 0.001:
                                _emit_trade('swing', swing_pos)
                            if clear_scalp and abs(scalp_pos) > 0.001:
                                _emit_trade('scalp', scalp_pos)
                        except Exception:
                            pass

                        # Clear our internal tracking since exchange says no position
                        if clear_swing and abs(swing_pos) > 0.001:
                            logger.info(f"  -> Clearing swing position")
                            # Zero the tracked size before clearing metadata
                            try:
                                self.set_position_by_type(symbol, 'swing', 0.0)
                            except Exception:
                                pass
                            self._clear_position_tracking(symbol, 'swing')
                        if clear_scalp and abs(scalp_pos) > 0.001:
                            logger.info(f"  -> Clearing scalp position")
                            try:
                                self.set_position_by_type(symbol, 'scalp', 0.0)
                            except Exception:
                                pass
                            self._clear_position_tracking(symbol, 'scalp')
                        # Reset miss counters after clearing
                        if clear_swing:
                            self._no_position_miss_count[(symbol, 'swing')] = 0
                        if clear_scalp:
                            self._no_position_miss_count[(symbol, 'scalp')] = 0
            
            logger.debug(f"[POSITION SYNC] Completed - tracked equity: ${self.tracked_equity:.2f}")
            
        except Exception as e:
            logger.error(f"[POSITION SYNC] Failed to sync positions: {e}")
