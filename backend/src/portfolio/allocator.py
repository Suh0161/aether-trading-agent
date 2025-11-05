"""Simple portfolio allocator helpers.

This module provides lightweight helpers to enforce a single portfolio cap
across multiple trades and to apply per-trade ceilings (swing/scalp targets).

It does not do global ranking here; that can be added later if we centralize
decision collection at the cycle level. For now, these helpers are used inside
symbol processing to cap requested capital to the remaining portfolio budget
and per-type targets.
"""

from typing import Dict


class PortfolioAllocator:
    def __init__(self, config, position_manager):
        self.config = config
        self.position_manager = position_manager

    def get_used_margin(self) -> float:
        used = 0.0
        caps = getattr(self.position_manager, "position_capital_used", {})
        if isinstance(caps, dict):
            for _sym, c in caps.items():
                if isinstance(c, dict):
                    for _t, amt in c.items():
                        if amt:
                            used += amt
                elif c:
                    used += c
        return used

    def remaining_budget(self, equity: float) -> float:
        max_margin = equity * getattr(self.config, "max_equity_usage_pct", 0.30)
        return max(0.0, max_margin - self.get_used_margin())

    def per_type_ceiling(self, position_type: str, equity: float) -> float:
        base_pct = (
            getattr(self.config, "swing_target_pct", 0.25)
            if position_type == "swing"
            else getattr(self.config, "scalp_target_pct", 0.15)
        )
        return max(0.0, base_pct * equity)

    def cap_capital(self, position_type: str, requested_capital: float, equity: float) -> float:
        # Apply per-trade ceiling first
        ceiling = self.per_type_ceiling(position_type, equity)
        capped = min(requested_capital, ceiling)
        # Then apply remaining portfolio budget
        remaining = self.remaining_budget(equity)
        capped = min(capped, remaining)
        # Enforce minimum allocation threshold
        min_alloc = getattr(self.config, "min_allocation_usd", 3.0)
        if capped < min_alloc:
            return 0.0
        return capped


