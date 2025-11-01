"""Data models for the Autonomous Trading Agent."""

from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class MarketSnapshot:
    """Normalized market data snapshot."""
    
    timestamp: int  # Unix milliseconds
    symbol: str
    price: float  # Last trade price
    bid: float
    ask: float
    ohlcv: List[List[float]]  # [[ts, o, h, l, c, v], ...]
    indicators: Dict[str, float]  # {"ema_20": 68500.0, "ema_50": 67800.0, "rsi_14": 55.2}


@dataclass
class DecisionObject:
    """Structured trading decision from LLM."""
    
    action: str  # "long" | "short" | "close" | "hold"
    size_pct: float  # 0.0 to 1.0
    reason: str
    stop_loss: Optional[float] = None  # Stop loss price for position monitoring
    take_profit: Optional[float] = None  # Take profit price for position monitoring
    position_type: str = "swing"  # "swing" | "scalp" - indicates trade duration style


@dataclass
class RiskResult:
    """Result of risk validation."""
    
    approved: bool
    reason: str  # Empty if approved, explanation if denied


@dataclass
class ExecutionResult:
    """Result of trade execution."""
    
    executed: bool
    order_id: Optional[str]
    filled_size: Optional[float]
    fill_price: Optional[float]
    error: Optional[str]


@dataclass
class CycleLog:
    """Complete log record for one agent cycle."""
    
    timestamp: int
    symbol: str
    market_price: float
    position_before: float
    llm_raw_output: str
    parsed_action: str
    parsed_size_pct: float
    parsed_reason: str
    risk_approved: bool
    risk_reason: str
    executed: bool
    order_id: Optional[str]
    filled_size: Optional[float]
    fill_price: Optional[float]
    mode: str  # "testnet" | "live"
