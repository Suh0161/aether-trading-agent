#!/usr/bin/env python3
"""
Main entry point for the Autonomous Trading Agent.

This script loads configuration, initializes the loop controller,
and starts the trading agent with proper error handling.
"""

import argparse
import logging
import sys
from pathlib import Path

from src.config import Config
from src.loop_controller import LoopController


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging for the application.
    
    Args:
        verbose: If True, set log level to DEBUG, otherwise INFO
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Create logs directory if it doesn't exist
    Path("logs").mkdir(exist_ok=True)
    
    # Configure logging format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/agent.log", mode="a")
        ]
    )


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.
    
    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Autonomous Trading Agent - LLM-driven trading system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Run with default .env file
  python main.py --env .env.testnet # Run with custom env file
  python main.py --verbose          # Run with debug logging
  
Environment Variables:
  See .env.example for required configuration variables.
  
Safety:
  Always test on testnet before running in live mode!
  Set RUN_MODE=testnet in your .env file for safe testing.
        """
    )
    
    parser.add_argument(
        "--env",
        type=str,
        default=".env",
        help="Path to environment file (default: .env)"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="Autonomous Trading Agent v1.0.0"
    )
    
    return parser.parse_args()


def main() -> int:
    """
    Main entry point for the trading agent.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    # Parse command-line arguments
    args = parse_arguments()
    
    # Setup logging
    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 80)
    logger.info("AUTONOMOUS TRADING AGENT")
    logger.info("=" * 80)
    
    # Load configuration
    try:
        logger.info(f"Loading configuration from: {args.env}")
        
        # Set environment file path if not default
        if args.env != ".env":
            import os
            from dotenv import load_dotenv
            if not Path(args.env).exists():
                logger.error(f"Environment file not found: {args.env}")
                return 1
            load_dotenv(args.env, override=True)
        
        config = Config.from_env()
        logger.info("✓ Configuration loaded successfully")
        
    except ValueError as e:
        logger.error(f"✗ Configuration error: {e}")
        logger.error("Please check your .env file and ensure all required variables are set.")
        logger.error("See .env.example for reference.")
        return 1
    except Exception as e:
        logger.error(f"✗ Unexpected error loading configuration: {e}")
        return 1
    
    # Display run mode warning
    if config.run_mode == "live":
        logger.warning("!" * 80)
        logger.warning("!!! LIVE MODE ENABLED !!!")
        logger.warning("!!! REAL MONEY WILL BE TRADED !!!")
        logger.warning("!" * 80)
        logger.warning("Press Ctrl+C within 5 seconds to abort...")
        
        import time
        try:
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("\nAborted by user")
            return 0
    else:
        logger.info("=" * 80)
        logger.info("TESTNET MODE - Safe testing environment")
        logger.info("=" * 80)
    
    # Initialize loop controller
    try:
        logger.info("Initializing loop controller...")
        controller = LoopController(config)
        logger.info("✓ Loop controller initialized")
        
    except NotImplementedError as e:
        logger.error(f"✗ Initialization error: {e}")
        return 1
    except Exception as e:
        logger.error(f"✗ Failed to initialize loop controller: {e}", exc_info=True)
        return 1
    
    # Register signal handlers for graceful shutdown
    controller.register_signal_handlers()
    
    # Run startup tests
    try:
        logger.info("Running startup connectivity tests...")
        if not controller.startup():
            logger.error("✗ Startup tests failed")
            logger.error("Please check your API credentials and network connectivity.")
            return 1
        logger.info("✓ All startup tests passed")
        
    except Exception as e:
        logger.error(f"✗ Startup test error: {e}", exc_info=True)
        return 1
    
    # Start main loop
    try:
        logger.info("Starting main trading loop...")
        logger.info("Press Ctrl+C to stop gracefully")
        logger.info("=" * 80)
        
        controller.run()
        
        logger.info("=" * 80)
        logger.info("Agent stopped successfully")
        logger.info("=" * 80)
        return 0
        
    except KeyboardInterrupt:
        logger.info("\nKeyboard interrupt received")
        controller.shutdown()
        return 0
    except Exception as e:
        logger.error(f"✗ Fatal error in main loop: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
