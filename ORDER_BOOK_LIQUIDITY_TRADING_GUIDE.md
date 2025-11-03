# How Agent Interprets Order Book & Liquidity Zones

## Overview
The agent uses **Tier 2 data** (order book microstructure + liquidity zones) to make smarter trading decisions. This data is:
1. Applied by **rule-based filters** (deterministic, before AI)
2. Included in **AI prompts** (for decision making)
3. Used differently for **swing vs scalp** and **long vs short**

---

## Order Book Imbalance

### What It Means:
- **Range**: -1.0 to +1.0
- **Positive (+0.1 to +1.0)**: Buyers heavier → BULLISH
- **Negative (-0.1 to -1.0)**: Sellers heavier → BEARISH
- **Near zero (-0.1 to +0.1)**: Balanced → NEUTRAL

### How Agent Uses It:

#### FOR LONG ENTRIES (Swing or Scalp):
- ✅ **Imbalance > +0.2**: STRONG buy-side pressure
  - Rule-based: **BOOST confidence +0.05**
  - AI sees: "SUPPORTS" → Extra confidence
  - **Action**: Proceed with confidence
  
- ⚠️ **Imbalance < -0.2**: Strong sell-side pressure
  - Rule-based: **REDUCE confidence -0.15**
  - AI sees: "OPPOSES" → Should consider VETO if severe
  - **Action**: May still trade but with lower confidence
  
- ➡️ **Imbalance -0.2 to +0.2**: Neutral
  - **Action**: Use other signals (trend, volume, etc.)

#### FOR SHORT ENTRIES (Swing or Scalp):
- ✅ **Imbalance < -0.2**: STRONG sell-side pressure
  - Rule-based: **BOOST confidence +0.05**
  - AI sees: "SUPPORTS" → Extra confidence
  - **Action**: Proceed with confidence
  
- ⚠️ **Imbalance > +0.2**: Strong buy-side pressure
  - Rule-based: **REDUCE confidence -0.15**
  - AI sees: "OPPOSES" → Should consider VETO if severe
  - **Action**: May still trade but with lower confidence
  
- ➡️ **Imbalance -0.2 to +0.2**: Neutral
  - **Action**: Use other signals (trend, volume, etc.)

### Spread & Bid/Ask Ratio:
- **Spread > 5bp**: Thin liquidity → Reduce confidence -0.1
- **Bid/Ask Vol Ratio > 2x**: Buyers dominating → Favor LONG
- **Bid/Ask Vol Ratio < 0.5x**: Sellers dominating → Favor SHORT

---

## Liquidity Zones

### What They Are:
- **Swing Highs** = Sell-side liquidity (above price) = Where SHORT stop-losses accumulate
- **Swing Lows** = Buy-side liquidity (below price) = Where LONG stop-losses accumulate
- "Smart money" targets these zones to trigger stop-losses, then reverses

### Distance to Zone:
- **< 0.5%**: Very close → Zone about to be tested → **BOOST confidence +0.05**
- **0.5% - 2.0%**: Approaching zone → Watch for sweep opportunity
- **> 2.0%**: Too far → **BLOCK trade** (unless sweep detected)

### How Agent Uses It:

#### FOR LONG POSITIONS (Swing or Scalp):
✅ **BEST Setup**: 
- **Bullish sweep detected** (swing_low swept)
  - Rule-based: **BOOST confidence** (+sweep_confidence × 0.2, up to +0.2)
  - Rule-based: **BOOST size +15%** (if sweep_confidence > 0.5)
  - AI sees: "STRONG CONFIRMATION - smart money grabbed buy-side liquidity"
  - **Action**: HIGH confidence trade

✅ **GOOD Setup**:
- **Near swing_low (< 0.5% away)** + volume spike
  - Rule-based: **BOOST confidence +0.05**
  - AI sees: "Zone nearby - watch for sweep"
  - **Action**: MEDIUM confidence trade

❌ **AVOID**:
- **Too far from zone (> 2.0%)** + no sweep
  - Rule-based: **BLOCK trade** → Returns "hold"
  - AI sees: "Too far from zone - WEAK signal"
  - **Action**: Wait for price to approach zone OR wait for sweep

❌ **NEVER**:
- **Bearish sweep detected** (swing_high swept)
  - Rule-based: **REDUCE confidence -0.2**
  - AI sees: "OPPOSES - bearish sweep detected, reduce confidence"
  - **Action**: Low confidence or HOLD

#### FOR SHORT POSITIONS (Swing or Scalp):
✅ **BEST Setup**:
- **Bearish sweep detected** (swing_high swept)
  - Rule-based: **BOOST confidence** (+sweep_confidence × 0.2, up to +0.2)
  - Rule-based: **BOOST size +15%** (if sweep_confidence > 0.5)
  - AI sees: "STRONG CONFIRMATION - smart money grabbed sell-side liquidity"
  - **Action**: HIGH confidence trade

✅ **GOOD Setup**:
- **Near swing_high (< 0.5% away)** + volume spike
  - Rule-based: **BOOST confidence +0.05**
  - AI sees: "Zone nearby - watch for sweep"
  - **Action**: MEDIUM confidence trade

❌ **AVOID**:
- **Too far from zone (> 2.0%)** + no sweep
  - Rule-based: **BLOCK trade** → Returns "hold"
  - AI sees: "Too far from zone - WEAK signal"
  - **Action**: Wait for price to approach zone OR wait for sweep

❌ **NEVER**:
- **Bullish sweep detected** (swing_low swept)
  - Rule-based: **REDUCE confidence -0.2**
  - AI sees: "OPPOSES - bullish sweep detected, reduce confidence"
  - **Action**: Low confidence or HOLD

---

## Sweep Confidence Scaling

- **0.7 - 1.0**: High quality sweep → MAX boost (+0.14 to +0.2)
- **0.4 - 0.7**: Medium quality → Moderate boost (+0.08 to +0.14)
- **< 0.4**: Weak sweep → Small boost or ignore

---

## Complete Trading Flow

### Example 1: LONG Swing Trade
1. **Strategy** generates LONG signal
2. **Rule-based liquidity filter** checks:
   - Distance to zone: 1.5% → OK (not blocked)
   - Order book imbalance: +0.25 → **BOOST confidence +0.05**
   - Sweep: Bullish sweep detected (confidence 0.8) → **BOOST confidence +0.16**, **BOOST size +15%**
   - Spread: 3bp → OK
3. **AI filter** sees:
   - Tier 2 data shows: "SUPPORTS LONG", "Bullish sweep = MAX CONFIDENCE"
   - Multi-TF alignment: ✅
   - Volume: ✅
   - **Result**: APPROVE

### Example 2: SHORT Scalp Trade
1. **Strategy** generates SHORT signal
2. **Rule-based liquidity filter** checks:
   - Distance to zone: 2.5% → **BLOCKED** (too far, no sweep)
   - **Result**: Returns "hold" → Trade blocked before AI filter

### Example 3: LONG Scalp (Opposed by OB)
1. **Strategy** generates LONG signal
2. **Rule-based liquidity filter** checks:
   - Distance to zone: 0.8% → OK
   - Order book imbalance: -0.3 → **REDUCE confidence -0.15**
   - Sweep: None
   - Spread: 2bp → OK
   - **Result**: Confidence reduced but trade proceeds
3. **AI filter** sees:
   - Tier 2 data shows: "OPPOSES LONG" (sellers heavy)
   - Should check if other signals are strong enough
   - **Result**: May VETO if confidence already low

---

## Key Differences: Swing vs Scalp

### SWING:
- Uses same order book & liquidity filters
- More emphasis on **HTF alignment** (1d/4h) + liquidity zones
- Can tolerate slightly wider distances (if HTF aligned)

### SCALP:
- Uses same order book & liquidity filters
- More emphasis on **5m/1m trends** + order book imbalance
- Requires **near zone (< 2.0%)** OR **sweep** to proceed
- **Spread > 5bp** = Higher slippage risk (more critical for scalps)

---

## Summary

The agent uses order book and liquidity zones in a **two-layer system**:

1. **Rule-based filters** (deterministic):
   - Blocks trades if too far from zone (> 2.0%)
   - Adjusts confidence/sizing based on order book imbalance
   - Boosts confidence/sizing when sweeps align
   - Reduces confidence when order book opposes

2. **AI filter** (intelligent):
   - Receives Tier 2 data in prompt
   - Can VETO if order book strongly opposes AND no other signals
   - Can APPROVE if sweep detected (even if other signals weak)
   - Makes final decision based on all context

Both filters work together to ensure trades only execute when:
- ✅ Near liquidity zones OR sweep detected
- ✅ Order book supports (or at least doesn't strongly oppose)
- ✅ Spread is reasonable (< 5bp for best execution)

