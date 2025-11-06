"""Lightweight persistent agent memory for trades and actions.

Stores a compact JSON file with recent trade and action events, so the agent
can remember prior activity across restarts. Designed to be robust and simple
without external DB dependencies.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional


DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agent_memory.json")


class AgentMemory:
    """Thread-safe JSON-backed memory for trades and actions.

    Schema:
      {
        "trades": [
          {
            "ts": 1730832000,
            "symbol": "ETH/USDT",
            "position_type": "swing"|"scalp",
            "event": "open"|"close",
            "side": "long"|"short",
            "price": 3404.79,
            "size": 0.015,
            "leverage": 1,
            "reason": "...",
            "confidence": 0.78,
            "pnl": 0.02  # optional for closes
          },
          ...
        ],
        "actions": [
          {"ts": 1730832005, "symbol": "ETH/USDT", "position_type": "swing", "action": "close"},
          ...
        ]
      }
    """

    def __init__(self, path: Optional[str] = None, max_events: int = 5000) -> None:
        self.path = path or DEFAULT_PATH
        self.max_events = max_events
        self._lock = threading.RLock()
        self._data: Dict[str, List[Dict[str, Any]]] = {"trades": [], "actions": []}
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    if isinstance(raw, dict):
                        self._data["trades"] = list(raw.get("trades", []))
                        self._data["actions"] = list(raw.get("actions", []))
        except Exception:
            # Corrupt or missing file: start fresh
            self._data = {"trades": [], "actions": []}

    def _save(self) -> None:
        try:
            tmp_path = f"{self.path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp_path, self.path)
        except Exception:
            # Best-effort persistence; ignore failures to not break trading loop
            pass

    def _trim(self) -> None:
        # Keep memory bounded
        for key in ("trades", "actions"):
            if len(self._data[key]) > self.max_events:
                self._data[key] = self._data[key][-self.max_events :]

    def record_trade(
        self,
        *,
        symbol: str,
        position_type: str,
        event: str,  # "open"|"close"
        side: str,   # "long"|"short"
        price: float,
        size: float,
        leverage: float,
        reason: Optional[str] = None,
        confidence: Optional[float] = None,
        pnl: Optional[float] = None,
        ts: Optional[int] = None,
    ) -> None:
        with self._lock:
            self._data["trades"].append(
                {
                    "ts": int(ts or time.time()),
                    "symbol": symbol,
                    "position_type": position_type,
                    "event": event,
                    "side": side,
                    "price": float(price) if price is not None else None,
                    "size": float(size) if size is not None else None,
                    "leverage": float(leverage) if leverage is not None else None,
                    "reason": reason,
                    "confidence": float(confidence) if confidence is not None else None,
                    "pnl": float(pnl) if pnl is not None else None,
                }
            )
            self._trim()
            self._save()

    def record_action(self, *, symbol: str, position_type: str, action: str, ts: Optional[int] = None) -> None:
        with self._lock:
            self._data["actions"].append(
                {
                    "ts": int(ts or time.time()),
                    "symbol": symbol,
                    "position_type": position_type,
                    "action": action,
                }
            )
            self._trim()
            self._save()

    def get_last_close_time(self, symbol: str, position_type: str) -> Optional[int]:
        with self._lock:
            for evt in reversed(self._data.get("trades", [])):
                if (
                    evt.get("symbol") == symbol
                    and evt.get("position_type") == position_type
                    and evt.get("event") == "close"
                ):
                    return int(evt.get("ts", 0))
        return None

    def get_last_close_time_any(self, symbol: str) -> Optional[int]:
        """Last close timestamp for a symbol (any position type)."""
        with self._lock:
            for evt in reversed(self._data.get("trades", [])):
                if evt.get("symbol") == symbol and evt.get("event") == "close":
                    return int(evt.get("ts", 0))
        return None

    def get_last_open_time(self) -> Optional[int]:
        """Last open timestamp across all symbols/types."""
        with self._lock:
            for evt in reversed(self._data.get("trades", [])):
                if evt.get("event") == "open":
                    return int(evt.get("ts", 0))
        return None

    def count_recent_opens(self, window_seconds: int = 600) -> int:
        """Number of open events within the recent window across all trades."""
        cutoff = int(time.time()) - int(window_seconds)
        n = 0
        with self._lock:
            for evt in reversed(self._data.get("trades", [])):
                ts = int(evt.get("ts", 0))
                if ts < cutoff:
                    break
                if evt.get("event") == "open":
                    n += 1
        return n

    def recent_stats(self, symbol: str, position_type: Optional[str] = None, window_seconds: int = 3600) -> Dict[str, Any]:
        cutoff = int(time.time()) - int(window_seconds)
        wins = 0
        losses = 0
        pnl_sum = 0.0
        count = 0
        with self._lock:
            for evt in self._data.get("trades", []):
                if evt.get("ts", 0) < cutoff:
                    continue
                if evt.get("symbol") != symbol:
                    continue
                if position_type and evt.get("position_type") != position_type:
                    continue
                if evt.get("event") == "close":
                    pnl = float(evt.get("pnl") or 0.0)
                    pnl_sum += pnl
                    wins += 1 if pnl > 0 else 0
                    losses += 1 if pnl < 0 else 0
                    count += 1
        return {"wins": wins, "losses": losses, "pnl_sum": pnl_sum, "closes": count}

    # --------- New: Last-N trades and summary over closes ---------
    def get_recent_closed_trades(
        self,
        *,
        limit: int = 20,
        symbol: Optional[str] = None,
        position_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return details for the last-N closed trades (most recent first).

        Attempts to pair each close with its preceding open to compute duration
        and entry/exit prices. If pairing fails, returns what's available.
        """
        with self._lock:
            events = list(self._data.get("trades", []))

        # Process in chronological order to pair opens with closes via a stack per (symbol,ptype,side)
        stacks: Dict[tuple, List[Dict[str, Any]]] = {}
        closed: List[Dict[str, Any]] = []
        for evt in events:
            if symbol and evt.get("symbol") != symbol:
                continue
            if position_type and evt.get("position_type") != position_type:
                continue
            key = (evt.get("symbol"), evt.get("position_type"), evt.get("side"))
            if evt.get("event") == "open":
                stacks.setdefault(key, []).append(evt)
            elif evt.get("event") == "close":
                open_evt = None
                if key in stacks and stacks[key]:
                    open_evt = stacks[key].pop()
                trade = {
                    "symbol": evt.get("symbol"),
                    "position_type": evt.get("position_type"),
                    "side": evt.get("side"),
                    "entry_price": open_evt.get("price") if open_evt else None,
                    "exit_price": evt.get("price"),
                    "size": evt.get("size"),
                    "entry_ts": open_evt.get("ts") if open_evt else None,
                    "exit_ts": evt.get("ts"),
                    "duration_secs": (evt.get("ts") - open_evt.get("ts")) if (open_evt and evt.get("ts") and open_evt.get("ts")) else None,
                    "pnl": evt.get("pnl"),
                    "confidence": evt.get("confidence"),
                    "reason": evt.get("reason"),
                }
                closed.append(trade)

        return list(reversed(closed[-limit:]))

    def summarize_recent_closes(
        self,
        *,
        limit: int = 20,
        symbol: Optional[str] = None,
        position_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        trades = self.get_recent_closed_trades(limit=limit, symbol=symbol, position_type=position_type)
        wins = 0
        losses = 0
        pnl_sum = 0.0
        durations = []
        for t in trades:
            pnl = float(t.get("pnl") or 0.0)
            pnl_sum += pnl
            wins += 1 if pnl > 0 else 0
            losses += 1 if pnl < 0 else 0
            if t.get("duration_secs") is not None:
                durations.append(int(t["duration_secs"]))
        count = len(trades)
        avg_pnl = (pnl_sum / count) if count else 0.0
        win_rate = (wins / count) if count else 0.0
        avg_duration = (sum(durations) / len(durations)) if durations else None
        return {
            "count": count,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "pnl_sum": pnl_sum,
            "avg_pnl": avg_pnl,
            "avg_duration_secs": avg_duration,
            "trades": trades,
        }


# Singleton accessors ---------------------------------------------------------
_MEM_SINGLETON: Optional[AgentMemory] = None


def get_memory() -> AgentMemory:
    global _MEM_SINGLETON
    if _MEM_SINGLETON is None:
        _MEM_SINGLETON = AgentMemory()
    return _MEM_SINGLETON


