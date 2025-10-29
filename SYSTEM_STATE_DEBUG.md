# Bot System State & Debugging Guide

## Current Configuration (As of 2025-10-29)

### Wallet
- **Address**: New wallet (switched from old wallet)
- **Private Key**: `2eChRagM49m2mXqASyuDHCoh9GkF2xwaUUioHL8XgcHJuivxZi8JfSinVXtvzS1vbH5gcRyDZBTT7ded6caT8hBU`
- **Balance**: ~0.0099 SOL ($1.97) + $0.00 USDC = $1.97 total
- **Status**: ✅ Active and funded

### Strategy: Watch & Strike (Deployed 2025-10-29)
**ALL SIGNALS → WATCH LIST → TRACK MOMENTUM → BUY BEST MOVERS**

#### Entry Criteria (For Watch List Addition)
- Minimum score: 7/10
- Must pass Jupiter validation (tradeable)
- Must pass rugpull detection
- No cooldown on token
- No existing position

#### Buy Criteria (From Watch List → Actual Entry)
- **Gain**: +5% from signal price
- **Velocity**: 2%/min sustained movement
- **Time Window**: 2-5 minutes of tracking
- **Re-entry**: After stop loss, can re-enter if +10% from exit price

---

## Entry Gates & Filters

### Gate 1: Worker Bot (Signal Detection)
**Purpose**: Find quality signals from Cielo feed

**Filters**:
1. Market Cap: $10k - $500k (sweet spot)
2. Preliminary Score: >=2/10
3. Debate System: Nuanced scoring (7+ to pass)

**Debug**:
- Check: `docker logs callsbot-worker --tail 100`
- Look for: `✅ MARKET CAP SWEET SPOT`, `DEBUG: Token X scored Y/10`
- Common rejections: Too low mcap (<$10k), too high mcap (>$500k), low score

### Gate 2: Trader Pre-Entry Validation
**Purpose**: Verify token is safe and tradeable

**Filters**:
1. **Token Age**: Minimum 1 hour old (prevents brand new scams)
2. **Rugpull Detection**: Check for suspicious patterns
3. **Jupiter Validation**: Multi-strategy tradeability check
   - Strategy 1: Direct routes (0.01 SOL, 20% slippage)
   - Strategy 2: Multi-hop routes (0.01 SOL, 50% slippage)
   - Strategy 3: Micro-amount (0.001 SOL, 20% slippage)
4. **Recent Dump Detection**: No -20%+ drops in last 5 minutes

**Debug**:
- Check: `docker logs callsbot-trader | grep -E "VALIDATOR|RUGPULL"`
- Look for: `✅ All validation checks passed` vs `❌ Token too young` / `❌ Recent dump detected`

### Gate 3: Watch List (Momentum Tracking)
**Purpose**: Only buy tokens showing REAL movement

**Entry Conditions**:
- Price gain: +5% from signal price
- Velocity: 2%/min sustained (not just spike)
- Time tracked: 2-5 minutes minimum

**Debug**:
- Check: `docker logs callsbot-trader | grep WATCHLIST`
- Look for: `➕ Added X to watch list`, `🎯 ENTRY SIGNAL`, `⏰ Expired X`

### Gate 4: Position Limits & Budget
**Purpose**: Risk management

**Limits**:
1. Max concurrent positions: 6
2. Position size: ~$0.12 per trade (6.25% of $1.97 wallet)
3. Min wallet balance: Must have SOL for gas

**Debug**:
- Check: `docker logs callsbot-trader | grep -E "WALLET|open_positions"`
- Look for: `Balance: X SOL`, `{'open_positions': N}`

---

## Current State (Last Check: 2025-10-29 20:50 UTC)

### Open Positions
- **Count**: 0
- **Tokens**: None
- **Reason**: Fresh start with new wallet, waiting for first entry

### Watch List
**Active Signals Being Tracked**:
1. **468R1Wbw** - Score 10/10, High Confidence, MCap $71k + $31k Liq
2. **7g8qyxJD** - Score 10/10, High Confidence, MCap $21k
3. **6XuMjerg** - Score 7/10, Nuanced Conviction, MCap $38k

**Status**: Background monitor checking prices every few seconds

### Recent Signal Rejections (Last Hour)
1. **eRSXnxRW** (Score 8/10) - ❌ Rejected: Too young (0.0h old, need 1.0h)
2. **7XeR2pjf** (Score 10/10) - ❌ Rejected: Recent dump (-24.41% in 5min)

---

## Why Bot Hasn't Bought Anything (Expected Reasons)

### Normal Operations (Not Issues)
1. ✅ **Waiting for momentum**: Watch list strategy means we wait 2-5min for confirmation
2. ✅ **No signal met criteria yet**: None of the 3 tracked signals showed +5% at 2%/min velocity
3. ✅ **Filtering scams**: Rejected 2 signals that looked good but had red flags

### Potential Issues (Check These if No Buys After 1 Hour)
1. ❌ **Watch list monitor not running**: Check `docker logs callsbot-trader | grep WATCH_MONITOR`
2. ❌ **Jupiter API rate limited**: Check `docker logs callsbot-trader | grep "rate limit"`
3. ❌ **All signals expiring**: Check `docker logs callsbot-trader | grep "Expired"`
4. ❌ **Wallet insufficient funds**: Check SOL balance (need ~0.005 SOL per trade)
5. ❌ **Redis connection lost**: Check `docker logs callsbot-trader | grep Redis`

---

## Critical Fixes Deployed (2025-10-29)

### Fix 1: Database Sync Bug (CRITICAL)
**Problem**: Broker returned requested qty instead of actual qty sold, causing phantom positions
**Fix**: Broker now returns actual qty, trader auto-syncs DB on mismatch
**Impact**: Self-healing database, no more phantom positions

### Fix 2: Wallet Migration
**Problem**: Old wallet with 6 orphaned positions causing rate limiting
**Fix**: Switched to new wallet, closed all orphaned positions
**Impact**: Clean slate, no rate limiting

### Fix 3: Watch & Strike Strategy
**Problem**: Instant buys caught scams and dumps
**Fix**: All signals → watch list → track momentum → buy only movers
**Impact**: Avoid scams, only buy proven momentum

---

## Debug Commands (Quick Reference)

### Check Bot Health
```bash
# Trader status
ssh root@64.227.157.221 "docker logs callsbot-trader --tail 50"

# Worker signals
ssh root@64.227.157.221 "docker logs callsbot-worker --tail 30"

# Watch list status
ssh root@64.227.157.221 "docker logs callsbot-trader | grep WATCHLIST | tail -20"

# Open positions
ssh root@64.227.157.221 "docker logs callsbot-trader | grep 'open_positions' | tail -5"
```

### Check Signal Flow
```bash
# Worker finding signals
ssh root@64.227.157.221 "docker logs callsbot-worker | grep 'scored.*10' | tail -10"

# Trader validation
ssh root@64.227.157.221 "docker logs callsbot-trader | grep 'VALIDATOR.*✅' | tail -10"

# Watch list additions
ssh root@64.227.157.221 "docker logs callsbot-trader | grep '➕ Added' | tail -10"

# Entry executions
ssh root@64.227.157.221 "docker logs callsbot-trader | grep 'ENTRY SIGNAL' | tail -10"
```

### Check Rejections
```bash
# Token age rejections
ssh root@64.227.157.221 "docker logs callsbot-trader | grep 'too young' | tail -10"

# Dump detections
ssh root@64.227.157.221 "docker logs callsbot-trader | grep 'dump detected' | tail -10"

# Jupiter failures
ssh root@64.227.157.221 "docker logs callsbot-trader | grep 'Jupiter.*failed' | tail -10"
```

### Check Wallet & Funds
```bash
# SOL balance
ssh root@64.227.157.221 "docker logs callsbot-trader | grep 'Balance:.*SOL' | tail -5"

# Position sizing
ssh root@64.227.157.221 "docker logs callsbot-trader | grep 'usd_size' | tail -10"
```

---

## Expected Timeline for First Buy

### Immediate (0-5 minutes)
- Worker finds quality signal (7+/10)
- Trader validates and adds to watch list
- Background monitor starts tracking

### Short-term (5-15 minutes)
- Token shows momentum (+5% gain)
- Velocity sustained (2%/min for 2-5min)
- **BUY EXECUTES** automatically

### If No Buy After 1 Hour
**Check in order**:
1. Are signals being found? (Check worker logs for 7+/10 scores)
2. Are signals being added to watch list? (Check trader logs for `➕ Added`)
3. Is background monitor running? (Check for `WATCH_MONITOR` logs)
4. Are tokens showing momentum? (Market might just be slow)
5. Is wallet funded? (Need ~$0.12 per position)

---

## Success Metrics

### Watch & Strike Working Correctly
- ✅ High-score signals (7-10/10) added to watch list
- ✅ Scam signals (too young, dumping) rejected
- ✅ Background monitor checking prices
- ✅ Only buy when momentum confirmed

### Bot Needs Attention
- ❌ No signals found for >30 minutes (check worker logs)
- ❌ All signals rejected (filters too strict?)
- ❌ Watch list not adding signals (check Redis connection)
- ❌ Background monitor not logging (check for errors)

---

## Recent Performance

### Signals Processed (Last Hour)
- **Found**: 6+ signals
- **High Quality (7+/10)**: 4 signals
- **Added to Watch List**: 3 signals
- **Rejected (Safety)**: 2 signals (1 too young, 1 dumping)
- **Bought**: 0 (waiting for momentum confirmation)

### Safety Filters Effectiveness
- ✅ Prevented buying a -24% dump (7XeR2pjf)
- ✅ Prevented buying a 0-hour scam (eRSXnxRW)
- ✅ 3 quality signals being tracked for real momentum

**Status**: Bot operating as designed, filters working perfectly

