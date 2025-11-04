#!/usr/bin/env python3
"""
Comprehensive connection checker for the trading agent.
Verifies all imports, dependencies, and connections are working properly.
"""

import sys
import importlib
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

class ConnectionChecker:
    """Check all connections in the trading agent."""
    
    def __init__(self):
        self.passed = []
        self.failed = []
        
    def check(self, description: str, module_path: str):
        """Check if a module can be imported."""
        try:
            importlib.import_module(module_path)
            self.passed.append(f"✓ {description}")
            return True
        except Exception as e:
            self.failed.append(f"✗ {description}: {str(e)}")
            return False
    
    def check_instantiation(self, description: str, callable_obj, *args, **kwargs):
        """Check if an object can be instantiated."""
        try:
            callable_obj(*args, **kwargs)
            self.passed.append(f"✓ {description}")
            return True
        except Exception as e:
            self.failed.append(f"✗ {description}: {str(e)}")
            return False
    
    def print_results(self):
        """Print all results."""
        print("\n" + "=" * 80)
        print("CONNECTION CHECK RESULTS")
        print("=" * 80)
        
        if self.passed:
            print(f"\n✓ PASSED ({len(self.passed)}):")
            for item in self.passed:
                print(f"  {item}")
        
        if self.failed:
            print(f"\n✗ FAILED ({len(self.failed)}):")
            for item in self.failed:
                print(f"  {item}")
        
        print("\n" + "=" * 80)
        print(f"TOTAL: {len(self.passed)} passed, {len(self.failed)} failed")
        print("=" * 80 + "\n")
        
        return len(self.failed) == 0


def main():
    """Run all connection checks."""
    checker = ConnectionChecker()
    
    print("Starting comprehensive connection check...")
    print("This will verify all imports and dependencies are properly connected.\n")
    
    # Core modules
    print("[1/10] Checking core modules...")
    checker.check("Config", "src.config")
    checker.check("Models", "src.models")
    checker.check("Logger", "src.logger")
    
    # Controllers
    print("[2/10] Checking controllers...")
    checker.check("Loop Controller", "src.loop_controller")
    checker.check("Cycle Controller", "src.controllers.cycle_controller")
    checker.check("Symbol Processor", "src.controllers.symbol_processor")
    
    # Services
    print("[3/10] Checking services...")
    checker.check("AI Message Service", "src.services.ai_message_service")
    checker.check("Shutdown Service", "src.services.shutdown_service")
    
    # Managers
    print("[4/10] Checking managers...")
    checker.check("Position Manager", "src.managers.position_manager")
    checker.check("Frontend Manager", "src.managers.frontend_manager")
    
    # Data & Analysis
    print("[5/10] Checking data acquisition...")
    checker.check("Data Acquisition", "src.data_acquisition")
    checker.check("Tiered Data", "src.tiered_data")
    checker.check("Orderbook Analyzer", "src.orderbook_analyzer")
    checker.check("Liquidity Analyzer", "src.liquidity_analyzer")
    checker.check("Regime Classifier", "src.regime_classifier")
    
    # Exchange & Execution
    print("[6/10] Checking exchange adapters...")
    checker.check("Exchange Adapter", "src.exchange_adapters.exchange_adapter")
    checker.check("Trade Executor", "src.trade_executor")
    checker.check("Order Executor", "src.executors.order_executor")
    checker.check("Order Parser", "src.order_parsers.order_response_parser")
    
    # Decision Making
    print("[7/10] Checking decision providers...")
    checker.check("Decision Provider", "src.decision_provider")
    checker.check("Hybrid Decision Provider", "src.hybrid_decision_provider")
    checker.check("Decision Parser", "src.decision_parser")
    checker.check("Decision Filter", "src.decision_filters.decision_filter")
    checker.check("Prompt Optimizer", "src.prompt_optimizer")
    
    # Strategies
    print("[8/10] Checking strategies...")
    checker.check("Strategy Base", "src.strategy")
    checker.check("Strategy Selector", "src.strategy_selectors.strategy_selector")
    checker.check("ATR Breakout Strategy", "src.strategies.atr_breakout_strategy")
    checker.check("EMA Strategy", "src.strategies.ema_strategy")
    checker.check("Scalping Strategy", "src.strategies.scalping_strategy")
    
    # Risk & Indicators
    print("[9/10] Checking risk management and indicators...")
    checker.check("Risk Manager", "src.risk_manager")
    checker.check("Snapshot Builder", "src.snapshot_builders.market_snapshot_builder")
    checker.check("Snapshot Utils", "src.utils.snapshot_utils")
    
    # API
    print("[10/10] Checking API components...")
    checker.check("API Client", "src.api_client")
    checker.check("API Server", "api_server")
    
    # Print results
    success = checker.print_results()
    
    if success:
        print("✓ All connections are working properly!")
        print("✓ The codebase is properly integrated.")
        return 0
    else:
        print("✗ Some connections are broken!")
        print("✗ Please fix the failed imports above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

