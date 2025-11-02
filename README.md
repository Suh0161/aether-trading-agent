# AETHER - Autonomous AI Trading Agent

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![React 18](https://img.shields.io/badge/react-18-blue.svg)](https://reactjs.org/)
[![DeepSeek AI](https://img.shields.io/badge/AI-DeepSeek-purple.svg)](https://www.deepseek.com/)

**AETHER** is a sophisticated autonomous cryptocurrency trading agent powered by **DeepSeek AI**. It combines multi-timeframe technical analysis, intelligent risk management, and real-time execution with a beautiful web dashboard for complete control and monitoring.

> **Current Status: Testing Phase**
> 
> **This project is currently in active testing and development. It has only been tested with demo/paper trading accounts and has NOT been tested with real funds on live exchanges. Use at your own risk. Always start with demo mode (`RUN_MODE=demo`) and thoroughly test all functionality before considering any live trading. The authors assume no responsibility for any financial losses.**

### Why AETHER?

- **AI-Powered Decision Making** - DeepSeek AI analyzes market conditions and validates every trade
- **Multi-Timeframe Analysis** - Combines 1D, 4H, 1H, 15m, 5m, and 1m data for comprehensive market view
- **Adaptive Strategies** - Automatically switches between swing trading and scalping based on market conditions
- **Smart Risk Management** - Dynamic position sizing, leverage limits, and automatic stop-loss/take-profit
- **Interactive AI Chat** - Ask your agent questions and get real-time market insights
- **Modern Dashboard** - Beautiful, responsive UI with live charts and real-time updates

## Key Features

### Trading Intelligence
- **Multi-Coin Trading** - Simultaneously monitors 6 cryptocurrencies (BTC, ETH, SOL, DOGE, BNB, XRP) and automatically trades the coin with the highest confidence setup each cycle
- **Adaptive Strategy System** - Automatically switches between swing trading (multi-day holds) and scalping (quick in-and-out) based on market conditions
- **Bidirectional Trading** - Supports both LONG (buy low, sell high) and SHORT (sell high, buy low) positions with proper stop-loss/take-profit for each direction
- **AI Risk Filter** - DeepSeek AI validates every trade, vetoing risky entries and approving high-confidence setups
- **Multi-Timeframe Analysis** - Analyzes 6 timeframes simultaneously (1D → 1m) for comprehensive market view
- **Volume Confirmation** - Requires strong volume (1.2x-1.5x average) to confirm breakouts and avoid fake moves
- **Support/Resistance Detection** - Automatically calculates pivot points, swing highs/lows, and key price levels
- **VWAP Filtering** - Uses Volume-Weighted Average Price to identify institutional order flow

### Risk Management
- **Two-Layer Position Sizing** - Layer 1: Capital allocation based on confidence (6-25% of equity). Layer 2: Leverage multiplier (1-3x) for amplification
- **Confidence-Based Leverage** - High-confidence setups (≥0.9) get 3x leverage, medium (0.6-0.8) get 1.5-2x, low (<0.6) get 1x
- **Smart Capital Allocation** - Allocates 25% capital for high-confidence swings, 15% for scalps, down to 6% for uncertain setups
- **Auto Stop-Loss/Take-Profit** - Every position (both LONG and SHORT) has automatic exit levels with calculated risk/reward ratios. SHORT positions have inverted SL/TP logic (SL above entry, TP below entry)
- **Daily Loss Cap** - Optional daily loss limit to prevent catastrophic drawdowns
- **Cooldown Periods** - Prevents rapid-fire trading and overtrading
- **Demo Account Mode** - Configurable mock starting equity via `.env` for testing without real funds
- **Futures Trading** - Full support for Binance USD-M Futures (long and short positions)

### Dashboard Features
- **Live TradingView Charts** - Professional candlestick/area charts with trade markers and multi-coin selector (BTC, ETH, SOL, DOGE, BNB, XRP)
- **Interactive AI Chat** - Ask your agent questions like "when will you trade?" and get real-time answers with full position awareness
- **Real-Time P&L Tracking** - Monitor unrealized P&L, leverage, and position details live. Positions tab shows SIDE (LONG/SHORT), coin, leverage, notional value, and unrealized P&L
- **Complete Trade History** - Audit trail with entry/exit prices, holding times, P&L, and trade direction (LONG/SHORT)
- **Emergency Controls** - One-click kill switch to close all positions + pause/resume agent
- **Agent Messages** - Intelligent filtering shows only key decisions and market analysis with detailed reasoning

### Technical Indicators
- **EMA** (50-period) - Trend direction
- **RSI** (14-period) - Momentum and overbought/oversold
- **ATR** (14-period) - Volatility measurement
- **Keltner Channels** - Breakout detection
- **VWAP** (1h, 5m) - Institutional order flow
- **Pivot Points** (R1-R3, S1-S3) - Support/resistance levels
- **OBV** (On-Balance Volume) - Volume trend confirmation

## Trading Concepts

### LONG vs SHORT (Direction)
- **LONG** - Buy low, sell high. Profit when price goes UP. Stop-loss is BELOW entry, take-profit is ABOVE entry.
- **SHORT** - Sell high, buy low. Profit when price goes DOWN. Stop-loss is ABOVE entry, take-profit is BELOW entry.

### SWING vs SCALP (Time Horizon)
- **SWING** - Multi-day holds (hours to days). Larger position sizes (up to 25% capital), higher leverage (up to 3x), wider stops, bigger targets.
- **SCALP** - Quick in-and-out (minutes). Smaller position sizes (up to 15% capital), moderate leverage (up to 2x), tight stops, quick profits.

**Example**: You can have a "LONG SWING" (buying BTC for a multi-day uptrend) or a "SHORT SCALP" (selling ETH for a quick 5-minute drop).

## How It Works

AETHER operates in a continuous 30-second cycle, analyzing markets and making decisions:

1. **Data Collection** - Fetches OHLCV data from Binance Futures API for 6 timeframes (1D, 4H, 1H, 15m, 5m, 1m)
2. **Indicator Calculation** - Computes EMA, RSI, ATR, Keltner Channels, VWAP, Pivot Points, and volume metrics
3. **Strategy Analysis** - Rule-based strategies (ATR Breakout or EMA Crossover) generate trade signals with confidence scores for both LONG and SHORT positions
4. **Position Sizing** - Two-layer system calculates capital allocation (6-25%) and leverage multiplier (1-3x) based on confidence, fully respecting `MAX_EQUITY_USAGE_PCT`
5. **Cost Optimization** - Intelligent LLM call skipping based on market change detection to reduce API costs by 50-70%
6. **AI Validation** - DeepSeek AI reviews the signal and market context, approving or vetoing the trade
7. **Risk Check** - Risk manager validates position size, leverage, and portfolio limits (prevents duplicate positions)
8. **Execution** - If approved, order is placed on Binance Futures with automatic stop-loss/take-profit for both LONG and SHORT positions
9. **P&L Tracking** - Real-time calculation of realized and unrealized P&L with accurate reporting in agent messages
10. **Monitoring** - Position is tracked every cycle for exit conditions (SL/TP hit, trend reversal, etc.)
11. **Communication** - Agent sends intelligent updates to dashboard with accurate profit/loss reporting and responds to user questions with full position awareness

### Decision Flow

```
Market Data → Strategy Signal → AI Filter → Risk Manager → Execute
                                    ↓
                              [VETO if risky]
                              [APPROVE if confident]
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (React)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Header  │  │  Chart   │  │ Sidebar  │  │  Modal   │   │
│  │ (Balance)│  │(Candles) │  │(Positions│  │ (Exit    │   │
│  │(Controls)│  │  Trades) │  │ Trades   │  │  Plans)  │   │
│  └────┬─────┘  └────┬─────┘  │Messages) │  └──────────┘   │
└───────┼──────────────┼────────┼──────────┼─────────────────┘
        │              │        │          │
        └──────────────┴────────┴──────────┘
                       │ HTTP (REST API)
        ┌──────────────┴──────────────────────────────┐
        │         FastAPI Server (Port 8000)          │
        │  ┌──────────────────────────────────────┐  │
        │  │ /api/balance                         │  │
        │  │ /api/positions                       │  │
        │  │ /api/trades                          │  │
        │  │ /api/agent-messages                  │  │
        │  │ /api/emergency-close                 │  │
        │  │ /api/agent/pause|resume|status       │  │
        │  └──────────────────────────────────────┘  │
        └──────────────────┬──────────────────────────┘
                           │
        ┌──────────────────┴──────────────────────────┐
        │      Trading Agent Backend (Python)         │
        │  ┌──────────────────────────────────────┐  │
        │  │  Loop Controller                     │  │
        │  │  ├─ Data Acquisition (CCXT)          │  │
        │  │  ├─ Strategy Engine                  │  │
        │  │  ├─ Hybrid Decision Provider         │  │
        │  │  ├─ Risk Manager                     │  │
        │  │  ├─ Trade Executor                   │  │
        │  │  └─ API Client → FastAPI             │  │
        │  └──────────────────────────────────────┘  │
        └──────────────────┬──────────────────────────┘
                           │
        ┌──────────────────┴──────────────────────────┐
        │           External Services                  │
        │  ┌──────────────┐  ┌──────────────────┐    │
        │  │  Exchange    │  │   DeepSeek API   │    │
        │  │  (Binance/   │  │   (LLM)          │    │
        │  │  Hyperliquid)│  │                  │    │
        │  └──────────────┘  └──────────────────┘    │
        └──────────────────────────────────────────────┘
```

## Prerequisites

- **Python 3.8+** with pip
- **Node.js 16+** and npm
- **Exchange Account**: 
  - **Demo Mode**: No account needed! Uses mock equity for testing
  - **Testnet**: Binance testnet account for testing with virtual funds
  - **Live**: Binance live account with Futures trading enabled
- **DeepSeek API Key**: Get one at [platform.deepseek.com](https://platform.deepseek.com)
- **For Futures Trading**: Enable "Enable Futures Trading" in Binance API Management settings

## Quick Start

### 1. Clone the Repository

**Bash / Linux / macOS:**
```bash
git clone <repository-url>
cd aether-trading-agent
```

**PowerShell / Windows:**
```powershell
git clone <repository-url>
cd aether-trading-agent
```

### 2. Backend Setup

**Bash / Linux / macOS:**
```bash
cd backend
pip install -r requirements.txt
```

**PowerShell / Windows:**
```powershell
cd backend
pip install -r requirements.txt
```

Create a `.env` file in the `backend` directory:

```bash
# Exchange Configuration
EXCHANGE_TYPE=binance_demo
# Options: binance_demo (demo trading), binance_testnet, binance (live), hyperliquid
SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT,DOGE/USDT,BNB/USDT,XRP/USDT

# API Credentials
EXCHANGE_API_KEY=your_exchange_api_key
EXCHANGE_API_SECRET=your_exchange_api_secret
DEEPSEEK_API_KEY=your_deepseek_api_key

# Agent Behavior
LOOP_INTERVAL_SECONDS=30
MAX_EQUITY_USAGE_PCT=0.10
MAX_LEVERAGE=3.0
RUN_MODE=demo
# Options: demo (uses MOCK_STARTING_EQUITY), testnet, live

# Strategy Mode: hybrid_atr, hybrid_ema, or ai_only
STRATEGY_MODE=hybrid_atr
# or STRATEGY_MODE=ai_only
DECISION_PROVIDER=deepseek

# Demo Account Configuration (for RUN_MODE=demo)
MOCK_STARTING_EQUITY=100.0
# Starting equity amount for demo mode testing
# This is the initial equity when using RUN_MODE=demo with binance_demo
# The agent will track equity changes based on realized P&L from trades
# Example: Set to 100.0 for $100 starting balance, 50.0 for $50, etc.
```

### 3. Frontend Setup

**Bash / Linux / macOS:**
```bash
cd frontend
npm install
```

**PowerShell / Windows:**
```powershell
cd frontend
npm install
```

### 4. Start the Services

**Terminal 1 - Start Trading Agent (includes API server):**

Bash / Linux / macOS:
```bash
cd backend
python main.py
```

PowerShell / Windows:
```powershell
cd backend
python main.py
```

This will start both the trading loop AND the API server on `http://localhost:8000`

**Terminal 2 - Start Frontend:**

Bash / Linux / macOS:
```bash
cd frontend
npm run dev
```

PowerShell / Windows:
```powershell
cd frontend
npm run dev
```

The frontend will run on `http://localhost:3000`

### 5. Access the Dashboard

Open your browser and navigate to `http://localhost:3000`

> **Note**: The trading agent now automatically starts the API server in a background thread. You no longer need to run `api_server.py` separately!

> **Demo Mode with MOCK_STARTING_EQUITY**: When using `RUN_MODE=demo` with `EXCHANGE_TYPE=binance_demo`, the agent uses `MOCK_STARTING_EQUITY` as the initial account balance. All trades update this equity based on realized P&L. This allows you to test the trading system without needing a real exchange account or risking real funds. The UI will show your starting equity (from `MOCK_STARTING_EQUITY`) plus any realized profits/losses from completed trades. Unrealized P&L is also tracked and displayed in real-time.

## Position Sizing System

AETHER uses a sophisticated **two-layer position sizing system** that adapts to trade confidence:

### Layer 1: Capital Allocation (How much $ to use)

Based on the strategy's confidence score (0.0 to 1.0):

| Confidence | Swing Trades | Scalp Trades | Example ($100 account) |
|------------|--------------|--------------|------------------------|
| ≥ 0.8 (High) | 25% of equity | 15% of equity | $25 or $15 |
| 0.6-0.8 (Medium) | 12% of equity | 10% of equity | $12 or $10 |
| < 0.6 (Low) | 6% of equity | 5% of equity | $6 or $5 |

### Layer 2: Leverage Multiplier (How much to amplify)

Based on confidence + setup quality:

| Confidence | Leverage | Position Multiplier |
|------------|----------|---------------------|
| ≥ 0.9 (Very High) | 3.0x | Capital × 3 |
| ≥ 0.8 (High) | 2.0x | Capital × 2 |
| ≥ 0.7 (Medium-High) | 1.5x | Capital × 1.5 |
| ≥ 0.6 (Medium) | 1.2x | Capital × 1.2 |
| < 0.6 (Low) | 1.0x | No amplification |

### Real-World Examples

**Example 1: Perfect Swing Setup (Confidence 0.95)**
- Account: $100
- Capital Allocation: 25% = $25
- Leverage: 3.0x
- **Final Position: $75 of BTC**
- Risk if SL hits: ~$1.50
- Reward if TP hits: ~$3.00

**Example 2: Good Scalp Setup (Confidence 0.75)**
- Account: $100
- Capital Allocation: 15% = $15
- Leverage: 1.5x
- **Final Position: $22.50 of BTC**
- Risk if SL hits: ~$0.45
- Reward if TP hits: ~$0.68

**Example 3: Uncertain Setup (Confidence 0.55)**
- Account: $100
- Capital Allocation: 6% = $6
- Leverage: 1.0x
- **Final Position: $6 of BTC**
- Risk if SL hits: ~$0.12
- Reward if TP hits: ~$0.24

### What Affects Confidence?

- **Volume Strength**: Strong volume (≥1.5x avg) boosts confidence to 0.95
- **Multi-Timeframe Alignment**: All timeframes trending same direction increases confidence
- **Breakout Quality**: Clean breakouts above/below Keltner bands increase confidence
- **S/R Positioning**: Trading away from resistance/support increases confidence

## Configuration

### Environment Variables

#### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `EXCHANGE_TYPE` | Exchange type | `binance_demo`, `binance_testnet`, `binance`, `hyperliquid` |
| `SYMBOLS` | Trading pairs (comma-separated) | `BTC/USDT,ETH/USDT,SOL/USDT,DOGE/USDT,BNB/USDT,XRP/USDT` |
| `EXCHANGE_API_KEY` | Exchange API key | Your exchange API key |
| `EXCHANGE_API_SECRET` | Exchange API secret | Your exchange API secret |
| `DEEPSEEK_API_KEY` | DeepSeek API key | Your DeepSeek API key |
| `RUN_MODE` | Execution mode | `demo`, `testnet`, or `live` |

#### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `LOOP_INTERVAL_SECONDS` | Cycle interval in seconds | `30` |
| `MAX_EQUITY_USAGE_PCT` | Max equity usage (0.0-1.0) | `0.10` |
| `MAX_LEVERAGE` | Maximum leverage allowed | `3.0` |
| `STRATEGY_MODE` | Strategy type | `hybrid_atr` |
| `MOCK_STARTING_EQUITY` | Starting equity for demo mode (only used when `RUN_MODE=demo` and `EXCHANGE_TYPE=binance_demo`) | `100.0` |
| `DAILY_LOSS_CAP_PCT` | Daily loss cap (0.0-1.0) | None |
| `COOLDOWN_SECONDS` | Cooldown between trades | None |

### Strategy Modes

- **`hybrid_atr`**: ATR-filtered Trend/Breakout strategy with AI risk filtering
- **`hybrid_ema`**: Simple EMA crossover strategy with AI risk filtering
- **`ai_only`**: Pure AI decision-making without rule-based signals

## API Endpoints

### Frontend → Backend Communication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/balance` | GET | Get account balance and unrealized P&L |
| `/api/positions` | GET | Get all open positions |
| `/api/positions` | PUT | Sync all positions (used by agent) |
| `/api/trades` | GET | Get completed trades history |
| `/api/agent-messages` | GET | Get agent chat messages |
| `/api/agent-chat` | POST | Send message to AI agent and get response |
| `/api/emergency-close` | POST | Trigger emergency close all positions |
| `/api/agent/pause` | POST | Pause the trading agent |
| `/api/agent/resume` | POST | Resume the trading agent |
| `/api/agent/status` | GET | Get agent pause status |

### Data Flow

1. **Agent → API Server**: Trading agent uses `APIClient` to push updates via PUT/POST
2. **Frontend → API Server**: Frontend polls API every 5 seconds via GET requests
3. **Real-time Updates**: Position sync happens on each cycle, balance updates on P&L changes

## Usage

### Dashboard Controls

#### Header Controls
- **START AI** / **PAUSE AI**: Control agent execution
- **CLOSE ALL**: Emergency kill switch to close all positions (agent continues running)
- **Balance Display**: Shows available cash and total unrealized P&L

#### Sidebar Tabs

**Positions Tab:**
- View all open positions with real-time P&L
- Hover over a position to see 3-dot menu
- Click menu to view Exit Plan (Target, Stop Loss, Invalid Condition)

**Completed Trades Tab:**
- View all closed trades with entry/exit details
- Shows holding time, quantity, notional values
- Displays net P&L for each trade

**Agent Chat Tab:**
- **Interactive AI Chat** - Ask your agent questions in real-time!
  - "when will you trade?" → Get specific entry conditions
  - "why are you holding?" → Understand current market analysis
  - "what's your strategy?" → Learn about decision-making process
- Intelligent message filtering (no spam)
- Shows buy/sell decisions, price targets, market analysis
- Timestamped messages from DeepSeek AI
- Auto-scrolls to latest messages

#### Chart
- Interactive candlestick or area chart
- Trade markers at entry/exit timestamps
- Timeframe selection (1D, 5D, 1M, 3M, 6M, 1Y)
- Real-time price updates from Binance API


## Safety Features

### Risk Management
- **Position Sizing**: Configurable percentage of equity per trade
- **Leverage Limits**: Maximum leverage enforcement
- **Stop Loss/Take Profit**: Automatic monitoring and execution
- **Daily Loss Cap**: Optional daily loss limit
- **Cooldown Periods**: Prevents rapid-fire trading
- **AI Veto**: DeepSeek can reject risky trades even if strategy signals

### Emergency Controls
- **Kill Switch**: Close all positions immediately
- **Pause/Resume**: Temporarily stop agent without closing positions
- **Live Mode Warning**: 5-second confirmation before live trading

### Best Practices
- ✅ **Always start with demo mode** (`RUN_MODE=demo` with `MOCK_STARTING_EQUITY`) for initial testing
- ✅ **Test on testnet** before live trading
- ✅ **Use API keys with read/trade only** (disable withdrawals)
- ✅ **For Futures trading**: Enable "Enable Futures Trading" in Binance API settings
- ✅ **Set conservative position sizes** (MAX_EQUITY_USAGE_PCT < 0.20)
- ✅ **Monitor the dashboard regularly**
- ✅ **Keep logs for audit trail** (`logs/agent_log.jsonl`)

##  Project Structure

```
spooky/
├── backend/
│   ├── api_server.py           # FastAPI server for frontend
│   ├── main.py                 # Agent entry point
│   ├── requirements.txt        # Python dependencies
│   ├── src/
│   │   ├── config.py           # Configuration management
│   │   ├── loop_controller.py  # Main trading loop orchestrator
│   │   ├── data_acquisition.py # Market data & indicators
│   │   ├── strategy.py         # Rule-based strategies
│   │   ├── decision_provider.py    # AI decision providers
│   │   ├── hybrid_decision_provider.py  # Hybrid strategy + AI
│   │   ├── risk_manager.py     # Risk checks
│   │   ├── trade_executor.py   # Order execution
│   │   ├── api_client.py       # Frontend API client
│   │   ├── decision_parser.py  # LLM output parser
│   │   ├── logger.py           # Structured logging
│   │   └── models.py           # Data models
│   └── logs/                   # Application logs
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # Main React component
│   │   ├── components/
│   │   │   ├── Header.jsx      # Header with controls
│   │   │   ├── Chart.jsx       # Trading chart
│   │   │   └── Sidebar.jsx     # Positions/trades/chat
│   │   └── main.jsx            # React entry point
│   ├── public/                 # Static assets
│   │   ├── aether.png          # Logo
│   │   ├── deepseek.png        # AI logo
│   │   └── favicon.*           # Favicons
│   ├── package.json            # Node dependencies
│   └── vite.config.js          # Vite configuration
│
├── README.md                   # This file
├── START_TRADING_AGENT.md      # Quick start guide
└── STRATEGY_GUIDE.md           # Strategy documentation
```

##  Monitoring & Logging

### Dashboard Tabs

#### Positions Tab
Displays all open positions with:
- **SIDE**: LONG (green) or SHORT (red) - indicates trade direction
- **COIN**: Which cryptocurrency (BTC, ETH, SOL, etc.)
- **LEVERAGE**: Actual leverage used (e.g., 2.0X)
- **NOTIONAL**: Total position value in USD
- **UNREAL P&L**: Current profit/loss ($ amount and %)
- **Exit Plan**: Click the menu button to see stop-loss, take-profit, and invalidation conditions

**Note**: Position type (SWING/SCALP) is tracked internally but not displayed in the UI. The agent knows which positions are swings vs scalps and manages them accordingly.

#### Completed Trades Tab
Shows trade history with:
- **Trade Summary**: "completed a **long** trade on BTC" (green for LONG, red for SHORT)
- **Entry/Exit Prices**: Where you entered and exited
- **Holding Time**: How long the position was held (e.g., "4H 53M")
- **P&L**: Profit or loss in USD
- **Timestamp**: When the trade was completed

#### Agent Chat Tab
- **Auto-Updates**: Agent sends messages when opening/closing positions or when market conditions change
- **Interactive Chat**: Ask questions like "why aren't you trading?" or "what's your plan?" and get detailed responses
- **Full Awareness**: Agent knows its current positions, P&L, leverage, risk/reward, and can explain its reasoning

### Log Files
- **`logs/agent.log`**: Standard application log (INFO/DEBUG)
- **`logs/agent_log.jsonl`**: Structured JSON log for each cycle

### Log Format (JSONL)
Each cycle is logged as a JSON object with:
- Timestamp
- Market snapshot (price, indicators)
- Decision (action, confidence, reasoning, position_type)
- Risk check results
- Execution result
- P&L updates

### Dashboard Updates
- Positions sync every cycle
- Balance updates on P&L changes
- Agent messages filtered for relevance
- Chart markers use actual trade timestamps

##  Troubleshooting

### Common Issues

**Frontend can't connect to backend:**
- Ensure API server is running on port 8000
- Check CORS settings in `api_server.py`
- Verify `API_BASE` in `App.jsx` matches server URL

**Agent not executing trades:**
- Check exchange API credentials
- Verify `RUN_MODE=demo` for demo mode or `RUN_MODE=testnet` for testing
- For Futures trading: Ensure "Enable Futures Trading" is enabled in Binance API settings
- Check logs for error messages
- Ensure sufficient balance on exchange (or correct `MOCK_STARTING_EQUITY` for demo mode)
- Verify `EXCHANGE_TYPE` matches your `RUN_MODE` (e.g., `binance_demo` for demo mode)

**Chart not loading:**
- Chart fetches directly from Binance public API
- Check browser console for CORS errors
- Verify symbol format (e.g., `BTC/USDT`)

**Emergency close not working:**
- Ensure agent is running and reading flag files
- Check `emergency_close.flag` exists in backend directory
- Verify file permissions

## Development

### Adding New Strategies

1. Add strategy class to `backend/src/strategy.py`
2. Implement `analyze()` method returning `StrategySignal`
3. Update `hybrid_decision_provider.py` to use new strategy
4. Add `STRATEGY_MODE` option in `config.py`

### Adding New Indicators

1. Add calculation in `backend/src/data_acquisition.py`
2. Include in `MarketSnapshot` model
3. Update strategy/decision provider to use indicator

### Frontend Customization

- Styling: Edit CSS files in `frontend/src/components/`
- Components: Modify React components in `frontend/src/components/`
- API calls: Update `App.jsx` fetch endpoints

## Recent Updates (November 2, 2025)

| Feature | Description |
|---------|-------------|
| **Futures Trading Support** | Full integration with Binance USD-M Futures for both LONG and SHORT positions |
| **Demo Account Mode** | Configurable mock starting equity via `MOCK_STARTING_EQUITY` environment variable |
| **Enhanced Short Trading** | Comprehensive multi-timeframe analysis for short positions (1D, 4H, 1H, 15m, 5m, 1m) |
| **Accurate P&L Reporting** | Fixed realized/unrealized P&L calculations with precise AI message reporting |
| **Cost Optimization** | Intelligent LLM call skipping based on market conditions to reduce API costs by 50-70% |
| **Position Tracking** | Internal position and equity tracking for demo mode with real-time UI updates |
| **Emergency Close** | Enhanced emergency stop functionality with proper position cleanup |
| **Configurable Equity Limits** | `MAX_EQUITY_USAGE_PCT` now fully respected across all strategy components |
| **Testing Phase Disclaimer** | Added clear warnings about testing status and demo-only usage |

### Future Improvements

- **UI Enhancements** - Planned improvements to the dashboard interface for better user experience and functionality

## License

Apache License 2.0

Copyright 2025 AETHER Trading Agent Contributors

**Last Updated: November 2, 2025**

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

## Disclaimer

**This software is for educational and research purposes only. Trading cryptocurrencies involves substantial risk of loss. This project is currently in testing phase and has only been tested with demo/paper trading accounts - it has NOT been tested with real funds on live exchanges. Always test thoroughly with demo mode (`RUN_MODE=demo`) or testnet before considering any live trading. Do NOT use real funds until you have thoroughly tested and validated the system in demo mode. The authors are not responsible for any financial losses incurred while using this software.**

##  Acknowledgments

- **CCXT**: Universal cryptocurrency exchange trading library
- **DeepSeek**: AI-powered decision making
- **TradingView Lightweight Charts**: Professional charting library
- **FastAPI**: Modern Python web framework
- **React**: UI framework



