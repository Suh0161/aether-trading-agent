"""Shutdown service for graceful application termination."""

import logging
import signal

logger = logging.getLogger(__name__)


class ShutdownService:
    """Service for handling graceful shutdown operations."""

    def __init__(self, loop_controller):
        """
        Initialize shutdown service.

        Args:
            loop_controller: Reference to the loop controller for shutdown operations
        """
        self.loop_controller = loop_controller

    def shutdown(self) -> None:
        """
        Gracefully shutdown the agent.

        Sets running flag to false, allowing current iteration to complete.
        """
        logger.info("\n" + "=" * 60)
        logger.info("SHUTDOWN SIGNAL RECEIVED")
        logger.info("=" * 60)
        logger.info("Completing current iteration before shutdown...")
        self.loop_controller.running = False

    def register_signal_handlers(self) -> None:
        """
        Register signal handlers for graceful shutdown.

        Handles SIGINT (Ctrl+C) and SIGTERM (kill command).
        """
        def signal_handler(signum, frame):
            signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
            logger.info(f"\nReceived {signal_name}")
            self.shutdown()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        logger.info("Signal handlers registered (SIGINT, SIGTERM)")
