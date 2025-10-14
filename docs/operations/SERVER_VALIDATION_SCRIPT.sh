#!/bin/bash
# Server Validation Script - CallsBot Production
# Run this to validate the complete server setup
# Usage: bash SERVER_VALIDATION_SCRIPT.sh

echo "=========================================="
echo "CALLSBOT SERVER VALIDATION"
echo "Server: 64.227.157.221"
echo "Date: $(date)"
echo "=========================================="
echo ""

# 1. DOCKER CONTAINERS STATUS
echo "1. DOCKER CONTAINERS"
echo "--------------------"
docker compose ps
echo ""
echo "Container Details:"
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep callsbot
echo ""

# 2. CONTAINER HEALTH & RESTARTS
echo "2. CONTAINER HEALTH"
echo "-------------------"
echo "Worker restarts: $(docker inspect callsbot-worker --format='{{.RestartCount}}' 2>/dev/null || echo 'N/A')"
echo "Web restarts: $(docker inspect callsbot-web --format='{{.RestartCount}}' 2>/dev/null || echo 'N/A')"
echo "Tracker restarts: $(docker inspect callsbot-tracker --format='{{.RestartCount}}' 2>/dev/null || echo 'N/A')"
echo "Paper Trader restarts: $(docker inspect callsbot-paper-trader --format='{{.RestartCount}}' 2>/dev/null || echo 'N/A')"
echo ""

# 3. API HEALTH CHECK
echo "3. API HEALTH CHECK"
echo "-------------------"
echo "Quick Stats:"
curl -s http://localhost/api/v2/quick-stats 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "API not responding"
echo ""
echo "Budget Status:"
curl -s http://localhost/api/v2/budget-status 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "API not responding"
echo ""

# 4. WORKER HEARTBEAT
echo "4. WORKER HEARTBEAT"
echo "-------------------"
echo "Last 3 heartbeats:"
docker logs callsbot-worker --tail 2000 2>&1 | grep '"type": "heartbeat"' | tail -3 | while read line; do
  echo "$line" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"{d.get('ts', 'N/A')[:19]} | Cycle: {d.get('cycle', 'N/A')} | Signals: {d.get('signals_enabled', 'N/A')}\")" 2>/dev/null || echo "$line"
done
echo ""

# 5. RECENT SIGNALS
echo "5. RECENT SIGNALS (Last Hour)"
echo "-----------------------------"
SIGNAL_COUNT=$(docker logs callsbot-worker --since 1h 2>&1 | grep -c '"component": "alerts"' 2>/dev/null || echo "0")
echo "Signals in last hour: $SIGNAL_COUNT"
echo ""
echo "Last 3 signals:"
docker logs callsbot-worker --tail 1000 2>&1 | grep '"component": "alerts"' | tail -3
echo ""

# 6. DATABASE STATUS
echo "6. DATABASE STATUS"
echo "------------------"
if [ -f /opt/callsbotonchain/deployment/var/alerted_tokens.db ]; then
  echo "Database location: /opt/callsbotonchain/deployment/var/alerted_tokens.db"
  sqlite3 /opt/callsbotonchain/deployment/var/alerted_tokens.db << 'SQL'
SELECT 'Total Signals: ' || COUNT(*) FROM alerted_tokens;
SELECT 'Signals Last 24h: ' || COUNT(*) FROM alerted_tokens WHERE alerted_at > (strftime('%s', 'now') - 86400);
SELECT 'Signals Last 7d: ' || COUNT(*) FROM alerted_tokens WHERE alerted_at > (strftime('%s', 'now') - 604800);
SQL
else
  echo "Database not found at expected location"
fi
echo ""

# 7. CONFIGURATION CHECK
echo "7. ACTIVE CONFIGURATION"
echo "-----------------------"
if [ -f /opt/callsbotonchain/deployment/.env ]; then
  echo "Key settings from .env:"
  grep -E "^(HIGH_CONFIDENCE_SCORE|GENERAL_CYCLE_MIN_SCORE|MIN_LIQUIDITY_USD|MAX_24H_CHANGE_FOR_ALERT|TRACK_INTERVAL_MIN)=" /opt/callsbotonchain/deployment/.env 2>/dev/null || echo "Settings not found"
else
  echo ".env file not found"
fi
echo ""

# 8. DISK & MEMORY
echo "8. SYSTEM RESOURCES"
echo "-------------------"
echo "Disk Usage:"
df -h / | tail -1
echo ""
echo "Memory Usage:"
free -h | grep Mem
echo ""
echo "Docker Container Resources:"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep callsbot
echo ""

# 9. RECENT ERRORS
echo "9. ERROR CHECK (Last 1000 Lines)"
echo "---------------------------------"
ERROR_COUNT=$(docker logs callsbot-worker --tail 1000 2>&1 | grep -iE 'exception|traceback|fatal|critical|error' | grep -v 'JSONDecodeError' | grep -v 'Telegram' | wc -l)
echo "Critical errors found: $ERROR_COUNT"
if [ "$ERROR_COUNT" -gt 0 ]; then
  echo "Recent errors:"
  docker logs callsbot-worker --tail 1000 2>&1 | grep -iE 'exception|traceback|fatal|critical|error' | grep -v 'JSONDecodeError' | grep -v 'Telegram' | tail -5
fi
echo ""

# 10. LOG FILES
echo "10. LOG FILES"
echo "-------------"
echo "Log directory: /opt/callsbotonchain/deployment/data/logs/"
ls -lh /opt/callsbotonchain/deployment/data/logs/ 2>/dev/null || echo "Log directory not found"
echo ""

# 11. GIT STATUS
echo "11. GIT STATUS"
echo "--------------"
cd /opt/callsbotonchain 2>/dev/null || cd /opt/callsbotonchain/deployment 2>/dev/null
echo "Current branch: $(git branch --show-current 2>/dev/null || echo 'N/A')"
echo "Last commit: $(git log -1 --oneline 2>/dev/null || echo 'N/A')"
echo "Git status:"
git status -s 2>/dev/null || echo "Not a git repository or git not available"
echo ""

# 12. NETWORK CONNECTIVITY
echo "12. NETWORK CONNECTIVITY"
echo "------------------------"
echo "Testing Cielo API:"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" 'https://feed-api.cielo.finance/api/v1/feed?limit=1' 2>/dev/null || echo "Failed to connect"
echo ""
echo "Testing Jupiter API:"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" 'https://quote-api.jup.ag/v6/quote?inputMint=So11111111111111111111111111111111111111112&outputMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&amount=1000000' 2>/dev/null || echo "Failed to connect"
echo ""

# SUMMARY
echo "=========================================="
echo "VALIDATION COMPLETE"
echo "=========================================="
echo ""
echo "Next Steps:"
echo "1. Review any errors or warnings above"
echo "2. Check that all containers are running"
echo "3. Verify signals are being generated"
echo "4. Monitor dashboard at https://callsbotonchain.com"
echo ""

