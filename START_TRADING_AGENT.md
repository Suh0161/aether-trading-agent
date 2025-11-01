# Start Your AI Trading Agent with Live Frontend

## Prerequisites

1. **Set up your `.env` file** in the `backend/` directory:
```bash
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
LOOP_INTERVAL_SECONDS=300
```

## Start Everything

### Option 1: Automatic (Windows)
Double-click `start_all.bat`

### Option 2: Manual

**Terminal 1 - API Server:**
```bash
cd backend
python api_server.py
```

**Terminal 2 - Trading Agent:**
```bash
cd backend
python main.py
```

**Terminal 3 - Frontend:**
```bash
cd frontend
npm run dev
```

## What Happens

1. **API Server** runs on http://localhost:8000
   - Receives data from trading agent
   - Serves data to frontend

2. **Trading Agent** runs your AI bot
   - Fetches market data every 5 minutes (configurable)
   - AI makes trading decisions
   - Executes trades on exchange
   - Sends updates to API server

3. **Frontend** displays everything live on http://localhost:3001
   - Real-time chart with BTC price
   - Current positions
   - Completed trades with AI markers
   - Agent reasoning in chat
   - Balance updates

## Watch It Work!

Open http://localhost:3001 and you'll see:
- 📊 Live BTC chart updating every 30 seconds
- 🤖 AI trade signals showing where it bought/sold
- 💬 Agent messages explaining its decisions
- 💰 Real-time balance and P&L
- 📈 All your open positions

## Safety Tips

- **ALWAYS use testnet first!** Set `RUN_MODE=testnet` and `BINANCE_TESTNET=true`
- Test with small amounts
- Monitor the agent closely
- Check logs in `backend/logs/agent.log`

## Troubleshooting

**Agent not showing in frontend?**
- Make sure API server is running
- Check backend logs for errors
- Verify `.env` file is configured

**No trades executing?**
- Check your API keys are correct
- Verify you have balance on testnet
- Look at risk manager logs

**Frontend not updating?**
- Hard refresh browser (Ctrl+Shift+R)
- Check API server is on port 8000
- Look at browser console (F12) for errors
