"""Risk management layer for the Autonomous Trading Agent."""

import logging
from datetime import datetime, timezone
from typing import Optional

from src.config import Config
from src.models import DecisionObject, MarketSnapshot, RiskResult


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
        
        # State tracking
        self.last_open_time: Optional[int] = None
        self.starting_equity: Optional[float] = None
        self.current_day: Optional[int] = None
        self.consecutive_100pct_count: int = 0
    
    def validate(
        self,
        decision: DecisionObject,
        snapshot: MarketSnapshot,
        position_size: float,
        equity: float
    ) -> RiskResult:
        """
        Run all risk checks and return approval or denial.
        
        Args:
            decision: Parsed trading decision from LLM
            snapshot: Current market data
            position_size: Current position size (positive for long, negative for short)
            equity: Current account equity
            
        Returns:
            RiskResult with approval status and reason
        """
        # Track starting equity for daily loss cap
        self._update_daily_equity(equity)
        
        # Rule 1: Hold auto-approve
        if decision.action == "hold":
            logger.info("Risk check: hold action auto-approved")
            return RiskResult(approved=True, reason="")
        
        # Rule 2: Close/Sell validation - auto-approve closing positions
        if decision.action in ["close", "sell"]:
            if position_size == 0:
                logger.warning("Risk check: denied - no position to close")
                return RiskResult(approved=False, reason="no position to close")
            else:
                logger.info("Risk check: close/sell action approved (exiting position)")
                return RiskResult(approved=True, reason="")
        
        # Rule 3: Price validity
        if snapshot.price <= 0:
            logger.warning(f"Risk check: denied - invalid price {snapshot.price}")
            return RiskResult(approved=False, reason="no valid price")
        
        # Rule 4: Position size limit (only for opening new positions)
        proposed_size = (equity * decision.size_pct) / snapshot.price
        max_allowed_size = (equity * self.max_equity_usage_pct) / snapshot.price
        
        if proposed_size > max_allowed_size:
            logger.warning(
                f"Risk check: denied - proposed size {proposed_size:.4f} exceeds "
                f"max allowed {max_allowed_size:.4f}"
            )
            return RiskResult(approved=False, reason="exceeds max position size")
        
        # Rule 5: Smart leverage limit (adaptive based on portfolio size)
        proposed_position_value = proposed_size * snapshot.price
        
        # Calculate smart leverage based on portfolio size
        # Smaller accounts = more conservative leverage, larger accounts = can use more
        smart_max_leverage = self._calculate_smart_leverage(equity)
        max_leverage_value = equity * smart_max_leverage
        
        # Also check current leverage if we have a position
        current_position_value = position_size * snapshot.price if position_size > 0 else 0.0
        total_proposed_value = current_position_value + proposed_position_value
        proposed_leverage = (total_proposed_value / equity) if equity > 0 else 0.0
        
        if proposed_leverage > smart_max_leverage:
            logger.warning(
                f"Risk check: denied - proposed leverage {proposed_leverage:.2f}x "
                f"exceeds smart max leverage {smart_max_leverage:.2f}x (equity: ${equity:,.2f})"
            )
            return RiskResult(approved=False, reason=f"exceeds smart max leverage ({smart_max_leverage:.2f}x)")
        
        if proposed_position_value > max_leverage_value:
            logger.warning(
                f"Risk check: denied - proposed position value {proposed_position_value:.2f} "
                f"exceeds max leverage value {max_leverage_value:.2f} (smart max: {smart_max_leverage:.2f}x)"
            )
            return RiskResult(approved=False, reason="exceeds max leverage")
        
        # Rule 6: Daily loss cap
        if self.daily_loss_cap_pct is not None and self.starting_equity is not None:
            loss_threshold = self.starting_equity * (1 - self.daily_loss_cap_pct)
            
            if equity < loss_threshold and decision.action != "close":
                logger.warning(
                    f"Risk check: denied - equity {equity:.2f} below daily loss cap "
                    f"threshold {loss_threshold:.2f}"
                )
                return RiskResult(approved=False, reason="daily loss cap reached")
        
        # Rule 7: Cooldown period
        if self.cooldown_seconds is not None and decision.action in ["long", "short"]:
            if self.last_open_time is not None:
                current_time = int(datetime.now(timezone.utc).timestamp())
                time_since_open = current_time - self.last_open_time
                
                if time_since_open < self.cooldown_seconds:
                    logger.warning(
                        f"Risk check: denied - cooldown active "
                        f"({time_since_open}s < {self.cooldown_seconds}s)"
                    )
                    return RiskResult(approved=False, reason="cooldown period active")
        
        # Rule 8: LLM sanity check (3 consecutive 100% size requests)
        if decision.size_pct >= 1.0:
            self.consecutive_100pct_count += 1
            
            if self.consecutive_100pct_count >= 3:
                logger.error(
                    f"Risk check: denied - LLM requested 100% size "
                    f"{self.consecutive_100pct_count} consecutive times"
                )
                return RiskResult(approved=False, reason="LLM sanity check failed")
        else:
            # Reset counter if size is less than 100%
            self.consecutive_100pct_count = 0
        
        # All checks passed
        logger.info("Risk check: all rules passed, trade approved")
        
        # Update last open time if opening a position
        if decision.action in ["long", "short"]:
            self.last_open_time = int(datetime.now(timezone.utc).timestamp())
        
        return RiskResult(approved=True, reason="")
    
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
