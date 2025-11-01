# Autonomous Trading Agent

An LLM-driven autonomous trading system that retrieves live market data, asks DeepSeek for trading decisions, validates decisions against risk rules, executes orders via exchange API, and logs all activity.

## ⚠️ Safety Warnings

**IMPORTANT: Always test on testnet before running in live mode!**

- **Testnet Mode**: Safe testing environment with fake money. Set `RUN_MODE=testnet` in your `.env` file.
- **Live Mode**: Real money trading. Only use after thorough testing on testnet. The system will display a 5-second warning before starting.
- **API Key Permissions**: Ensure your exchange API keys have **read and trade permissions only**. **Never enable withdrawal permissions**.
- **Risk Management**: The system includes built-in risk controls, but you are responsible for monitoring and managing your trading activity.
- **No Guarantees**: This software is provided as-is with no guarantees of profitability or safety. Use at your own risk.

## Features

- **LLM-Driven Decisions**: Uses DeepSeek to analyze market data and make trading decisions
- **Risk Management**: Built-in position limits, leverage controls, and optional safeguards
- **Exchange Support**: Works with Binance (testnet and live) via CCXT
- **Technical Indicators**: Computes EMA(20), EMA(50), and RSI(14) for market analysis
- **Comprehensive Logging**: All decisions and executions logged in JSONL format
- **Graceful Shutdown**: Handles SIGINT/SIGTERM signals to complete current iteration
- **Extensible**: Pluggable LLM provider architecture (DeepSeek now, others later)

## Architecture

The system follows a modular pipeline architecture:

```
Data Acquisition → Agent Reasoning → Decision Parsing → Risk Validation → Trade Execution → Logging
```

Each component is independent and can be tested/modified separately.

## Requirements

- Python 3.10 or higher
- Exchange account (Binance testnet recommended for testing)
- DeepSeek API key

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd autonomous-trading-agent
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Create environment file**:
   ```bash
   cp .env.example .env
   ```

4. **Configure your environment** (see Configuration section below)

## Configuration

### Environment Variables

Edit your `.env` file with the following configuration:

#### Exchange Configuration

```bash
# Exchange type: binance_testnet, binance, or hyperliquid
EXCHANGE_TYPE=binance_testnet

# Trading symbol (use exchange-specific format)
SYMBOL=BTC/USDT
```

#### API Credentials

```bash
# Exchange API credentials
# For Binance testnet: https://testnet.binance.vision/
# For Binance live: https://www.binance.com/
EXCHANGE_API_KEY=your_exchange_api_key_here
EXCHANGE_API_SECRET=your_exchange_api_secret_here

# DeepSeek API key
# Get yours at: https://platform.deepseek.com/
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

**Security Best Practices**:
- Never commit your `.env` file to version control
- Use API keys with **read and trade permissions only**
- Disable withdrawal permissions on your exchange API keys
- Store API keys securely

#### Agent Behavior

```bash
# How often to run the agent cycle (in seconds)
LOOP_INTERVAL_SECONDS=30

# Maximum percentage of equity to use for positions (0.0 to 1.0)
# Example: 0.10 = use up to 10% of account equity
MAX_EQUITY_USAGE_PCT=0.10

# Maximum leverage allowed (e.g., 3.0 = 3x leverage)
MAX_LEVERAGE=3.0
```

#### Run Mode

```bash
# Run mode: testnet or live
# ALWAYS start with testnet!
RUN_MODE=testnet
```

#### Optional Risk Management

```bash
# Optional: Daily loss cap as percentage of starting equity
# Example: 0.05 = stop trading if down 5% for the day
# DAILY_LOSS_CAP_PCT=0.05

# Optional: Cooldown period in seconds between opening new positions
# Example: 60 = wait 60 seconds after opening a position before opening another
# COOLDOWN_SECONDS=60
```

#### LLM Provider

```bash
# Decision provider: deepseek (more providers coming soon)
DECISION_PROVIDER=deepseek
```

### Getting API Keys

#### Binance Testnet (Recommended for Testing)

1. Visit [Binance Testnet](https://testnet.binance.vision/)
2. Create an account (no KYC required)
3. Generate API keys from the account dashboard
4. You'll receive free testnet funds automatically

#### Binance Live (Production)

1. Create account at [Binance](https://www.binance.com/)
2. Complete KYC verification
3. Go to API Management
4. Create new API key with **read and trade permissions only**
5. **Disable withdrawal permissions**
6. Whitelist your IP address for additional security

#### DeepSeek API

1. Visit [DeepSeek Platform](https://platform.deepseek.com/)
2. Sign up for an account
3. Navigate to API Keys section
4. Generate a new API key
5. Copy the key to your `.env` file

## Usage

### Basic Usage

Run the agent with default configuration:

```bash
python main.py
```

### Command-Line Options

```bash
# Use a custom environment file
python main.py --env .env.testnet

# Enable verbose (DEBUG) logging
python main.py --verbose

# Show version
python main.py --version

# Show help
python main.py --help
```

### Starting the Agent

When you start the agent, you'll see output like this:

**Testnet Mode**:
```
================================================================================
AUTONOMOUS TRADING AGENT
================================================================================
2024-10-31 10:30:00 - __main__ - INFO - Loading configuration from: .env
2024-10-31 10:30:00 - __main__ - INFO - ✓ Configuration loaded successfully
================================================================================
TESTNET MODE - Safe testing environment
================================================================================
2024-10-31 10:30:00 - __main__ - INFO - Initializing loop controller...
2024-10-31 10:30:00 - __main__ - INFO - ✓ Loop controller initialized
2024-10-31 10:30:00 - __main__ - INFO - Running startup connectivity tests...
2024-10-31 10:30:01 - src.loop_controller - INFO - ✓ Exchange connectivity test passed
2024-10-31 10:30:02 - src.loop_controller - INFO - ✓ DeepSeek API connectivity test passed
2024-10-31 10:30:02 - __main__ - INFO - ✓ All startup tests passed
2024-10-31 10:30:02 - __main__ - INFO - Starting main trading loop...
2024-10-31 10:30:02 - __main__ - INFO - Press Ctrl+C to stop gracefully
================================================================================
```

**Live Mode** (with 5-second warning):
```
================================================================================
AUTONOMOUS TRADING AGENT
================================================================================
2024-10-31 10:30:00 - __main__ - INFO - Loading configuration from: .env
2024-10-31 10:30:00 - __main__ - INFO - ✓ Configuration loaded successfully
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
!!! LIVE MODE ENABLED !!!
!!! REAL MONEY WILL BE TRADED !!!
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
2024-10-31 10:30:00 - __main__ - WARNING - Press Ctrl+C within 5 seconds to abort...
```

### Stopping the Agent

Press `Ctrl+C` to stop the agent gracefully. The agent will complete its current iteration before shutting down:

```
^C
2024-10-31 10:35:00 - __main__ - INFO - Keyboard interrupt received
2024-10-31 10:35:00 - src.loop_controller - INFO - Shutdown signal received
2024-10-31 10:35:00 - src.loop_controller - INFO - Completing current iteration...
2024-10-31 10:35:01 - src.loop_controller - INFO - Agent stopped gracefully
================================================================================
Agent stopped successfully
================================================================================
```

## How It Works

### Agent Cycle

The agent runs in a continuous loop with the following steps:

1. **Fetch Market Data**: Retrieves current price, bid/ask, OHLCV candles, and computes technical indicators
2. **Get LLM Decision**: Constructs a prompt with market context and asks DeepSeek for a trading decision
3. **Parse Decision**: Validates the LLM output and ensures it's in the correct format
4. **Risk Validation**: Checks the decision against position limits, leverage constraints, and safety rules
5. **Execute Trade**: If approved, submits the order to the exchange
6. **Log Everything**: Records all data, decisions, and results to a JSONL file
7. **Sleep**: Waits for the configured interval before starting the next cycle

### Decision Format

The LLM returns decisions in JSON format:

```json
{
  "action": "long",
  "size_pct": 0.25,
  "reason": "EMA(20) crossed above EMA(50), RSI at 55 indicates bullish momentum"
}
```

**Actions**:
- `long`: Open or add to a long position
- `short`: Open or add to a short position
- `close`: Close the current position
- `hold`: Do nothing

**Size Percentage**: A value between 0.0 and 1.0 representing what percentage of available equity to use.

### Risk Management

The system includes multiple layers of risk protection:

**Core Risk Rules** (always active):
- Position size cannot exceed `MAX_EQUITY_USAGE_PCT` of account equity
- Leverage cannot exceed `MAX_LEVERAGE`
- Cannot close a position that doesn't exist
- Requires valid market price data

**Optional Risk Safeguards**:
- **Daily Loss Cap**: Stops trading (except closing positions) if daily loss exceeds threshold
- **Cooldown Period**: Enforces minimum time between opening new positions
- **LLM Sanity Check**: Alerts if LLM repeatedly requests 100% position sizes

## Logging

### Log Files

The agent creates two types of logs:

1. **Application Logs**: `logs/agent.log` - System events, errors, and status messages
2. **Cycle Logs**: `agent_log.jsonl` - Detailed record of every trading cycle

### Cycle Log Format

Each line in `agent_log.jsonl` is a JSON object containing:

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

### Example Log Output

**Successful Trade**:
```json
{
  "timestamp": 1730395200000,
  "symbol": "BTC/USDT",
  "market_price": 68654.5,
  "position_before": 0.0,
  "llm_raw_output": "{\"action\": \"long\", \"size_pct\": 0.25, \"reason\": \"Strong bullish momentum with EMA(20) > EMA(50) and RSI at 58\"}",
  "parsed_action": "long",
  "parsed_size_pct": 0.25,
  "parsed_reason": "Strong bullish momentum with EMA(20) > EMA(50) and RSI at 58",
  "risk_approved": true,
  "risk_reason": "",
  "executed": true,
  "order_id": "87654321",
  "filled_size": 0.036,
  "fill_price": 68655.0,
  "mode": "testnet"
}
```

**Risk Denial**:
```json
{
  "timestamp": 1730395230000,
  "symbol": "BTC/USDT",
  "market_price": 68700.0,
  "position_before": 0.036,
  "llm_raw_output": "{\"action\": \"long\", \"size_pct\": 0.50, \"reason\": \"Continue building position\"}",
  "parsed_action": "long",
  "parsed_size_pct": 0.5,
  "parsed_reason": "Continue building position",
  "risk_approved": false,
  "risk_reason": "exceeds max position size",
  "executed": false,
  "order_id": null,
  "filled_size": null,
  "fill_price": null,
  "mode": "testnet"
}
```

**Hold Decision**:
```json
{
  "timestamp": 1730395260000,
  "symbol": "BTC/USDT",
  "market_price": 68680.0,
  "position_before": 0.036,
  "llm_raw_output": "{\"action\": \"hold\", \"size_pct\": 0.0, \"reason\": \"Market consolidating, waiting for clearer signal\"}",
  "parsed_action": "hold",
  "parsed_size_pct": 0.0,
  "parsed_reason": "Market consolidating, waiting for clearer signal",
  "risk_approved": true,
  "risk_reason": "",
  "executed": false,
  "order_id": null,
  "filled_size": null,
  "fill_price": null,
  "mode": "testnet"
}
```

**Parsing Error (Forced Hold)**:
```json
{
  "timestamp": 1730395290000,
  "symbol": "BTC/USDT",
  "market_price": 68720.0,
  "position_before": 0.036,
  "llm_raw_output": "I think we should buy more because the trend looks good",
  "parsed_action": "hold",
  "parsed_size_pct": 0.0,
  "parsed_reason": "forced hold due to parsing error",
  "risk_approved": true,
  "risk_reason": "",
  "executed": false,
  "order_id": null,
  "filled_size": null,
  "fill_price": null,
  "mode": "testnet"
}
```

## Monitoring

### What to Monitor

1. **Application Logs**: Check `logs/agent.log` for errors and warnings
2. **Cycle Logs**: Analyze `agent_log.jsonl` for decision patterns and execution results
3. **Exchange Account**: Monitor your exchange account for positions and balance
4. **Risk Denials**: Watch for repeated risk denials (may indicate configuration issues)
5. **API Errors**: Look for connectivity issues with exchange or DeepSeek

### Common Issues

**Exchange API Errors**:
- Check API key permissions (should have read + trade, not withdrawal)
- Verify API key is not expired
- Check IP whitelist settings if configured
- Ensure sufficient balance for trading

**DeepSeek API Errors**:
- Verify API key is valid
- Check API rate limits
- Ensure network connectivity

**Risk Denials**:
- Review `MAX_EQUITY_USAGE_PCT` setting (may be too restrictive)
- Check `MAX_LEVERAGE` setting
- Verify position size calculations

**Parsing Errors**:
- LLM may be returning invalid JSON
- Check DeepSeek API status
- Review prompt template if errors persist

## Testing

### Unit Tests

Run the test suite:

```bash
pytest tests/
```

Run specific test file:

```bash
pytest tests/test_decision_parser.py
```

Run with verbose output:

```bash
pytest -v tests/
```

### Manual Testing on Testnet

1. Set `RUN_MODE=testnet` in `.env`
2. Configure Binance testnet API keys
3. Start the agent: `python main.py`
4. Monitor logs and exchange account
5. Test different market conditions
6. Verify risk rules are working correctly

## Project Structure

```
autonomous-trading-agent/
├── main.py                 # Entry point
├── requirements.txt        # Python dependencies
├── .env.example           # Example environment configuration
├── .env                   # Your configuration (not in git)
├── README.md              # This file
├── logs/                  # Application logs
│   └── agent.log
├── agent_log.jsonl        # Cycle logs
├── src/                   # Source code
│   ├── config.py          # Configuration loading
│   ├── data_acquisition.py # Market data fetching
│   ├── decision_provider.py # LLM integration
│   ├── decision_parser.py  # Decision validation
│   ├── risk_manager.py     # Risk rules
│   ├── trade_executor.py   # Order execution
│   ├── logger.py           # Cycle logging
│   ├── loop_controller.py  # Main orchestration
│   └── models.py           # Data models
└── tests/                  # Unit tests
    ├── test_decision_parser.py
    └── test_logger.py
```

## Extending the System

### Adding a New LLM Provider

1. Create a new class that extends `DecisionProvider` in `src/decision_provider.py`
2. Implement the `get_decision()` method
3. Update `src/loop_controller.py` to support the new provider
4. Add configuration option in `.env`

Example:
```python
class AliveDecisionProvider(DecisionProvider):
    def get_decision(self, snapshot: MarketSnapshot, 
                     position_size: float, equity: float) -> str:
        # Implement Alive-1 API call
        pass
```

### Adding a New Exchange

1. Update `src/data_acquisition.py` to handle exchange-specific initialization
2. Update `src/trade_executor.py` for exchange-specific order handling
3. Add exchange type to configuration validation
4. Test thoroughly on testnet

### Adding New Technical Indicators

1. Update `src/data_acquisition.py` to compute additional indicators
2. Update the `MarketSnapshot` model in `src/models.py`
3. Update the LLM prompt template to include new indicators

## Troubleshooting

### Agent Won't Start

- Check `.env` file exists and has all required variables
- Verify API keys are correct
- Check Python version (3.10+ required)
- Ensure all dependencies are installed: `pip install -r requirements.txt`

### No Trades Executing

- Check risk manager logs for denials
- Verify `MAX_EQUITY_USAGE_PCT` is not too restrictive
- Ensure LLM is returning valid decisions (check cycle logs)
- Verify exchange account has sufficient balance

### Frequent Parsing Errors

- Check DeepSeek API status
- Review LLM responses in cycle logs
- Verify prompt template is correct
- Consider adjusting LLM temperature/parameters

### Exchange Connection Issues

- Verify API keys have correct permissions
- Check network connectivity
- Ensure exchange is not under maintenance
- Review rate limit settings

## License

[Add your license here]

## Disclaimer

This software is provided for educational and research purposes only. Trading cryptocurrencies carries significant risk of loss. The authors and contributors are not responsible for any financial losses incurred through the use of this software. Always test thoroughly on testnet before using real funds, and never trade with money you cannot afford to lose.

## Support

For issues, questions, or contributions, please [open an issue](link-to-issues) or submit a pull request.

## Acknowledgments

- Built with [CCXT](https://github.com/ccxt/ccxt) for exchange connectivity
- Powered by [DeepSeek](https://www.deepseek.com/) for LLM reasoning
- Technical indicators via [pandas-ta](https://github.com/twopirllc/pandas-ta)
