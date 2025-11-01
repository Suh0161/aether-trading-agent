# Trading Strategy Guide

## Overview

AETHER supports **3 trading modes** with adaptive swing/scalp capabilities:

### 1. **HYBRID_ATR** (Recommended - Adaptive Swing/Scalp)
- **Strategy**: Multi-timeframe ATR Breakout with VWAP + Volume Confirmation
- **AI Role**: Risk filter with full market awareness
- **Capabilities**: LONG and SHORT positions
- **How it works**:
  1. **Swing Mode** (1D/4H/1H trends):
     - Checks multi-timeframe trend alignment
     - Validates Keltner band breakout with volume (≥1.2x avg)
     - Confirms VWAP positioning and S/R levels
     - AI validates setup against resistance/support
     - Adaptive position sizing (1-5% based on account size)
     - ATR-based stop loss and 2R take profit
  
  2. **Scalp Mode** (15m/5m/1m trends):
     - Activates when no swing opportunity exists
     - Uses tighter Keltner bands and VWAP filter
     - Requires stronger volume (≥1.3x avg)
     - Faster exits on trend reversal or VWAP cross
     - Smaller position sizes (0.5-3%)
  
  3. **Short Trading**:
     - Mirrors long logic for downtrends
     - Sells below Keltner lower band
     - VWAP acts as resistance
     - Volume-confirmed breakdowns

**Pros**: Adaptive, volume-validated, multi-timeframe, both directions
**Cons**: Complex logic, requires patience for quality setups

### 2. **HYBRID_EMA** (Simple Trend Following)
- **Strategy**: EMA Crossover
- **AI Role**: Risk filter
- **How it works**:
  1. Rule checks: Is EMA20 > EMA50 and RSI < 70?
  2. If YES → Ask AI: "Is this setup risky?"
  3. If AI approves → Execute
  4. Position size: Adaptive based on account equity

**Pros**: Simple, more frequent trades
**Cons**: Less sophisticated, prone to whipsaws

### 3. **AI_ONLY** (Full AI Control)
- **Strategy**: None (AI decides everything)
- **AI Role**: Makes ALL decisions
- **How it works**:
  1. AI analyzes all multi-timeframe indicators
  2. AI considers VWAP, S/R levels, volume, OBV
  3. AI decides: buy, sell, hold, position size
  4. No hard rules, fully adaptive

**Pros**: Maximum flexibility, learns from all data
**Cons**: Not backtestable, harder to debug

## How to Switch Modes

Edit `backend/.env`:

```env
# For ATR Breakout (recommended)
STRATEGY_MODE=hybrid_atr

# For EMA Crossover
STRATEGY_MODE=hybrid_ema

# For pure AI
STRATEGY_MODE=ai_only
```

Then restart the agent.

## Current Configuration

**Mode**: HYBRID_ATR (Adaptive Swing/Scalp + AI Filter)
**Timeframes**: Multi-timeframe (1D, 4H, 1H, 15m, 5m, 1m)
**Indicators**: 
- Trend: EMA20, EMA50 (all timeframes)
- Momentum: RSI14 (all timeframes)
- Volatility: ATR14, Keltner Bands (all timeframes)
- Volume: Volume Ratio, OBV Trend (1H, 5m, 1m)
- Price Levels: VWAP, Pivot Points (R1-R3, S1-S3), Swing High/Low

**Risk Management**:
- Risk per trade: 1-5% (adaptive based on account size)
- Max position: 10% of equity
- Stop loss: ATR×2 (swing), ATR×1 (scalp)
- Take profit: 2R (swing), 1.5R (scalp)
- Virtual equity cap: $100 for testing (configurable)

**Position Sizing**:
- Accounts < $500: 5% risk per trade
- Accounts < $1000: 3% risk per trade
- Accounts ≥ $1000: 1% risk per trade
- Minimum position: 0.5% (scalp), 1% (swing)

## Key Features

### Multi-Timeframe Analysis
- **1D/4H**: Major trend direction
- **1H**: Primary swing timeframe
- **15m/5m**: Scalp entry timing
- **1m**: Micro-trend confirmation

### Volume Confirmation
- **Swing trades**: Require ≥1.2x average volume
- **Scalp trades**: Require ≥1.3x average volume
- **Strong volume** (≥1.5x): Boosts confidence
- **OBV trend**: Confirms accumulation/distribution

### Support/Resistance Awareness
- **Pivot Points**: Classic S/R levels (R1-R3, S1-S3)
- **Swing High/Low**: Recent price extremes
- **VWAP**: Intraday equilibrium price
- **AI Filter**: Vetoes trades into resistance/support

### Adaptive Strategy Selection
- **Swing Priority**: Always checks for swing opportunities first
- **Scalp Fallback**: Activates when no swing setup exists
- **Position Management**: Routes to correct strategy based on position type

## Expected Behavior

**HYBRID_ATR mode**:
- **Swing trades**: 1-3 per week (patient, high-quality setups)
- **Scalp trades**: 5-10 per week (opportunistic, quick exits)
- **Win rate**: 60-70% (swings), 50-60% (scalps)
- **AI veto rate**: 60-80% (filters out low-quality setups)
- **Short trades**: Activates in strong downtrends
- **Volume-aware**: Rejects breakouts with weak volume

**HYBRID_EMA mode**:
- More frequent trades (3-5 per week)
- Simpler logic, faster execution
- Good for trending markets

**AI_ONLY mode**:
- Fully adaptive, unpredictable frequency
- Uses all available indicators
- Good for testing AI decision-making

## Monitoring

Watch the **Agent Chat** for messages like:
- "Swing long setup detected on 1H breakout above $110.5k with 1.5x volume"
- "AI filter APPROVED: Clean breakout above R1 resistance"
- "AI filter VETOED: Weak volume (0.8x avg) - likely fake breakout"
- "Scalp short: 5m downtrend + price below VWAP"
- "Exiting scalp: 5m and 1m trends reversed"

The agent also responds to your questions in real-time:
- Ask "Why not trading?" to understand current market conditions
- Ask "What's the setup?" to see current S/R levels and trends
- Ask "Should I be worried?" to get risk assessment

## Next Steps

1. **Run on testnet** for 1-2 weeks
2. **Track performance** (win rate, avg P&L)
3. **Tune parameters** if needed (ATR multiplier, stop distance)
4. **Go live** when confident

## Resources

- ATR Breakout: https://medium.com/@quantifiedstrategies
- Keltner Channels: https://www.investopedia.com/terms/k/keltnerchannel.asp
- Risk Management: https://www.babypips.com/learn/forex/money-management
