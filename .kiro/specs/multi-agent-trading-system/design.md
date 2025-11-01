# Design Document

## Overview

The Autonomous Trading Agent is a Python-based system that executes a continuous loop: fetch market data → ask DeepSeek for a decision → validate with risk rules → execute on exchange → log everything. The architecture is modular with clear separation between data acquisition, reasoning, risk management, execution, and logging.

The system is designed to be:
- **Safe**: All trades pass through risk validation; testnet mode available
- **Observable**: Every decision and execution is logged with full context
- **Extensible**: LLM provider is pluggable (DeepSeek now, Alive-1 later)
- **Simple**: Single symbol, single agent, no distributed complexity

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Loop Controller                         │
│                   (orchestrates cycles)                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │  Data Acquisition Layer     │
         │  - Fetch ticker & OHLCV     │
         │  - Compute indicators       │
         │  - Normalize to snapshot    │
         └─────────────┬───────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │  Agent Reasoning Layer      │
         │  - Build prompt             │
         │  - Call DeepSeek API        │
         │  - Return raw response      │
         └─────────────┬───────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │  Decision Parsing Layer     │
         │  - Parse JSON               │
         │  - Validate fields          │
         │  - Force hold if invalid    │
         └─────────────┬───────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │  Risk Layer                 │
         │  - Check position limits    │
         │  - Check leverage           │
         │  - Check price validity     │
         │  - Approve or deny          │
         └─────────────┬───────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │  Trade Executor             │
         │  - Calculate order size     │
         │  - Submit to exchange       │
         │  - Return execution result  │
         └─────────────┬───────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │  Logging Layer              │
         │  - Persist full cycle data  │
         │  - Append-only JSONL        │
         └─────────────────────────────┘
```

## Components and Interfaces

### 1. Configuration Module

**Responsibility**: Load and validate all configuration from environment variables.

**Interface**:
```python
@dataclass
class Config:
    # Exchange
    exchange_type: str  # "binance_testnet" | "binance" | "hyperliquid"
    symbol: str  # "BTC/USDT"
    
    # Credentials
    exchange_api_key: str
    exchange_api_secret: str
    deepseek_api_key: str
    
    # Agent behavior
    loop_interval_seconds: int  # default 30
    max_equity_usage_pct: float  # default 0.10
    max_leverage: float  # default 3.0
    
    # Mode
    run_mode: str  # "testnet" | "live"
    
    # Optional risk
    daily_loss_cap_pct: Optional[float]  # default None
    cooldown_seconds: Optional[int]  # default None
    
    # LLM
    decision_provider: str  # "deepseek" | "alive"
    
    @classmethod
    def from_env(cls) -> Config:
        """Load from environment variables with validation"""
```

**Implementation Notes**:
- Use `python-dotenv` to load `.env` file
- Validate required fields are present
- Validate numeric ranges (e.g., max_equity_usage_pct between 0 and 1)
- Raise clear error messages for missing or invalid config

### 2. Data Acquisition Layer

**Responsibility**: Fetch and normalize market data from exchange APIs.

**Interface**:
```python
@dataclass
class MarketSnapshot:
    timestamp: int  # Unix milliseconds
    symbol: str
    price: float  # Last trade price
    bid: float
    ask: float
    ohlcv: List[List[float]]  # [[ts, o, h, l, c, v], ...]
    indicators: Dict[str, float]  # {"ema_20": 68500.0, "ema_50": 67800.0, "rsi_14": 55.2}

class DataAcquisition:
    def __init__(self, config: Config):
        self.exchange = self._init_exchange(config)
    
    def fetch_market_snapshot(self, symbol: str) -> MarketSnapshot:
        """Fetch ticker, OHLCV, compute indicators, return normalized snapshot"""
```

**Implementation Notes**:
- Use `ccxt` library for exchange abstraction
- For Binance testnet, set `exchange.urls['api'] = 'https://testnet.binance.vision'`
- Fetch at least 50 candles for indicator calculation
- Compute indicators using `pandas` and `ta-lib` or `pandas_ta`
- Cache previous snapshot; return it if API call fails
- Handle rate limits with exponential backoff

**Technical Indicators**:
- EMA(20): `df['close'].ewm(span=20).mean()`
- EMA(50): `df['close'].ewm(span=50).mean()`
- RSI(14): Use `pandas_ta.rsi(df['close'], length=14)`

### 3. Agent Reasoning Layer

**Responsibility**: Construct prompts and call LLM APIs to generate trading decisions.

**Interface**:
```python
@dataclass
class DecisionObject:
    action: str  # "long" | "short" | "close" | "hold"
    size_pct: float  # 0.0 to 1.0
    reason: str

class DecisionProvider(ABC):
    @abstractmethod
    def get_decision(self, snapshot: MarketSnapshot, position_size: float, equity: float) -> str:
        """Return raw LLM response as string"""

class DeepSeekDecisionProvider(DecisionProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    
    def get_decision(self, snapshot: MarketSnapshot, position_size: float, equity: float) -> str:
        prompt = self._build_prompt(snapshot, position_size, equity)
        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            timeout=5.0
        )
        return response.choices[0].message.content
```

**Prompt Template**:
```
You are an automated trading agent for {symbol}.

MARKET CONTEXT:
- Current price: {price}
- Bid: {bid}, Ask: {ask}
- EMA(20): {ema_20}, EMA(50): {ema_50}
- RSI(14): {rsi_14}
- Trend: {"bullish" if ema_20 > ema_50 else "bearish"}

YOUR POSITION:
- Current position size: {position_size} {symbol}
- Account equity: {equity} USDT

ALLOWED ACTIONS:
- "long": open or add to long position
- "short": open or add to short position
- "close": close current position
- "hold": do nothing

CONSTRAINTS:
- You must output ONLY valid JSON
- Prefer "hold" over reckless trades
- If uncertain, output "hold"

OUTPUT FORMAT (strict JSON):
{
  "action": "long|short|close|hold",
  "size_pct": 0.0-1.0,
  "reason": "brief explanation"
}

Output your decision now:
```

**Implementation Notes**:
- Use OpenAI-compatible client for DeepSeek
- Set timeout to 5 seconds
- Catch timeout exceptions and return error string
- Log raw LLM response before returning

### 4. Decision Parsing Layer

**Responsibility**: Parse and validate LLM output into structured DecisionObject.

**Interface**:
```python
class DecisionParser:
    ALLOWED_ACTIONS = {"long", "short", "close", "hold"}
    
    def parse(self, raw_response: str) -> DecisionObject:
        """Parse LLM response; force hold if invalid"""
```

**Implementation Notes**:
- Try to parse as JSON; if fails, force hold
- Validate `action` is in ALLOWED_ACTIONS; if not, force hold
- Validate `size_pct` is float between 0.0 and 1.0; if not, force hold
- Ensure `reason` field exists; default to empty string if missing
- Log all validation failures with original response
- Return DecisionObject with forced values if any validation fails

### 5. Risk Layer

**Responsibility**: Validate trading decisions against safety rules.

**Interface**:
```python
@dataclass
class RiskResult:
    approved: bool
    reason: str  # Empty if approved, explanation if denied

class RiskManager:
    def __init__(self, config: Config):
        self.max_equity_usage_pct = config.max_equity_usage_pct
        self.max_leverage = config.max_leverage
        self.daily_loss_cap_pct = config.daily_loss_cap_pct
        self.cooldown_seconds = config.cooldown_seconds
        self.last_open_time: Optional[int] = None
        self.starting_equity: Optional[float] = None
    
    def validate(self, decision: DecisionObject, snapshot: MarketSnapshot, 
                 position_size: float, equity: float) -> RiskResult:
        """Run all risk checks; return approval or denial"""
```

**Risk Rules** (in order):
1. **Hold auto-approve**: If action is "hold", return approved=True
2. **Close validation**: If action is "close" and position_size == 0, deny with "no position to close"
3. **Price validity**: If snapshot.price <= 0, deny with "no valid price"
4. **Position size limit**: Calculate proposed_size = equity * decision.size_pct / snapshot.price; if proposed_size > equity * max_equity_usage_pct / snapshot.price, deny with "exceeds max position size"
5. **Leverage limit**: If max_leverage is set and proposed_size * snapshot.price > equity * max_leverage, deny with "exceeds max leverage"
6. **Daily loss cap**: If daily_loss_cap_pct is set and equity < starting_equity * (1 - daily_loss_cap_pct), deny with "daily loss cap reached"
7. **Cooldown**: If cooldown_seconds is set and action in ["long", "short"] and last_open_time is not None and (current_time - last_open_time) < cooldown_seconds, deny with "cooldown period active"

**Implementation Notes**:
- Store starting_equity at the beginning of each UTC day
- Update last_open_time when a long/short trade is approved
- All checks return early with denial if failed
- If all checks pass, return approved=True with empty reason

### 6. Trade Executor

**Responsibility**: Submit orders to exchange and return execution results.

**Interface**:
```python
@dataclass
class ExecutionResult:
    executed: bool
    order_id: Optional[str]
    filled_size: Optional[float]
    fill_price: Optional[float]
    error: Optional[str]

class TradeExecutor:
    def __init__(self, config: Config):
        self.exchange = self._init_exchange(config)
    
    def execute(self, decision: DecisionObject, snapshot: MarketSnapshot, 
                position_size: float, equity: float) -> ExecutionResult:
        """Calculate size, submit order, return result"""
```

**Execution Logic**:
1. **Calculate order size**:
   - `order_size = (equity * decision.size_pct) / snapshot.price`
   - Round to exchange's precision (e.g., 3 decimals for BTC)

2. **Action handling**:
   - **long**: `exchange.create_market_buy_order(symbol, order_size)`
   - **short**: `exchange.create_market_sell_order(symbol, order_size)`
   - **close**: 
     - If position_size > 0 (long), sell position_size
     - If position_size < 0 (short), buy abs(position_size)
   - **hold**: Return ExecutionResult(executed=False)

3. **Parse exchange response**:
   - Extract order_id, filled amount, average fill price
   - Return ExecutionResult with all fields populated

**Implementation Notes**:
- Use `ccxt` for order submission
- Handle exchange errors gracefully (insufficient balance, invalid size, etc.)
- If order fails, return ExecutionResult with executed=False and error message
- Query positions after execution to verify state

### 7. Logging Layer

**Responsibility**: Persist all cycle data in structured, append-only format.

**Interface**:
```python
@dataclass
class CycleLog:
    timestamp: int
    symbol: str
    market_price: float
    position_before: float
    llm_raw_output: str
    parsed_action: str
    parsed_size_pct: float
    parsed_reason: str
    risk_approved: bool
    risk_reason: str
    executed: bool
    order_id: Optional[str]
    filled_size: Optional[float]
    fill_price: Optional[float]
    mode: str  # "testnet" | "live"

class Logger:
    def __init__(self, log_file: str):
        self.log_file = log_file
    
    def log_cycle(self, cycle_log: CycleLog):
        """Append cycle log to JSONL file"""
```

**Implementation Notes**:
- Use JSONL format (one JSON object per line)
- Open file in append mode
- Flush after each write to ensure durability
- Never log API keys or secrets
- Include mode field to distinguish testnet vs live logs

### 8. Loop Controller

**Responsibility**: Orchestrate the agent cycle and handle errors gracefully.

**Interface**:
```python
class LoopController:
    def __init__(self, config: Config):
        self.config = config
        self.data_acquisition = DataAcquisition(config)
        self.decision_provider = self._init_decision_provider(config)
        self.decision_parser = DecisionParser()
        self.risk_manager = RiskManager(config)
        self.trade_executor = TradeExecutor(config)
        self.logger = Logger("agent_log.jsonl")
        self.running = True
    
    def startup(self):
        """Test exchange and LLM connectivity"""
    
    def run(self):
        """Execute agent cycles in a loop"""
    
    def shutdown(self):
        """Graceful shutdown"""
```

**Cycle Steps**:
1. Fetch market snapshot (catch errors, skip iteration if fails)
2. Fetch current position and equity from exchange
3. Call decision provider (catch errors, force hold if fails)
4. Parse decision (always succeeds, may force hold)
5. Validate with risk manager
6. If approved, execute trade
7. Log full cycle data
8. Sleep for configured interval

**Error Handling**:
- Exchange API errors: Log and skip iteration
- DeepSeek API errors: Force hold, log, continue
- Parsing errors: Force hold, log, continue
- Risk denials: Log, do not execute, continue
- Execution errors: Log, continue

**Shutdown**:
- Register signal handlers for SIGINT and SIGTERM
- Set `self.running = False` on signal
- Complete current iteration before exiting
- Do not automatically close positions (operator decision)

## Data Models

### Environment Variables

```bash
# Exchange
EXCHANGE_TYPE=binance_testnet
SYMBOL=BTC/USDT

# Credentials
EXCHANGE_API_KEY=your_key_here
EXCHANGE_API_SECRET=your_secret_here
DEEPSEEK_API_KEY=your_deepseek_key_here

# Agent behavior
LOOP_INTERVAL_SECONDS=30
MAX_EQUITY_USAGE_PCT=0.10
MAX_LEVERAGE=3.0

# Mode
RUN_MODE=testnet

# Optional risk
DAILY_LOSS_CAP_PCT=0.05
COOLDOWN_SECONDS=60

# LLM
DECISION_PROVIDER=deepseek
```

### Log Record Example

```json
{
  "timestamp": 1730395200000,
  "symbol": "BTC/USDT",
  "market_price": 68654.5,
  "position_before": 0.0,
  "llm_raw_output": "{\"action\": \"long\", \"size_pct\": 0.25, \"reason\": \"EMA crossover bullish\"}",
  "parsed_action": "long",
  "parsed_size_pct": 0.25,
  "parsed_reason": "EMA crossover bullish",
  "risk_approved": true,
  "risk_reason": "",
  "executed": true,
  "order_id": "12345678",
  "filled_size": 0.036,
  "fill_price": 68655.0,
  "mode": "testnet"
}
```

## Error Handling

### Exchange API Failures
- **Symptom**: Network timeout, rate limit, invalid credentials
- **Handling**: Log error, return cached snapshot or skip iteration
- **Recovery**: Retry on next cycle

### DeepSeek API Failures
- **Symptom**: Timeout, invalid API key, model unavailable
- **Handling**: Force action to "hold", log error
- **Recovery**: Retry on next cycle

### Parsing Failures
- **Symptom**: Invalid JSON, missing fields, wrong types
- **Handling**: Force action to "hold", log original response
- **Recovery**: Automatic on next cycle

### Risk Denials
- **Symptom**: Position too large, no valid price, cooldown active
- **Handling**: Log denial reason, do not execute
- **Recovery**: Depends on rule (cooldown expires, price becomes valid, etc.)

### Execution Failures
- **Symptom**: Insufficient balance, invalid order size, exchange rejection
- **Handling**: Log error, return ExecutionResult with executed=False
- **Recovery**: Operator intervention may be required

## Testing Strategy

### Unit Tests

1. **Config Module**:
   - Test loading from environment variables
   - Test validation of required fields
   - Test validation of numeric ranges

2. **Data Acquisition**:
   - Mock ccxt exchange responses
   - Test OHLCV normalization
   - Test indicator calculation
   - Test error handling for API failures

3. **Decision Parser**:
   - Test valid JSON parsing
   - Test invalid JSON handling (force hold)
   - Test invalid action handling (force hold)
   - Test invalid size_pct handling (force hold)

4. **Risk Manager**:
   - Test each risk rule independently
   - Test hold auto-approve
   - Test close with no position
   - Test position size limit
   - Test leverage limit
   - Test daily loss cap
   - Test cooldown

5. **Trade Executor**:
   - Mock ccxt order submission
   - Test order size calculation
   - Test long/short/close actions
   - Test error handling

6. **Logger**:
   - Test JSONL writing
   - Test append-only behavior
   - Test no secrets in logs

### Integration Tests

1. **End-to-End Cycle** (with mocks):
   - Mock exchange API to return test data
   - Mock DeepSeek API to return test decision
   - Run full cycle
   - Verify log output

2. **Testnet Validation**:
   - Run agent on Binance testnet
   - Verify orders are submitted
   - Verify positions are tracked
   - Verify logs are written

### Manual Testing

1. **Startup Test**:
   - Run with invalid credentials → should fail with clear error
   - Run with valid credentials → should connect successfully

2. **Decision Test**:
   - Observe LLM decisions in logs
   - Verify decisions are reasonable given market context

3. **Risk Test**:
   - Trigger each risk rule
   - Verify denials are logged correctly

4. **Execution Test**:
   - Verify orders appear in exchange UI
   - Verify positions are updated correctly

## Security Considerations

1. **API Key Storage**:
   - Store in `.env` file
   - Add `.env` to `.gitignore`
   - Never commit credentials to version control

2. **API Key Permissions**:
   - Exchange keys: read + trade only, no withdrawal
   - Verify permissions in exchange UI before running

3. **Testnet First**:
   - Always test on testnet before live
   - Verify all functionality works as expected

4. **Kill Switch**:
   - Add `TRADING_ENABLED=true` flag to config
   - If false, agent runs but does not execute trades
   - Allows observation without risk

5. **Log Security**:
   - Never log API keys or secrets
   - Sanitize LLM responses if they might contain sensitive data

## Deployment

### Local Development

1. Install dependencies:
   ```bash
   pip install ccxt python-dotenv openai pandas pandas-ta
   ```

2. Create `.env` file with configuration

3. Run agent:
   ```bash
   python main.py
   ```

### Production Deployment

1. **VPS Setup**:
   - 1 vCPU, 1GB RAM sufficient
   - Ubuntu 22.04 or similar
   - Python 3.10+

2. **Process Management**:
   - Use `systemd` service or `supervisor`
   - Auto-restart on failure
   - Log rotation

3. **Monitoring**:
   - Monitor log file for errors
   - Alert on repeated API failures
   - Alert on risk denials

4. **Backup**:
   - Backup log file daily
   - Store logs for at least 30 days

## Future Extensibility

### Adding Alive-1 Provider

1. Implement `AliveDecisionProvider` class
2. Update config to support `DECISION_PROVIDER=alive`
3. No changes needed to other components

### Adding Hyperliquid Exchange

1. Implement Hyperliquid-specific exchange client
2. Handle EIP-712 signing for orders
3. Update `TradeExecutor` to route based on exchange type
4. No changes needed to other components

### Adding Multiple Symbols

1. Update config to support list of symbols
2. Run separate agent instance per symbol
3. Share data acquisition and logging layers

### Adding WebSocket Data

1. Implement WebSocket client in data acquisition layer
2. Update market snapshot in real-time
3. Trigger agent cycle on significant price changes
