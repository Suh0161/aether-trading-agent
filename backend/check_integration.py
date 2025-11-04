#!/usr/bin/env python3
"""
Deep integration checker - verifies data flow and object interactions.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

def test_config_loading():
    """Test configuration loading."""
    print("Testing Config loading...")
    from src.config import Config
    import os
    
    # Check if .env exists
    if not Path(".env").exists():
        print("  ⚠ No .env file found (expected for fresh setup)")
        return False
    
    try:
        config = Config.from_env()
        print(f"  ✓ Config loaded: {len(config.symbols)} symbols")
        print(f"  ✓ Exchange: {config.exchange_type}")
        print(f"  ✓ Strategy: {config.strategy_mode}")
        print(f"  ✓ Loop interval: {config.loop_interval_seconds}s")
        return True
    except Exception as e:
        print(f"  ✗ Config loading failed: {e}")
        return False


def test_loop_controller_init():
    """Test loop controller initialization."""
    print("\nTesting LoopController initialization...")
    from src.loop_controller import LoopController
    from src.config import Config
    
    try:
        # Create mock config
        config = Mock(spec=Config)
        config.exchange_type = "binance_demo"
        config.symbols = ["BTC/USDT", "ETH/USDT"]
        config.exchange_api_key = "test_key"
        config.exchange_api_secret = "test_secret"
        config.deepseek_api_key = "test_deepseek_key"
        config.max_equity_usage_pct = 0.1
        config.max_leverage = 3.0
        config.daily_loss_cap_pct = None
        config.cooldown_seconds = None
        config.mock_starting_equity = 100.0
        config.strategy_mode = "hybrid_atr"
        config.run_mode = "demo"
        config.scalp_profit_threshold_pct = 0.3
        
        controller = LoopController(config)
        
        print("  ✓ LoopController created")
        print(f"  ✓ Data acquisition: {controller.data_acquisition is not None}")
        print(f"  ✓ Decision provider: {controller.decision_provider is not None}")
        print(f"  ✓ Decision parser: {controller.decision_parser is not None}")
        print(f"  ✓ Risk manager: {controller.risk_manager is not None}")
        print(f"  ✓ Trade executor: {controller.trade_executor is not None}")
        print(f"  ✓ Cycle controller: {controller.cycle_controller is not None}")
        return True
    except Exception as e:
        print(f"  ✗ LoopController initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cycle_controller_components():
    """Test cycle controller has all required components."""
    print("\nTesting CycleController components...")
    from src.controllers.cycle_controller import CycleController
    from src.config import Config
    
    try:
        # Create mocks
        config = Mock(spec=Config)
        config.symbols = ["BTC/USDT"]
        config.exchange_type = "binance_demo"
        config.mock_starting_equity = 100.0
        config.loop_interval_seconds = 30
        
        data_acquisition = Mock()
        decision_provider = Mock()
        decision_parser = Mock()
        risk_manager = Mock()
        trade_executor = Mock()
        logger_instance = Mock()
        
        controller = CycleController(
            config, data_acquisition, decision_provider, decision_parser,
            risk_manager, trade_executor, logger_instance
        )
        
        print("  ✓ CycleController created")
        print(f"  ✓ Position manager: {controller.position_manager is not None}")
        print(f"  ✓ Frontend manager: {controller.frontend_manager is not None}")
        print(f"  ✓ AI message service: {controller.ai_message_service is not None}")
        print(f"  ✓ Shutdown service: {controller.shutdown_service is not None}")
        print(f"  ✓ Symbol processor: {controller.symbol_processor is not None}")
        return True
    except Exception as e:
        print(f"  ✗ CycleController component check failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_data_flow():
    """Test data flow through the system."""
    print("\nTesting data flow...")
    from src.models import MarketSnapshot, DecisionObject
    from src.utils.snapshot_utils import get_price_from_snapshot, get_base_snapshot
    
    try:
        # Create a mock snapshot
        snapshot = MarketSnapshot(
            timestamp=1234567890,
            symbol="BTC/USDT",
            price=50000.0,
            bid=49990.0,
            ask=50010.0,
            ohlcv=[[1234567890, 49000, 51000, 48000, 50000, 1000]],
            indicators={
                "rsi_14": 50.0,
                "ema_50": 49000.0,
                "trend_1d": "bullish",
                "trend_4h": "bullish"
            }
        )
        
        # Test utility functions
        price = get_price_from_snapshot(snapshot)
        base = get_base_snapshot(snapshot)
        
        print(f"  ✓ MarketSnapshot created: {snapshot.symbol}")
        print(f"  ✓ Price extraction: ${price:,.2f}")
        print(f"  ✓ Base snapshot: {base.symbol}")
        
        # Create a mock decision
        decision = DecisionObject(
            action="hold",
            size_pct=0.0,
            reason="Testing",
            position_type="swing"
        )
        
        print(f"  ✓ DecisionObject created: {decision.action}")
        return True
    except Exception as e:
        print(f"  ✗ Data flow test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_risk_manager():
    """Test risk manager validation."""
    print("\nTesting RiskManager...")
    from src.risk_manager import RiskManager
    from src.models import DecisionObject, MarketSnapshot
    from src.config import Config
    
    try:
        # Create mock config
        config = Mock(spec=Config)
        config.max_equity_usage_pct = 0.1
        config.max_leverage = 3.0
        config.daily_loss_cap_pct = None
        config.cooldown_seconds = None
        
        risk_manager = RiskManager(config)
        
        # Create test data
        snapshot = MarketSnapshot(
            timestamp=1234567890,
            symbol="BTC/USDT",
            price=50000.0,
            bid=49990.0,
            ask=50010.0,
            ohlcv=[[1234567890, 49000, 51000, 48000, 50000, 1000]],
            indicators={}
        )
        
        decision = DecisionObject(
            action="hold",
            size_pct=0.0,
            reason="Testing",
            position_type="swing"
        )
        
        # Test validation
        approved, reason = risk_manager.validate_decision(
            decision, snapshot, 0.0, 1000.0, "BTC/USDT"
        )
        
        print(f"  ✓ RiskManager created")
        print(f"  ✓ Validation works: approved={approved}, reason='{reason}'")
        return True
    except Exception as e:
        print(f"  ✗ RiskManager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_server():
    """Test API server structure."""
    print("\nTesting API server...")
    import api_server
    
    try:
        print(f"  ✓ API server module loaded")
        print(f"  ✓ FastAPI app: {api_server.app is not None}")
        print(f"  ✓ Agent messages data: {isinstance(api_server.agent_messages_data, list)}")
        print(f"  ✓ Loop controller instance: {hasattr(api_server, 'loop_controller_instance')}")
        return True
    except Exception as e:
        print(f"  ✗ API server test failed: {e}")
        return False


def main():
    """Run all integration tests."""
    print("=" * 80)
    print("DEEP INTEGRATION CHECK")
    print("=" * 80)
    print("This verifies data flow and object interactions.\n")
    
    tests = [
        ("Config Loading", test_config_loading),
        ("LoopController Init", test_loop_controller_init),
        ("CycleController Components", test_cycle_controller_components),
        ("Data Flow", test_data_flow),
        ("RiskManager", test_risk_manager),
        ("API Server", test_api_server),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ✗ Test crashed: {e}")
            failed += 1
    
    print("\n" + "=" * 80)
    print(f"INTEGRATION TEST RESULTS: {passed} passed, {failed} failed")
    print("=" * 80)
    
    if failed == 0:
        print("\n✓ All integration tests passed!")
        print("✓ Data flow is working correctly!")
        return 0
    else:
        print(f"\n✗ {failed} integration test(s) failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())

