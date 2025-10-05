# Troubleshooting Guide

## Common Issues and Solutions

---

## 1. No Heartbeat / Worker Stuck

### Symptoms:
- No heartbeat in logs for > 5 minutes
- Container shows as "running" but inactive
- No new alerts being generated

### Diagnosis:
```bash
# Check last heartbeat
docker logs callsbot-worker --tail 2000 2>&1 | grep heartbeat | tail -1

# Check if process is alive
docker exec callsbot-worker ps aux | grep python

# Check for errors
docker logs callsbot-worker --tail 50 2>&1 | grep -iE 'error|exception|fatal'
```

### Solution:
```bash
# Restart worker
docker restart callsbot-worker

# If restart doesn't help, rebuild
cd /opt/callsbotonchain
docker compose up -d --build worker

# Verify it's working
sleep 120  # Wait 2 minutes
docker logs callsbot-worker --tail 50 | grep heartbeat
```

---

## 2. High Budget Usage / API Exhaustion

### Symptoms:
- `daily_percent` > 90%
- `status: "exhausted"`
- Frequent `budget_blocked` messages in logs

### Diagnosis:
```bash
# Check current usage
curl -s http://127.0.0.1/api/v2/budget-status | jq

# Check tracking frequency
docker exec callsbot-worker env | grep TRACK_INTERVAL_MIN
```

### Solution A: Increase Daily Budget
```bash
# Edit .env
vim /opt/callsbotonchain/.env
# Change: BUDGET_PER_DAY_MAX=15000  # Increase from 10000

# Restart worker
docker restart callsbot-worker
```

### Solution B: Reduce Tracking Frequency
```bash
# Edit .env
vim /opt/callsbotonchain/.env
# Change: TRACK_INTERVAL_MIN=20  # Increase from 15
# Change: TRACK_BATCH_SIZE=20  # Decrease from 30

# Restart worker
docker restart callsbot-worker
```

### Solution C: Reset Budget (Emergency)
```bash
# Reset credits_budget.json
echo '{"minute_epoch":0,"minute_count":0,"day_utc":0,"day_count":0}' > \
  /opt/callsbotonchain/var/credits_budget.json

# Restart worker
docker restart callsbot-worker
```

---

## 3. No Alerts Being Generated

### Symptoms:
- Worker running but no new alerts
- Heartbeat shows `alerts_sent` not increasing
- Empty `alerts.jsonl` or no recent entries

### Diagnosis:
```bash
# Check if feed is being received
docker logs callsbot-worker --tail 100 | grep feed_items

# Check if items are being rejected
docker logs callsbot-worker --tail 100 | grep REJECTED

# Test Cielo API directly
curl -s 'https://feed-api.cielo.finance/api/v1/feed?limit=5' \
  -H 'x-api-key: YOUR_API_KEY' | jq '.data.items | length'
```

### Solution A: Cielo API Issue
```bash
# Check API key is valid
docker exec callsbot-worker env | grep CIELO_API_KEY

# Test with correct key
export API_KEY=$(docker exec callsbot-worker env | grep CIELO_API_KEY | cut -d= -f2)
curl -s "https://feed-api.cielo.finance/api/v1/feed?limit=5" \
  -H "x-api-key: $API_KEY"
```

### Solution B: Gates Too Strict
```bash
# Temporarily lower gates for testing
vim /opt/callsbotonchain/.env
# Change: HIGH_CONFIDENCE_SCORE=4  # Lower from 5
# Change: MIN_LIQUIDITY_USD=3000  # Lower from 5000

# Restart and monitor
docker restart callsbot-worker
docker logs callsbot-worker -f | grep "ALERT SENT"
```

### Solution C: Force Fallback Mode
```bash
# Edit docker-compose.yml
vim /opt/callsbotonchain/docker-compose.yml
# Find worker service, add:
#   CALLSBOT_FORCE_FALLBACK=false  # Ensure this is false

# Rebuild
docker compose up -d --build worker
```

---

## 4. Database Errors / Permission Issues

### Symptoms:
- `sqlite3.OperationalError: attempt to write a readonly database`
- `PermissionError` in logs
- Tracking not updating

### Diagnosis:
```bash
# Check database permissions
ls -lh /opt/callsbotonchain/var/alerted_tokens.db

# Should show: -rw-r--r-- 1 10001 10001
```

### Solution:
```bash
# Fix ownership
chown 10001:10001 /opt/callsbotonchain/var/alerted_tokens.db
chown 10001:10001 /opt/callsbotonchain/var/*.db*

# Restart worker
docker restart callsbot-worker
```

---

## 5. Missing Tracking Data (null values)

### Symptoms:
- `peak_multiple: null` in tracked API
- `last_price: null` for many tokens
- Dashboard showing empty tracking data

### Diagnosis:
```bash
# Check if stats table has entries
sqlite3 /opt/callsbotonchain/var/alerted_tokens.db \
  'SELECT COUNT(*) FROM alerted_token_stats;'

# Check for orphaned alerts
sqlite3 /opt/callsbotonchain/var/alerted_tokens.db << 'SQL'
SELECT COUNT(*) FROM alerted_tokens at
LEFT JOIN alerted_token_stats ats ON at.token_address = ats.token_address
WHERE ats.token_address IS NULL;
SQL
```

### Solution:
```bash
# Backfill missing stats
cat > /tmp/backfill_stats.py << 'EOF'
import sqlite3
conn = sqlite3.connect('/app/var/alerted_tokens.db')
c = conn.cursor()

# Get tokens without stats
c.execute('''
  SELECT token_address, alerted_at 
  FROM alerted_tokens 
  WHERE token_address NOT IN (SELECT token_address FROM alerted_token_stats)
''')
missing = c.fetchall()

for token, alerted_at in missing:
    c.execute('''
      INSERT INTO alerted_token_stats 
      (token_address, first_alert_at, last_checked_at, 
       first_price_usd, last_price_usd, peak_price_usd)
      VALUES (?, ?, CURRENT_TIMESTAMP, 0, 0, 0)
    ''', (token, alerted_at))

conn.commit()
print(f"Backfilled {len(missing)} stats entries")
conn.close()
EOF

# Run in container
docker exec -i callsbot-worker python3 << 'EOF'
$(cat /tmp/backfill_stats.py)
EOF
```

---

## 6. Smart Money Detection Not Working

### Symptoms:
- `smart_money_detected: false` for all alerts
- `Smart Money` conviction type missing
- Smart cycle not generating alerts

### Diagnosis:
```bash
# Check feed cycle logs
docker logs callsbot-worker --tail 500 | grep '"cycle": "smart"'

# Check smart money parameters
docker logs callsbot-worker --tail 1000 | grep smart_money

# Verify in database
sqlite3 /opt/callsbotonchain/var/alerted_tokens.db \
  'SELECT COUNT(*), SUM(smart_money_detected) FROM alerted_tokens;'
```

### Solution:
```bash
# Verify smart money detection is enabled
grep -r "smart_money_only" /opt/callsbotonchain/app/fetch_feed.py

# Check if cycles are alternating
docker logs callsbot-worker --tail 1000 | \
  grep heartbeat | tail -10 | \
  python3 -c "import json,sys; [print(json.loads(l).get('cycle')) for l in sys.stdin]"

# Should show: general, smart, general, smart...
```

---

## 7. High Error Rate in Logs

### Symptoms:
- Many `token_stats_error` messages
- Status 530 or 400 errors
- `token_stats_unavailable` frequently

### Diagnosis:
```bash
# Count error types
docker logs callsbot-worker --tail 1000 2>&1 | \
  grep token_stats_error | \
  python3 -c "import json,sys; from collections import Counter; \
  errors = [json.loads(l).get('status') for l in sys.stdin]; \
  print(Counter(errors))"
```

### Solution:
**✅ These errors are NORMAL and EXPECTED:**
- **Status 530**: Cloudflare blocking (protects against junk tokens)
- **Status 400**: Invalid token addresses (correctly filtered)
- **"native" tokens**: SOL swaps being rejected (correct behavior)

**No action needed unless:**
- Error rate > 50% of all logs
- Seeing actual Python exceptions or tracebacks
- Errors preventing alerts from being generated

---

## 8. Container Restarts / Crashes

### Symptoms:
- `RestartCount > 0` in docker inspect
- Containers showing "restarting" status
- Missing data after restart

### Diagnosis:
```bash
# Check restart count
docker inspect callsbot-worker --format='{{.RestartCount}}'

# Check exit code and reason
docker inspect callsbot-worker --format='{{.State.ExitCode}} | {{.State.Error}}'

# Check logs before crash
docker logs callsbot-worker --tail 100 2>&1 | tail -50
```

### Solution A: Memory Issue
```bash
# Check memory usage
docker stats --no-stream callsbot-worker

# If memory is high, increase limit in docker-compose.yml
vim /opt/callsbotonchain/docker-compose.yml
# Add under worker service:
#   mem_limit: 512m

# Rebuild
docker compose up -d
```

### Solution B: Code Error
```bash
# Check for Python exceptions
docker logs callsbot-worker 2>&1 | grep -A 10 "Traceback"

# If found, report issue or rollback
cd /opt/callsbotonchain
git log --oneline -10  # Find last good commit
# git reset --hard <commit-hash>  # Only if certain!
```

### Solution C: Dependency Issue
```bash
# Rebuild from scratch
docker compose down
docker rmi callsbotonchain-worker
docker compose up -d --build worker
```

---

## 9. Dashboard Not Loading / API Errors

### Symptoms:
- Dashboard shows blank page
- API endpoints return 500 errors
- Browser console shows errors

### Diagnosis:
```bash
# Check web container
docker logs callsbot-web --tail 50

# Test API endpoints
curl -s http://127.0.0.1/healthz
curl -s http://127.0.0.1/api/v2/quick-stats

# Check if database is accessible
docker exec callsbot-web ls -lh /app/var/alerted_tokens.db
```

### Solution:
```bash
# Restart web container
docker restart callsbot-web

# If that doesn't work, rebuild
cd /opt/callsbotonchain
docker compose up -d --build web

# Clear browser cache (Ctrl+Shift+R)
```

---

## 10. Disk Space Full

### Symptoms:
- `df -h` shows > 90% usage
- `No space left on device` errors
- Containers failing to write logs

### Diagnosis:
```bash
# Check disk usage
df -h /

# Check what's using space
du -sh /opt/callsbotonchain/* | sort -h
du -sh /var/lib/docker/* | sort -h
```

### Solution:
```bash
# Clean Docker resources
docker system prune -af
docker image prune -af
docker volume prune -f

# Clean old logs (if > 100MB)
find /opt/callsbotonchain/data/logs -name "*.jsonl" -size +100M -delete

# Check space freed
df -h /
```

---

## Emergency Recovery Procedures

### Complete System Reset (DESTRUCTIVE)
```bash
# ⚠️ WARNING: This deletes all data!
cd /opt/callsbotonchain
docker compose down
rm -rf var/*.db var/*.json data/logs/*.jsonl
docker compose up -d --build
```

### Backup Before Troubleshooting
```bash
# Always backup first!
tar -czf ~/callsbot_backup_$(date +%Y%m%d_%H%M%S).tar.gz \
  /opt/callsbotonchain/var/*.db \
  /opt/callsbotonchain/data/logs/*.jsonl \
  /opt/callsbotonchain/.env
```

### Restore from Backup
```bash
# Extract backup
tar -xzf ~/callsbot_backup_*.tar.gz -C /

# Fix permissions
chown -R 10001:10001 /opt/callsbotonchain/var/
docker restart callsbot-worker
```

---

## Getting Help

### Collect Diagnostic Info:
```bash
# Create diagnostic report
cat > /tmp/diagnostic_report.txt << EOF
=== DIAGNOSTIC REPORT ===
Date: $(date)

Container Status:
$(docker ps -a | grep callsbot)

Recent Worker Logs:
$(docker logs callsbot-worker --tail 50 2>&1)

Database Status:
$(sqlite3 /opt/callsbotonchain/var/alerted_tokens.db 'SELECT COUNT(*) FROM alerted_tokens; SELECT COUNT(*) FROM alerted_token_stats;')

Budget Status:
$(curl -s http://127.0.0.1/api/v2/budget-status)

Disk Usage:
$(df -h /)

Environment:
$(docker exec callsbot-worker env | grep -E 'CIELO|BUDGET|TRACK|HIGH_CONFIDENCE')
EOF

# Review report
cat /tmp/diagnostic_report.txt
```

### Common Debugging Commands:
```bash
# Follow logs in real-time
docker logs callsbot-worker -f

# Execute commands inside container
docker exec -it callsbot-worker bash

# Check environment variables
docker exec callsbot-worker env | sort

# Test Python imports
docker exec callsbot-worker python3 -c "import app.fetch_feed; print('OK')"
```

