# Time-Based Exit Feature

**Status:** ✅ ACTIVE  
**Deployed:** 2025-10-23 01:55 UTC+5:30  
**Environment Variable:** `TS_MAX_HOLD_TIME_SEC`  
**Default Value:** 3600 seconds (1 hour)

---

## Overview

Automatically sells positions that have been held for too long without triggering stop loss or trailing stop. This prevents capital from being stuck in stagnant or dead tokens.

---

## How It Works

### 1. Position Tracking
When a position is opened, the system records:
- `open_at`: Unix timestamp of when the position was created
- This timestamp is stored in the live position data in memory

### 2. Time-Based Check
On every exit check (every 2 seconds):
1. Calculate how long the position has been open: `hold_time = current_time - open_at`
2. If `hold_time >= TS_MAX_HOLD_TIME_SEC`, trigger a time-based exit
3. The position is sold at market with the standard escalating slippage (20-50%)

### 3. Exit Priority
The system checks exit conditions in this order:
1. **Time-based exit** (stagnant position) ← **NEW**
2. Stop loss (from entry price)
3. Trailing stop (from peak price)

This means a stagnant position will be sold **regardless of its current price**, freeing up capital for new opportunities.

---

## Configuration

### Environment Variable
```bash
TS_MAX_HOLD_TIME_SEC=3600  # 1 hour (default)
```

### Common Values
- `1800` = 30 minutes (aggressive capital rotation)
- `3600` = 1 hour (recommended default)
- `5400` = 90 minutes (conservative)
- `7200` = 2 hours (very conservative)
- `0` = Disabled (not recommended)

### Where to Set
In `deployment/docker-compose.yml` under the `trader` service:
```yaml
trader:
  environment:
    - TS_MAX_HOLD_TIME_SEC=3600
```

---

## Use Cases

### 1. Dead Tokens
Token pumped quickly, then went completely dead with no volume:
- **Without time-based exit:** Position stuck indefinitely
- **With time-based exit:** Sold after 1 hour, capital freed

### 2. Slow Bleed
Token slowly bleeding out but not quite hitting -15% stop loss:
- **Without time-based exit:** Position stuck for hours at -10% to -14%
- **With time-based exit:** Sold after 1 hour, preventing further losses

### 3. Stagnant Tokens
Token not moving up or down, just sitting there:
- **Without time-based exit:** Capital locked, missing other opportunities
- **With time-based exit:** Sold after 1 hour, freeing capital for better trades

### 4. Capital Rotation
Multiple good signals coming in but all slots filled with old positions:
- **Without time-based exit:** Miss new opportunities
- **With time-based exit:** Old positions automatically rotated out

---

## Logs

### Exit Type: `timeout`
When a time-based exit occurs, you'll see logs like:
```json
{
  "event": "exit_timeout",
  "token": "ix3VmeCT6tDTfbNwPhicrBnFv5H1Uycj5EyrjZcpump",
  "pid": 27,
  "strategy": "General",
  "entry_price": 0.00001234,
  "exit_price": 0.00001200,
  "peak": 0.00001400,
  "pnl_usd": -0.34,
  "pnl_pct": -2.75,
  "reason": "Max hold time reached: 60 min >= 60 min (freeing capital)",
  "tx": "abc123..."
}
```

### Log Messages
- `Max hold time reached: 60 min >= 60 min (freeing capital)` - Position held for 1 hour
- `Cooldown added after timeout exit` - 4-hour rebuy cooldown applied

---

## Integration with Other Features

### 1. Cooldown System
After a time-based exit, the token is added to the 4-hour cooldown list to prevent immediate rebuy.

### 2. Circuit Breaker
Time-based exits count toward the circuit breaker:
- If the exit is at a loss, it contributes to daily PnL and consecutive losses
- Circuit breaker will trip if limits are exceeded (20% daily loss or 5 consecutive losses)

### 3. Price Caching
Uses the standard price cache (10s TTL) to get current token price for the exit.

### 4. Escalating Slippage
Time-based exits use the same escalating slippage as stop loss/trailing stop exits:
- Attempt 1: 20% slippage
- Attempt 2: 30% slippage
- Attempt 3: 40% slippage
- Attempt 4: 50% slippage (max)

---

## Performance Impact

### Benefits
- **Frees capital:** Prevents positions from being stuck indefinitely
- **Better rotation:** Allows new high-quality signals to be traded
- **Risk management:** Limits exposure to stagnant/dead tokens
- **Prevents FOMO holds:** Forces discipline on holding times

### Potential Downsides
- **Late pumps:** A token that pumps after being held for 55+ minutes might be sold just before the pump
- **Small losses:** May exit at small losses (-5% to -10%) before stop loss is hit
- **Missed moonshots:** Very rare tokens that pump hours after buy might be missed

### Optimization
- **1 hour is a good default** based on typical memecoin pump/dump cycles
- Most profitable exits happen within 30 minutes
- Tokens that don't move within 1 hour are unlikely to pump significantly
- Adjust based on your strategy and signal quality

---

## Code Changes

### 1. `tradingSystem/config_optimized.py`
```python
# Time-Based Exit - Automatically sell stagnant positions
# Prevents capital from being stuck in dead/inactive tokens
MAX_HOLD_TIME_SECONDS = _get_int("TS_MAX_HOLD_TIME_SEC", 3600)  # Default: 1 hour
```

### 2. `tradingSystem/trader_optimized.py`
```python
# In open_position(): Track open timestamp
self.live[token] = {
    "pid": pid,
    "strategy": strategy,
    "entry_price": fill.price,
    "peak_price": fill.price,
    "price_failures": 0,
    "sell_failures": 0,
    "open_at": time.time(),  # NEW
}

# In check_exits(): Check time-based exit first
open_at = data.get("open_at", 0)
if open_at > 0:
    hold_time = time.time() - open_at
    if hold_time >= MAX_HOLD_TIME_SECONDS:
        exit_type = "timeout"
        hold_minutes = int(hold_time / 60)
        max_minutes = int(MAX_HOLD_TIME_SECONDS / 60)
        exit_reason = f"Max hold time reached: {hold_minutes} min >= {max_minutes} min (freeing capital)"
```

### 3. `deployment/docker-compose.yml`
```yaml
trader:
  environment:
    - TS_MAX_HOLD_TIME_SEC=3600
```

---

## Testing

### Verify Feature is Active
```bash
# Check environment variable
ssh root@64.227.157.221 "docker exec callsbot-trader env | grep TS_MAX_HOLD_TIME_SEC"
# Should output: TS_MAX_HOLD_TIME_SEC=3600

# Monitor for time-based exits
ssh root@64.227.157.221 "docker logs callsbot-trader --follow 2>&1 | grep -E 'timeout|Max hold time'"
```

### Manual Test
1. Buy a token
2. Wait 1 hour
3. If the token hasn't hit stop loss or trailing stop, it should automatically sell
4. Check logs for `exit_timeout` event

---

## Monitoring

### Key Metrics to Track
- **Time-based exit frequency:** How often are positions being sold due to timeout?
- **Average hold time:** Are positions consistently hitting the timeout?
- **PnL of timeout exits:** Are these exits profitable or lossy on average?

### Adjustment Guidelines
- **If >50% of exits are timeouts:** Consider increasing the hold time
- **If <10% of exits are timeouts:** Consider decreasing the hold time
- **If timeout exits are mostly lossy:** Good, it's preventing bigger losses
- **If timeout exits are mostly profitable:** Consider increasing the hold time to capture more gains

---

## Status

✅ **DEPLOYED AND ACTIVE**
- Environment variable: Set to 3600 seconds (1 hour)
- Code changes: Applied and deployed
- Docker container: Rebuilt and restarted
- No errors: Clean startup logs

**Next Step:** Monitor the bot over the next few hours to see if time-based exits occur and evaluate their effectiveness.






