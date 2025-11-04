"""Decision filtering and validation logic."""

import logging

from src.strategy import StrategySignal
from src.strategy_utils.position_sizing import get_max_equity_usage

logger = logging.getLogger(__name__)


class DecisionFilter:
    """Handles decision validation and filtering."""

    def __init__(self):
        """Initialize decision filter."""
        pass

    def is_entry_decision(self, decision_json: str) -> bool:
        """
        Check if decision is an entry (long/short) decision.

        Args:
            decision_json: JSON decision string

        Returns:
            True if entry decision, False otherwise
        """
        try:
            import json
            decision = json.loads(decision_json)
            action = decision.get('action', '').lower()
            return action in ['long', 'short']
        except:
            return False

    def is_close_decision(self, decision_json: str) -> bool:
        """
        Check if decision is a close decision.

        Args:
            decision_json: JSON decision string

        Returns:
            True if close decision, False otherwise
        """
        try:
            import json
            decision = json.loads(decision_json)
            action = decision.get('action', '').lower()
            return action == 'close'
        except:
            return False

    def apply_liquidity_filters(self, snapshot, signal: StrategySignal, position_size: float = 0.0) -> StrategySignal:
        """
        Apply rule-based liquidity filters to strategy signal.

        Filters:
        1. Distance check: Only trade when near liquidity zones (< 2.0%) OR sweep detected
        2. Order book imbalance: Reduce confidence if imbalance opposes direction
        3. Sweep detection: Boost confidence/sizing when sweep aligns with direction
        4. Spread check: Reduce confidence if spread > 5bp (thin liquidity)

        Args:
            snapshot: Market snapshot
            signal: Strategy signal to filter
            position_size: Current position size (for Tier 1 data construction)

        Returns:
            Modified StrategySignal (may be changed to "hold" if filtered, or confidence/sizing adjusted)
        """
        try:
            # Get enhanced snapshot with Tier 2 data
            import api_server
            if not hasattr(api_server, 'loop_controller_instance') or not api_server.loop_controller_instance:
                return signal  # Can't access enhanced data, skip filter

            loop_controller = api_server.loop_controller_instance
            data_acq = loop_controller.data_acquisition

            # Fetch enhanced snapshot for this symbol
            enhanced_snapshot = data_acq.fetch_enhanced_snapshot(snapshot.symbol, position_size)

            if not enhanced_snapshot or not enhanced_snapshot.tier2:
                return signal  # No Tier 2 data available, skip filter

            tier2 = enhanced_snapshot.tier2

            # FILTER 1: Distance to liquidity zone
            if tier2.liquidity_zone_type and tier2.distance_to_liquidity_zone_pct is not None:
                distance = tier2.distance_to_liquidity_zone_pct

                # Conservative: Only trade when near zone (< 2.0%) OR sweep detected
                if distance > 2.0 and not tier2.liquidity_sweep_detected:
                    # Too far from liquidity zone and no sweep - skip trade
                    logger.info(
                        f"  |-- [LIQUIDITY FILTER] {snapshot.symbol} {signal.action.upper()}: "
                        f"Too far from zone ({distance:.2f}%), no sweep - BLOCKED"
                    )
                    return StrategySignal(
                        action="hold",
                        size_pct=0.0,
                        reason=f"Too far from liquidity zone ({distance:.2f}%), waiting for zone approach or sweep",
                        confidence=0.0,
                        symbol=snapshot.symbol,
                        position_type=signal.position_type
                    )
                elif distance < 0.5:
                    # Very close to zone - boost confidence slightly
                    logger.debug(f"  |-- [LIQUIDITY FILTER] Near zone ({distance:.2f}%) - slight boost")
                    signal.confidence = min(0.95, signal.confidence + 0.05)

            # FILTER 2: Order book imbalance check
            if signal.action == "long" and tier2.order_book_imbalance < -0.2:
                # Want to long but sellers are heavy (imbalance < -0.2)
                logger.info(
                    f"  |-- [LIQUIDITY FILTER] Order book opposes LONG "
                    f"(imbalance={tier2.order_book_imbalance:.3f}) - reducing confidence"
                )
                # Don't block, but reduce confidence
                signal.confidence = max(0.3, signal.confidence - 0.15)
                signal.reason += f" | OB opposes (imbalance={tier2.order_book_imbalance:.3f})"

            elif signal.action == "short" and tier2.order_book_imbalance > 0.2:
                # Want to short but buyers are heavy (imbalance > 0.2)
                logger.info(
                    f"  |-- [LIQUIDITY FILTER] Order book opposes SHORT "
                    f"(imbalance={tier2.order_book_imbalance:.3f}) - reducing confidence"
                )
                # Don't block, but reduce confidence
                signal.confidence = max(0.3, signal.confidence - 0.15)
                signal.reason += f" | OB opposes (imbalance={tier2.order_book_imbalance:.3f})"

            elif signal.action == "long" and tier2.order_book_imbalance > 0.2:
                # Long with buyers heavy - boost confidence
                logger.debug(f"  |-- [LIQUIDITY FILTER] Order book supports LONG (imbalance={tier2.order_book_imbalance:.3f})")
                signal.confidence = min(0.95, signal.confidence + 0.05)

            elif signal.action == "short" and tier2.order_book_imbalance < -0.2:
                # Short with sellers heavy - boost confidence
                logger.debug(f"  |-- [LIQUIDITY FILTER] Order book supports SHORT (imbalance={tier2.order_book_imbalance:.3f})")
                signal.confidence = min(0.95, signal.confidence + 0.05)

            # FILTER 3: Sweep detection boost/penalty
            if tier2.liquidity_sweep_detected:
                sweep_direction = tier2.sweep_direction
                sweep_confidence = tier2.sweep_confidence

                # Check if sweep direction aligns with trade direction
                if (signal.action == "long" and sweep_direction == "bullish") or \
                   (signal.action == "short" and sweep_direction == "bearish"):
                    # Sweep aligns with trade - BOOST confidence and sizing
                    sweep_boost = sweep_confidence * 0.2  # Up to +0.2 confidence boost
                    signal.confidence = min(0.95, signal.confidence + sweep_boost)

                    # Increase position size if confidence boost is significant
                    if sweep_boost > 0.1:
                        max_equity_pct = get_max_equity_usage()
                        signal.size_pct = min(signal.size_pct * 1.15, max_equity_pct)  # Up to 15% size boost

                    logger.info(
                        f"  |-- [LIQUIDITY FILTER] SWEEP DETECTED ({sweep_direction.upper()}, "
                        f"conf:{sweep_confidence:.2f}) - BOOSTING confidence (+{sweep_boost:.2f})"
                    )
                    signal.reason += f" | SWEEP({sweep_direction}, conf:{sweep_confidence:.2f}) BOOST"

                else:
                    # Sweep opposes trade - reduce confidence significantly
                    logger.warning(
                        f"  |-- [LIQUIDITY FILTER] Sweep {sweep_direction.upper()} OPPOSES "
                        f"{signal.action.upper()} - reducing confidence"
                    )
                    signal.confidence = max(0.3, signal.confidence - 0.2)
                    signal.reason += f" | Sweep {sweep_direction} opposes"

            # FILTER 4: Spread check (thin liquidity warning)
            if tier2.spread_bp > 5.0:  # Spread > 5bp = thin liquidity
                logger.warning(
                    f"  |-- [LIQUIDITY FILTER] Wide spread ({tier2.spread_bp:.2f}bp) - "
                    f"thin liquidity, reducing confidence"
                )
                signal.confidence = max(0.3, signal.confidence - 0.1)
                signal.reason += f" | Wide spread ({tier2.spread_bp:.2f}bp)"

            return signal

        except Exception as e:
            logger.warning(f"Liquidity filter error for {snapshot.symbol}: {e} - skipping filter")
            return signal  # On error, skip filter and proceed

    def format_decision(self, signal: StrategySignal) -> str:
        """
        Format strategy signal as JSON decision string.

        Args:
            signal: Strategy signal to format

        Returns:
            JSON string representation of the decision
        """
        import json

        decision = {
            "action": signal.action,
            "size_pct": signal.size_pct,
            "reason": signal.reason,
            "confidence": signal.confidence,
            "position_type": getattr(signal, 'position_type', 'swing')
        }

        # Add optional fields if they exist
        if signal.stop_loss is not None:
            decision["stop_loss"] = signal.stop_loss
        if signal.take_profit is not None:
            decision["take_profit"] = signal.take_profit
        if signal.leverage != 1.0:
            decision["leverage"] = signal.leverage
        if signal.risk_amount is not None:
            decision["risk_amount"] = signal.risk_amount
        if signal.reward_amount is not None:
            decision["reward_amount"] = signal.reward_amount

        return json.dumps(decision, separators=(',', ':'))
