# Trading Strategy Guide

## Overview

Your agent now supports **3 trading modes**:

### 1. **HYBRID_ATR** (Recommended - "Crypto-Realistic")
- **Strategy**: ATR Breakout + Trend Filter
- **AI Role**: Risk filter (vetoes bad setups)
- **How it works**:
  1. Rule checks: Is price > EMA50? (uptrend)
  2. Rule checks: Did price break above Keltner band? (volatility breakout)
  3. If YES → Ask AI: "Is this a fake breakout?"
  4. If AI says NO → Execute trade
  5. Stop loss: ATR×2 below entry
  6. Take profit: 2R (risk-reward ratio)
  7. Position size: 1% risk per trade

**Pros**: Backtestable, proven for crypto, AI adds intelligence
**Cons**: Fewer trades, requires patience

### 2. **HYBRID_EMA** (Improved Current System)
- **Strategy**: EMA Crossover
- **AI Role**: Risk filter
- **How it works**:
  1. Rule checks: Is EMA20 > EMA50 and RSI < 70?
  2. If YES → Ask AI: "Is this setup risky?"
  3. If AI approves → Execute
  4. Position size: 5-10% based on signal strength

**Pros**: More trades, simpler logic
**Cons**: Less proven, can get chopped in sideways markets

### 3. **AI_ONLY** (Original System)
- **Strategy**: None
- **AI Role**: Makes ALL decisions
- **How it works**:
  1. AI analyzes EMAs, RSI, cash, leverage
  2. AI decides: buy, sell, hold
  3. No hard rules

**Pros**: Flexible, adapts to any market
**Cons**: Not backtestable, "vibes-based", unpredictable

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

**Mode**: HYBRID_ATR (ATR Breakout + AI Filter)
**Timeframe**: 1 hour
**Indicators**: EMA20, EMA50, RSI14, ATR14, Keltner Bands
**Risk per trade**: 1% of equity
**Max position**: 10% of equity
**Stop loss**: ATR×2
**Take profit**: 2R

## What Changed

### New Indicators
- **ATR (Average True Range)**: Measures volatility
- **Keltner Bands**: EMA20 ± ATR×1.5 (volatility bands)

### New Logic
- **Rule-based entry**: Price must break above Keltner upper band
- **Trend filter**: Only long when price > EMA50
- **AI filter**: DeepSeek vetoes fake breakouts
- **Proper stops**: ATR-based stop loss (adapts to volatility)
- **Risk management**: 1% risk per trade (not 10% YOLO)

## Expected Behavior

**HYBRID_ATR mode**:
- Fewer trades (maybe 1-3 per week)
- Higher win rate (60-70%)
- Waits for clean breakouts
- AI will veto most signals (that's good!)
- More patient, less gambling

**AI_ONLY mode**:
- More trades
- Lower win rate
- Unpredictable
- Good for testing/learning

## Monitoring

Watch the **Agent Chat** for messages like:
- "Strategy signal: long (confidence: 0.8)"
- "AI filter APPROVED the trade"
- "AI filter VETOED: likely fake breakout"

This shows you the strategy + AI working together.

## Next Steps

1. **Run on testnet** for 1-2 weeks
2. **Track performance** (win rate, avg P&L)
3. **Tune parameters** if needed (ATR multiplier, stop distance)
4. **Go live** when confident

## Resources

- ATR Breakout: https://medium.com/@quantifiedstrategies
- Keltner Channels: https://www.investopedia.com/terms/k/keltnerchannel.asp
- Risk Management: https://www.babypips.com/learn/forex/money-management
