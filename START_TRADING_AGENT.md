# Start Your AI Trading Agent with Live Frontend

## Prerequisites

### 1. Install Backend Dependencies
**Bash:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**PowerShell:**
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Install Frontend Dependencies
**Bash:**
```bash
cd frontend
npm install
```

**PowerShell:**
```powershell
cd frontend
npm install
```

### 3. Set up your `.env` file in the `backend/` directory:
```env
# Exchange API (use testnet for safety!)
EXCHANGE_TYPE=binance
BINANCE_API_KEY=your_testnet_api_key
BINANCE_SECRET=your_testnet_secret
BINANCE_TESTNET=true

# DeepSeek API
DEEPSEEK_API_KEY=your_deepseek_api_key

# Trading Config
SYMBOL=BTC/USDT
RUN_MODE=testnet
STRATEGY_MODE=hybrid_atr
LOOP_INTERVAL_SECONDS=30

# Virtual Equity (for testing with small balance)
VIRTUAL_STARTING_EQUITY=100

# Risk Management
MAX_DAILY_LOSS_PCT=10
MAX_LEVERAGE=3
```

## Start Everything

### Option 1: Single Command (Recommended)

**Bash:**
```bash
cd backend
python main.py
```

**PowerShell:**
```powershell
cd backend
python main.py
```

This starts both the trading agent AND the API server in the same process.

### Option 2: Frontend

**Terminal 2 - Frontend:**

**Bash:**
```bash
cd frontend
npm run dev
```

**PowerShell:**
```powershell
cd frontend
npm run dev
```

## What Happens

1. **Trading Agent + API Server** (single process)
   - Fetches multi-timeframe market data every 30 seconds
   - Analyzes 6 timeframes (1D, 4H, 1H, 15m, 5m, 1m)
   - Calculates 20+ indicators (EMA, RSI, ATR, VWAP, S/R, Volume, OBV)
   - AI makes trading decisions (swing/scalp, long/short)
   - Executes trades on Binance Testnet
   - API server runs in background thread on http://localhost:8000

2. **Frontend** displays everything live on http://localhost:5173
   - Real-time chart with BTC price
   - Trade markers showing entry/exit points
   - Current positions with live P&L
   - Completed trades history
   - Interactive agent chat
   - Balance and leverage monitoring

## Watch It Work!

Open http://localhost:5173 and you'll see:

### Chart Tab
- Live BTC/USDT price chart
- Trade annotations (LONG/SHORT markers)
- Multiple timeframe views (1D, 5D, 1M, 3M, 6M, 1Y)

### Positions Tab
- Open positions with:
  - Entry price and current price
  - Position size and type (SWING/SCALP)
  - Stop loss and take profit levels
  - Unrealized P&L
  - Leverage used

### Completed Trades Tab
- Trade history with:
  - Entry/exit prices
  - Position size and direction (LONG/SHORT)
  - Realized P&L
  - Timestamp

### Agent Chat Tab
- Real-time agent reasoning:
  - "Swing long setup detected on 1H breakout above $110.5k with 1.5x volume"
  - "AI filter APPROVED: Clean breakout above R1 resistance"
  - "Holding: Waiting for volume confirmation"
- **Interactive chat**: Ask the agent questions!
  - "Why not trading?"
  - "What's the current setup?"
  - "Should I be worried?"

## Safety Tips

- **ALWAYS use testnet first!** Set `RUN_MODE=testnet` and `BINANCE_TESTNET=true`
- Use `VIRTUAL_STARTING_EQUITY=100` to test with small virtual balance
- Monitor the agent closely for the first 24-48 hours
- Check terminal logs for decision reasoning
- Use emergency controls in the header (PAUSE AI, CLOSE ALL)

## Troubleshooting

**"fastapi not found" or "openai not found" error?**
- Make sure you installed backend requirements: `pip install -r requirements.txt`
- Activate virtual environment first: `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Linux/Mac)

**"DEEPSEEK_API_KEY is not set" error?**
- Check your `backend/.env` file exists
- Verify `DEEPSEEK_API_KEY=sk-...` is set correctly
- Restart the agent after editing `.env`

**Agent not showing in frontend?**
- Make sure `python main.py` is running (this starts both agent and API server)
- Check terminal for errors
- Verify API server started on http://localhost:8000

**No trades executing?**
- Check "Execution error: Order size is zero or negative" in logs
  - Solution: Increase `VIRTUAL_STARTING_EQUITY` to at least 100
- Check "Filter failure: NOTIONAL" errors
  - Solution: Minimum order is $10 on Binance Testnet
- Verify you have balance on testnet (get free testnet BTC/USDT from Binance)
- Agent is very selective - it may wait hours/days for quality setups

**Agent saying "Market data is currently unavailable"?**
- Make sure you're running `python main.py` (not `python api_server.py` separately)
- The API server must run in the same process as the trading loop

**Frontend not updating?**
- Hard refresh browser (Ctrl+Shift+R)
- Check API server is on port 8000
- Look at browser console (F12) for errors
- Verify frontend is running on http://localhost:5173

**Unicode errors in Windows terminal?**
- This is normal - the agent uses ASCII-only output
- Logs are still readable, just ignore the encoding warnings

**Position not appearing in Positions tab?**
- Refresh the page
- Check if the trade was actually executed (look at Binance Testnet)
- Verify the agent didn't immediately close the position

**Virtual equity suddenly changed?**
- If you started with an existing position, the agent pauses virtual equity tracking
- Virtual equity only tracks trades initiated by the agent
- Close all positions manually and restart for clean virtual equity tracking
