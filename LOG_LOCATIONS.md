# 📍 LOG FILE LOCATIONS - IMPORTANT

## ⚠️ CRITICAL: Use the Correct Log Directory

### ✅ ACTIVE LOGS (Use These)
```
/opt/callsbotonchain/deployment/data/logs/
```

**All Docker containers write logs here.**

### ❌ DEPRECATED (Do Not Use)
```
/opt/callsbotonchain/data/logs/  ← OLD, EMPTY, IGNORE
```

---

## 📊 Active Log Files

| File | Purpose | Size | Update Frequency |
|------|---------|------|------------------|
| **stdout.log** | Main bot output | ~28MB | Real-time |
| **process.jsonl** | Structured events | ~22MB | Real-time |
| **alerts.jsonl** | Token alerts | ~400KB | Per alert |
| **trading.jsonl** | Trading events | ~200B | Per trade |
| **trading.log** | Trading text logs | ~100B | Per trade |

---

## 🔍 Quick Reference Commands

### View Live Bot Activity
```bash
# Main bot logs
tail -f /opt/callsbotonchain/deployment/data/logs/stdout.log

# Recent alerts (last 10)
tail -n 10 /opt/callsbotonchain/deployment/data/logs/alerts.jsonl | jq

# Process events
tail -f /opt/callsbotonchain/deployment/data/logs/process.jsonl | jq
```

### Check Log Sizes
```bash
du -sh /opt/callsbotonchain/deployment/data/logs/*
ls -lh /opt/callsbotonchain/deployment/data/logs/
```

### Docker Container Logs
```bash
# Bot worker
docker logs callsbot-worker --tail 100 -f

# Tracker
docker logs callsbot-tracker --tail 50 -f

# Web server
docker logs callsbot-web --tail 50 -f

# Paper trader
docker logs callsbot-paper-trader --tail 50 -f
```

### Search for Errors
```bash
# In stdout.log
grep -i 'error\|exception\|failed' /opt/callsbotonchain/deployment/data/logs/stdout.log | tail -n 20

# In Docker logs
docker logs callsbot-worker 2>&1 | grep -i 'error\|exception'
```

---

## 🐳 Docker Volume Mounts

The containers mount logs as follows:

```yaml
volumes:
  - /opt/callsbotonchain/deployment/var:/app/var
  - /opt/callsbotonchain/deployment/data/logs:/app/data/logs
```

**Inside Container:** `/app/data/logs/`  
**On Host:** `/opt/callsbotonchain/deployment/data/logs/`

---

## 📈 Log Analysis Examples

### Count Recent Alerts
```bash
# Alerts in last 24 hours
jq -r 'select(.ts > (now - 86400 | todate)) | .token' \
  /opt/callsbotonchain/deployment/data/logs/alerts.jsonl | wc -l
```

### View Alert Details
```bash
# Last 5 alerts with token name and score
tail -n 5 /opt/callsbotonchain/deployment/data/logs/alerts.jsonl | \
  jq -r '[.ts, .symbol, .final_score, .liquidity] | @tsv'
```

### Check Bot Health
```bash
# Last log entry timestamp
tail -n 1 /opt/callsbotonchain/deployment/data/logs/stdout.log

# Check if bot is sleeping (should see "Sleeping for 60 seconds")
tail -n 5 /opt/callsbotonchain/deployment/data/logs/stdout.log | grep -i sleep
```

---

## 🌐 API Access

### Web Dashboard
```bash
# Quick stats
curl http://localhost/api/v2/quick-stats

# External access
curl http://64.227.157.221/api/v2/quick-stats
```

**Note:** Port 8080 is internal only. Use port 80 (Caddy proxy) for external access.

---

## 🔧 Troubleshooting

### "Logs are empty"
✅ **Solution:** You're checking the wrong directory!
- ❌ Don't use: `/opt/callsbotonchain/data/logs/`
- ✅ Use: `/opt/callsbotonchain/deployment/data/logs/`

### "Can't access API on port 8080"
✅ **Solution:** Port 8080 is internal only.
- ❌ Don't use: `http://localhost:8080`
- ✅ Use: `http://localhost` (port 80, Caddy proxy)

### "No recent activity in logs"
```bash
# Check if containers are running
docker ps

# Check container logs directly
docker logs callsbot-worker --tail 20

# Verify log file timestamps
stat /opt/callsbotonchain/deployment/data/logs/stdout.log
```

---

## 📝 Database Locations

Similarly, databases are in the deployment directory:

```
/opt/callsbotonchain/deployment/var/alerted_tokens.db  ← ACTIVE
/opt/callsbotonchain/deployment/var/trading.db         ← ACTIVE
/opt/callsbotonchain/deployment/var/paper_trading.db   ← ACTIVE
```

**Not here:**
```
/opt/callsbotonchain/var/*.db  ← OLD/EMPTY
```

---

**Last Updated:** October 13, 2025  
**System:** Production deployment at 64.227.157.221

