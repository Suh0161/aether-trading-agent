"""Trading strategies for the Autonomous Trading Agent."""

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class StrategySignal:
    """Signal from a trading strategy."""
    action: str  # "long" | "short" | "close" | "hold"
    size_pct: float  # 0.0 to 1.0 (percentage of equity to allocate as capital)
    reason: str
    confidence: float  # 0.0 to 1.0
    symbol: str = "BTC/USDT"  # Trading symbol for this signal
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_type: str = "swing"  # "swing" | "scalp" - indicates trade duration style
    leverage: float = 1.0  # Leverage multiplier (1.0 = no leverage, 2.0 = 2x, 3.0 = 3x)
    risk_amount: Optional[float] = None  # Dollar amount at risk if SL hits
    reward_amount: Optional[float] = None  # Dollar amount if TP hits