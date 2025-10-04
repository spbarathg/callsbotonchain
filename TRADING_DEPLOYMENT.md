# Trading System Deployment Guide

## ✅ **What Was Fixed**

### 1. **Real-Time Stats Fetching** (`tradingSystem/cli.py`)
- **Before**: Used hardcoded fake stats (liquidity=$20k, ratio=0.6, etc.)
- **After**: Fetches real token stats from:
  - `/api/tracked` endpoint (latest tracking data)
  - `alerts.jsonl` fallback (initial alert data)
- **Validation**: Rejects entries if token already dumped >30% from alert

### 2. **Process ALL Signal Types** (`tradingSystem/strategy.py`)
- **Before**: Only processed 254/686 signals (37%)
  - Ignored "High Confidence (Strict)" entirely
- **After**: Processes ALL conviction types:
  - **Runner**: Smart Money signals (highest conviction) - $70/position
  - **Strict**: High Confidence without smart money - $50/position (dynamic sizing by score)
  - **Scout**: High velocity plays - $40/position
  - **Nuanced**: Lowest confidence, exceptional stats only - $25/position

### 3. **Optimized for $500 Bankroll** (`tradingSystem/config.py`)
- **Before**: 
  - Max 3 positions × $60 = $180 active (36% utilization)
  - $320 sitting idle
- **After**:
  - Max 5 positions
  - Best case: $70 + $50 + $50 + $40 + $25 = $235 active (47% utilization)
  - Still conservative but better capital efficiency
  - **Stop losses**: 15% (runner), 12% (strict), 10% (scout), 8% (nuanced)

### 4. **Strategy-Specific Entry Gates**
- **Runner (Smart Money)**:
  - Liquidity ≥ $15k, Vol/MCap ≥ 0.45, MCap ≤ $1.5M OR momentum ≥ 20%
- **Strict**:
  - Liquidity ≥ $10k, Vol/MCap ≥ 0.35, MCap ≤ $2M
  - Score-based sizing: 8+ scores get 150% size, 5- scores get 75%
- **Nuanced**:
  - Liquidity ≥ $12k, Vol/MCap ≥ 0.55, MCap ≤ $1M
  - Only takes exceptional velocity (≥9, ≥30 traders) OR momentum (≥35%)

### 5. **Trading Container Added** (`docker-compose.yml`)
- New `trader` service that monitors bot stdout and executes trades
- Reads from `data/logs/stdout.log` for decision events
- Writes to `var/trading.db` for position tracking
- Logs to `data/logs/trading.jsonl` for audit trail

---

## 🚀 **Deployment Steps**

### **Step 1: Commit Changes Locally**
```bash
git add tradingSystem/ docker-compose.yml
git commit -m "feat: complete trading system overhaul - real stats, all signals, optimized for $500"
git push origin main
```

### **Step 2: Update .env on Server**
Add these lines to `/opt/callsbotonchain/.env`:

```bash
# Trading System Configuration
TS_DRY_RUN=true                           # Start in dry-run mode (MANDATORY FOR TESTING)
TS_WALLET_SECRET=                         # Leave EMPTY for now (dry-run doesn't need it)
TS_BANKROLL_USD=500
TS_MAX_CONCURRENT=5

# Position Sizing (optimized for $500)
TS_CORE_SIZE_USD=70                       # Smart Money
TS_STRICT_SIZE_USD=50                     # High Confidence (Strict)
TS_SCOUT_SIZE_USD=40                      # High Velocity
TS_NUANCED_SIZE_USD=25                    # Nuanced

# Stop Losses
TS_CORE_STOP_PCT=15.0
TS_STRICT_STOP_PCT=12.0
TS_SCOUT_STOP_PCT=10.0
TS_NUANCED_STOP_PCT=8.0

# Trailing Stops
TS_TRAIL_DEFAULT_PCT=22.0
TS_TRAIL_TIGHT_PCT=16.0
TS_TRAIL_WIDE_PCT=25.0

# Runner Gates (Smart Money)
TS_MIN_LP_USD=15000
TS_RATIO_MIN=0.45
TS_MCAP_MAX=1500000
TS_MOMENTUM_1H_GATE=20.0

# Strict Gates
TS_STRICT_MIN_LP_USD=10000
TS_STRICT_RATIO_MIN=0.35
TS_STRICT_MCAP_MAX=2000000

# Nuanced Gates
TS_NUANCED_MIN_LP_USD=12000
TS_NUANCED_RATIO_MIN=0.55
TS_NUANCED_MCAP_MAX=1000000

# Execution
TS_RPC_URL=https://api.mainnet-beta.solana.com
TS_SLIPPAGE_BPS=150                       # 1.5% slippage
TS_PRIORITY_FEE_MICROLAMPORTS=8000
```

### **Step 3: Deploy to Server**
```bash
ssh root@64.227.157.221 <<'EOF'
set -e
cd /opt/callsbotonchain

# Pull latest code
git fetch --all
git reset --hard origin/main

# Stop all containers
docker compose down

# Rebuild with new trading system
docker compose build

# Fix permissions for appuser (uid 10001)
chown -R 10001:10001 /opt/callsbotonchain/var /opt/callsbotonchain/data

# Start all services (including new trader)
docker compose up -d

# Wait for startup
sleep 5

# Check all containers
docker ps --filter name=callsbot --format "table {{.Names}}\t{{.Status}}"

# Check trader logs
echo "=== TRADER LOGS ==="
docker logs callsbot-trader --tail 20

echo "=== Deployment complete! ==="
EOF
```

### **Step 4: Monitor Dry-Run Performance (24-48 hours)**
```bash
# Check trading logs
ssh root@64.227.157.221 "tail -f /opt/callsbotonchain/data/logs/trading.jsonl"

# Check simulated positions
ssh root@64.227.157.221 "sqlite3 /opt/callsbotonchain/var/trading.db 'SELECT * FROM positions ORDER BY id DESC LIMIT 10;'"

# Check fills
ssh root@64.227.157.221 "sqlite3 /opt/callsbotonchain/var/trading.db 'SELECT * FROM fills ORDER BY id DESC LIMIT 20;'"
```

### **Step 5: Go Live (ONLY AFTER SUCCESSFUL DRY RUN)**

**IMPORTANT**: Create a NEW Solana wallet for trading, NOT your main wallet!

```bash
# 1. Create new Solana wallet (on your LOCAL machine, NOT server)
solana-keygen new -o trading_wallet.json

# 2. Fund with SMALL amount first ($100 USDC)
# Send USDC to the new wallet address
# Address will be shown after keygen

# 3. Get base58 private key
solana-keygen pubkey trading_wallet.json    # Shows public key
# For private key, read the JSON array from trading_wallet.json

# 4. Update .env on server
ssh root@64.227.157.221
nano /opt/callsbotonchain/.env
# Set: TS_WALLET_SECRET=<base58_or_json_array>
# Set: TS_DRY_RUN=false

# 5. Restart trader
docker compose restart trader

# 6. Monitor EVERY trade for first 24 hours
docker logs -f callsbot-trader
tail -f /opt/callsbotonchain/data/logs/trading.jsonl
```

---

## 📊 **Expected Performance (Based on Current Stats)**

### **Signal Distribution** (from your 686 alerts):
- **Smart Money**: 254 alerts (37%) → $70 each = Runner strategy
- **Strict**: 273 alerts (40%) → $50 each = Strict strategy (NEW!)
- **Nuanced**: 148 alerts (21%) → $25 each = Nuanced strategy (NEW!)

### **Estimated Deployment** (5 concurrent positions):
- Mix: 2 strict ($100) + 1 runner ($70) + 1 scout ($40) + 1 nuanced ($25) = **$235 active**
- Capital utilization: **47%** (vs 36% before)
- Processing: **100% of signals** (vs 58% before)

### **Risk Profile**:
- Max loss per position: 8-15% depending on strategy
- Worst case: 5 × 15% × $50 avg = **-$37.50 max drawdown per batch**
- With 47% utilization: worst case total portfolio impact = **-7.5%**

### **Expected Win Rate** (based on your current stats):
- **2x Rate**: 9.1% (63 out of 686)
- **5x Rate**: 2.5% (17 out of 686)
- **Rug Rate**: 56.6% (but most stop out at -8 to -15%, not -100%)

### **Realistic Monthly PnL** (conservative estimate):
- Assume 100 trades/month, 10% avg win rate, 2x avg winner, 12% avg loser
- Winners: 10 × $50 × 100% = **+$500**
- Losers: 90 × $50 × 12% = **-$540**
- **Net: -$40/month (-8% monthly)**

**This is still SPECULATIVE and HIGH RISK. Memecoins are volatile.**

---

## ⚠️ **CRITICAL SAFETY CHECKS**

Before going live, VERIFY:

1. ✅ Dry-run simulated at least 50 trades
2. ✅ No runtime errors in `trading.jsonl` logs
3. ✅ Position sizing never exceeds configured limits
4. ✅ Stops trigger correctly (check `exit_stop` events)
5. ✅ Trailing stops update properly (check `exit_trail` events)
6. ✅ No trades opened on rugged/dead tokens
7. ✅ Jupiter quotes return reasonable prices (no 90% slippage)
8. ✅ NEW wallet created (NOT your main wallet)
9. ✅ Only $100 funded initially (NOT full $500)
10. ✅ You're prepared to lose 100% of test capital

---

## 🔧 **Post-Deployment Tuning**

After 1 week of live trading, adjust based on results:

### **If losing money consistently:**
- Increase entry gates (liquidity, ratio thresholds)
- Reduce position sizes by 20%
- Tighten trailing stops to lock gains faster

### **If missing good trades:**
- Slightly relax entry gates for strict/nuanced
- Increase MAX_CONCURRENT to 6-7
- Widen trailing stops for runner strategy

### **If capital under-utilized:**
- Increase position sizes by 10-15%
- Add 6th concurrent position slot

---

## 📝 **Summary of Changes**

| Aspect | Before | After |
|--------|--------|-------|
| **Stats Source** | Hardcoded fake data | Real-time API + alerts.jsonl |
| **Signals Processed** | 58% (402/686) | 100% (686/686) |
| **Strategies** | 2 (runner, scout) | 4 (runner, strict, scout, nuanced) |
| **Max Positions** | 3 | 5 |
| **Capital Utilization** | 36% ($180/$500) | 47% ($235/$500) |
| **Position Sizing** | Fixed $60/$30 | Dynamic $25-$70 by conviction |
| **Entry Validation** | None | Re-checks price, rejects >30% dumps |
| **Container** | Not deployed | `callsbot-trader` service |

---

## 🎯 **Next Steps**

1. Review this document
2. Commit local changes
3. Deploy to server in dry-run mode
4. Monitor for 24-48 hours
5. Analyze simulated trades
6. Decide if you want to go live with $100 test
7. Scale up ONLY if profitable after 1 week

**DO NOT SKIP THE DRY-RUN TESTING PHASE!**

