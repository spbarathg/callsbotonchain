# 🏥 Server Health & Performance Guide

**Purpose:** Quick reference for checking server health and performance

---

## ⚡ Quick Health Check

```bash
# Check all containers
ssh root@64.227.157.221 "docker ps --format 'table {{.Names}}\t{{.Status}}'"

# Check worker logs (last 50 lines)
ssh root@64.227.157.221 "docker logs callsbot-worker --tail 50"

# Check for errors
ssh root@64.227.157.221 "docker logs callsbot-worker --tail 100 | grep -i error"
```

---

## 📊 Performance Verification

### Check Config Values
```bash
# View environment variables
ssh root@64.227.157.221 "cat /opt/callsbotonchain/deployment/.env | grep -E '(MIN_LIQUIDITY|GENERAL_CYCLE|MAX_24H_CHANGE)'"

# Expected values:
# MIN_LIQUIDITY_USD=15000
# GENERAL_CYCLE_MIN_SCORE=3
# MAX_24H_CHANGE_FOR_ALERT=1000
# MAX_1H_CHANGE_FOR_ALERT=2000
# DRAW_24H_MAJOR=-60
```

### Check Code Version
```bash
# Check current commit
ssh root@64.227.157.221 "cd /opt/callsbotonchain ; git log --oneline -1"

# Should match local/remote
git log --oneline -1
```

### Check Signal Volume
```bash
# Signals in last hour
ssh root@64.227.157.221 "sqlite3 /opt/callsbotonchain/alerted_tokens.db \"SELECT COUNT(*) FROM alerted_token_stats WHERE datetime(alerted_at) > datetime('now', '-1 hour')\""

# Signals in last 24 hours
ssh root@64.227.157.221 "sqlite3 /opt/callsbotonchain/alerted_tokens.db \"SELECT COUNT(*) FROM alerted_token_stats WHERE datetime(alerted_at) > datetime('now', '-24 hours')\""
```

---

## 🔄 Update & Restart

### Update Code
```bash
# Update to latest
ssh root@64.227.157.221 "cd /opt/callsbotonchain ; git fetch ; git reset --hard origin/main"

# Restart containers
ssh root@64.227.157.221 "cd /opt/callsbotonchain/deployment ; docker compose down ; docker compose up -d"
```

### Update Config
```bash
# Edit .env file
ssh root@64.227.157.221 "nano /opt/callsbotonchain/deployment/.env"

# After editing, restart to reload
ssh root@64.227.157.221 "cd /opt/callsbotonchain/deployment ; docker compose restart callsbot-worker"
```

---

## 🎯 Expected Performance Metrics

### Signal Volume
- **Healthy:** 150-250 signals/day
- **Warning:** <100 signals/day (too restrictive)
- **Warning:** >400 signals/day (too loose)

### Prelim Score Distribution
- **Healthy:** 40-60% of tokens are prelim 1-3
- **Warning:** <20% prelim 1-3 (gate too high)
- **Warning:** >80% prelim 1-3 (gate too low)

### Container Health
- **All containers:** Should show "healthy" status
- **Worker uptime:** Should be stable (no frequent restarts)
- **Logs:** Should show continuous processing, no errors

---

## 🚨 Troubleshooting

### No Signals Being Sent
1. Check Telethon connection: `docker logs callsbot-worker | grep Telethon`
2. Check for errors: `docker logs callsbot-worker | grep -i error`
3. Check config loaded: Verify .env values
4. Restart worker: `docker compose restart callsbot-worker`

### Too Few Signals
1. Check PRELIM_DETAILED_MIN (should be 1)
2. Check MAX_24H_CHANGE (should be 1000)
3. Check MIN_LIQUIDITY (should be 15000)
4. Check logs for rejection reasons

### Too Many Junk Signals
1. Check GENERAL_CYCLE_MIN_SCORE (should be 3)
2. Check MIN_LIQUIDITY_USD (raise if needed)
3. Review recent signal quality in database

---

## 📋 Critical Config Values

**For 100% Performance, these MUST be set:**

```bash
# In deployment/.env:
PRELIM_DETAILED_MIN=1
MIN_LIQUIDITY_USD=15000
GENERAL_CYCLE_MIN_SCORE=3
HIGH_CONFIDENCE_SCORE=5
VOL_TO_MCAP_RATIO_MIN=0.02
MAX_24H_CHANGE_FOR_ALERT=1000
MAX_1H_CHANGE_FOR_ALERT=2000
DRAW_24H_MAJOR=-60
```

**If any are different, the bot is NOT running optimally!**

---

**Last Updated:** October 15, 2025  
**For Issues:** Check this guide first, then review logs

