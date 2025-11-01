# AETHER - Autonomous AI Trading Agent

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![React 18](https://img.shields.io/badge/react-18-blue.svg)](https://reactjs.org/)
[![DeepSeek AI](https://img.shields.io/badge/AI-DeepSeek-purple.svg)](https://www.deepseek.com/)

**AETHER** is a sophisticated autonomous cryptocurrency trading agent powered by **DeepSeek AI**. It combines multi-timeframe technical analysis, intelligent risk management, and real-time execution with a beautiful web dashboard for complete control and monitoring.

### Why AETHER?

- **AI-Powered Decision Making** - DeepSeek AI analyzes market conditions and validates every trade
- **Multi-Timeframe Analysis** - Combines 1D, 4H, 1H, 15m, 5m, and 1m data for comprehensive market view
- **Adaptive Strategies** - Automatically switches between swing trading and scalping based on market conditions
- **Smart Risk Management** - Dynamic position sizing, leverage limits, and automatic stop-loss/take-profit
- **Interactive AI Chat** - Ask your agent questions and get real-time market insights
- **Modern Dashboard** - Beautiful, responsive UI with live charts and real-time updates

## Key Features

### Trading Intelligence
- **Adaptive Strategy System** - Automatically switches between swing trading (multi-day holds) and scalping (quick in-and-out) based on market conditions
- **AI Risk Filter** - DeepSeek AI validates every trade, vetoing risky entries and approving high-confidence setups
- **Multi-Timeframe Analysis** - Analyzes 6 timeframes simultaneously (1D → 1m) for comprehensive market view
- **Volume Confirmation** - Requires strong volume (1.2x-1.5x average) to confirm breakouts and avoid fake moves
- **Support/Resistance Detection** - Automatically calculates pivot points, swing highs/lows, and key price levels
- **VWAP Filtering** - Uses Volume-Weighted Average Price to identify institutional order flow

### Risk Management
- **Smart Position Sizing** - Adaptive risk based on account size (5% for <$500, 3% for <$1K, 1% for $1K+)
- **Dynamic Leverage** - Automatically scales leverage based on portfolio size (1x-3x)
- **Auto Stop-Loss/Take-Profit** - Every position has automatic exit levels (0.2% SL, 0.3% TP for scalps)
- **Daily Loss Cap** - Optional daily loss limit to prevent catastrophic drawdowns
- **Cooldown Periods** - Prevents rapid-fire trading and overtrading
- **Virtual Equity Mode** - Test with $100 virtual balance while using real testnet account

### Dashboard Features
- **Live TradingView Charts** - Professional candlestick/area charts with trade markers
- **Interactive AI Chat** - Ask your agent questions like "when will you trade?" and get real-time answers
- **Real-Time P&L Tracking** - Monitor unrealized P&L, leverage, and position details live
- **Complete Trade History** - Audit trail with entry/exit prices, holding times, and performance
- **Emergency Controls** - One-click kill switch to close all positions + pause/resume agent
- **Agent Messages** - Intelligent filtering shows only key decisions and market analysis

### Technical Indicators
- **EMA** (50-period) - Trend direction
- **RSI** (14-period) - Momentum and overbought/oversold
- **ATR** (14-period) - Volatility measurement
- **Keltner Channels** - Breakout detection
- **VWAP** (1h, 5m) - Institutional order flow
- **Pivot Points** (R1-R3, S1-S3) - Support/resistance levels
- **OBV** (On-Balance Volume) - Volume trend confirmation

## How It Works

AETHER operates in a continuous 30-second cycle, analyzing markets and making decisions:

1. **Data Collection** - Fetches OHLCV data from exchange for 6 timeframes (1D, 4H, 1H, 15m, 5m, 1m)
2. **Indicator Calculation** - Computes EMA, RSI, ATR, Keltner Channels, VWAP, Pivot Points, and volume metrics
3. **Strategy Analysis** - Rule-based strategies (ATR Breakout or EMA Crossover) generate trade signals
4. **AI Validation** - DeepSeek AI reviews the signal and market context, approving or vetoing the trade
5. **Risk Check** - Risk manager validates position size, leverage, and portfolio limits
6. **Execution** - If approved, order is placed on exchange with automatic stop-loss/take-profit
7. **Monitoring** - Position is tracked every cycle for exit conditions (SL/TP hit, trend reversal, etc.)
8. **Communication** - Agent sends intelligent updates to dashboard and responds to user questions

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
- **Exchange Account**: Binance testnet (recommended) or live account
- **DeepSeek API Key**: Get one at [platform.deepseek.com](https://platform.deepseek.com)

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
EXCHANGE_TYPE=binance_testnet
SYMBOL=BTC/USDT

# API Credentials
EXCHANGE_API_KEY=your_exchange_api_key
EXCHANGE_API_SECRET=your_exchange_api_secret
DEEPSEEK_API_KEY=your_deepseek_api_key

# Agent Behavior
LOOP_INTERVAL_SECONDS=30
MAX_EQUITY_USAGE_PCT=0.10
MAX_LEVERAGE=3.0
RUN_MODE=testnet

# Strategy Mode: hybrid_atr, hybrid_ema, or ai_only
STRATEGY_MODE=hybrid_atr or STRATEGY_MODE=ai_only
DECISION_PROVIDER=deepseek

# Virtual Equity (optional) - Test with virtual balance instead of real account balance
# VIRTUAL_STARTING_EQUITY=100.0
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

## Configuration

### Environment Variables

#### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `EXCHANGE_TYPE` | Exchange type | `binance_testnet`, `binance`, `hyperliquid` |
| `SYMBOL` | Trading pair | `BTC/USDT` |
| `EXCHANGE_API_KEY` | Exchange API key | Your exchange API key |
| `EXCHANGE_API_SECRET` | Exchange API secret | Your exchange API secret |
| `DEEPSEEK_API_KEY` | DeepSeek API key | Your DeepSeek API key |
| `RUN_MODE` | Execution mode | `testnet` or `live` |

#### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `LOOP_INTERVAL_SECONDS` | Cycle interval in seconds | `30` |
| `MAX_EQUITY_USAGE_PCT` | Max equity usage (0.0-1.0) | `0.10` |
| `MAX_LEVERAGE` | Maximum leverage allowed | `3.0` |
| `STRATEGY_MODE` | Strategy type | `hybrid_atr` |
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
- ✅ **Always start with testnet**
- ✅ **Use API keys with read/trade only** (disable withdrawals)
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

### Log Files
- **`logs/agent.log`**: Standard application log (INFO/DEBUG)
- **`logs/agent_log.jsonl`**: Structured JSON log for each cycle

### Log Format (JSONL)
Each cycle is logged as a JSON object with:
- Timestamp
- Market snapshot (price, indicators)
- Decision (action, confidence, reasoning)
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
- Verify `RUN_MODE=testnet` for testing
- Check logs for error messages
- Ensure sufficient balance on exchange

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

## License

Apache License 2.0

Copyright 2025 AETHER Trading Agent Contributors

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

**This software is for educational and research purposes only. Trading cryptocurrencies involves substantial risk of loss. Always test thoroughly on testnet before using real funds. The authors are not responsible for any financial losses incurred while using this software.**

##  Acknowledgments

- **CCXT**: Universal cryptocurrency exchange trading library
- **DeepSeek**: AI-powered decision making
- **TradingView Lightweight Charts**: Professional charting library
- **FastAPI**: Modern Python web framework
- **React**: UI framework



