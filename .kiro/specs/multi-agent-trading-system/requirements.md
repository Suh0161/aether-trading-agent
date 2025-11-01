# Requirements Document

## Introduction

The Autonomous Trading Agent is a single LLM-driven trading system that retrieves live market data for one symbol, asks DeepSeek for trading decisions, validates decisions against risk rules, executes orders via exchange API, and logs all activity. The agent runs in a continuous loop and supports both testnet and live trading modes.

## Glossary

- **Trading Agent**: The autonomous software system that orchestrates market data retrieval, LLM reasoning, risk validation, and trade execution
- **Data Acquisition Layer**: The component that fetches and normalizes market data including price, bid/ask, OHLCV candles, and technical indicators
- **Agent Reasoning Layer**: The component that constructs prompts and calls DeepSeek to generate trading decisions
- **Decision Parsing Layer**: The component that validates and canonicalizes LLM output into a structured decision object
- **Risk Layer**: The validation component that enforces position limits, leverage constraints, and safety rules before execution
- **Trade Executor**: The component that submits orders to exchange APIs and handles execution results
- **Logging Layer**: The component that persists all market snapshots, decisions, risk evaluations, and execution results
- **Loop Controller**: The runtime orchestrator that executes the agent cycle at fixed intervals
- **Market Snapshot**: A normalized data structure containing current price, bid/ask, OHLCV candles, and computed technical indicators
- **Decision Object**: A structured output from the LLM containing action (long/short/close/hold), size_pct (0-1), and reason

## Requirements

### Requirement 1

**User Story:** As a system operator, I want to configure the trading agent with exchange credentials and operating parameters, so that the agent can connect securely and operate within defined constraints

#### Acceptance Criteria

1. WHEN the system initializes, THE Trading Agent SHALL load configuration from environment variables including exchange type, symbol, loop interval, max risk percentage, and run mode
2. THE Trading Agent SHALL load API credentials from environment variables including exchange API key, exchange API secret, and DeepSeek API key
3. THE Trading Agent SHALL validate that API keys have read and trade permissions but not withdrawal permissions
4. WHERE run mode is "testnet", THE Trading Agent SHALL route all requests to testnet endpoints
5. WHERE run mode is "live", THE Trading Agent SHALL route all requests to production endpoints and log a clear "LIVE MODE" indicator

### Requirement 2

**User Story:** As a trading agent, I want to retrieve normalized market data for a single symbol, so that I can provide consistent context to the LLM

#### Acceptance Criteria

1. WHEN the agent cycle executes, THE Data Acquisition Layer SHALL fetch the latest ticker data including current price, best bid, and best ask
2. THE Data Acquisition Layer SHALL fetch recent OHLCV candles for the configured timeframe with at least 50 periods of history
3. THE Data Acquisition Layer SHALL compute technical indicators including EMA(20), EMA(50), and RSI(14) from the OHLCV data
4. THE Data Acquisition Layer SHALL normalize all data into a Market Snapshot object with fields: timestamp, symbol, price, bid, ask, ohlcv, and indicators
5. IF the exchange API fails to return data, THEN THE Data Acquisition Layer SHALL log the error and return the previous Market Snapshot

### Requirement 3

**User Story:** As a trading agent, I want to construct a structured prompt for DeepSeek, so that the LLM generates trading decisions in a machine-readable format

#### Acceptance Criteria

1. WHEN the agent cycle executes, THE Agent Reasoning Layer SHALL retrieve the current account balance and open position size
2. THE Agent Reasoning Layer SHALL construct a prompt containing role definition, market context, current position, allowed actions, output format specification, and fallback rule
3. THE Agent Reasoning Layer SHALL include in the prompt: current price, trend summary, position size, and explicit instruction to output JSON with keys action, size_pct, and reason
4. THE Agent Reasoning Layer SHALL specify in the prompt that allowed actions are: long, short, close, hold
5. THE Agent Reasoning Layer SHALL call the DeepSeek API with the constructed prompt and a timeout of 5 seconds

### Requirement 4

**User Story:** As a trading agent, I want to parse and validate LLM output, so that malformed or invalid responses do not cause system errors

#### Acceptance Criteria

1. WHEN the LLM returns a response, THE Decision Parsing Layer SHALL attempt to parse the response as JSON
2. IF the response is not valid JSON, THEN THE Decision Parsing Layer SHALL force the action to "hold" and log the parsing error
3. THE Decision Parsing Layer SHALL validate that the action field is one of: long, short, close, hold
4. THE Decision Parsing Layer SHALL validate that size_pct is a number between 0.0 and 1.0 inclusive
5. IF any validation fails, THEN THE Decision Parsing Layer SHALL force the action to "hold" and log the validation error with the original LLM output

### Requirement 5

**User Story:** As a system operator, I want risk rules to validate trading decisions, so that the agent cannot execute trades that violate safety constraints

#### Acceptance Criteria

1. WHEN a parsed decision is received, THE Risk Layer SHALL validate that position size does not exceed the configured max equity usage percentage (default 10 percent)
2. THE Risk Layer SHALL validate that leverage does not exceed the configured maximum (default 3x)
3. IF the latest market price is missing or zero, THEN THE Risk Layer SHALL deny the trade and log "no valid price"
4. WHERE the action is "hold", THE Risk Layer SHALL approve without further validation
5. WHERE the action is "close" and no open position exists, THE Risk Layer SHALL deny and log "no position to close"

### Requirement 6

**User Story:** As a system operator, I want optional risk safeguards to prevent excessive losses, so that the agent pauses trading during adverse conditions

#### Acceptance Criteria

1. WHERE daily loss cap is configured, WHEN the current equity is less than starting equity minus the cap, THE Risk Layer SHALL deny all trades except "close" until the next UTC day
2. WHERE cooldown period is configured, WHEN a position was opened less than the cooldown seconds ago, THE Risk Layer SHALL deny new "long" or "short" actions
3. WHERE LLM sanity check is enabled, WHEN the LLM requests 100 percent size_pct more than 3 consecutive times, THE Risk Layer SHALL force "hold" and raise an alert
4. WHEN any risk rule denies a trade, THE Risk Layer SHALL return a result object with approved=false and a reason string
5. WHEN all risk rules pass, THE Risk Layer SHALL return a result object with approved=true

### Requirement 7

**User Story:** As a trading agent, I want to execute approved trades on the exchange, so that trading decisions result in actual market positions

#### Acceptance Criteria

1. WHEN the Risk Layer approves a trade, THE Trade Executor SHALL calculate the order size by multiplying account equity, size_pct, and dividing by current price
2. WHERE the action is "long", THE Trade Executor SHALL submit a market buy order for the calculated size
3. WHERE the action is "short", THE Trade Executor SHALL submit a market sell order for the calculated size
4. WHERE the action is "close", THE Trade Executor SHALL query the current position and submit a market order in the opposite direction to flatten the position
5. WHEN an order is submitted, THE Trade Executor SHALL return an execution result containing executed status, order_id, filled_size, and fill_price

### Requirement 8

**User Story:** As a system operator, I want comprehensive logging of every agent cycle, so that I can replay and analyze agent behavior

#### Acceptance Criteria

1. WHEN an agent cycle completes, THE Logging Layer SHALL persist a structured record containing timestamp, symbol, market_price, position_before, llm_raw_output, parsed_action, risk_result, execution_result, and mode
2. THE Logging Layer SHALL write logs in append-only format to prevent data loss
3. THE Logging Layer SHALL support output formats including JSONL, CSV, or SQLite
4. THE Logging Layer SHALL never log API keys or secrets
5. THE Logging Layer SHALL ensure each log record is human-readable and contains sufficient context for post-analysis

### Requirement 9

**User Story:** As a system operator, I want the agent to run in a continuous loop, so that it responds to market conditions at regular intervals

#### Acceptance Criteria

1. WHEN the agent starts, THE Loop Controller SHALL execute a startup sequence that tests exchange connectivity and DeepSeek API connectivity
2. THE Loop Controller SHALL execute agent cycles at the configured interval (default 30 seconds)
3. WHEN an exchange API error occurs, THE Loop Controller SHALL log the error and continue to the next iteration without crashing
4. WHEN a DeepSeek API error occurs, THE Loop Controller SHALL force action to "hold", log the error, and continue to the next iteration
5. WHEN the process receives SIGINT or SIGTERM, THE Loop Controller SHALL complete the current iteration and shut down gracefully

### Requirement 10

**User Story:** As a system operator, I want the agent to support multiple LLM providers, so that I can switch from DeepSeek to Alive-1 without changing other components

#### Acceptance Criteria

1. THE Agent Reasoning Layer SHALL define an interface for decision providers with a method that accepts Market Snapshot and returns Decision Object
2. THE Trading Agent SHALL support a DeepSeekDecisionProvider implementation that calls the DeepSeek API
3. THE Trading Agent SHALL be designed to support future AliveDecisionProvider implementation without modifying Risk Layer or Trade Executor
4. THE configuration SHALL specify which decision provider to use via an environment variable
5. WHEN switching decision providers, THE Data Acquisition Layer, Risk Layer, Trade Executor, and Logging Layer SHALL remain unchanged
