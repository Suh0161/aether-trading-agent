# Implementation Plan

- [x] 1. Set up project structure and configuration module





  - Create directory structure: `src/`, `tests/`, `logs/`
  - Create `requirements.txt` with dependencies: ccxt, python-dotenv, openai, pandas, pandas-ta
  - Implement `Config` dataclass in `src/config.py` that loads from environment variables
  - Add validation for required fields and numeric ranges
  - Create `.env.example` template file
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. Implement data acquisition layer






  - [x] 2.1 Create market snapshot data model

    - Define `MarketSnapshot` dataclass in `src/models.py` with fields: timestamp, symbol, price, bid, ask, ohlcv, indicators
    - _Requirements: 2.4_
  

  - [x] 2.2 Implement exchange client and data fetching

    - Create `DataAcquisition` class in `src/data_acquisition.py`
    - Initialize ccxt exchange with config (handle testnet URL override for Binance)
    - Implement `fetch_market_snapshot()` method that fetches ticker and OHLCV
    - Add error handling to return cached snapshot on API failure
    - _Requirements: 2.1, 2.2, 2.5_
  

  - [x] 2.3 Add technical indicator computation

    - Implement indicator calculation using pandas: EMA(20), EMA(50), RSI(14)
    - Integrate indicators into `MarketSnapshot` object
    - _Requirements: 2.3, 2.4_

- [x] 3. Implement agent reasoning layer




  - [x] 3.1 Create decision provider interface and models


    - Define `DecisionObject` dataclass in `src/models.py` with fields: action, size_pct, reason
    - Create abstract `DecisionProvider` base class in `src/decision_provider.py`
    - _Requirements: 3.3, 10.1_
  
  - [x] 3.2 Implement DeepSeek decision provider


    - Create `DeepSeekDecisionProvider` class that extends `DecisionProvider`
    - Implement prompt template with market context, position, allowed actions, and output format
    - Implement `get_decision()` method that calls DeepSeek API with 5-second timeout
    - Add error handling for API timeouts and failures
    - _Requirements: 3.1, 3.2, 3.4, 3.5_

- [x] 4. Implement decision parsing layer





  - Create `DecisionParser` class in `src/decision_parser.py`
  - Implement `parse()` method that validates JSON structure
  - Add validation for action field (must be in allowed set)
  - Add validation for size_pct field (must be 0.0-1.0)
  - Force action to "hold" on any validation failure
  - Log all parsing and validation errors
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 5. Implement risk management layer




  - [x] 5.1 Create risk result model and manager class


    - Define `RiskResult` dataclass in `src/models.py` with fields: approved, reason
    - Create `RiskManager` class in `src/risk_manager.py` with config-based initialization
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  
  - [x] 5.2 Implement core risk rules

    - Implement hold auto-approve rule
    - Implement close validation (deny if no position)
    - Implement price validity check (deny if price <= 0)
    - Implement position size limit check
    - Implement leverage limit check
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  
  - [x] 5.3 Implement optional risk safeguards

    - Implement daily loss cap with UTC day tracking
    - Implement cooldown period tracking
    - Implement LLM sanity check (deny after 3 consecutive 100% size requests)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 6. Implement trade execution layer






  - [x] 6.1 Create execution result model and executor class

    - Define `ExecutionResult` dataclass in `src/models.py` with fields: executed, order_id, filled_size, fill_price, error
    - Create `TradeExecutor` class in `src/trade_executor.py`
    - Initialize ccxt exchange with config
    - _Requirements: 7.5_
  

  - [x] 6.2 Implement order execution logic

    - Implement order size calculation based on equity and size_pct
    - Implement long action (market buy order)
    - Implement short action (market sell order)
    - Implement close action (flatten position)
    - Implement hold action (no execution)
    - Parse exchange response and return `ExecutionResult`
    - Add error handling for exchange rejections
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 7. Implement logging layer





  - Define `CycleLog` dataclass in `src/models.py` with all required fields
  - Create `Logger` class in `src/logger.py`
  - Implement `log_cycle()` method that appends to JSONL file
  - Ensure API keys and secrets are never logged
  - Add file flushing after each write
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 8. Implement loop controller




  - [x] 8.1 Create loop controller class and initialization


    - Create `LoopController` class in `src/loop_controller.py`
    - Initialize all components (data acquisition, decision provider, parser, risk manager, executor, logger)
    - Implement decision provider factory based on config
    - _Requirements: 9.1, 10.2, 10.3, 10.4, 10.5_
  
  - [x] 8.2 Implement startup and connectivity tests


    - Implement `startup()` method that tests exchange connectivity (fetch balance)
    - Test DeepSeek API connectivity with a test prompt
    - Log startup results and fail fast if connectivity issues
    - _Requirements: 9.1_
  
  - [x] 8.3 Implement main agent cycle loop


    - Implement `run()` method with continuous loop
    - Fetch market snapshot with error handling
    - Fetch current position and equity from exchange
    - Call decision provider with error handling (force hold on failure)
    - Parse decision
    - Validate with risk manager
    - Execute trade if approved
    - Log full cycle data
    - Sleep for configured interval
    - _Requirements: 9.2, 9.3, 9.4, 9.5_
  
  - [x] 8.4 Implement graceful shutdown


    - Register signal handlers for SIGINT and SIGTERM
    - Implement `shutdown()` method that completes current iteration
    - Set running flag to false on signal
    - _Requirements: 9.5_

- [x] 9. Create main entry point





  - Create `main.py` that loads config and starts loop controller
  - Add command-line argument parsing for config file path
  - Add clear logging of run mode (testnet vs live)
  - Handle startup failures with clear error messages
  - _Requirements: 1.1, 1.5_

- [x] 10. Add project documentation





  - Create `README.md` with setup instructions, configuration guide, and usage examples
  - Document environment variable requirements
  - Add safety warnings for testnet vs live mode
  - Include example log output
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
