"""Strategy selection and fallback logic."""

import logging
from typing import Optional

from src.strategies.atr_breakout_strategy import ATRBreakoutStrategy
from src.strategies.ema_strategy import SimpleEMAStrategy
from src.strategies.scalping_strategy import ScalpingStrategy
from src.strategy import StrategySignal

logger = logging.getLogger(__name__)


class StrategySelector:
    """Handles strategy selection and fallback logic."""

    def __init__(self, strategy_type: str = "atr", config=None):
        """
        Initialize strategy selector.

        Args:
            strategy_type: "atr" for ATR breakout, "ema" for simple EMA
            config: Optional config for scalping parameters
        """
        self.strategy_type = strategy_type
        self.config = config

        # Initialize strategies
        if strategy_type == "atr":
            self.primary_strategy = ATRBreakoutStrategy()
            logger.info("Using ATR Breakout Strategy (swing)")
        else:
            self.primary_strategy = SimpleEMAStrategy()
            logger.info("Using Simple EMA Strategy")

        # Initialize scalping strategy for fallback
        profit_threshold = getattr(config, 'scalp_profit_threshold_pct', 0.3) if config else 0.3
        self.scalping_strategy = ScalpingStrategy()

    def select_strategy(self, snapshot, position_size: float, equity: float, suppress_logs: bool = False) -> StrategySignal:
        """
        Select appropriate strategy based on market conditions.
        
        SUPPORTS SIMULTANEOUS SWING + SCALP:
        - Primary strategy (swing) evaluates independently
        - Scalping strategy evaluates independently
        - Can hold BOTH position types at once!

        Args:
            snapshot: Market snapshot
            position_size: Current position size (total, for backward compatibility)
            equity: Account equity

        Returns:
            Strategy signal from appropriate strategy
        """
        # Get position-type-specific sizes
        swing_position = self._get_position_by_type(snapshot.symbol, 'swing')
        scalp_position = self._get_position_by_type(snapshot.symbol, 'scalp')
        
        # First, try primary strategy (swing) - pass swing position only
        signal = self.primary_strategy.analyze(snapshot, swing_position, equity, suppress_logs)

        # If primary strategy says HOLD, check if scalping is appropriate
        # CRITICAL: Check scalp position separately, not total position!
        if signal.action == "hold":
            scalping_signal = self._check_scalping_fallback(snapshot, scalp_position, equity, suppress_logs)
            if scalping_signal and scalping_signal.action != "hold":
                if not suppress_logs:
                    logger.info(f"Primary strategy HOLD - scalping opportunity found (swing: {swing_position:.4f}, scalp: {scalp_position:.4f})")
                return scalping_signal

        return signal

    def _check_scalping_fallback(self, snapshot, scalp_position_size: float, equity: float, suppress_logs: bool = False) -> Optional[StrategySignal]:
        """
        Check if scalping strategy should be used as fallback.
        
        SIMULTANEOUS POSITIONS ENABLED:
        - Now checks SCALP position only (not total position)
        - Can scalp even if swing position exists!

        Args:
            snapshot: Market snapshot
            scalp_position_size: Current SCALP position size (not total)
            equity: Account equity

        Returns:
            Scalping signal if appropriate, None otherwise
        """
        # REMOVED RESTRICTION: Now allows scalping even with swing position!
        # Only check if we already have a SCALP position (not swing)
        if abs(scalp_position_size) > 0.0001:
            # Already have a scalp position - let strategy decide if it should close/hold
            pass

        try:
            scalping_signal = self.scalping_strategy.analyze(snapshot, scalp_position_size, equity, suppress_logs)

            # Only return scalping signal if it's an actual trade (not hold)
            if scalping_signal.action in ["long", "short", "close"]:
                logger.debug(f"Scalping strategy signal: {scalping_signal.action} (scalp pos: {scalp_position_size:.4f})")
                return scalping_signal

        except Exception as e:
            logger.debug(f"Scalping strategy failed: {e}")

        return None

    def _get_position_by_type(self, symbol: str, position_type: str) -> float:
        """
        Helper to get position size by type (swing or scalp).

        Accesses the global loop controller to get position tracking.
        """
        try:
            import api_server
            if hasattr(api_server, 'loop_controller_instance') and api_server.loop_controller_instance:
                loop_controller = api_server.loop_controller_instance
                # In new architecture, positions are tracked in cycle_controller.position_manager
                if hasattr(loop_controller, 'cycle_controller') and loop_controller.cycle_controller:
                    position_manager = loop_controller.cycle_controller.position_manager
                    return position_manager.get_position_by_type(symbol, position_type)
                # Fallback for old architecture
                elif hasattr(loop_controller, 'tracked_position_sizes'):
                    positions = loop_controller.tracked_position_sizes.get(symbol, {})
                    if isinstance(positions, dict):
                        return positions.get(position_type, 0.0)
                    return positions if position_type == 'swing' else 0.0
        except Exception as e:
            logger.debug(f"Could not get position by type: {e}")
        return 0.0
    
    def get_position_by_type(self, symbol: str, position_type: str) -> float:
        """
        Public method - delegates to _get_position_by_type.
        """
        return self._get_position_by_type(symbol, position_type)
