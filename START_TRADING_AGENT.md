# Start AETHER Trading Agent with Live Frontend

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
SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT,DOGE/USDT,BNB/USDT,XRP/USDT  # 6 coins monitored
RUN_MODE=testnet
STRATEGY_MODE=hybrid_atr
LOOP_INTERVAL_SECONDS=30

# Demo mode starting equity (only used for binance_demo exchange type)
MOCK_STARTING_EQUITY=100

# Risk Management
MAX_DAILY_LOSS_PCT=10
MAX_LEVERAGE=3  # Scales automatically based on account size
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
   - **Monitors 6 cryptocurrencies**: BTC, ETH, SOL, DOGE, BNB, XRP
   - Analyzes 6 timeframes per coin (1D, 4H, 1H, 15m, 5m, 1m)
   - Calculates 20+ indicators (EMA, RSI, ATR, VWAP, S/R, Volume, OBV, Order Book)
   - **Simultaneous swing + scalp trading** on same coins
   - AI makes trading decisions with detailed reasoning (long/short/close/hold)
   - **Confidence-based trailing stops** (10-15% based on setup quality)
   - Executes trades on Binance Testnet or Demo mode
   - API server runs in background thread on http://localhost:8000
   - **JSON logging** for AI memory and audit trail

2. **Frontend** displays everything live on http://localhost:5173
   - **Multi-coin dashboard**: Switch between BTC, ETH, SOL, DOGE, BNB, XRP
   - Real-time charts with trade markers (LONG/SHORT/SWING/SCALP indicators)
   - Multiple timeframe views (1D, 5D, 1M, 3M, 6M, 1Y)
   - **Current positions**: Separate SWING/SCALP tabs with live P&L
   - **Trailing stop indicators** on charts
   - Completed trades history with strategy type
   - **Interactive agent chat** with detailed AI reasoning
   - Balance, leverage, and risk monitoring
   - **Real-time agent status** and cycle summaries

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
- Real-time agent reasoning with detailed AI analysis:
  - "Swing long setup detected on 1H breakout above $110.5k with 1.5x volume"
  - "AI APPROVED: Clean breakout above R1 resistance, 1D bullish trend intact, volume confirms momentum"
  - "AI VETOED: Price testing R1 with weak volume (0.8x avg), RSI overbought at 75, risk of rejection"
  - "Trailing stop: LONG position moved SL to $111.2k (10% trail, conf: 0.85)"
  - "Cycle summary: All 6 coins holding - mixed market sentiment, waiting for clearer signals"
- **Interactive chat**: Ask the agent questions!
- AI reasoning includes: current conditions, why the action, what would change the decision, risk levels, key triggers
  - "Why not trading?"
  - "What's the current setup?"
  - "Should I be worried?"

## Safety Tips

- **ALWAYS use testnet first!** Set `RUN_MODE=testnet` and `BINANCE_TESTNET=true`
- Use `VIRTUAL_STARTING_EQUITY=100` to test with small virtual balance
- Monitor the agent closely for the first 24-48 hours
- Check terminal logs for decision reasoning and position sizing details
- Use emergency controls in the header (PAUSE AI, CLOSE ALL)
- **Understand position sizing**: Three-tier leverage system (account size → confidence → final leverage)
  - Small accounts ($100): Conservative 1.0x leverage
  - Medium accounts ($2k): Moderate 2.0x leverage
  - Large accounts ($10k+): Full 3.0x leverage capability
- **Simultaneous trading**: Agent can run swing + scalp positions on same coin
- **Trailing stops**: Automatic profit protection (10-15% based on confidence)
- **Start conservative**: Monitor the first few trades closely!

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
- Check for separate SWING/SCALP position tabs

**Want to see AI decision logs?**
- Check `backend/agent_log.jsonl` for detailed JSON logs of all decisions
- Each cycle includes: market data, AI reasoning, risk assessment, execution status
- Useful for analyzing AI decision patterns and audit trails

**Virtual equity suddenly changed?**
- If you started with an existing position, the agent pauses virtual equity tracking
- Virtual equity only tracks trades initiated by the agent
- Close all positions manually and restart for clean virtual equity tracking
