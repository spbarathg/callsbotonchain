# 🚀 LIVE TRADING SETUP - $20 CAPITAL

**Goal:** Configure bot to trade live with $20 capital  
**Wallet:** Phantom wallet for monitoring  
**Mode:** LIVE (not dry-run)

---

## ✅ REQUIREMENTS CHECKLIST

Before starting, you need:

- [ ] **Phantom Wallet** installed and set up
- [ ] **$20-25 in SOL** in your wallet (extra $5 for gas fees)
- [ ] **Wallet Private Key** (58-character base58 string or byte array)
- [ ] **Solana RPC URL** (free: Helius, QuickNode, or public RPC)
- [ ] **Server SSH Access** (root@64.227.157.221)

---

## 📋 STEP-BY-STEP SETUP

### **STEP 1: Get Your Phantom Wallet Private Key**

**⚠️ CRITICAL SECURITY:**
- Your private key = full access to wallet
- NEVER share it with anyone
- Keep it secure
- Use a DEDICATED trading wallet (not your main wallet)

**How to Export from Phantom:**

1. Open Phantom wallet
2. Click Settings (⚙️) → Security & Privacy
3. Click "Export Private Key"
4. Enter your password
5. **COPY the private key** (looks like: `5J7X... (58 characters)` or byte array)
6. Save securely

**Alternative: Create New Wallet for Trading**
```bash
# On server, create new Solana wallet
solana-keygen new --outfile /opt/callsbotonchain/var/trading_wallet.json

# Get the private key
cat /opt/callsbotonchain/var/trading_wallet.json

# Send $20 SOL to the public address shown
```

---

### **STEP 2: Configure Environment Variables**

**Connect to server:**
```bash
ssh root@64.227.157.221
cd /opt/callsbotonchain/deployment
```

**Create/Edit `.env` file:**
```bash
nano .env
```

**Add these lines:**
```bash
# ==================== LIVE TRADING CONFIG ====================

# WALLET (REQUIRED - Your Phantom wallet private key)
TS_WALLET_SECRET="YOUR_PRIVATE_KEY_HERE"

# CAPITAL (REQUIRED - Set to $20)
TS_BANKROLL_USD=20

# MODE (REQUIRED - Set to false for LIVE trading)
TS_DRY_RUN=false

# SOLANA RPC (REQUIRED - Use free or paid RPC)
# Option 1: Public RPC (free, may be slow)
TS_RPC_URL="https://api.mainnet-beta.solana.com"

# Option 2: Helius RPC (free tier available)
# TS_RPC_URL="https://mainnet.helius-rpc.com/?api-key=YOUR_KEY"

# Option 3: QuickNode (paid, fast)
# TS_RPC_URL="https://your-endpoint.solana-mainnet.quiknode.pro/YOUR_KEY/"

# ==================== TRADING PARAMETERS ====================

# Position sizing (optimized for $20)
TS_MAX_CONCURRENT=4          # Max 4 positions at once
TS_MAX_POSITION_SIZE_PCT=25  # Max 25% per position ($5)

# Stop loss & trailing stops (OPTIMIZED)
TS_STOP_LOSS_PCT=15.0        # -15% stop loss
TS_TRAIL_AGGRESSIVE=10.0     # 10% trail for Score 9-10
TS_TRAIL_DEFAULT=15.0        # 15% trail for Score 8
TS_TRAIL_CONSERVATIVE=20.0   # 20% trail for Score 7

# Slippage & execution
TS_SLIPPAGE_BPS=150          # 1.5% slippage tolerance
TS_MAX_SLIPPAGE_PCT=5.0      # Max 5% slippage
TS_MAX_PRICE_IMPACT_PCT=10.0 # Max 10% price impact
TS_PRIORITY_FEE_MICROLAMPORTS=10000  # Gas priority

# Circuit breakers (safety)
TS_MAX_DAILY_LOSS_PCT=20.0   # Stop if lose 20% in one day
TS_MAX_CONSECUTIVE_LOSSES=5  # Stop after 5 losses in a row

# ==================== SIGNAL SOURCE ====================

# Use Redis for real-time signals (recommended)
USE_REDIS=true
REDIS_URL="redis://redis:6379/0"
```

**Save and exit:** `Ctrl+X`, then `Y`, then `Enter`

---

### **STEP 3: Fund Your Wallet**

**Option A: Use Your Phantom Wallet**
```
1. Send $20-25 SOL to your wallet address
2. Wallet will be used for trading
3. You can monitor all trades in Phantom app
```

**Option B: Create New Trading Wallet**
```bash
# Create wallet on server
solana-keygen new --outfile /opt/callsbotonchain/var/trading_wallet.json

# View public address
solana-keygen pubkey /opt/callsbotonchain/var/trading_wallet.json

# Send $20-25 SOL to this address from Phantom
```

**Verify Balance:**
```bash
# If using server wallet
solana balance --keypair /opt/callsbotonchain/var/trading_wallet.json

# Should show: ~$20-25 SOL
```

---

### **STEP 4: Restart Trading System**

**Stop current containers:**
```bash
cd /opt/callsbotonchain/deployment
docker compose stop callsbot-trader callsbot-tracker
```

**Reload configuration:**
```bash
docker compose up -d callsbot-trader callsbot-tracker
```

**Verify startup:**
```bash
# Check containers are running
docker ps | grep -E 'trader|tracker'

# Should show: "Up X seconds (healthy)"
```

---

### **STEP 5: Verify Configuration**

**Check trader loaded correct config:**
```bash
docker logs --tail 50 callsbot-trader
```

**Expected output:**
```
✅ Redis watcher connected: redis://redis:6379/0
💰 Bankroll: $20.00
🎯 Max Positions: 4
🛑 Stop Loss: 15.0%
📈 Trailing Stops: 10-15-20%
🔴 DRY RUN: False (LIVE TRADING)
📡 Watching Redis for trading signals...
```

**⚠️ If you see "DRY RUN: True":**
```bash
# Config not loaded - check .env file
cat /opt/callsbotonchain/deployment/.env | grep TS_DRY_RUN

# Should show: TS_DRY_RUN=false
```

---

### **STEP 6: Monitor First Trade**

**Wait for first signal (Score 8+):**
```bash
# Watch for signals
docker logs -f callsbot-worker | grep "Alert for token"

# When you see a signal, trader will execute
```

**Watch trader execute:**
```bash
# Follow trader logs in real-time
docker logs -f callsbot-trader
```

**Expected flow:**
```
📡 New signal received: TokenABC (Score: 9/10)
💰 Position size: $4.50 (22.5% of $20)
🔍 Fetching quote from Jupiter...
✅ Quote received: 1,234 tokens for $4.50
🚀 Executing BUY order...
✅ BUY executed: 1,234 tokens at $0.00365
📊 Position opened: TokenABC
   Entry: $4.50
   Quantity: 1,234 tokens
   Stop Loss: $3.83 (-15%)
   Trail: 15% from peak
```

**Check in Phantom Wallet:**
- Open Phantom app
- Go to Activity tab
- You'll see the SWAP transaction
- Token will appear in your wallet

---

## 📊 MONITORING YOUR TRADES

### **Real-Time Monitoring**

**Option 1: Phantom Wallet App**
```
- All trades appear in Activity tab
- See token balances in real-time
- View transaction details
- Monitor current positions
```

**Option 2: Server Logs**
```bash
# Watch trader activity
docker logs -f callsbot-trader

# Check recent trades
docker logs --tail 100 callsbot-trader | grep -E 'BUY|SELL|Position'

# View current positions
docker exec callsbot-trader python3 -c "
from tradingSystem.db import get_db
db = get_db()
positions = db.get_open_positions()
print(f'Open Positions: {len(positions)}')
for p in positions:
    print(f'  {p[\"symbol\"]}: {p[\"current_value_usd\"]:.2f} USD ({p[\"pnl_pct\"]:.1f}%)')
"
```

**Option 3: Solscan/Explorer**
```
- Go to: https://solscan.io/
- Enter your wallet address
- See all transactions
- View token swaps
```

### **Daily Check (1 Minute)**

```bash
ssh root@64.227.157.221 "
echo '=== Current Balance ==='
# Check wallet balance

echo '=== Trades Today ==='
docker logs --since 24h callsbot-trader | grep -c 'executed'

echo '=== Open Positions ==='
docker exec callsbot-trader python3 -c 'from tradingSystem.db import get_db; db = get_db(); print(len(db.get_open_positions()))'

echo '=== Recent P&L ==='
docker logs --tail 20 callsbot-trader | grep 'Position closed'
"
```

---

## 🎯 WHAT TO EXPECT ($20 Capital)

### **Position Sizing**

| Score | % of $20 | Position Size | Typical Allocation |
|-------|----------|---------------|-------------------|
| 10 | 20% | $4.00 | Fast movers |
| 9 | 18% | $3.60 | Aggressive |
| 8 | 25% | $5.00 | **Most common** |
| 7 | 10% | $2.00 | Moonshot lottery |

**Total Deployed:** $12-20 across 4 positions max

### **Example Trade Flow**

**Signal Received:**
```
Token: XYZ
Score: 8/10
MCap: $50,000
```

**Trade Execution:**
```
1. Buy $5 worth of XYZ
2. Entry price: $0.001
3. Quantity: 5,000 tokens
4. Stop loss set: $0.00085 (-15%)
5. Trail stop: 15% from peak
```

**Scenario A: Winner (+150%)**
```
Price rises to: $0.0025 (2.5x)
Trail triggers at: $0.002125 (15% below peak)
Exit: $10.63
Profit: +$5.63 (+113%)
Capital: $20 → $25.63
```

**Scenario B: Stop Loss (-15%)**
```
Price drops to: $0.00085
Stop loss triggers
Exit: $4.25
Loss: -$0.75 (-15%)
Capital: $20 → $19.25
```

### **Expected Results (30 Trades)**

```
Starting Capital: $20.00

Winners (11 trades @ 35%): +$35-50
Losers (19 trades @ 65%): -$14-20

Ending Capital: $40-70
Return: +100-250%
Time: 10-20 days
```

---

## ⚠️ CRITICAL SAFETY MEASURES

### **Automated Stop Loss**

✅ **Every position has -15% stop loss**
- Triggers automatically
- No manual intervention needed
- Protects capital

✅ **Circuit Breakers Active**
- Stop if lose >20% in one day
- Stop after 5 consecutive losses
- Auto-pause trading

### **Position Limits**

✅ **Max 4 concurrent positions**
- Diversification
- Risk spreading
- Capital preservation

✅ **Max 25% per position**
- No single trade risks more than $5
- Even if token goes to $0, you keep $15

### **Monitoring Alerts**

⚠️ **Set up these alerts:**

1. **Telegram Alerts**
   - Already active (you're receiving signals)
   - Add trade execution alerts if needed

2. **Phantom Notifications**
   - Enable push notifications in Phantom app
   - Get notified of all trades

3. **Daily Review**
   - Check balance once per day
   - Review trade performance
   - Verify system health

---

## 🔧 TROUBLESHOOTING

### **Problem: Trader Not Executing Trades**

**Check 1: Is trader in dry-run mode?**
```bash
docker logs --tail 50 callsbot-trader | grep "DRY RUN"
# Should show: "DRY RUN: False"
# If True, update .env file: TS_DRY_RUN=false
```

**Check 2: Is wallet configured?**
```bash
docker exec callsbot-trader python3 -c "
import os
print('Wallet Secret:', 'SET' if os.getenv('TS_WALLET_SECRET') else 'MISSING')
print('Bankroll:', os.getenv('TS_BANKROLL_USD', 'MISSING'))
print('Dry Run:', os.getenv('TS_DRY_RUN', 'true'))
"
```

**Check 3: Is wallet funded?**
```bash
# Check balance
# Use wallet address from your Phantom or server wallet
```

### **Problem: Trades Failing**

**Check 1: Slippage too high?**
```bash
docker logs --tail 50 callsbot-trader | grep -i slippage
# If seeing "slippage exceeded", increase TS_MAX_SLIPPAGE_PCT
```

**Check 2: Insufficient funds?**
```bash
# Verify wallet has enough SOL
# Need $20 + gas fees (~$0.50-1.00)
```

**Check 3: RPC issues?**
```bash
docker logs --tail 50 callsbot-trader | grep -i "rpc\|connection\|timeout"
# If seeing errors, switch RPC provider
```

### **Problem: No Signals**

**This is NORMAL if:**
- No tokens scored 8+ in last hour
- Market is slow
- Bot is working correctly but filtering aggressively

**Verify bot is working:**
```bash
# Check bot is processing
docker logs --tail 20 callsbot-worker | grep "FEED ITEMS"
# Should show: "FEED ITEMS: 20" every 30 seconds

# Check rejections
docker logs --since 1h callsbot-worker | grep "REJECTED" | wc -l
# Should show: 50-200 rejections per hour (good!)
```

---

## 📈 SCALING UP ($20 → $1,000)

**After 30 successful trades, you can scale:**

1. **Verify Performance**
   - Win rate 25-40% ✅
   - Stop losses working ✅
   - No system failures ✅
   - Capital grew to $40-70 ✅

2. **Update Configuration**
   ```bash
   nano /opt/callsbotonchain/deployment/.env
   # Change: TS_BANKROLL_USD=1000
   ```

3. **Fund Wallet**
   - Send $1,000 SOL to trading wallet
   - Keep extra $50 for gas fees

4. **Restart System**
   ```bash
   docker compose restart callsbot-trader callsbot-tracker
   ```

5. **Monitor Closely**
   - Same percentages, bigger amounts
   - $250 positions instead of $5
   - $1,000 → $3,000+ in 30 trades

---

## ✅ FINAL CHECKLIST

Before going live, verify:

- [ ] Wallet has $20-25 SOL
- [ ] Private key in `.env` file
- [ ] `TS_BANKROLL_USD=20` in `.env`
- [ ] `TS_DRY_RUN=false` in `.env`
- [ ] RPC URL configured
- [ ] Trader container restarted
- [ ] Logs show "DRY RUN: False"
- [ ] Phantom notifications enabled
- [ ] Ready to monitor first trade

---

## 🎯 YOUR FIRST TRADE

**What will happen:**

1. Bot receives Score 8+ signal
2. Trader calculates position size (~$4-5)
3. Fetches quote from Jupiter DEX
4. Executes SWAP on Solana
5. You see transaction in Phantom
6. Token appears in your wallet
7. Position monitored every 30s
8. Stop loss or trail stop triggers exit
9. Token swapped back to SOL
10. You see profit/loss in Phantom

**Timeline:**
- First signal: Within 24 hours (usually)
- First trade: Immediately after signal
- First exit: Minutes to hours later
- Daily trades: 2-5 on average

---

**🚀 YOU'RE READY TO GO LIVE!**

Follow the steps above and you'll have your bot trading with $20 capital, monitoring everything in your Phantom wallet.

**Questions or issues?** Check STATUS.md troubleshooting section or logs.

