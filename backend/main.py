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


def setup_logging(verbose: bool = False, json_logs: bool = False) -> None:
    """
    Configure logging for the application.
    
    Args:
        verbose: If True, set log level to DEBUG, otherwise INFO
        json_logs: If True, enable JSON structured logging
    """
    import json
    from datetime import datetime
    
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Create logs directory if it doesn't exist
    Path("logs").mkdir(exist_ok=True)
    
    if json_logs:
        # JSON structured logging format
        class JSONFormatter(logging.Formatter):
            def format(self, record):
                log_entry = {
                    "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno
                }
                # Add exception info if present
                if record.exc_info:
                    log_entry["exception"] = self.formatException(record.exc_info)
                return json.dumps(log_entry)
        
        formatter = JSONFormatter()
    else:
        # Standard text logging format
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        date_format = "%Y-%m-%d %H:%M:%S"
        formatter = logging.Formatter(log_format, date_format)
    
    # Configure root logger
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/agent.log", mode="a")
    ]
    
    # Apply formatter to all handlers
    for handler in handlers:
        handler.setFormatter(formatter)
    
    logging.basicConfig(
        level=log_level,
        handlers=handlers
    )
    
    # If JSON logging enabled, also create a separate JSON log file
    if json_logs:
        json_handler = logging.FileHandler("logs/agent.json", mode="a")
        json_handler.setFormatter(formatter)
        logging.root.addHandler(json_handler)
    
    # Reduce noisy third-party loggers (suppress HTTP URL spam and API retries)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("openai._base_client").setLevel(logging.WARNING)  # Suppress retry messages


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
        "--json-logs",
        action="store_true",
        help="Enable JSON structured logging (outputs to logs/agent.json)"
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
    setup_logging(verbose=args.verbose, json_logs=args.json_logs)
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 80)
    logger.info("AETHER TRADING AGENT")
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
        logger.info("[OK] Configuration loaded successfully")
        
    except ValueError as e:
        logger.error(f"[ERROR] Configuration error: {e}")
        logger.error("Please check your .env file and ensure all required variables are set.")
        logger.error("See .env.example for reference.")
        return 1
    except Exception as e:
        logger.error(f"[ERROR] Unexpected error loading configuration: {e}")
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
        logger.info("[OK] Loop controller initialized")
        
    except NotImplementedError as e:
        logger.error(f"[ERROR] Initialization error: {e}")
        return 1
    except Exception as e:
        logger.error(f"[ERROR] Failed to initialize loop controller: {e}", exc_info=True)
        return 1
    
    # Register signal handlers for graceful shutdown
    controller.register_signal_handlers()
    
    # Run startup tests
    try:
        logger.info("Running startup connectivity tests...")
        if not controller.startup():
            logger.error("[ERROR] Startup tests failed")
            logger.error("Please check your API credentials and network connectivity.")
            return 1
        logger.info("[OK] All startup tests passed")
        
    except Exception as e:
        logger.error(f"[ERROR] Startup test error: {e}", exc_info=True)
        return 1
    
    # Start API server in background thread
    try:
        import threading
        import uvicorn
        import api_server
        
        # Register controller BEFORE starting API server
        api_server.loop_controller_instance = controller
        logger.info("Loop controller registered with API server")
        
        def run_api_server():
            try:
                logger.info("Starting API server thread...")
                uvicorn.run(api_server.app, host="0.0.0.0", port=8000, log_level="warning")
            except Exception as e:
                logger.error(f"API server thread crashed: {e}", exc_info=True)
        
        api_thread = threading.Thread(target=run_api_server, daemon=True)
        api_thread.start()
        
        # Give API server a moment to initialize
        import time
        time.sleep(2)
        
        # Verify API server is actually running
        try:
            import requests
            response = requests.get("http://localhost:8000/", timeout=2)
            if response.status_code == 200:
                logger.info("API server started successfully on http://0.0.0.0:8000")
            else:
                logger.warning(f"API server responded with status {response.status_code}")
        except Exception as e:
            logger.warning(f"API server health check failed: {e}")
            logger.warning("Frontend may not be able to connect. Check if port 8000 is available.")
    except Exception as e:
        logger.warning(f"Failed to start API server: {e}", exc_info=True)
        logger.warning("Interactive chat will not be available")
    
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
        logger.error(f"[ERROR] Fatal error in main loop: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
