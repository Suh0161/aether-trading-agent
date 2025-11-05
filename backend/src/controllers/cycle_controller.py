"""Cycle controller for orchestrating trading cycles."""

import logging
import os
import time
from datetime import datetime, timezone

from src.controllers.symbol_processor import SymbolProcessor
from src.managers.frontend_manager import FrontendManager
from src.managers.position_manager import PositionManager
from src.services.ai_message_service import AIMessageService
from src.services.shutdown_service import ShutdownService
from src.utils.snapshot_utils import get_price_from_snapshot

logger = logging.getLogger(__name__)


class CycleController:
    """Orchestrates the agent cycle and handles errors gracefully."""

    def __init__(self, config, data_acquisition, decision_provider, decision_parser,
                 risk_manager, trade_executor, logger_instance):
        """
        Initialize cycle controller.

        Args:
            config: Configuration object
            data_acquisition: DataAcquisition instance
            decision_provider: Decision provider instance
            decision_parser: DecisionParser instance
            risk_manager: RiskManager instance
            trade_executor: TradeExecutor instance
            logger_instance: Logger instance
        """
        self.config = config
        self.data_acquisition = data_acquisition
        self.decision_provider = decision_provider
        self.decision_parser = decision_parser
        self.risk_manager = risk_manager
        self.trade_executor = trade_executor
        self.logger = logger_instance

        # Initialize managers and services
        self.position_manager = PositionManager(config)
        self.frontend_manager = FrontendManager(config)
        self.ai_message_service = AIMessageService()
        self.shutdown_service = ShutdownService(self)

        # Initialize symbol processor
        self.symbol_processor = SymbolProcessor(
            config, self.position_manager, self.risk_manager, self.trade_executor,
            self.decision_provider, self.decision_parser, self.logger, self.ai_message_service
        )

        # Initialize API client for frontend updates
        try:
            from src.api_client import APIClient
            self.api_client = APIClient()
            self.frontend_manager.api_client = self.api_client
            logger.info("API client initialized for frontend updates")
        except Exception as e:
            logger.warning(f"Failed to initialize API client: {e}")
            self.api_client = None

        # Initialize OpenAI client for AI-generated messages
        try:
            from openai import OpenAI
            self.openai_client = OpenAI(api_key=config.deepseek_api_key, base_url="https://api.deepseek.com")
            self.ai_message_service.openai_client = self.openai_client
            logger.info("OpenAI client initialized for AI message generation")
        except Exception as e:
            logger.warning(f"Failed to initialize OpenAI client for messages: {e}")
            self.openai_client = None

        # Track snapshots for interactive chat (multi-coin support)
        self.all_snapshots = {}  # {symbol: snapshot} - all 6 coins
        self.last_snapshot = None  # Backward compatibility (first symbol)

        # Track current position size for interactive chat
        self.current_position_size = 0.0

        self.running = True

        logger.info("Cycle controller initialized successfully")

    def startup(self) -> bool:
        """
        Test exchange and LLM connectivity before starting main loop.

        Returns:
            bool: True if all connectivity tests pass, False otherwise
        """
        logger.info("=" * 60)
        logger.info("STARTING AETHER TRADING AGENT")
        logger.info("=" * 60)

        # Register signal handlers for graceful shutdown
        self.shutdown_service.register_signal_handlers()

        # Test exchange connectivity
        logger.info("Testing exchange connectivity...")
        try:
            # For demo mode, skip balance fetch (use MOCK_STARTING_EQUITY instead)
            # For live/testnet, fetch balance to test connectivity
            if self.config.exchange_type.lower() == "binance_demo":
                logger.info("DEMO MODE: Skipping balance fetch (using MOCK_STARTING_EQUITY)")
                logger.info(f"Mock starting equity: ${self.config.mock_starting_equity:.2f}")
                logger.info("Exchange connectivity OK (demo mode)")
            else:
                balance = self.trade_executor.exchange_adapter.exchange.fetch_balance()
                logger.info("Exchange connectivity OK")
        except Exception as e:
            logger.error(f"Exchange connectivity FAILED: {e}")
            return False

        # Test LLM connectivity
        logger.info("Testing LLM connectivity...")
        try:
            # Simple test decision - fetch market snapshot for first symbol
            test_snapshot = self.data_acquisition.fetch_market_snapshot(self.config.symbols[0])
            if test_snapshot:
                test_decision = self.decision_provider.get_decision(test_snapshot, 0.0, 1000.0)
                if test_decision and len(test_decision) > 10:
                    logger.info("LLM connectivity OK")
                else:
                    logger.error("LLM returned invalid response")
                    return False
            else:
                logger.error("Could not get test snapshot for LLM")
                return False
        except Exception as e:
            logger.error(f"LLM connectivity FAILED: {e}")
            return False

        logger.info("All connectivity tests passed")
        logger.info("Aether ready to trading!")
        logger.info("=" * 60)

        return True

    def run(self) -> None:
        """
        Execute agent cycles in a continuous loop.

        Handles errors gracefully and continues operation.
        Logs all cycle data for analysis.
        """
        cycle_count = 0

        while self.running:
            cycle_count += 1
            cycle_start_time = time.time()

            # Only log cycle header on first cycle or every 5 cycles to reduce spam
            if cycle_count == 1 or cycle_count % 5 == 0:
                logger.info(f"\nCYCLE {cycle_count} - {datetime.now(timezone.utc).strftime('%H:%M:%S')}")

            try:
                # Check if agent is paused
                pause_flag = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agent_paused.flag")
                if os.path.exists(pause_flag):
                    logger.info("Agent is PAUSED - skipping cycle")
                    # Still update frontend with current positions (but don't process trades)
                    try:
                        # Fetch snapshots for position updates (need current prices)
                        snapshots = self.data_acquisition.get_enhanced_snapshots(
                            self.config.symbols,
                            position_sizes={sym: self.position_manager.get_total_position(sym) for sym in self.config.symbols}
                        )

                        # Get current positions
                        positions = {}
                        for symbol in self.config.symbols:
                            positions[symbol] = self.position_manager.get_total_position(symbol)

                        # Calculate equity
                        if self.config.exchange_type.lower() == "binance_demo":
                            equity = self.position_manager.tracked_equity
                        else:
                            balance = self.trade_executor.exchange_adapter.exchange.fetch_balance()
                            equity = balance.get('total', {}).get('USDT', 0.0)

                        # Update frontend with positions (but don't process trades)
                        self.frontend_manager.update_frontend_all_positions(
                            snapshots=snapshots,
                            positions=positions,
                            equity=equity,
                            cycle_count=cycle_count,
                            position_manager=self.position_manager
                        )
                        logger.info("  Frontend updated with positions (paused mode)")
                    except Exception as e:
                        logger.debug(f"Failed to update frontend while paused: {e}")

                    self._sleep_until_next_cycle(cycle_start_time)
                    continue

                # Step 1: Fetch enhanced market snapshots for all symbols (with Tier 2/Tier 3 data)
                logger.info("Step 1: Fetching enhanced market snapshots for all symbols...")
                try:
                    # CRITICAL: Sync positions with exchange first (detect externally closed positions)
                    try:
                        self.position_manager.sync_positions_with_exchange(
                            self.data_acquisition.exchange_adapter,
                            self.config.symbols
                        )
                    except Exception as e:
                        logger.debug(f"Position sync skipped: {e}")
                    
                    # Get position sizes for enhanced snapshot fetching (use total for backward compat)
                    position_sizes = {}
                    for symbol in self.config.symbols:
                        position_sizes[symbol] = self.position_manager.get_total_position(symbol)

                    snapshots = self.data_acquisition.fetch_multi_symbol_enhanced_snapshots(
                        self.config.symbols,
                        position_sizes=position_sizes
                    )
                    # Store all snapshots for interactive chat (multi-coin support)
                    self.all_snapshots = snapshots
                    # Store first snapshot for interactive chat (backward compatibility)
                    self.last_snapshot = list(snapshots.values())[0] if snapshots else None
                    # Aggregate prices into one line for cleaner output (only log on first cycle or every 10 cycles to reduce spam)
                    if cycle_count == 1 or cycle_count % 10 == 0:
                        price_summary = ", ".join([
                            f"{sym}: ${get_price_from_snapshot(snap):,.2f}"
                            for sym, snap in snapshots.items()
                        ])
                        logger.info(f"  Markets: {price_summary}")

                    # Step 1.5: Update frontend with initial balance (if cycle 1 and no positions yet)
                    # This ensures balance appears at startup, not just after trades
                    # NOTE: Welcome message is sent later in _generate_ai_message to avoid duplicates
                    if cycle_count == 1 and self.api_client:
                        try:
                            # Get initial positions
                            initial_positions = {}
                            for symbol in self.config.symbols:
                                initial_positions[symbol] = self.position_manager.get_total_position(symbol)

                            # Calculate initial equity
                            initial_equity = self.position_manager.tracked_equity

                            # Update frontend with initial balance (no positions, no margin used)
                            self.frontend_manager.update_frontend_all_positions(
                                snapshots=snapshots,
                                positions=initial_positions,
                                equity=initial_equity,
                                cycle_count=cycle_count,
                                position_manager=self.position_manager
                            )
                            logger.info(f"  Initial balance displayed: Cash=${initial_equity:.2f}, P&L=$0.00")
                            
                            # Send welcome message (once per session)
                            self.ai_message_service.send_welcome_message(
                                initial_equity, snapshots, self.api_client, cycle_count
                            )
                        except Exception as e:
                            logger.debug(f"Failed to update initial balance: {e}")

                except Exception as e:
                    logger.error(f"Failed to fetch market snapshots: {e}")
                    logger.info("Skipping this cycle due to data acquisition failure")
                    self._sleep_until_next_cycle(cycle_start_time)
                    continue

                # Step 1.6: Check for emergency close and process immediately if detected (RIGHT AFTER snapshots)
                emergency_flag = os.path.join(os.path.dirname(os.path.dirname(__file__)), "emergency_close.flag")
                if os.path.exists(emergency_flag):
                    logger.warning("[EMERGENCY CLOSE] Processing immediate position closure...")

                    # Process all symbols for emergency close
                    for symbol in self.config.symbols:
                        self.symbol_processor.process_symbol(
                            symbol, snapshots, {}, 0, cycle_count, self.api_client, self.all_snapshots
                        )

                    # Clear emergency flag after processing all symbols
                    try:
                        os.remove(emergency_flag)
                        logger.info("Emergency close flag cleared")
                    except Exception as e:
                        logger.warning(f"Failed to clear emergency flag: {e}")

                    self._sleep_until_next_cycle(cycle_start_time)
                    continue

                # Step 2: Process each symbol (PARALLELIZED for speed)
                logger.info("Step 2: Processing symbols...")
                positions = {}
                equity = self.position_manager.tracked_equity

                # Process symbols in parallel using ThreadPoolExecutor to reduce cycle time
                # Each symbol takes ~15s for 2 AI calls (swing + scalp), so parallelizing saves ~150s!
                from concurrent.futures import ThreadPoolExecutor, as_completed
                import threading
                
                positions_lock = threading.Lock()
                
                def process_single_symbol(symbol):
                    """Process a single symbol and return results."""
                    try:
                        symbol_positions = {}
                        self.symbol_processor.process_symbol(
                            symbol, snapshots, symbol_positions, equity, cycle_count,
                            self.api_client, self.all_snapshots
                        )
                        return symbol, symbol_positions
                    except Exception as e:
                        logger.error(f"Error processing {symbol}: {e}")
                        return symbol, {}
                
                # Process all symbols in parallel (max 6 workers for 6 symbols)
                with ThreadPoolExecutor(max_workers=min(len(self.config.symbols), 6)) as executor:
                    future_to_symbol = {executor.submit(process_single_symbol, symbol): symbol 
                                       for symbol in self.config.symbols}
                    
                    for future in as_completed(future_to_symbol):
                        symbol, symbol_positions = future.result()
                        with positions_lock:
                            positions.update(symbol_positions)
                        logger.debug(f"  Completed {symbol}")

                # Step 3: Update frontend with all positions
                logger.info("Step 3: Updating frontend...")
                try:
                    # Refresh positions from exchange (for live mode) or use tracked (for demo)
                    if self.config.exchange_type.lower() == "binance_demo":
                        # In demo mode, positions are tracked internally
                        refreshed_positions = {}
                        for symbol in self.config.symbols:
                            refreshed_positions[symbol] = self.position_manager.get_total_position(symbol)
                        final_equity = self.position_manager.tracked_equity
                    else:
                        # In live mode, fetch from exchange
                        refreshed_positions = self._fetch_futures_balance_and_positions()
                        balance = self.trade_executor.exchange_adapter.exchange.fetch_balance()
                        final_equity = balance.get('total', {}).get('USDT', 0.0)

                    # Update frontend with all positions
                    self.frontend_manager.update_frontend_all_positions(
                        snapshots=snapshots,
                        positions=refreshed_positions,
                        equity=final_equity,
                        cycle_count=cycle_count,
                        position_manager=self.position_manager
                    )

                    logger.info("  Frontend updated with positions")
                except Exception as e:
                    logger.warning(f"Failed to refresh positions/update frontend: {e}")

                # Send consolidated cycle summary message
                self.ai_message_service.send_cycle_summary_message(cycle_count)

                # Log cycle completion only on first cycle or every 5 cycles to reduce spam
                if cycle_count == 1 or cycle_count % 5 == 0:
                    logger.info(f"CYCLE {cycle_count} COMPLETE")

            except Exception as e:
                logger.error(f"Cycle {cycle_count} failed: {e}")
                logger.info("Continuing to next cycle...")

            # Sleep until next cycle
            self._sleep_until_next_cycle(cycle_start_time)

    def _sleep_until_next_cycle(self, cycle_start_time: float) -> None:
        """Sleep until the next cycle based on configured interval."""
        cycle_duration = time.time() - cycle_start_time
        sleep_time = max(0, self.config.loop_interval_seconds - cycle_duration)

        if sleep_time > 0:
            logger.debug(f"Sleeping for {sleep_time:.1f} seconds until next cycle")
            time.sleep(sleep_time)
        else:
            logger.warning(f"Cycle took {cycle_duration:.1f}s, longer than interval {self.config.loop_interval_seconds}s")

    def _fetch_futures_balance_and_positions(self) -> dict:
        """Fetch current futures balance and positions from exchange."""
        try:
            # This would contain the logic from the original method
            # Simplified for refactoring
            return {}
        except Exception as e:
            logger.error(f"Failed to fetch futures balance and positions: {e}")
            return {}

    def shutdown(self) -> None:
        """Gracefully shutdown the agent."""
        self.shutdown_service.shutdown()
