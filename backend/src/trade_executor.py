"""Trade execution layer for the Autonomous Trading Agent."""

import logging
from typing import Optional
from src.config import Config
from src.models import DecisionObject, MarketSnapshot, ExecutionResult
from src.exchange_adapters.exchange_adapter import ExchangeAdapter
from src.order_validators.order_validator import OrderValidator
from src.position_calculators.order_sizer import OrderSizer
from src.order_parsers.order_response_parser import OrderResponseParser
from src.executors.order_executor import OrderExecutor


logger = logging.getLogger(__name__)


class TradeExecutor:
    """Handles trade execution on the exchange."""

    def __init__(self, config: Config):
        """
        Initialize the trade executor with exchange configuration.

        Args:
            config: Configuration object containing exchange credentials and settings
        """
        self.config = config

        # Initialize modular components
        self.exchange_adapter = ExchangeAdapter(config)
        self.order_validator = OrderValidator()
        self.order_sizer = OrderSizer(self.exchange_adapter.exchange)
        self.order_parser = OrderResponseParser(self.exchange_adapter.exchange, config)
        self.order_executor = OrderExecutor(self.exchange_adapter.exchange, config, self.order_parser)

    def execute(
        self,
        decision: DecisionObject,
        snapshot: MarketSnapshot,
        position_size: float,
        equity: float
    ) -> ExecutionResult:
        """
        Execute a trading decision on the exchange.

        Args:
            decision: Parsed decision object from LLM
            snapshot: Current market snapshot
            position_size: Current position size (positive for long, negative for short)
            equity: Current account equity

        Returns:
            ExecutionResult with execution details or error
        """
        action = decision.action.lower()

        # Handle hold action - no execution needed
        if action == "hold":
            logger.info("Action is 'hold', no execution needed")
            return ExecutionResult(
                executed=False,
                order_id=None,
                filled_size=None,
                fill_price=None,
                error=None
            )

        try:
            # Handle close action
            if action == "close":
                # Check if this is an emergency close
                is_emergency = 'emergency' in decision.reason.lower()
                return self.order_executor.execute_close(snapshot.symbol, position_size, snapshot.price, is_emergency)

            # Calculate order size for long/short actions (with leverage)
            leverage = getattr(decision, 'leverage', 1.0)  # Default to 1.0 if not provided
            confidence = getattr(decision, 'confidence', None)  # Get AI confidence for leverage adjustment
            confidence_str = f"{confidence:.2f}" if confidence is not None else 'N/A'
            logger.info(f"Trade execution: Requested leverage {int(leverage)}x for {action.upper()} {decision.size_pct*100:.1f}% position (confidence: {confidence_str})")

            # Pass confidence to order_sizer for smart money leverage adjustment
            order_size, actual_leverage, capital_amount = self.order_sizer.calculate_order_size(
                snapshot.symbol, equity, decision.size_pct, snapshot.price, leverage, confidence
            )
            
            # Store capital_amount in decision for margin calculation
            decision.capital_amount = capital_amount

            # Update decision with actual leverage used (may be higher for small accounts)
            if actual_leverage != leverage:
                logger.info(f"Leverage adjusted: {int(leverage)}x -> {int(actual_leverage)}x (minimum order size requirement)")
                decision.leverage = actual_leverage
            else:
                logger.info(f"Leverage confirmed: {int(actual_leverage)}x")

            if order_size <= 0:
                logger.warning(f"Calculated order size is {order_size}, skipping execution")
                return ExecutionResult(
                    executed=False,
                    order_id=None,
                    filled_size=None,
                    fill_price=None,
                    error="Order size is zero or negative"
                )

            # Final validation: Check minimum notional value (symbol-specific)
            # Note: order_sizer already validates, but this is a final safety check
            try:
                min_notional, _, _ = self.order_sizer._get_symbol_minimums(snapshot.symbol)
                # Demo safety floor: enforce $20 even if API reports lower
                try:
                    if str(self.config.exchange_type).lower() == 'binance_demo' and (min_notional is None or min_notional < 20):
                        min_notional = 20.0
                except Exception:
                    pass
                actual_notional = order_size * snapshot.price
                if actual_notional < min_notional:
                    logger.warning(
                        f"Order notional ${actual_notional:.2f} below minimum ${min_notional:.2f} "
                        f"for {snapshot.symbol}, skipping execution "
                        f"(order size: {order_size:.8f}, price: ${snapshot.price:.2f})"
                    )
                    return ExecutionResult(
                        executed=False,
                        order_id=None,
                        filled_size=None,
                        fill_price=None,
                        error=f"Order notional ${actual_notional:.2f} below minimum ${min_notional:.2f}"
                    )
            except Exception as e:
                logger.debug(f"Could not validate minimum notional: {e}, proceeding with execution")

            # Execute long or short action
            if action == "long":
                return self.order_executor.execute_long(snapshot.symbol, order_size)
            elif action == "short":
                return self.order_executor.execute_short(snapshot.symbol, order_size)
            else:
                logger.error(f"Unknown action: {action}")
                return ExecutionResult(
                    executed=False,
                    order_id=None,
                    filled_size=None,
                    fill_price=None,
                    error=f"Unknown action: {action}"
                )

        except Exception as e:
            logger.error(f"Execution error: {str(e)}")
            return ExecutionResult(
                executed=False,
                order_id=None,
                filled_size=None,
                fill_price=None,
                error=str(e)
            )