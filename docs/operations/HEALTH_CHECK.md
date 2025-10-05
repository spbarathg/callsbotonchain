# Health Check Guide

## Quick Health Check (30 seconds)

Run this command for instant bot status:

```bash
# On server
docker ps && \
curl -s http://127.0.0.1/api/v2/quick-stats | jq && \
curl -s http://127.0.0.1/api/v2/budget-status | jq
```

### Expected Output:
- ✅ All 4 containers running (worker, web, trader, proxy)
- ✅ `total_alerts` increasing
- ✅ `tracking_count` matches total alerts
- ✅ `signals_enabled: true`
- ✅ `daily_percent` < 80%
- ✅ `status: "healthy"`

---

## Comprehensive Health Check (5 minutes)

### 1. Container Health
```bash
# Check container status
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

# Check restart counts (should be 0)
docker inspect callsbot-worker --format='Restarts: {{.RestartCount}}'
docker inspect callsbot-web --format='Restarts: {{.RestartCount}}'
docker inspect callsbot-trader --format='Restarts: {{.RestartCount}}'
```

**✅ Good**: All running, 0 restarts
**⚠️ Warning**: Any restarts > 0
**❌ Bad**: Containers exited or restarting loop

### 2. Worker Heartbeat
```bash
# Check last heartbeat (should be < 2 minutes ago)
docker logs callsbot-worker --tail 2000 2>&1 | grep '"type": "heartbeat"' | tail -1
```

**✅ Good**: Timestamp within last 2 minutes
**⚠️ Warning**: 2-5 minutes ago
**❌ Bad**: > 5 minutes ago or no heartbeat

### 3. Feed Cycle Check
```bash
# Verify feed alternation (should alternate general ↔ smart)
docker logs callsbot-worker --tail 1000 2>&1 | \
  grep '"type": "heartbeat"' | tail -5 | \
  python3 -c "import json,sys; [print(json.loads(line).get('cycle')) for line in sys.stdin]"
```

**✅ Good**: Alternating pattern (general, smart, general, smart...)
**❌ Bad**: All same cycle or stuck

### 4. Alert Generation
```bash
# Check alerts in last hour
docker logs callsbot-worker --since 1h 2>&1 | \
  grep '"component": "alerts"' | wc -l
```

**✅ Good**: > 10 alerts per hour
**⚠️ Warning**: 1-10 alerts (may be normal during quiet periods)
**❌ Bad**: 0 alerts for multiple hours

### 5. Database Integrity
```bash
sqlite3 /opt/callsbotonchain/var/alerted_tokens.db << 'SQL'
SELECT 
  'Total: ' || COUNT(*) || 
  ' | Smart: ' || SUM(CASE WHEN smart_money_detected = 1 THEN 1 ELSE 0 END) ||
  ' (' || ROUND(100.0 * SUM(CASE WHEN smart_money_detected = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) || '%)'
FROM alerted_tokens;

SELECT 'Orphans: ' || COUNT(*) 
FROM alerted_tokens at 
LEFT JOIN alerted_token_stats ats ON at.token_address = ats.token_address 
WHERE ats.token_address IS NULL;
SQL
```

**✅ Good**: Orphans = 0, Smart Money > 50%
**⚠️ Warning**: Orphans > 0 (need backfill)
**❌ Bad**: Smart Money < 30% (detection issue)

### 6. Budget Status
```bash
curl -s http://127.0.0.1/api/v2/budget-status | \
  python3 -c "import json,sys; d=json.load(sys.stdin); \
  print(f\"Daily: {d['daily_used']}/{d['daily_max']} ({d['daily_percent']:.1f}%)\"); \
  print(f\"Status: {d['status']}\"); \
  print(f\"Zero-Miss: {'ON' if d['zero_miss_mode'] else 'OFF'}\")"
```

**✅ Good**: < 70% usage, status=healthy, zero-miss ON
**⚠️ Warning**: 70-90% usage
**❌ Bad**: > 90% usage or status=exhausted

### 7. API Connectivity
```bash
# Test Cielo API
curl -s 'https://feed-api.cielo.finance/api/v1/feed?limit=3' \
  -H 'x-api-key: YOUR_API_KEY' | \
  python3 -c "import json,sys; d=json.load(sys.stdin); \
  print(f\"Items: {len(d.get('data',{}).get('items',[]))}\")"
```

**✅ Good**: Items > 0
**❌ Bad**: Items = 0 or error

### 8. Resource Usage
```bash
# Check disk and memory
df -h / | tail -1
free -h | grep Mem
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep callsbot
```

**✅ Good**: Disk < 80%, Memory < 80%, CPU < 50%
**⚠️ Warning**: Disk 80-90%, Memory 80-90%
**❌ Bad**: Disk > 90%, Memory > 90%, CPU sustained > 80%

### 9. Error Analysis
```bash
# Check for critical errors (exclude expected token_stats_error)
docker logs callsbot-worker --tail 1000 2>&1 | \
  grep -iE 'exception|traceback|fatal|critical' | \
  grep -v 'JSONDecodeError' | grep -v 'Telegram' | wc -l
```

**✅ Good**: 0 critical errors
**⚠️ Warning**: 1-5 errors (investigate)
**❌ Bad**: > 5 errors (needs immediate attention)

### 10. Tracking System
```bash
curl -s 'http://127.0.0.1/api/tracked?limit=5' | \
  python3 -c "import json,sys; rows=json.load(sys.stdin).get('rows',[]); \
  print(f\"Tracking {len(rows)} tokens\"); \
  [print(f\"  {r['token'][:20]} | Peak: {r.get('peak_multiple',0):.2f}x\") for r in rows[:5]]"
```

**✅ Good**: All tokens have peak_multiple values
**⚠️ Warning**: Some null values (may be new)
**❌ Bad**: All null values (tracking broken)

---

## Automated Health Check Script

Save as `/opt/callsbotonchain/ops/health_check.sh`:

```bash
#!/bin/bash
echo "=== CALLSBOT HEALTH CHECK ==="
echo ""

# 1. Containers
echo "1. CONTAINERS:"
RUNNING=$(docker ps --filter "name=callsbot" --format "{{.Names}}" | wc -l)
if [ "$RUNNING" -eq 4 ]; then
  echo "✅ All 4 containers running"
else
  echo "❌ Only $RUNNING/4 containers running"
fi

# 2. Stats
echo ""
echo "2. STATS:"
curl -s http://127.0.0.1/api/v2/quick-stats | jq -r '"Alerts: \(.total_alerts) | Tracking: \(.tracking_count) | 24h: \(.alerts_24h)"'

# 3. Budget
echo ""
echo "3. BUDGET:"
curl -s http://127.0.0.1/api/v2/budget-status | jq -r '"Daily: \(.daily_used)/\(.daily_max) (\(.daily_percent)%) | Status: \(.status)"'

# 4. Heartbeat
echo ""
echo "4. HEARTBEAT:"
LAST_HB=$(docker logs callsbot-worker --tail 2000 2>&1 | grep '"type": "heartbeat"' | tail -1)
if [ -n "$LAST_HB" ]; then
  echo "$LAST_HB" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"✅ {d['ts'][:19]} | Cycle: {d['cycle']}\")"
else
  echo "❌ No heartbeat found"
fi

echo ""
echo "=== CHECK COMPLETE ==="
```

Run with:
```bash
chmod +x /opt/callsbotonchain/ops/health_check.sh
/opt/callsbotonchain/ops/health_check.sh
```

---

## Troubleshooting

### Issue: No heartbeat
**Fix**: Check if worker is stuck
```bash
docker logs callsbot-worker --tail 50
docker restart callsbot-worker
```

### Issue: High budget usage
**Fix**: Adjust tracking interval
```bash
# Edit .env
TRACK_INTERVAL_MIN=20  # Increase from 15 to 20
docker restart callsbot-worker
```

### Issue: No alerts
**Fix**: Check feed connectivity
```bash
# Test Cielo API
curl -s 'https://feed-api.cielo.finance/api/v1/feed?limit=3' \
  -H 'x-api-key: YOUR_API_KEY'
```

### Issue: Database errors
**Fix**: Check permissions
```bash
ls -lh /opt/callsbotonchain/var/alerted_tokens.db
# Should be owned by 10001:10001 (appuser)
# If not: chown 10001:10001 /opt/callsbotonchain/var/alerted_tokens.db
```

---

## Monitoring Schedule

### Every Hour:
- Quick health check (30 seconds)
- Check dashboard at http://64.227.157.221/

### Every Day:
- Comprehensive health check (5 minutes)
- Review budget usage trend
- Check for any disk/memory issues

### Every Week:
- Review best performing tokens
- Analyze win rate and avg multiples
- Clean up old Docker images if needed

---

## Alert Thresholds

Configure alerts (optional) for:
- ❌ Container restarts > 0
- ⚠️ Budget usage > 80%
- ⚠️ Disk usage > 80%
- ❌ No heartbeat for 5+ minutes
- ⚠️ No alerts for 2+ hours
- ❌ Orphaned database records > 10

