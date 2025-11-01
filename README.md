# AETHER - Autonomous Trading Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![React 18](https://img.shields.io/badge/react-18-blue.svg)](https://reactjs.org/)

A sophisticated autonomous cryptocurrency trading agent powered by DeepSeek AI, featuring real-time market analysis, intelligent risk management, and a modern web dashboard for monitoring and control.

## 🎯 Features

### Core Trading Capabilities
- **Hybrid Strategy System**: Combines rule-based technical analysis (ATR-filtered Trend/Breakout, EMA) with AI-powered risk filtering
- **AI-Only Mode**: Full autonomous decision-making using DeepSeek LLM
- **Intelligent Risk Management**: Position sizing, leverage limits, stop-loss/take-profit monitoring, daily loss caps
- **Multi-Exchange Support**: Binance (testnet & live) and Hyperliquid
- **Real-time Execution**: Automated order placement with configurable intervals

### Dashboard Features
- **Live Market Chart**: Interactive candlestick/area charts with trade markers using TradingView Lightweight Charts
- **Position Monitoring**: Real-time P&L tracking, leverage, notional values, and exit plans
- **Trade History**: Complete audit trail with holding times, entry/exit prices, and performance metrics
- **Agent Chat**: Intelligent message filtering showing key decisions and market analysis
- **Emergency Controls**: One-click kill switch to close all positions, pause/resume agent

### Technical Indicators
- EMA (20, 50 periods)
- RSI (14 period)
- ATR (14 period)
- Keltner Channels
- Real-time price action analysis

## 🏗️ Architecture

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

## 📋 Prerequisites

- **Python 3.8+** with pip
- **Node.js 16+** and npm
- **Exchange Account**: Binance testnet (recommended) or live account
- **DeepSeek API Key**: Get one at [platform.deepseek.com](https://platform.deepseek.com)

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone <repository-url>
cd spooky
```

### 2. Backend Setup

```bash
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
STRATEGY_MODE=hybrid_atr
DECISION_PROVIDER=deepseek
```

### 3. Frontend Setup

```bash
cd frontend
npm install
```

### 4. Start the Services

**Terminal 1 - Start FastAPI Server:**
```bash
cd backend
python api_server.py
```
The API server will run on `http://localhost:8000`

**Terminal 2 - Start Trading Agent:**
```bash
cd backend
python main.py
```

**Terminal 3 - Start Frontend:**
```bash
cd frontend
npm run dev
```
The frontend will run on `http://localhost:3000`

### 5. Access the Dashboard

Open your browser and navigate to `http://localhost:3000`

## 📖 Configuration

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

## 🔌 API Endpoints

### Frontend → Backend Communication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/balance` | GET | Get account balance and unrealized P&L |
| `/api/positions` | GET | Get all open positions |
| `/api/positions` | PUT | Sync all positions (used by agent) |
| `/api/trades` | GET | Get completed trades history |
| `/api/agent-messages` | GET | Get agent chat messages |
| `/api/emergency-close` | POST | Trigger emergency close all positions |
| `/api/agent/pause` | POST | Pause the trading agent |
| `/api/agent/resume` | POST | Resume the trading agent |
| `/api/agent/status` | GET | Get agent pause status |

### Data Flow

1. **Agent → API Server**: Trading agent uses `APIClient` to push updates via PUT/POST
2. **Frontend → API Server**: Frontend polls API every 5 seconds via GET requests
3. **Real-time Updates**: Position sync happens on each cycle, balance updates on P&L changes

## 🎮 Usage

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
- Intelligent message filtering (no spam)
- Shows buy/sell decisions, price targets, market analysis
- Timestamped messages from DeepSeek AI

#### Chart
- Interactive candlestick or area chart
- Trade markers at entry/exit timestamps
- Timeframe selection (1D, 5D, 1M, 3M, 6M, 1Y)
- Real-time price updates from Binance API


## 🛡️ Safety Features

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

## 🚧 Development

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

##  License

MIT License

## Disclaimer

**This software is for educational and research purposes only. Trading cryptocurrencies involves substantial risk of loss. Always test thoroughly on testnet before using real funds. The authors are not responsible for any financial losses incurred while using this software.**

##  Acknowledgments

- **CCXT**: Universal cryptocurrency exchange trading library
- **DeepSeek**: AI-powered decision making
- **TradingView Lightweight Charts**: Professional charting library
- **FastAPI**: Modern Python web framework
- **React**: UI framework



