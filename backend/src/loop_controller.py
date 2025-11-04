"""Loop controller for the Autonomous Trading Agent."""

import logging

from src.config import Config
from src.controllers.cycle_controller import CycleController
from src.data_acquisition import DataAcquisition
from src.decision_provider import DecisionProvider, DeepSeekDecisionProvider
from src.decision_parser import DecisionParser
from src.logger import Logger
from src.risk_manager import RiskManager
from src.trade_executor import TradeExecutor


logger = logging.getLogger(__name__)


class LoopController:
    """Orchestrates the agent cycle and handles errors gracefully."""

    def __init__(self, config: Config):
        """
        Initialize loop controller with all components.

        Args:
            config: Configuration object
        """
        self.config = config

        # Initialize all components
        logger.info("Initializing loop controller components...")

        self.data_acquisition = DataAcquisition(config)
        self.decision_provider = self._init_decision_provider(config)
        self.decision_parser = DecisionParser()
        self.risk_manager = RiskManager(config)
        self.trade_executor = TradeExecutor(config)
        self.logger = Logger("logs/agent_log.jsonl")

        # Initialize the cycle controller with all components
        self.cycle_controller = CycleController(
            config, self.data_acquisition, self.decision_provider, self.decision_parser,
            self.risk_manager, self.trade_executor, self.logger
        )

        logger.info("Loop controller initialized successfully")

    def _init_decision_provider(self, config: Config) -> DecisionProvider:
        """
        Initialize decision provider based on configuration.

        Args:
            config: Configuration object

        Returns:
            Configured decision provider instance

        Raises:
            ValueError: If decision provider type is not supported
        """
        strategy_mode = config.strategy_mode.lower()

        if strategy_mode == "hybrid_atr":
            logger.info("Initializing HYBRID mode: ATR Breakout Strategy + AI Filter")
            from src.hybrid_decision_provider import HybridDecisionProvider
            return HybridDecisionProvider(config.deepseek_api_key, strategy_type="atr", config=config)
        elif strategy_mode == "hybrid_ema":
            logger.info("Initializing HYBRID mode: Simple EMA Strategy + AI Filter")
            from src.hybrid_decision_provider import HybridDecisionProvider
            return HybridDecisionProvider(config.deepseek_api_key, strategy_type="ema", config=config)
        elif strategy_mode == "ai_only":
            logger.info("Initializing AI-ONLY mode: DeepSeek makes all decisions")
            return DeepSeekDecisionProvider(config.deepseek_api_key)
        else:
            raise ValueError(f"Unsupported strategy mode: {strategy_mode}. Use 'hybrid_atr', 'hybrid_ema', or 'ai_only'")

    def startup(self) -> bool:
        """Delegate startup to cycle controller."""
        return self.cycle_controller.startup()

    def run(self) -> None:
        """Delegate run to cycle controller."""
        self.cycle_controller.run()

    def shutdown(self) -> None:
        """Delegate shutdown to cycle controller."""
        self.cycle_controller.shutdown()

    def register_signal_handlers(self) -> None:
        """Delegate signal handler registration to cycle controller."""
        self.cycle_controller.shutdown_service.register_signal_handlers()
