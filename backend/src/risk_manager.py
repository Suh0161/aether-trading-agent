"""Risk management layer for the Autonomous Trading Agent."""

import logging
from datetime import datetime, timezone
from typing import Optional

from src.config import Config
from src.models import DecisionObject, MarketSnapshot


logger = logging.getLogger(__name__)


class RiskManager:
    """Validates trading decisions against safety rules."""
    
    def __init__(self, config: Config):
        """
        Initialize risk manager with configuration.
        
        Args:
            config: Configuration object with risk parameters
        """
        self.max_equity_usage_pct = config.max_equity_usage_pct
        self.max_leverage = config.max_leverage
        self.daily_loss_cap_pct = config.daily_loss_cap_pct
        self.cooldown_seconds = config.cooldown_seconds
        # Minimum hold requirements to reduce churn (seconds)
        self.min_hold_seconds_swing = getattr(config, 'min_hold_seconds_swing', 900)
        self.min_hold_seconds_scalp = getattr(config, 'min_hold_seconds_scalp', 300)
        # Anti-churn: cooldown between any scalp actions (open/close)
        self.min_action_interval_scalp = getattr(config, 'scalp_action_cooldown_seconds', 180)
        self.min_action_interval_swing = getattr(config, 'swing_action_cooldown_seconds', 300)
        self.allow_scalp_reversal_bypass = getattr(config, 'allow_scalp_reversal_bypass', False)
        
        # State tracking
        self.last_open_time: Optional[int] = None
        self.starting_equity: Optional[float] = None
        self.current_day: Optional[int] = None
        
        # Per-symbol, per-strategy cooldown tracking (prevents spam trading)
        self.last_close_time = {}  # {symbol: {'swing': timestamp, 'scalp': timestamp}}
        self.last_action_time = {}  # { (symbol, ptype): timestamp }
        
        # Scalp-specific cooldown (faster re-entry for scalping)
        self.scalp_cooldown_seconds = 60  # 1 minute minimum between scalp trades
        self.swing_cooldown_seconds = 300  # 5 minutes minimum between swing trades
        self.consecutive_100pct_count: int = 0
        # Portfolio-level controls
        # Hard defaults (no env required)
        self.max_open_positions_total = getattr(config, 'max_open_positions_total', 2)
        self.min_global_open_interval_seconds = getattr(config, 'min_global_open_interval_seconds', 180)
        self.symbol_cooldown_seconds = 300  # Do not reopen same symbol within 5 min after a close
    
    def validate_decision(
        self,
        decision: DecisionObject,
        snapshot: MarketSnapshot,
        position_size: float,
        equity: float,
        symbol: str,
        position_manager=None  # NEW: Optional position manager for margin calculation
    ) -> tuple[bool, str]:
        """
        Run all risk checks and return approval or denial.

        Args:
            decision: Parsed trading decision from LLM
            snapshot: Current market data
            position_size: Current position size (positive for long, negative for short)
            equity: Current account equity
            symbol: Trading symbol (e.g., 'BTC/USDT')
            position_manager: Optional PositionManager instance for margin calculation

        Returns:
            Tuple of (approved: bool, reason: str)
        """
        # Track starting equity for daily loss cap
        self._update_daily_equity(equity)
        
        # Rule 1: Hold auto-approve
        if decision.action == "hold":
            logger.info("Risk check: hold action auto-approved")
            return True, ""
        
        # Resolve position_type early
        position_type = getattr(decision, 'position_type', 'swing')

        # Rule 0: Anti-churn action spacing for scalp and swing (applies to open/close unless forced)
        try:
            ptype = getattr(decision, 'position_type', 'swing')
            if ptype in ('scalp', 'swing') and decision.action in ("long", "short", "close"):
                key = (symbol, ptype)
                last_act = self.last_action_time.get(key)
                if last_act is not None:
                    now_ts = int(datetime.now(timezone.utc).timestamp())
                    elapsed = now_ts - int(last_act)
                    reason_lower = (getattr(decision, 'reason', '') or '').lower()
                    forced = (
                        ('stop loss' in reason_lower) or
                        ('take profit' in reason_lower) or
                        ('emergency' in reason_lower) or
                        (self.allow_scalp_reversal_bypass and ('reversal' in reason_lower))
                    )
                    min_interval = self.min_action_interval_scalp if ptype == 'scalp' else self.min_action_interval_swing
                    if not forced and elapsed < min_interval:
                        logger.warning(
                            f"Risk check: denied - {ptype} action cooldown {elapsed}s < {min_interval}s for {symbol}"
                        )
                        return False, f"{ptype} action cooldown ({elapsed}s/{min_interval}s)"
        except Exception:
            pass

        # Rule 1a: Enforce minimum hold time before generic closes (prevents quick churn)
        # Always allow emergency/SL/TP-driven closes
        if decision.action == "close" and position_manager is not None:
            try:
                current_size_signed = position_manager.get_position_by_type(symbol, position_type)
                if abs(current_size_signed) > 0.0001:
                    ts = None
                    ts_dict = position_manager.position_entry_timestamps.get(symbol, {})
                    if isinstance(ts_dict, dict):
                        ts = ts_dict.get(position_type)
                    now_ts = int(datetime.now(timezone.utc).timestamp())
                    if ts:
                        held_secs = max(0, now_ts - int(ts))
                    else:
                        # Fallback: use last action timestamp if entry ts missing
                        held_secs = max(0, now_ts - int(self.last_action_time.get((symbol, position_type), now_ts)))
                        min_hold = self.min_hold_seconds_scalp if position_type == 'scalp' else self.min_hold_seconds_swing
                        reason_lower = (getattr(decision, 'reason', '') or '').lower()
                        # Forced exceptions: SL/TP/Emergency (+ optional reversal if enabled)
                        forced = (
                            ('stop loss' in reason_lower) or
                            ('take profit' in reason_lower) or
                            ('emergency' in reason_lower) or
                            (self.allow_scalp_reversal_bypass and ('reversal' in reason_lower))
                        )
                        if not forced and held_secs < min_hold:
                            logger.warning(
                                f"Risk check: denied - {position_type} min hold not satisfied for {symbol} ({held_secs}s < {min_hold}s)"
                            )
                            return False, f"min hold not satisfied ({held_secs}s/{min_hold}s)"
            except Exception:
                # On any error, be permissive to avoid trapping positions
                pass

        # Rule 1b: Prevent same-direction adds/pyramiding for a given strategy type
        if decision.action in ["long", "short"] and position_manager is not None:
            try:
                current_size_signed = position_manager.get_position_by_type(symbol, position_type)
                if ((decision.action == "long" and current_size_signed > 0.0001) or
                    (decision.action == "short" and current_size_signed < -0.0001)):
                    logger.warning(f"Risk check: denied - {position_type} same-direction add disabled for {symbol}")
                    return False, "same-direction add disabled"
            except Exception:
                pass

        # Rule 1c: Scalp must be opposite to swing if swing is open (pullback-only)
        if decision.action in ["long", "short"] and position_type == 'scalp' and position_manager is not None:
            try:
                swing_pos = position_manager.get_position_by_type(symbol, 'swing')
                if abs(swing_pos) > 0.0001:
                    if (swing_pos > 0 and decision.action == 'long') or (swing_pos < 0 and decision.action == 'short'):
                        logger.warning(
                            f"Risk check: denied - scalp matches swing direction for {symbol}; only opposite pullbacks allowed"
                        )
                        return False, "scalp must be opposite to swing"
            except Exception:
                pass
        
        # Rule 1b: Minimum confidence gate (uses AI-overridden confidence if present)
        # Aligns with AI filter guidance: Scalp >= 0.55, Swing >= 0.60
        if decision.action in ["long", "short"]:
            position_type = getattr(decision, 'position_type', 'swing')
            min_conf = 0.55 if position_type == 'scalp' else 0.60
            conf = getattr(decision, 'confidence', 0.0)
            if conf < min_conf:
                logger.warning(
                    f"Risk check: denied - confidence {conf:.2f} below minimum {min_conf:.2f} for {position_type}"
                )
                return False, "confidence below minimum"

            # Rule 1c: Minimum entry quality gate (precision mode)
            try:
                from src.decision_filters.entry_qualifier import compute_entry_qualifier
                direction = 'long' if decision.action == 'long' else 'short'
                qualifier = getattr(decision, 'entry_qualifier', None)
                if qualifier is None:
                    qualifier = compute_entry_qualifier(snapshot, position_type, direction)
                min_q = 0.60 if position_type == 'scalp' else 0.50
                if qualifier < min_q:
                    logger.warning(
                        f"Risk check: denied - entry qualifier {qualifier:.2f} below minimum {min_q:.2f} for {position_type}"
                    )
                    return False, "entry quality below minimum"
            except Exception as e:
                logger.debug(f"Precision gate skipped (qualifier failed): {e}")

        # Rule 2: Prevent new entries if position already exists (same direction)
        # Allow adding to position ONLY if it's the same direction (long+long or short+short)
        # But prevent opening NEW position if one already exists
        if decision.action in ["long", "short"]:
            # Check if we already have a position in the OPPOSITE direction
            if decision.action == "long" and position_size < 0:
                logger.warning("Risk check: denied - cannot open LONG while SHORT position exists")
                return False, "opposite position exists"
            elif decision.action == "short" and position_size > 0:
                logger.warning("Risk check: denied - cannot open SHORT while LONG position exists")
                return False, "opposite position exists"
            # If we already have a position in the SAME direction, also prevent (no adding)
            elif decision.action == "long" and position_size > 0:
                logger.warning("Risk check: denied - LONG position already exists (no position scaling)")
                return False, "position already exists"
            elif decision.action == "short" and position_size < 0:
                logger.warning("Risk check: denied - SHORT position already exists (no position scaling)")
                return False, "position already exists"
        
        # Rule 3: Close/Sell validation - auto-approve closing positions
        if decision.action in ["close", "sell"]:
            if position_size == 0:
                logger.warning("Risk check: denied - no position to close")
                return False, "no position to close"
            else:
                logger.info("Risk check: close/sell action approved (exiting position)")
                return True, ""
        
        # Rule 4: Price validity
        if snapshot.price <= 0:
            logger.warning(f"Risk check: denied - invalid price {snapshot.price}")
            return False, "no valid price"
        
        # Rule 5: Position size limit (only for opening new positions)
        proposed_size = (equity * decision.size_pct) / snapshot.price
        max_allowed_size = (equity * self.max_equity_usage_pct) / snapshot.price
        
        if proposed_size > max_allowed_size:
            logger.warning(
                f"Risk check: denied - proposed size {proposed_size:.4f} exceeds "
                f"max allowed {max_allowed_size:.4f}"
            )
            return False, "exceeds max position size"

        # Rule 5b: Check available cash for new position (CRITICAL: Prevent over-leverage)
        if decision.action in ["long", "short"] and position_manager:
            try:
                # Calculate total margin used across ALL positions
                total_margin_used = 0.0
                if hasattr(position_manager, 'tracked_position_sizes'):
                    for sym in position_manager.tracked_position_sizes:
                        positions = position_manager.tracked_position_sizes.get(sym, {})
                        if isinstance(positions, dict):
                            swing_pos = positions.get('swing', 0.0)
                            scalp_pos = positions.get('scalp', 0.0)
                        else:
                            swing_pos = positions if positions else 0.0
                            scalp_pos = 0.0
                        
                        # Get entry prices and leverage
                        entry_dict = position_manager.position_entry_prices.get(sym, {})
                        leverage_dict = position_manager.position_leverages.get(sym, {})
                        
                        if abs(swing_pos) > 0.0001:
                            if isinstance(entry_dict, dict):
                                swing_entry = entry_dict.get('swing', snapshot.price)
                            else:
                                swing_entry = entry_dict if entry_dict else snapshot.price
                            if isinstance(leverage_dict, dict):
                                leverage = leverage_dict.get('swing', 1.0)
                            else:
                                leverage = leverage_dict if leverage_dict else 1.0
                            swing_notional = abs(swing_pos) * swing_entry
                            total_margin_used += swing_notional / leverage if leverage > 0 else swing_notional
                        
                        if abs(scalp_pos) > 0.0001:
                            if isinstance(entry_dict, dict):
                                scalp_entry = entry_dict.get('scalp', snapshot.price)
                            else:
                                scalp_entry = snapshot.price
                            if isinstance(leverage_dict, dict):
                                leverage = leverage_dict.get('scalp', 1.0)
                            else:
                                leverage = 1.0
                            scalp_notional = abs(scalp_pos) * scalp_entry
                            total_margin_used += scalp_notional / leverage if leverage > 0 else scalp_notional
                
                # Calculate proposed margin for new position
                proposed_notional = proposed_size * snapshot.price
                proposed_leverage = getattr(decision, 'leverage', 1.0)
                proposed_margin = proposed_notional / proposed_leverage if proposed_leverage > 0 else proposed_notional
                
                # Calculate available cash
                tracked_equity = getattr(position_manager, 'tracked_equity', equity)
                available_cash = tracked_equity - total_margin_used
                
                # CRITICAL: Enforce maximum margin usage based on config to leave buffer for smart money management
                # This prevents using 100% of capital and ensures we always have some cash available
                max_allowed_margin = tracked_equity * self.max_equity_usage_pct
                
                if total_margin_used > max_allowed_margin:
                    logger.warning(
                        f"Risk check: denied - margin usage ({total_margin_used:.2f}) exceeds maximum allowed ({max_allowed_margin:.2f}) "
                        f"({int(self.max_equity_usage_pct*100)}% of equity: ${tracked_equity:.2f})."
                    )
                    return False, f"margin usage exceeds maximum ({int(self.max_equity_usage_pct*100)}% limit: ${max_allowed_margin:.2f})"
                
                # Require at least 10% buffer for new position
                required_cash = proposed_margin * 1.1
                
                if available_cash < required_cash:
                    logger.warning(
                        f"Risk check: denied - insufficient cash. "
                        f"Available: ${available_cash:.2f}, Required: ${required_cash:.2f} "
                        f"(margin used: ${total_margin_used:.2f}, equity: ${tracked_equity:.2f})"
                    )
                    return False, f"insufficient cash (available: ${available_cash:.2f}, required: ${required_cash:.2f})"
            except Exception as e:
                logger.debug(f"Cash check skipped (calculation failed): {e}")
                # Don't block if calculation fails, but log it
        
        # Rule 6: Smart leverage limit (adaptive based on portfolio size)
        proposed_position_value = proposed_size * snapshot.price
        
        # Calculate smart leverage based on portfolio size
        # Smaller accounts = more conservative leverage, larger accounts = can use more
        smart_max_leverage = self._calculate_smart_leverage(equity)
        max_leverage_value = equity * smart_max_leverage
        
        # Also check current leverage if we have a position (handle both LONG and SHORT)
        current_position_value = abs(position_size) * snapshot.price if position_size != 0 else 0.0
        total_proposed_value = current_position_value + proposed_position_value
        proposed_leverage = (total_proposed_value / equity) if equity > 0 else 0.0
        
        if proposed_leverage > smart_max_leverage:
            logger.warning(
                f"Risk check: denied - proposed leverage {proposed_leverage:.2f}x "
                f"exceeds smart max leverage {smart_max_leverage:.2f}x (equity: ${equity:,.2f})"
            )
            return False, f"exceeds smart max leverage ({smart_max_leverage:.2f}x)"

        if proposed_position_value > max_leverage_value:
            logger.warning(
                f"Risk check: denied - proposed position value {proposed_position_value:.2f} "
                f"exceeds max leverage value {max_leverage_value:.2f} (smart max: {smart_max_leverage:.2f}x)"
            )
            return False, "exceeds max leverage"
        
        # Rule 7: Daily loss cap
        if self.daily_loss_cap_pct is not None and self.starting_equity is not None:
            loss_threshold = self.starting_equity * (1 - self.daily_loss_cap_pct)
            
            if equity < loss_threshold and decision.action != "close":
                logger.warning(
                    f"Risk check: denied - equity {equity:.2f} below daily loss cap "
                    f"threshold {loss_threshold:.2f}"
                )
                return False, "daily loss cap reached"
        
        # Rule 7: Global open spacing (portfolio-wide) and per-symbol cooldowns
        # 7a. Global interval between ANY opens
        if decision.action in ["long", "short"]:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            # Prefer memory-backed last open (persists across restarts)
            elapsed = None
            try:
                from src.memory.agent_memory import get_memory
                mem_last = get_memory().get_last_open_time()
                if mem_last:
                    elapsed = now_ts - int(mem_last)
            except Exception:
                elapsed = None
            if elapsed is None and self.last_open_time is not None:
                elapsed = now_ts - int(self.last_open_time)
            if elapsed is not None and elapsed < self.min_global_open_interval_seconds:
                logger.warning(
                    f"Risk check: denied - global open cooldown {elapsed}s < {self.min_global_open_interval_seconds}s"
                )
                return False, f"global open cooldown ({elapsed}s/{self.min_global_open_interval_seconds}s)"

            # Also, symbol-level cooldown based on last close (any type)
            try:
                from src.memory.agent_memory import get_memory
                last_close_any = get_memory().get_last_close_time_any(symbol)
                if last_close_any is not None:
                    since_close = now_ts - int(last_close_any)
                    if since_close < self.symbol_cooldown_seconds:
                        logger.warning(
                            f"Risk check: denied - symbol cooldown {since_close}s < {self.symbol_cooldown_seconds}s for {symbol}"
                        )
                        return False, f"symbol cooldown ({since_close}s/{self.symbol_cooldown_seconds}s)"
            except Exception:
                pass

        # 7b. Per-symbol, per-strategy cooldown (PREVENTS SPAM TRADING)
        if decision.action in ["long", "short"]:
            position_type = getattr(decision, 'position_type', 'swing')
            current_time = int(datetime.now(timezone.utc).timestamp())
            
            # Get last close time for this symbol and strategy
            if symbol in self.last_close_time:
                last_close_dict = self.last_close_time.get(symbol, {})
                if isinstance(last_close_dict, dict):
                    last_close = last_close_dict.get(position_type, None)
                    
                    if last_close is not None:
                        time_since_close = current_time - last_close
                        
                        # Use different cooldowns for scalp vs swing
                        required_cooldown = self.scalp_cooldown_seconds if position_type == 'scalp' else self.swing_cooldown_seconds
                        
                        if time_since_close < required_cooldown:
                            logger.warning(
                                f"Risk check: denied - {position_type} cooldown active for {symbol} "
                                f"({time_since_close}s < {required_cooldown}s) - prevents spam trading"
                            )
                            return False, f"{position_type} cooldown active ({time_since_close}s/{required_cooldown}s)"
                else:
                    # No in-memory close time; try to hydrate from persistent memory
                    try:
                        from src.memory.agent_memory import get_memory
                        ts = get_memory().get_last_close_time(symbol, position_type)
                        if ts is not None:
                            if symbol not in self.last_close_time:
                                self.last_close_time[symbol] = {}
                            self.last_close_time[symbol][position_type] = int(ts)
                            time_since_close = current_time - int(ts)
                            required_cooldown = self.scalp_cooldown_seconds if position_type == 'scalp' else self.swing_cooldown_seconds
                            if time_since_close < required_cooldown:
                                logger.warning(
                                    f"Risk check: denied - {position_type} cooldown active for {symbol} "
                                    f"({time_since_close}s < {required_cooldown}s) - prevents spam trading"
                                )
                                return False, f"{position_type} cooldown active ({time_since_close}s/{required_cooldown}s)"
                    except Exception:
                        pass

        # 7c. Portfolio max concurrent open positions (across all symbols & types)
        if decision.action in ["long", "short"] and position_manager is not None:
            try:
                open_count = 0
                if hasattr(position_manager, 'tracked_position_sizes'):
                    for sym, pos in position_manager.tracked_position_sizes.items():
                        if isinstance(pos, dict):
                            if abs(pos.get('swing', 0.0)) > 0.0001:
                                open_count += 1
                            if abs(pos.get('scalp', 0.0)) > 0.0001:
                                open_count += 1
                        else:
                            if abs(pos or 0.0) > 0.0001:
                                open_count += 1
                if open_count >= int(self.max_open_positions_total):
                    logger.warning(
                        f"Risk check: denied - max open positions {open_count} >= {self.max_open_positions_total}"
                    )
                    return False, f"max open positions reached ({open_count}/{self.max_open_positions_total})"
            except Exception:
                pass
        
        # Rule 7b: Global cooldown (legacy, kept for backward compatibility)
        if self.cooldown_seconds is not None and decision.action in ["long", "short"]:
            if self.last_open_time is not None:
                current_time = int(datetime.now(timezone.utc).timestamp())
                time_since_open = current_time - self.last_open_time
                
                if time_since_open < self.cooldown_seconds:
                    logger.warning(
                        f"Risk check: denied - global cooldown active "
                        f"({time_since_open}s < {self.cooldown_seconds}s)"
                    )
                    return False, "cooldown period active"
        
        # Rule 8: LLM sanity check (3 consecutive 100% size requests)
        if decision.size_pct >= 1.0:
            self.consecutive_100pct_count += 1
            
            if self.consecutive_100pct_count >= 3:
                logger.error(
                    f"Risk check: denied - LLM requested 100% size "
                    f"{self.consecutive_100pct_count} consecutive times"
                )
                return False, "LLM sanity check failed"
        else:
            # Reset counter if size is less than 100%
            self.consecutive_100pct_count = 0
        
        # All checks passed
        logger.info("Risk check: all rules passed, trade approved")
        
        # Update last open time if opening a position
        if decision.action in ["long", "short"]:
            self.last_open_time = int(datetime.now(timezone.utc).timestamp())
        
        return True, ""
    
    def record_position_close(self, symbol: str, position_type: str) -> None:
        """
        Record when a position closes to enforce cooldown period.
        This prevents the agent from immediately re-entering the same position (spam trading).
        
        Args:
            symbol: Trading symbol (e.g., 'BTC/USDT')
            position_type: 'swing' or 'scalp'
        """
        from datetime import datetime, timezone
        current_time = int(datetime.now(timezone.utc).timestamp())
        
        if symbol not in self.last_close_time:
            self.last_close_time[symbol] = {}
        
        self.last_close_time[symbol][position_type] = current_time
        
        cooldown = self.scalp_cooldown_seconds if position_type == 'scalp' else self.swing_cooldown_seconds
        logger.info(
            f"[COOLDOWN] {symbol} {position_type} closed - "
            f"next entry allowed in {cooldown}s to prevent spam trading"
        )

    def record_action(self, symbol: str, position_type: str) -> None:
        """Record time of any executed action for anti-churn spacing."""
        try:
            from datetime import datetime, timezone
            now_ts = int(datetime.now(timezone.utc).timestamp())
            key = (symbol, position_type)
            self.last_action_time[key] = now_ts
        except Exception:
            pass
    
    def _calculate_smart_leverage(self, equity: float) -> float:
        """
        Calculate smart maximum leverage based on portfolio size.
        
        Smaller portfolios use more conservative leverage:
        - $0-$500:   1.0x (very conservative)
        - $500-$1k:  1.5x (conservative)
        - $1k-$5k:   2.0x (moderate)
        - $5k-$10k:  2.5x (moderate-high)
        - $10k+:     3.0x (can use configured max)
        
        Args:
            equity: Current account equity
            
        Returns:
            Maximum allowed leverage multiplier
        """
        # Use configured max leverage as absolute maximum
        absolute_max = self.max_leverage
        
        if equity < 500:
            # Very small accounts: very conservative (1x = no leverage)
            return min(1.0, absolute_max)
        elif equity < 1000:
            # Small accounts: conservative (1.5x)
            return min(1.5, absolute_max)
        elif equity < 5000:
            # Medium accounts: moderate (2x)
            return min(2.0, absolute_max)
        elif equity < 10000:
            # Large accounts: moderate-high (2.5x)
            return min(2.5, absolute_max)
        else:
            # Very large accounts: can use configured max (default 3x)
            return absolute_max
    
    def _update_daily_equity(self, equity: float) -> None:
        """
        Update starting equity at the beginning of each UTC day.
        
        Args:
            equity: Current account equity
        """
        now = datetime.now(timezone.utc)
        current_day = now.toordinal()
        
        if self.current_day is None or current_day != self.current_day:
            # New day, reset starting equity
            self.starting_equity = equity
            self.current_day = current_day
            logger.info(f"New UTC day: starting equity set to {equity:.2f}")
            # Log smart leverage for new day
            smart_leverage = self._calculate_smart_leverage(equity)
            logger.info(f"Smart leverage for equity ${equity:,.2f}: {smart_leverage:.2f}x")
