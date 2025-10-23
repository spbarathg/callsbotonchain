# Rate Limit Optimization & Prevention

## Issue Summary

**Date:** October 23, 2025  
**Problem:** Bot was unable to sell a token (AzRVm4rrzFERyKQj9RDxec5YhjNNKrJvXHhJUM6Gpump) that was down 40%, despite the token being sellable with proper liquidity ($29.2K).

## Root Cause

The bot had **overly aggressive Jupiter rate limit cooldown settings** that locked out API access for 5 minutes after just ONE 429 error:

### Previous Settings (PROBLEMATIC):
```yaml
JUP_RPM_LIMIT=20              # Only 33% of Jupiter's 60 RPM limit
JUP_RATE_BUCKET=3             # Small burst capacity
JUP_429_COOLDOWN_THRESHOLD=1  # Triggered after just 1x 429 error
JUP_429_COOLDOWN_SEC=300      # 5-minute lockout
```

**What Happened:**
1. Bot got ONE 429 error during startup health check
2. Entered 5-minute cooldown immediately
3. Stop loss triggered on token (down 40%)
4. Bot tried to sell every 2 seconds → kept hitting cooldown check
5. Cooldown never cleared because it kept getting checked
6. Token stuck in wallet, unable to sell

## Fixes Applied

### 1. Fixed Escalating Slippage
**File:** `tradingSystem/broker_optimized.py`
- **Problem:** Duplicate `market_sell` function was overriding the escalating slippage version
- **Fix:** Removed duplicate, now properly uses 20% → 30% → 40% → 50% slippage

### 2. Optimized Rate Limit Settings
**File:** `deployment/docker-compose.yml`

**New Settings (OPTIMIZED):**
```yaml
JUP_RPM_LIMIT=40              # 66% of Jupiter's 60 RPM limit (24 RPM safety margin)
JUP_RATE_BUCKET=5             # Larger burst capacity for peak times
JUP_429_COOLDOWN_THRESHOLD=3  # Requires 3 consecutive 429s to trigger cooldown
JUP_429_COOLDOWN_SEC=30       # 30-second cooldown (recoverable)
```

### 3. Rate Limit Budget Calculation

**With 4 open positions** (max):
- Exit loop interval: 2 seconds
- Price checks per minute: 30 per position
- Total API calls: 4 positions × 30 = **120 calls/min**

**Wait, that exceeds the limit!**

**BUT:** We have a **10-second price cache** (`tradingSystem/price_cache.py`):
- Each price is cached for 10 seconds
- Actual fetches: 4 positions × 6 fetches/min = **24 API calls/min**
- **Usage: 24 / 60 = 40% of Jupiter's limit**
- **Safety margin: 60%** ✅

### 4. Additional Protections

**Token Bucket Rate Limiter:**
- Refill rate: 40 tokens/minute (0.667 tokens/second)
- Bucket capacity: 5 tokens
- Allows small bursts while maintaining average rate

**Cooldown Logic:**
- Requires 3 consecutive 429 errors
- 30-second cooldown (not 5 minutes!)
- Resets on successful API call

## Verification

**Manual Jupiter API Test:**
```bash
curl "https://quote-api.jup.ag/v6/quote?inputMint=AzRVm4rrzFERyKQj9RDxec5YhjNNKrJvXHhJUM6Gpump&outputMint=So11111111111111111111111111111111111111112&amount=61278261048&slippageBps=5000"
```

**Result:**
- ✅ Route found through "Pump.fun Amm"
- ✅ Price impact: 1.15% (very low!)
- ✅ Expected output: $6.26 with 50% slippage
- ✅ Token IS sellable

## Prevention Measures

### For Future Issues:

1. **Rate Limit Monitoring:**
   - Watch for "Rate limited; cooling down" logs
   - If cooldown exceeds 1 minute → investigate settings

2. **Position Stuck Alerts:**
   - Bot logs "position_stuck_unsellable" after 20 sell failures
   - Check if it's rate limiting or actual illiquidity

3. **Manual Verification:**
   - If bot claims token is unsellable, test manually with curl
   - Compare bot's API usage to limits

4. **Settings Tuning:**
   - Current settings work for up to **6 positions** at 2-second exit intervals
   - If expanding to more positions, reduce exit check frequency or increase cache TTL

## Current System Status

✅ **Position closed** (manually sold, database updated)  
✅ **Escalating slippage enabled** (20%/30%/40%/50%)  
✅ **Rate limits optimized** (40 RPM, 3x threshold, 30s cooldown)  
✅ **Price caching active** (10-second TTL)  
✅ **Bot ready** (0 open positions, all systems operational)

## Lessons Learned

1. **Rate limit cooldowns must be recoverable** - 5 minutes is too long for a high-frequency trading bot
2. **Single 429 error is not catastrophic** - Require multiple consecutive errors before locking out
3. **Price caching is critical** - Reduces API calls by 80-90%
4. **Manual testing is essential** - Don't assume a token is unsellable without verification

## Related Files

- `tradingSystem/broker_optimized.py` - Escalating slippage logic
- `tradingSystem/price_cache.py` - Price caching with TTL
- `app/jupiter_client.py` - Rate limiting logic
- `deployment/docker-compose.yml` - Rate limit configuration







