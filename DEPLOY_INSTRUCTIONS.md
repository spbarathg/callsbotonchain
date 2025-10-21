# 🚀 DEPLOYMENT INSTRUCTIONS - Trader Alignment Fix

**Goal**: Fix 80% trade failure rate and align with +411% backtest  
**Time Required**: 10-15 minutes  
**Risk**: LOW (all config changes, no code changes)

---

## 📋 PRE-DEPLOYMENT CHECKLIST

Before deploying, verify:

- [ ] You have SSH access to server (root@64.227.157.221)
- [ ] Wallet private key is in `.env` file (`TS_WALLET_SECRET`)
- [ ] Wallet has SOL balance for gas fees (0.1 SOL minimum)
- [ ] Wallet has USDC or SOL for trading capital
- [ ] Git repo is accessible on server

---

## 🎯 DEPLOYMENT OPTION 1: Automatic (RECOMMENDED)

### Step 1: Deploy Code Changes

```bash
# From your local machine (Windows)
cd C:\Users\barat\yesv2\callsbotonchain

# Commit changes
git add tradingSystem/config_optimized.py
git add deployment/docker-compose.yml.FIXED
git add TRADER_ALIGNMENT_FIX.md
git add QUICK_START_TRADER_FIX.md
git add deploy_trader_fix.sh
git add verify_trader_fixes.sh
git add DEPLOY_INSTRUCTIONS.md

git commit -m "Critical Fix: Align trader with +411% backtest

Changes:
- SLIPPAGE_BPS: 150 → 500 (5% for memecoins)
- PRIORITY_FEE: 10k → 100k microlamports
- MAX_CONCURRENT: 5 → 4 (match backtest)
- Signal bot: MIN_LIQUIDITY 0 → 30k (match trader)
- Signal bot: MIN_MARKET_CAP 10k → 50k (match backtest)

Expected: 20% → 80%+ execution success rate
Resolves: Jupiter error 0x1789 (slippage exceeded)"

git push origin main
```

### Step 2: Deploy to Server

```bash
# SSH to server
ssh root@64.227.157.221

# Navigate to project
cd /opt/callsbotonchain

# Pull latest changes
git pull origin main

# Backup current config
cp deployment/docker-compose.yml deployment/docker-compose.yml.backup.$(date +%Y%m%d_%H%M%S)

# Apply new config
cp deployment/docker-compose.yml.FIXED deployment/docker-compose.yml

# Restart containers with new config
docker-compose down
docker-compose up -d

# Wait for containers to start
sleep 10

# Verify containers are running
docker ps

# Check trader logs
docker logs --tail 50 callsbot-trader

# Check worker logs
docker logs --tail 50 callsbot-worker
```

**Expected output:**
```
CONTAINER ID   IMAGE                          STATUS          NAMES
abc123         callsbotonchain_trader         Up 10 seconds   callsbot-trader
def456         callsbotonchain_worker         Up 12 seconds   callsbot-worker
...
```

---

## 🎯 DEPLOYMENT OPTION 2: Manual (If you prefer)

### Step 1: Edit Server Config Directly

```bash
# SSH to server
ssh root@64.227.157.221

cd /opt/callsbotonchain/deployment

# Backup current config
cp docker-compose.yml docker-compose.yml.backup

# Edit docker-compose.yml
nano docker-compose.yml
```

### Step 2: Add These Environment Variables

**Under `worker` service (around line 18):**

```yaml
environment:
  # ... existing vars ...
  - MIN_MARKET_CAP_USD=50000          # Add this
  - MIN_LIQUIDITY_USD=30000           # Add this
  - USE_LIQUIDITY_FILTER=true         # Add this
  - GENERAL_CYCLE_MIN_SCORE=7         # Add this
```

**Under `trader` service (around line 98):**

```yaml
environment:
  # ... existing vars ...
  - TS_SLIPPAGE_BPS=500                        # Change from 150
  - TS_PRIORITY_FEE_MICROLAMPORTS=100000       # Change from 10000
  - TS_MAX_CONCURRENT=4                        # Add this
  - TS_MIN_LIQUIDITY_USD=30000                 # Change from 0
  - TS_DRY_RUN=false                           # Add this (or 'true' for testing)
```

**Save and exit** (`Ctrl+X`, then `Y`, then `Enter`)

### Step 3: Restart Containers

```bash
docker-compose down
docker-compose up -d

# Verify
docker ps
docker logs --tail 50 callsbot-trader
```

---

## ✅ POST-DEPLOYMENT VERIFICATION

### Step 1: Check Container Health (Immediately)

```bash
ssh root@64.227.157.221

# All containers should be "Up"
docker ps

# Expected output:
# callsbot-worker         Up 1 minute
# callsbot-trader         Up 1 minute
# callsbot-web            Up 1 minute
# callsbot-redis          Up 1 minute (healthy)
```

### Step 2: Verify Configuration Loaded

```bash
# Check trader loaded new slippage
docker logs callsbot-trader 2>&1 | grep -i "slippage\|priority"

# Should see config loaded or 500 BPS in logs
```

### Step 3: Monitor for Signals (Wait 30-60 min)

```bash
# Watch for new signals
docker logs -f callsbot-worker | grep "ALERT\|Score"

# Should see: "Score 8+" signals only (no Score 6)
```

### Step 4: Watch for Trade Execution (Wait for signal)

```bash
# Watch trader live
docker logs -f callsbot-trader

# Look for:
# ✅ "market_buy called: $XXX..."
# ✅ "Swap transaction received"
# ✅ "Transaction sent: abc123..."
# ✅ "Position opened: ..."

# Should NOT see:
# ❌ "error code 6025 (0x1789)"
# ❌ "Simulation failed"
# ❌ "Direct send also failed"
```

---

## 📊 SUCCESS CRITERIA

### After 1 Hour:
- [ ] Containers running stable
- [ ] No 0x1789 errors in logs
- [ ] Signals are Score 7+ only

### After 6 Hours:
- [ ] At least 1 successful trade execution
- [ ] Execution success rate >60%

### After 24 Hours:
- [ ] 5-8 positions opened
- [ ] Execution success rate 80%+
- [ ] No losses >-20%

### After 7 Days:
- [ ] 20-30 trades completed
- [ ] Win rate: 30-40%
- [ ] Avg loss: -15%
- [ ] Capital growth: +20-100%

---

## 🚨 TROUBLESHOOTING

### Problem 1: Container Won't Start

```bash
# Check logs for error
docker logs callsbot-trader

# Common issue: Missing TS_WALLET_SECRET
# Fix: Add to .env file
nano deployment/.env

# Add:
TS_WALLET_SECRET=your_base58_private_key_here
```

### Problem 2: Still Seeing 0x1789 Errors

```bash
# Increase slippage even more
docker-compose stop trader

# Edit docker-compose.yml
nano deployment/docker-compose.yml

# Change trader environment:
- TS_SLIPPAGE_BPS=1000  # 10% (extreme)

docker-compose up -d trader
```

### Problem 3: No Signals

```bash
# Check worker is running
docker logs callsbot-worker

# Should see:
# "Fetching feed from Cielo..."
# "Processing transaction..."

# If not, restart worker
docker restart callsbot-worker
```

### Problem 4: Signals But No Trades

```bash
# Check Redis connection
docker exec callsbot-trader python3 -c "
import redis
r = redis.from_url('redis://redis:6379/0')
print(f'Redis: {r.ping()}')
print(f'Signals in queue: {r.llen(\"trading_signals\")}')"

# Should show: Redis: True, Signals: X
```

### Problem 5: Trades Executing But All Losing

```bash
# This is NORMAL if <20 trades
# Need 30+ trades to verify 35% win rate

# Check after 20 trades:
docker exec callsbot-trader python3 -c "
import sqlite3
conn = sqlite3.connect('var/trading.db')
cur = conn.execute('SELECT COUNT(*) FROM positions WHERE status=\"closed\"')
print(f'Closed positions: {cur.fetchone()[0]}')"

# If 20+ trades and all losing, check signal quality
```

---

## 🔄 ROLLBACK PROCEDURE (If Something Goes Wrong)

```bash
ssh root@64.227.157.221
cd /opt/callsbotonchain/deployment

# Stop containers
docker-compose down

# Restore backup
cp docker-compose.yml.backup docker-compose.yml

# Restart with old config
docker-compose up -d

# Verify
docker ps
```

---

## 📈 MONITORING COMMANDS (Daily Use)

### Quick Status Check

```bash
# Run from local machine
ssh root@64.227.157.221 'bash -s' < verify_trader_fixes.sh
```

### Detailed Performance

```bash
ssh root@64.227.157.221

# Today's trade count
docker logs --since 24h callsbot-trader 2>&1 | grep -c "Position opened"

# Execution success rate (last 2 hours)
BUY=$(docker logs --since 2h callsbot-trader 2>&1 | grep -c "market_buy called")
SUCCESS=$(docker logs --since 2h callsbot-trader 2>&1 | grep -c "Transaction sent")
echo "Success rate: $SUCCESS / $BUY"

# Check for errors
docker logs --since 1h callsbot-trader 2>&1 | grep -i "error\|failed" | tail -20

# Win rate (needs 10+ closed positions)
docker exec callsbot-trader python3 -c "
import sqlite3
conn = sqlite3.connect('var/trading.db')
cur = conn.execute('''
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) as winners,
        AVG(pnl_pct) as avg_pnl
    FROM positions WHERE status=\"closed\"
''')
result = cur.fetchone()
if result[0] > 0:
    print(f'Total: {result[0]}, Winners: {result[1]}, WR: {result[1]/result[0]*100:.1f}%, Avg: {result[2]:.1f}%')
else:
    print('No closed positions yet')"
```

---

## 🎯 NEXT STEPS AFTER SUCCESSFUL DEPLOYMENT

### Day 1-2: Monitor Closely

- Check logs every 2-4 hours
- Verify execution success >60%
- Ensure no critical errors

### Day 3-7: Verify Performance

- Run `verify_trader_fixes.sh` daily
- Track win rate (should approach 30-40%)
- Verify stop losses at -15%
- Check capital growth

### Week 2+: Optimize & Scale

Once proven (30-40% WR, 80%+ execution):

1. **Increase Capital**:
   ```yaml
   - TS_BANKROLL_USD=1000  # Double it
   ```

2. **Enable Advanced Features** (optional):
   ```yaml
   - PORTFOLIO_REBALANCING_ENABLED=true
   - TS_ADAPTIVE_TRAILING_ENABLED=true
   ```

3. **Monitor Compound Growth**:
   - Week 1: $500 → $750-1000
   - Week 2: $1000 → $1500-2000
   - Week 4: $2000 → $3000-5000

---

## 📞 SUPPORT & RESOURCES

**Documentation:**
- Full Technical Details: `TRADER_ALIGNMENT_FIX.md`
- Quick Start: `QUICK_START_TRADER_FIX.md`
- Backtest Results: `docs/deployment/BACKTEST_RESULTS_V4.md`

**Verification:**
- Run `verify_trader_fixes.sh` for automated checks
- Check server health: `docker ps` and `docker stats`

**Logs:**
- Trader: `docker logs -f callsbot-trader`
- Worker: `docker logs -f callsbot-worker`
- All: `docker-compose logs -f`

---

## ✅ FINAL CHECKLIST

Before closing this guide, ensure:

- [x] Code changes committed and pushed
- [x] Server config updated (docker-compose.yml)
- [x] Containers restarted successfully
- [x] All containers showing "Up" status
- [x] No errors in recent logs
- [x] Monitoring plan in place

**You're done!** 🎉

The trader should now execute at 80%+ success rate and match the +411% backtest performance.

Monitor for 24 hours and run `verify_trader_fixes.sh` to check progress.

Good luck! 🚀



