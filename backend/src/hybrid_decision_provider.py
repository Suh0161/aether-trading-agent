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

        # Log both strategy analyses for transparency (DEBUG to reduce spam)
        logger.debug(f"  Strategy Analysis - SWING: {swing_signal.action.upper()} (confidence: {swing_signal.confidence:.2f}) - {swing_signal.reason}")
        logger.debug(f"  Strategy Analysis - SCALP: {scalp_signal.action.upper()} (confidence: {scalp_signal.confidence:.2f}) - {scalp_signal.reason}")
        logger.debug(f"  Selected Strategy: {final_signal.position_type.upper()} {final_signal.action.upper()} (using strategy_selector logic)")

        # Apply liquidity filters
        final_signal = self.decision_filter.apply_liquidity_filters(snapshot, final_signal, position_size)

        # Get total margin used and all symbols for capital awareness (needed for AI filter)
        total_margin_used = 0.0
        all_symbols = []
        try:
            import api_server
            if hasattr(api_server, 'loop_controller_instance') and api_server.loop_controller_instance:
                loop_controller = api_server.loop_controller_instance
                position_manager = loop_controller.cycle_controller.position_manager
                # Get all symbols from config
                all_symbols = getattr(self.config, 'symbols', [snapshot.symbol])
                # Calculate total margin used across all positions
                # This is approximate - frontend_manager has the exact calculation
                for symbol in all_symbols:
                    swing_pos = position_manager.get_position_by_type(symbol, 'swing')
                    scalp_pos = position_manager.get_position_by_type(symbol, 'scalp')
                    if abs(swing_pos) > 0.0001 or abs(scalp_pos) > 0.0001:
                        # Approximate margin calculation (will be refined by frontend_manager)
                        entry_dict = position_manager.position_entry_prices.get(symbol, {})
                        if isinstance(entry_dict, dict):
                            swing_entry = entry_dict.get('swing', snapshot.price)
                            scalp_entry = entry_dict.get('scalp', snapshot.price)
                        else:
                            swing_entry = entry_dict if entry_dict else snapshot.price
                            scalp_entry = snapshot.price
                        # Estimate margin using leverage (more accurate)
                        if abs(swing_pos) > 0.0001:
                            lev_dict = position_manager.position_leverages.get(symbol, {})
                            if isinstance(lev_dict, dict):
                                leverage = lev_dict.get('swing', 1.0)
                            else:
                                leverage = lev_dict if lev_dict else 1.0
                            position_notional = abs(swing_pos) * swing_entry
                            total_margin_used += position_notional / leverage if leverage > 0 else position_notional
                        if abs(scalp_pos) > 0.0001:
                            lev_dict = position_manager.position_leverages.get(symbol, {})
                            if isinstance(lev_dict, dict):
                                leverage = lev_dict.get('scalp', 1.0)
                            else:
                                leverage = 1.0
                            position_notional = abs(scalp_pos) * scalp_entry
                            total_margin_used += position_notional / leverage if leverage > 0 else position_notional
        except Exception as e:
            logger.debug(f"Could not get total margin/positions: {e}")
            # Fallback: use current symbol only
            all_symbols = [snapshot.symbol]
            total_margin_used = abs(position_size) * snapshot.price if position_size != 0 else 0.0

        # Always apply AI filter for reasoning, even on hold decisions
        approved, ai_suggested_leverage, ai_confidence = self.ai_filter.filter_signal(
            snapshot, final_signal, position_size, equity, total_margin_used, all_symbols
        )

        # Use AI confidence if provided (AI overrides hardcoded strategy confidence)
        if ai_confidence is not None:
            original_confidence = final_signal.confidence
            final_signal.confidence = ai_confidence
            logger.info(f"AI confidence override: {ai_confidence:.2f} (strategy had: {original_confidence:.2f})")

        if final_signal.action == "hold":
            # For hold decisions, update reason with AI reasoning if available
            if approved and final_signal.confidence == 0.0:
                final_signal.reason = f"AI confirmed hold: No valid setups in current market conditions"
            return self.decision_filter.format_decision(final_signal)

        # For trade decisions, check if AI approved
        if not approved:
            # AI vetoed - change action to hold but preserve original confidence for analysis
            final_signal.action = "hold"
            final_signal.size_pct = 0.0
            final_signal.reason = f"AI vetoed setup (original confidence: {final_signal.confidence:.2f})"
            # Don't change confidence - preserve it for logging/analysis
            return self.decision_filter.format_decision(final_signal)

        # Adjust leverage based on confidence and account size
        base_leverage = self.risk_adjuster.get_smart_leverage(equity)
        logger.info(f"Leverage calculation: Account equity ${equity:,.0f} -> Base leverage {base_leverage:.1f}x")
        
        # Use AI leverage suggestion if provided and confidence >= 0.75 (use updated confidence after AI override)
        if ai_suggested_leverage is not None and final_signal.confidence >= 0.75:
            # Validate AI leverage is reasonable
            max_leverage = self.risk_adjuster.get_smart_leverage(equity)
            if 1.0 <= ai_suggested_leverage <= max_leverage * 1.2:  # Allow up to 20% over base
                final_signal.leverage = ai_suggested_leverage
                logger.info(f"AI leverage override: Using AI-suggested leverage {final_signal.leverage:.1f}x (confidence: {final_signal.confidence:.2f})")
            else:
                # AI leverage out of range, use calculated leverage
                logger.warning(f"AI leverage {ai_suggested_leverage:.1f}x out of range (1.0-{max_leverage*1.2:.1f}x), using calculated leverage")
                final_signal.leverage = self.risk_adjuster.adjust_leverage_by_confidence(base_leverage, final_signal.confidence)
                logger.info(f"Final leverage set: {final_signal.leverage:.1f}x (confidence: {final_signal.confidence:.2f})")
        else:
            # Use calculated leverage (no AI suggestion or confidence < 0.75)
            final_signal.leverage = self.risk_adjuster.adjust_leverage_by_confidence(base_leverage, final_signal.confidence)
            logger.info(f"Final leverage set: {final_signal.leverage:.1f}x (confidence: {final_signal.confidence:.2f})")

        # AI TP/SL/Trailing adjustment for high confidence signals
        adjusted_tp, adjusted_sl, trailing_pct = self.tp_sl_adjuster.adjust_tp_sl(snapshot, final_signal, position_size, equity)
        if adjusted_tp is not None:
            final_signal.take_profit = adjusted_tp
        if adjusted_sl is not None:
            final_signal.stop_loss = adjusted_sl
        if trailing_pct is not None:
            final_signal.trailing_stop_pct = trailing_pct
            logger.info(f"AI set trailing stop: {trailing_pct*100:.1f}% (swing trades only)")

        return self.decision_filter.format_decision(final_signal)