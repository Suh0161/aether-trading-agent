"""Hybrid decision provider: Rule-based strategy + AI filter."""

import logging
from typing import Optional
from openai import OpenAI
from src.models import MarketSnapshot
from src.ai_processors.ai_filter import AIFilter
from src.ai_processors.tp_sl_adjuster import TPSLAdjuster
from src.strategy_selectors.strategy_selector import StrategySelector
from src.decision_filters.decision_filter import DecisionFilter
from src.risk_adjusters.risk_adjuster import RiskAdjuster
from src.strategy import StrategySignal

logger = logging.getLogger(__name__)


class HybridDecisionProvider:
    """
    Hybrid approach: Rule-based strategy generates signals, AI filters them.
    
    This is the "crypto-realistic" approach:
    1. Strategy (ATR breakout) generates trade signals
    2. AI (DeepSeek) acts as risk filter to veto bad setups
    3. Only execute if both strategy AND AI approve
    """
    
    def __init__(self, api_key: str, strategy_type: str = "atr", config=None):
        """
        Initialize hybrid decision provider.
        
        Args:
            api_key: DeepSeek API key
            strategy_type: "atr" for ATR breakout, "ema" for simple EMA
            config: Optional Config object (for profit threshold)
        """
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.config = config
        
        # Initialize modular components
        self.ai_filter = AIFilter(self.client)
        self.tp_sl_adjuster = TPSLAdjuster(self.client)
        self.strategy_selector = StrategySelector(strategy_type, config)
        self.decision_filter = DecisionFilter()
        self.risk_adjuster = RiskAdjuster()
    
    def _get_position_by_type(self, symbol: str, position_type: str) -> float:
        """Helper to get position size by type (swing or scalp)."""
        try:
            import api_server
            if hasattr(api_server, 'loop_controller_instance') and api_server.loop_controller_instance:
                loop_controller = api_server.loop_controller_instance
                # In new architecture, positions are tracked in cycle_controller.position_manager
                if hasattr(loop_controller, 'cycle_controller') and loop_controller.cycle_controller:
                    position_manager = loop_controller.cycle_controller.position_manager
                    return position_manager.get_position_by_type(symbol, position_type)
                # Fallback for old architecture (if cycle_controller doesn't exist)
                elif hasattr(loop_controller, 'tracked_position_sizes'):
                    positions = loop_controller.tracked_position_sizes.get(symbol, {})
                    if isinstance(positions, dict):
                        return positions.get(position_type, 0.0)
                    # Backward compatibility: if old format (single value), return 0 for opposite type
                    return positions if position_type == 'swing' else 0.0
        except Exception as e:
            logger.debug(f"Could not get position by type: {e}")
        return 0.0
    
    def get_decision(self, snapshot: MarketSnapshot, position_size: float, equity: float) -> str:
        """
        Get trading decision using hybrid approach with simultaneous swing+scalp support.

        Args:
            snapshot: Current market snapshot
            position_size: Current total position size
            equity: Account equity

        Returns:
            JSON string with decision (may include position_type)
        """
        # Get position sizes by type
        swing_position = self._get_position_by_type(snapshot.symbol, 'swing')
        scalp_position = self._get_position_by_type(snapshot.symbol, 'scalp')

        # Use strategy_selector.select_strategy() which handles swing-first, then scalping fallback logic
        # Pass suppress_logs=True to avoid duplicate logging during selection
        final_signal = self.strategy_selector.select_strategy(snapshot, 0.0, equity, suppress_logs=True)

        # For logging, analyze both strategies individually (with logging enabled)
        swing_signal = self.strategy_selector.primary_strategy.analyze(snapshot, swing_position, equity, suppress_logs=False)
        swing_signal.position_type = "swing"

        scalp_signal = self.strategy_selector.scalping_strategy.analyze(snapshot, scalp_position, equity, suppress_logs=False)
        scalp_signal.position_type = "scalp"

        # Log both strategy analyses for transparency
        logger.info(f"  Strategy Analysis - SWING: {swing_signal.action.upper()} (confidence: {swing_signal.confidence:.2f}) - {swing_signal.reason}")
        logger.info(f"  Strategy Analysis - SCALP: {scalp_signal.action.upper()} (confidence: {scalp_signal.confidence:.2f}) - {scalp_signal.reason}")
        logger.info(f"  Selected Strategy: {final_signal.position_type.upper()} {final_signal.action.upper()} (using strategy_selector logic)")

        # Apply liquidity filters
        final_signal = self.decision_filter.apply_liquidity_filters(snapshot, final_signal, position_size)

        if final_signal.action == "hold":
            return self.decision_filter.format_decision(final_signal)

        # Apply AI filter
        if not self.ai_filter.filter_signal(snapshot, final_signal, position_size, equity):
            # AI vetoed - change action to hold but preserve original confidence for analysis
            final_signal.action = "hold"
            final_signal.size_pct = 0.0
            final_signal.reason = f"AI vetoed setup (original confidence: {final_signal.confidence:.2f})"
            # Don't change confidence - preserve it for logging/analysis
            return self.decision_filter.format_decision(final_signal)

        # Adjust leverage based on confidence and account size
        base_leverage = self.risk_adjuster.get_smart_leverage(equity)
        logger.info(f"Leverage calculation: Account equity ${equity:,.0f} -> Base leverage {base_leverage:.1f}x")
        final_signal.leverage = self.risk_adjuster.adjust_leverage_by_confidence(base_leverage, final_signal.confidence)
        logger.info(f"Final leverage set: {final_signal.leverage:.1f}x (confidence: {final_signal.confidence:.2f})")

        # AI TP/SL adjustment for high confidence signals
        adjusted_tp, adjusted_sl = self.tp_sl_adjuster.adjust_tp_sl(snapshot, final_signal, position_size, equity)
        if adjusted_tp is not None:
            final_signal.take_profit = adjusted_tp
        if adjusted_sl is not None:
            final_signal.stop_loss = adjusted_sl

        return self.decision_filter.format_decision(final_signal)