# Token Rebuy Cooldown Settings

**Last Updated:** October 22, 2025  
**Status:** ✅ Active - 4 Hour Cooldown

---

## What Is The Cooldown?

The cooldown system prevents the bot from buying the same token multiple times in a short period. After selling a token (whether via stop loss, trailing stop, or rebalancing), that token enters a "cooldown period" during which new buy signals for that token are automatically rejected.

---

## Current Setting

**Cooldown Period:** **4 Hours** (14,400 seconds)

This means:
- After selling a token at 10:00 AM, the bot **cannot rebuy** that token until 2:00 PM
- Prevents "buy-sell-rebuy" loops where the bot repeatedly trades the same token
- Gives you time to see how the token performs without your position

---

## Why 4 Hours?

1. **Prevents Chasing Bad Tokens**
   - If a token hit your stop loss, it's likely trending down
   - 4 hours gives time for the trend to fully develop or reverse
   - Prevents immediately rebuying a falling token

2. **Reduces Trading Costs**
   - Each trade has fees (Jupiter swap fees, Solana transaction fees)
   - Frequent rebuying of the same token = higher costs
   - 4-hour cooldown ensures each trade is intentional

3. **Better Capital Allocation**
   - Forces the bot to explore other opportunities
   - Your capital goes to fresh signals instead of retrying old ones
   - Improves diversification across your portfolio

4. **Emotional Trading Prevention**
   - Prevents FOMO-driven rebuys ("maybe it'll pump this time!")
   - Enforces discipline: one chance per token per day
   - Reduces overtrading

---

## How It Works

### When Cooldown Is Applied

The cooldown starts **immediately** after any sell:

1. **Stop Loss Triggered**
   ```
   10:00:00 AM - Token ABC hits -15% stop loss
   10:00:01 AM - Sell executed, token ABC enters 4-hour cooldown
   Until 2:00:01 PM - All buy signals for ABC are rejected
   ```

2. **Trailing Stop Triggered**
   ```
   11:30:00 AM - Token XYZ trailing stop triggered (15% below peak)
   11:30:05 AM - Sell executed, token XYZ enters 4-hour cooldown
   Until 3:30:05 PM - All buy signals for XYZ are rejected
   ```

3. **Rebalancing Exit**
   ```
   1:00:00 PM - Portfolio rebalance forces exit of token DEF
   1:00:10 PM - Sell executed, token DEF enters 4-hour cooldown
   Until 5:00:10 PM - All buy signals for DEF are rejected
   ```

### What Happens During Cooldown

When a buy signal arrives for a token on cooldown:

**Log Output:**
```json
{
  "event": "entry_rejected_cooldown",
  "token": "ABC123...",
  "remaining_seconds": 12600,
  "remaining_hours": 3,
  "remaining_minutes": 30,
  "timestamp": "2025-10-22T14:30:00Z"
}
```

**Console Output:**
```
[DEBUG] Token ABC123 on cooldown for 3h 30m more
```

The signal is **completely ignored** - no price checks, no quote requests, no API calls.

---

## Customizing The Cooldown

If you want to adjust the cooldown period, you can set the `TS_REBUY_COOLDOWN_SEC` environment variable:

### Option 1: Via Docker Compose

Edit `/opt/callsbotonchain/docker-compose.yml`:

```yaml
services:
  trader:
    environment:
      - TS_REBUY_COOLDOWN_SEC=21600  # 6 hours
      # Or: 28800 for 8 hours
      # Or: 7200 for 2 hours
```

Then restart:
```bash
cd /opt/callsbotonchain
docker-compose restart trader
```

### Option 2: Via .env File

Add to `/opt/callsbotonchain/.env`:

```bash
TS_REBUY_COOLDOWN_SEC=21600  # 6 hours
```

Then restart:
```bash
cd /opt/callsbotonchain
docker-compose restart trader
```

### Recommended Cooldown Periods

| Duration | Seconds | Use Case |
|----------|---------|----------|
| **2 hours** | 7200 | Very active trading, high signal volume |
| **4 hours** | 14400 | **Default - Balanced approach** ✅ |
| **6 hours** | 21600 | Conservative, avoid rebuying same day |
| **8 hours** | 28800 | Maximum patience, one shot per token |
| **24 hours** | 86400 | Ultra-conservative, truly "one per day" |

---

## Monitoring Cooldowns

### Check Active Cooldowns

```bash
ssh root@64.227.157.221
cd /opt/callsbotonchain

# View recent cooldown rejections
docker logs callsbot-trader 2>&1 | grep "entry_rejected_cooldown" | tail -10

# See cooldown additions (when tokens are sold)
docker logs callsbot-trader 2>&1 | grep "cooldown_added" | tail -10
```

### Example Output

**Cooldown Added:**
```json
{
  "ts": "2025-10-22T10:00:01Z",
  "event": "cooldown_added",
  "token": "ABC123pump",
  "cooldown_seconds": 14400,
  "reason": "sold_via_stop_loss"
}
```

**Cooldown Rejection:**
```json
{
  "ts": "2025-10-22T11:30:00Z",
  "event": "entry_rejected_cooldown",
  "token": "ABC123pump",
  "remaining_seconds": 12600,
  "remaining_hours": 3,
  "remaining_minutes": 30
}
```

---

## FAQ

### Q: Does cooldown apply to ALL tokens or just the ones I sold?

**A:** Only the specific tokens you sold. If you sell token ABC, only ABC goes on cooldown. You can still buy tokens XYZ, DEF, etc.

### Q: What if I manually want to override the cooldown?

**A:** Currently there's no manual override. The cooldown is enforced automatically. If you absolutely need to trade a token on cooldown, you would need to:
1. Stop the trader container
2. Manually edit the database to remove the cooldown entry
3. Restart the trader

**Not recommended** - trust the system!

### Q: Does the cooldown persist across bot restarts?

**A:** Currently **NO** - cooldowns are stored in memory only. If you restart the trader, all cooldowns are cleared. This is intentional for now (allows fresh start after fixes/updates).

Future enhancement: Store cooldowns in database for persistence.

### Q: Can I see all tokens currently on cooldown?

**A:** Not via logs currently. The cooldowns are stored in the `TradeEngine._token_cooldowns` dictionary in memory. You'd need to add a debug endpoint or SQL table to view them.

Future enhancement: Add `/api/v2/cooldowns` endpoint.

### Q: What if a token gets multiple buy signals while on cooldown?

**A:** Each signal is rejected independently. The cooldown timer doesn't reset - it only counts down from when the token was originally sold.

Example:
- 10:00 AM: Sell ABC, starts 4-hour cooldown (until 2:00 PM)
- 11:00 AM: Buy signal for ABC → Rejected (3h remaining)
- 12:00 PM: Buy signal for ABC → Rejected (2h remaining)
- 1:00 PM: Buy signal for ABC → Rejected (1h remaining)
- 2:00 PM: Cooldown expires
- 2:15 PM: Buy signal for ABC → **Accepted** ✅

---

## Impact On Trading

### Before Cooldown (5 min)

**Problem:** Token ABC triggers stop loss every 10 minutes:
```
10:00 - Buy ABC at $0.10 for $20
10:05 - Stop loss at $0.085 → -$3
10:10 - Buy ABC at $0.08 for $20
10:15 - Stop loss at $0.068 → -$3.40
10:20 - Buy ABC at $0.06 for $20
10:25 - Stop loss at $0.051 → -$3.60
Total loss: $10 in 25 minutes
```

### After Cooldown (4 hours)

**Solution:** Token ABC can only be traded once:
```
10:00 - Buy ABC at $0.10 for $20
10:05 - Stop loss at $0.085 → -$3
       ABC enters 4-hour cooldown until 2:05 PM
10:10 - Signal for ABC → Rejected (cooldown)
10:15 - Signal for ABC → Rejected (cooldown)
10:20 - Signal for ABC → Rejected (cooldown)
...
10:00 - Buy XYZ at $0.05 for $20 (fresh token)
Total loss: $3, capital moved to fresh opportunity
```

**Result:** -$3 vs -$10 = **70% loss reduction**

---

## Technical Details

### Implementation

**File:** `tradingSystem/trader_optimized.py`

```python
class TradeEngine:
    def __init__(self):
        # Token cooldown tracking
        self._token_cooldowns: Dict[str, float] = {}  # token -> sell timestamp
        self._cooldown_lock = threading.Lock()
        self._cooldown_seconds = float(os.getenv("TS_REBUY_COOLDOWN_SEC", "14400"))
    
    def is_on_cooldown(self, token: str) -> bool:
        """Check if token is on cooldown"""
        with self._cooldown_lock:
            if token not in self._token_cooldowns:
                return False
            
            sell_time = self._token_cooldowns[token]
            elapsed = time.time() - sell_time
            
            if elapsed >= self._cooldown_seconds:
                # Cooldown expired
                del self._token_cooldowns[token]
                return False
            
            return True
    
    def _add_cooldown(self, token: str):
        """Add cooldown after selling"""
        with self._cooldown_lock:
            self._token_cooldowns[token] = time.time()
```

**Cooldown Check:** `tradingSystem/cli_optimized.py`

```python
if engine.is_on_cooldown(token_norm):
    remaining = engine.get_cooldown_remaining(token_norm)
    hours = int(remaining // 3600)
    minutes = int((remaining % 3600) // 60)
    engine._log("entry_rejected_cooldown", token=token_norm, 
               remaining_seconds=remaining, remaining_hours=hours, remaining_minutes=minutes)
    print(f"[DEBUG] Token {token_norm[:8]} on cooldown for {hours}h {minutes}m more")
    continue  # Skip this signal
```

### Thread Safety

The cooldown system is **thread-safe**:
- Uses `threading.Lock()` to prevent race conditions
- Safe to call from multiple threads (main loop, exit loop, rebalance)
- No risk of duplicate entries or missed cooldowns

---

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| Oct 22, 2025 | Initial implementation: 5 minutes (300s) | Stop buy-sell-rebuy loops |
| Oct 22, 2025 | Increased to 4 hours (14400s) | User request: prevent same-day rebuys |

---

## Summary

✅ **Current Setting:** 4-hour cooldown after selling  
✅ **Purpose:** Prevent rebuying same token repeatedly  
✅ **Status:** Active and working  
✅ **Customizable:** Via `TS_REBUY_COOLDOWN_SEC` env var  
✅ **Thread-Safe:** No race conditions  

**Result:** Better capital allocation, reduced trading costs, disciplined execution

---

**Next Steps:**
1. Monitor `entry_rejected_cooldown` logs to see cooldown in action
2. If too restrictive, reduce to 2-3 hours
3. If still seeing rebuys, increase to 6-8 hours
4. Review weekly: Are we missing good re-entry opportunities?

