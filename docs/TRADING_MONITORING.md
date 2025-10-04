# Trading System Dry-Run Monitoring Guide

## ✅ **Deployment Status: COMPLETE**

### **What's Running:**
- **Worker**: Generating signals from Cielo feed ✅
- **Web**: Dashboard at http://64.227.157.221 ✅
- **Trader**: Monitoring signals and simulating trades in DRY-RUN mode ✅
- **Proxy**: Caddy reverse proxy ✅

### **Trading Configuration:**
- **Mode**: DRY_RUN=true (NO REAL MONEY)
- **Bankroll**: $500 (simulated)
- **Max Positions**: 5 concurrent
- **Position Sizes**: $25-$70 based on signal quality

---

## 📊 **How to Monitor Performance**

### **1. Check Trading Logs (Real-Time)**
```bash
# View live trading events
ssh root@64.227.157.221 "docker logs -f callsbot-trader"

# Last 50 entries
ssh root@64.227.157.221 "docker logs callsbot-trader --tail 50"
```

**What to look for:**
- `trading_system_start` - System initialized
- `open_position` - Simulated buy (with strategy, size, price)
- `exit_stop` - Hit stop loss
- `exit_trail` - Hit trailing stop
- `entry_rejected_dumped` - Token dumped >30% before entry
- `stats_fetch_failed` - Couldn't get real-time data

### **2. Check Simulated Positions**
```bash
# View all positions
ssh root@64.227.157.221 "sqlite3 /opt/callsbotonchain/var/trading.db 'SELECT id, token_address, strategy, entry_price, qty, usd_size, status, open_at FROM positions ORDER BY id DESC LIMIT 20;'"

# Count open vs closed
ssh root@64.227.157.221 "sqlite3 /opt/callsbotonchain/var/trading.db 'SELECT status, COUNT(*) FROM positions GROUP BY status;'"
```

### **3. Check Fills (Buy/Sell Events)**
```bash
# View recent fills
ssh root@64.227.157.221 "sqlite3 /opt/callsbotonchain/var/trading.db 'SELECT position_id, side, price, qty, usd, at FROM fills ORDER BY id DESC LIMIT 30;'"

# Calculate PnL for a position
ssh root@64.227.157.221 "sqlite3 /opt/callsbotonchain/var/trading.db 'SELECT p.id, p.token_address, p.strategy, SUM(CASE WHEN f.side=\"buy\" THEN -f.usd ELSE f.usd END) as pnl FROM positions p JOIN fills f ON p.id = f.position_id WHERE p.id = 1 GROUP BY p.id;'"
```

### **4. View Trading Logs (Structured)**
```bash
# Read trading.jsonl
ssh root@64.227.157.221 "tail -50 /opt/callsbotonchain/data/logs/trading.jsonl"

# Count events by type
ssh root@64.227.157.221 "cat /opt/callsbotonchain/data/logs/trading.jsonl | jq -r .event | sort | uniq -c"
```

### **5. Check Container Health**
```bash
# All containers status
ssh root@64.227.157.221 "docker ps --filter name=callsbot"

# Trader logs for errors
ssh root@64.227.157.221 "docker logs callsbot-trader 2>&1 | grep -i error"
```

---

## 📈 **Expected Results After 24 Hours**

### **Healthy Dry-Run Signals:**
- **Positions Opened**: 10-30 (depends on alert volume)
- **Strategies Used**: Runner (smart money), Strict (high conf), Scout (velocity), Nuanced (risky)
- **Some Stops Hit**: Normal - memecoins are volatile
- **Some Trailing Exits**: Good - taking profits
- **Entry Rejections**: Some tokens dump before entry (expected)

### **Red Flags:**
- ❌ No positions opened after 6 hours
- ❌ All positions hitting stop loss (0% winners)
- ❌ Trader container restarting repeatedly
- ❌ `stats_fetch_failed` for every signal
- ❌ Database errors in logs

---

## 🔍 **Analyzing Performance**

### **Calculate Win Rate:**
```bash
ssh root@64.227.157.221 << 'EOF'
sqlite3 /opt/callsbotonchain/var/trading.db << 'SQL'
WITH position_pnl AS (
  SELECT 
    p.id,
    p.token_address,
    p.strategy,
    SUM(CASE WHEN f.side='buy' THEN -f.usd ELSE f.usd END) as pnl,
    p.status
  FROM positions p
  JOIN fills f ON p.id = f.position_id
  WHERE p.status = 'closed'
  GROUP BY p.id
)
SELECT 
  COUNT(*) as total_closed,
  SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winners,
  SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losers,
  ROUND(AVG(pnl), 2) as avg_pnl,
  ROUND(SUM(pnl), 2) as total_pnl,
  ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate_pct
FROM position_pnl;
SQL
EOF
```

### **Strategy Performance:**
```bash
ssh root@64.227.157.221 << 'EOF'
sqlite3 /opt/callsbotonchain/var/trading.db << 'SQL'
WITH position_pnl AS (
  SELECT 
    p.strategy,
    SUM(CASE WHEN f.side='buy' THEN -f.usd ELSE f.usd END) as pnl
  FROM positions p
  JOIN fills f ON p.id = f.position_id
  WHERE p.status = 'closed'
  GROUP BY p.id, p.strategy
)
SELECT 
  strategy,
  COUNT(*) as trades,
  ROUND(AVG(pnl), 2) as avg_pnl,
  ROUND(SUM(pnl), 2) as total_pnl
FROM position_pnl
GROUP BY strategy;
SQL
EOF
```

---

## 🎯 **Decision Criteria (After 24-48 Hours)**

### **✅ GO LIVE** if:
1. Win rate > 15% (realistic for memecoins)
2. Average winner > 2× average loser
3. System opens 10+ positions without crashes
4. No database or fetch errors
5. Entry validation working (some rejections = good)
6. Trailing stops triggering (taking profits)

### **🔧 TUNE FIRST** if:
- Win rate 10-15% → Tighten entry gates slightly
- Win rate < 10% → Gates too loose, attracting rugs
- Capital utilization < 30% → Increase position sizes or MAX_CONCURRENT
- Too many stop losses → Widen stops by 2-3%
- Missing good trades → Relax gates, especially for strict/nuanced

### **❌ DON'T GO LIVE** if:
- Win rate < 5%
- System crashes or database errors
- All positions rug immediately
- Entry validation not working

---

## 🚀 **Going Live Checklist**

**Only proceed if dry-run shows promise:**

1. **Create New Trading Wallet** (NOT your main wallet!)
```bash
solana-keygen new -o trading_wallet.json
# Save the public key and backup the file securely!
```

2. **Fund with TEST AMOUNT** ($100 USDC, not $500)
```bash
# Get wallet address
solana-keygen pubkey trading_wallet.json

# Send 100 USDC from your main wallet to this address
```

3. **Update .env on Server**
```bash
ssh root@64.227.157.221
nano /opt/callsbotonchain/.env

# Add these lines:
TS_WALLET_SECRET=<BASE58_PRIVATE_KEY_OR_JSON_ARRAY>
TS_DRY_RUN=false
TS_BANKROLL_USD=100  # Start with $100, not $500!

# Save and exit
```

4. **Restart Trader**
```bash
docker compose restart trader
```

5. **Monitor EVERY Trade for First 24 Hours**
```bash
# Watch live
docker logs -f callsbot-trader

# Check positions every hour
sqlite3 /opt/callsbotonchain/var/trading.db 'SELECT * FROM positions WHERE status="open";'
```

6. **If Successful After 1 Week:**
- Increase to $250, then $500
- Adjust position sizes proportionally
- Keep monitoring daily

---

## ⚠️ **Emergency Stop**

If things go wrong:

```bash
# Stop trader immediately
ssh root@64.227.157.221 "docker compose stop trader"

# Check open positions
ssh root@64.227.157.221 "sqlite3 /opt/callsbotonchain/var/trading.db 'SELECT token_address FROM positions WHERE status=\"open\";'"

# Manually sell on Jupiter if needed
```

---

## 📊 **Quick Status Check (Run Daily)**

```bash
ssh root@64.227.157.221 << 'EOF'
echo "=== Container Status ==="
docker ps --filter name=callsbot --format "table {{.Names}}\t{{.Status}}"

echo -e "\n=== Positions Summary ==="
sqlite3 /opt/callsbotonchain/var/trading.db "SELECT status, COUNT(*) FROM positions GROUP BY status;"

echo -e "\n=== Recent Entries (Last 5) ==="
sqlite3 /opt/callsbotonchain/var/trading.db "SELECT id, token_address, strategy, ROUND(usd_size, 2) as size, datetime(open_at) FROM positions ORDER BY id DESC LIMIT 5;"

echo -e "\n=== Trader Health ==="
docker logs callsbot-trader --tail 5
EOF
```

---

## 📞 **Support & Troubleshooting**

### **Trader Not Opening Positions?**
1. Check if bot is generating alerts: `docker logs callsbot-worker --tail 50`
2. Check if trader is receiving signals: `docker logs callsbot-trader --tail 50`
3. Verify `trading_enabled()` toggle: `ssh root@64.227.157.221 "cat /opt/callsbotonchain/var/toggles.json"`

### **Database Errors?**
```bash
# Check permissions
ssh root@64.227.157.221 "ls -la /opt/callsbotonchain/var/trading.db"

# Should be owned by 10001:10001 (appuser)
# If not, fix:
ssh root@64.227.157.221 "chown 10001:10001 /opt/callsbotonchain/var/trading.db*"
```

### **Stats Fetch Failing?**
- Check if web API is running: `curl http://64.227.157.221/api/tracked?limit=10`
- Check if tokens are being tracked: `tail /opt/callsbotonchain/data/logs/tracking.jsonl`

---

## 🎉 **Summary**

Your trading system is now:
- ✅ Deployed and running in DRY-RUN mode
- ✅ Processing 100% of signals (all conviction types)
- ✅ Using real-time stats validation
- ✅ Simulating trades with $500 bankroll
- ✅ Ready for 24-48 hour evaluation

**Next Steps:**
1. Monitor performance for 24-48 hours
2. Run analysis queries to check win rate and PnL
3. Decide: Go live with $100 test, tune parameters, or abort

**Remember**: This is SPECULATIVE memecoin trading. Expect volatility, losses, and rugpulls. Only risk what you can afford to lose!

