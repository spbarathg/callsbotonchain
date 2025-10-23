# Blind Buy Mode Configuration

## Overview

**Blind Buy Mode** is enabled when `TS_BLIND_BUY=true`. In this mode, the bot will buy **every signal** sent by the signal detection system without applying additional filters.

## Current Status

✅ **Blind Buy Mode: ENABLED**

```yaml
Environment Variables:
- TS_BLIND_BUY=true
- TS_MIN_SCORE=0
```

## What Gets Bypassed

When blind buy is enabled, the following filters are **DISABLED**:

### 1. ❌ Staleness Check (DISABLED)
- **Normal mode:** Rejects signals if price has moved since alert
- **Blind mode:** Accepts all signals regardless of time delay

### 2. ❌ Minimum Score Filter (DISABLED)
- **Normal mode:** Requires score ≥ 8
- **Blind mode:** Accepts ANY score (0-10)

### 3. ❌ FOMO Protection (DISABLED)
- **Normal mode:** Rejects if price already pumped >50%
- **Blind mode:** Buys even if already pumped

### 4. ❌ Dump Protection (DISABLED)
- **Normal mode:** Rejects if price already dumped <-25%
- **Blind mode:** Buys even if already dumped

### 5. ❌ decide_trade Filters (ALREADY DISABLED)
- The `decide_trade()` function has **NO validation** - it accepts everything
- Line 50-51 in `strategy_optimized.py`:
  ```python
  # NO VALIDATION: Trade every signal blindly
  # Signal detection system already did all the filtering
  ```

## What Still Works

Even in blind buy mode, these protections **remain active**:

### ✅ Stop Loss (ACTIVE)
- Exits at -15% from entry price
- Protects capital on downside

### ✅ Trailing Stop (ACTIVE)
- Locks in profits as token pumps
- 15% trail from peak price

### ✅ Circuit Breaker (ACTIVE)
- Stops trading after 4 consecutive losses
- Stops trading after $4 daily loss

### ✅ Position Limits (ACTIVE)
- Max 4 open positions
- Prevents over-allocation

### ✅ Cooldown (ACTIVE)
- 4-hour rebuy cooldown after selling
- Prevents trading the same token repeatedly

## Trade Flow

**With Blind Buy Enabled:**

1. Signal Aggregator detects token → Publishes to Redis
2. Trader receives signal
3. ~~Staleness check~~ → **SKIPPED**
4. ~~Score filter~~ → **SKIPPED**
5. Calculate position size (based on score & conviction)
6. ~~FOMO/dump check~~ → **SKIPPED**
7. **BUY IMMEDIATELY** 🚀
8. Monitor position with stop loss/trailing stop

## Risk Management

**With blind buy, you're accepting higher risk:**

- ✅ **Pro:** Catch every signal, no missed opportunities
- ✅ **Pro:** Fastest execution, no delays
- ⚠️ **Con:** May buy tops (FOMO risk)
- ⚠️ **Con:** May buy dumps (catching falling knives)
- ⚠️ **Con:** No price validation before entry

**Your stop loss at -15% to -25% becomes CRITICAL** to protect capital!

## Example: GzPz8Kfk Token

**Before (with FOMO filter):**
- Signal received at $0.000027926
- Current price: $0.00004915 (+76%)
- **REJECTED:** Already pumped >50%
- **Protected from buying top** ✅

**After (blind buy):**
- Signal received at $0.000027926
- Current price: $0.00004915 (+76%)
- **BOUGHT:** No filter applied
- **Risk:** May dump immediately ⚠️

## Verification

Check logs for blind buy mode:
```bash
docker logs callsbot-trader 2>&1 | grep "Blind buy mode"
```

Expected output:
```
[DEBUG] Blind buy mode: skipping FOMO/dump filters
```

## Configuration Files

**Environment:** `deployment/docker-compose.yml`
```yaml
- TS_BLIND_BUY=true
- TS_MIN_SCORE=0
```

**Code:** `tradingSystem/cli_optimized.py`
```python
# Lines 705-726: FOMO/dump filters bypass
_blind_buy = os.getenv("TS_BLIND_BUY", "false").strip().lower() == "true"
if not _blind_buy:
    # Apply filters
else:
    print(f"[DEBUG] Blind buy mode: skipping FOMO/dump filters")
```

## Monitoring

Watch for these patterns:
- **Higher loss rate:** More trades caught at bad prices
- **Higher volatility:** More exposure to dumps/pumps
- **Faster entries:** No delays from filters

**Recommendation:** Monitor daily PnL closely and ensure circuit breaker is working!

## Related Files

- `tradingSystem/cli_optimized.py` - Main entry logic with filters
- `tradingSystem/strategy_optimized.py` - Position sizing (no filters)
- `deployment/docker-compose.yml` - Environment configuration







