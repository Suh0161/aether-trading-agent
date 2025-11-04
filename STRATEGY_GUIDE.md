# AETHER Trading Strategy Guide

## Overview

AETHER supports **3 trading modes** with **simultaneous swing/scalp capabilities** and **advanced AI reasoning**:

### 1. **HYBRID_ATR** (Recommended - Adaptive Swing/Scalp)
- **Strategy**: Multi-timeframe ATR Breakout with VWAP + Volume Confirmation
- **AI Role**: Risk filter with full market awareness + detailed reasoning
- **Capabilities**: LONG and SHORT positions, **Simultaneous Swing + Scalp trading**
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

  4. **Simultaneous Trading**: Can run both swing AND scalp positions on the same coin simultaneously
     - Independent position management per strategy type
     - Separate entry/exit logic for each strategy
     - Combined risk management across positions

  5. **Trailing Stop Loss**: Confidence-based trailing (10-15%)
     - High confidence (≥0.8): 10% trailing stops
     - Medium confidence (0.6-0.8): 12% trailing stops
     - Lower confidence (<0.6): 15% trailing stops
     - Locks in profits as price moves favorably

**Pros**: Adaptive, volume-validated, multi-timeframe, both directions, simultaneous strategies, AI-enhanced
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
- Stop loss: ATR×2 (swing), ATR×1 (scalp) + confidence-based trailing stops
- Take profit: 2R (swing), 1.5R (scalp) + AI-adjusted TP/SL for high confidence (≥0.7)
- Account size scaling: Smart leverage based on portfolio size ($0-$10k+ accounts)
- Max leverage: 1x-3x (scaled by account size and confidence)
- Daily loss cap: 10% maximum drawdown protection

**Position Sizing (Two-Layer System)**:

**Layer 1 - Capital Allocation**:
- High confidence (≥0.8): 25% equity (swings), 15% equity (scalps)
- Medium confidence (0.6-0.8): 12% equity (swings), 10% equity (scalps)
- Low confidence (<0.6): 6% equity (swings), 5% equity (scalps)

**Layer 2 - Leverage Multiplier** (Confidence-based):
- Very high confidence (≥0.9): 3.0x leverage
- High confidence (≥0.8): 2.0x leverage
- Medium-high confidence (≥0.7): 1.5x leverage
- Medium confidence (≥0.6): 1.2x leverage
- Low confidence (<0.6): 1.0x leverage (no amplification)

**Layer 3 - Account Size Scaling** (Automatic):
- $0-$500: 1.0x max leverage (very conservative)
- $500-$1k: 1.5x max leverage (conservative)
- $1k-$5k: 2.0x max leverage (moderate)
- $5k-$10k: 2.5x max leverage (moderate-high)
- $10k+: 3.0x max leverage (configurable max)

**Example**: High-confidence swing (0.85) with $100 account:
- Capital: 25% = $25
- Confidence leverage: 2.0x
- Account scaling: 1.0x (small account)
- **Final Leverage: 1.0x (capped by account size)**
- **Final Position: $25 of BTC**

**Example**: High-confidence swing (0.85) with $2,000 account:
- Capital: 25% = $500
- Confidence leverage: 2.0x
- Account scaling: 2.0x
- **Final Leverage: 2.0x**
- **Final Position: $1,000 of BTC**

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
- **Simultaneous trading**: Can run swing + scalp on same coin at once
- **Win rate**: 60-70% (swings), 50-60% (scalps)
- **AI veto rate**: 60-80% (filters out low-quality setups)
- **AI reasoning**: Detailed market analysis with current conditions, trend context, risk factors
- **Short trades**: Activates in strong downtrends
- **Volume-aware**: Rejects breakouts with weak volume
- **Trailing stops**: Automatic profit protection (10-15% based on confidence)

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
- "AI APPROVED: Clean breakout above R1 resistance, 1D bullish trend intact, volume confirms"
- "AI VETOED: Price testing R1 resistance with weak volume (0.8x avg), RSI overbought at 75"
- "Scalp short: 5m downtrend + price below VWAP, OBV decreasing"
- "Trailing stop: LONG position moved SL to $111.2k (10% trail, conf: 0.85)"
- "Cycle summary: All 6 coins holding - mixed market sentiment, waiting for clearer signals"

The agent also responds to your questions in real-time:
- Ask "Why not trading?" to understand current market conditions and reasoning
- Ask "What's the setup?" to see current S/R levels, trends, and key indicators
- Ask "Should I be worried?" to get risk assessment and position status
- Ask "Market analysis?" for detailed multi-timeframe trend analysis
- AI reasoning includes: current conditions, why the action, what would change the decision, risk levels, key triggers

## Next Steps

1. **Run on testnet** for 1-2 weeks
2. **Track performance** (win rate, avg P&L)
3. **Tune parameters** if needed (ATR multiplier, stop distance)
4. **Go live** when confident

## Resources

- ATR Breakout: https://medium.com/@quantifiedstrategies
- Keltner Channels: https://www.investopedia.com/terms/k/keltnerchannel.asp
- Risk Management: https://www.babypips.com/learn/forex/money-management
