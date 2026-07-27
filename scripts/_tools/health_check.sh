#!/bin/bash
# Quick health check for trading bot
# Usage: ssh root@64.227.157.221 "bash /opt/callsbotonchain/scripts/health_check.sh"

echo "=========================================="
echo "🏥 TRADING BOT HEALTH CHECK"
echo "=========================================="
echo ""

# Container status
echo "📦 CONTAINER STATUS:"
docker ps --filter "name=callsbot" --format "table {{.Names}}\t{{.Status}}\t{{.RunningFor}}"
echo ""

# Worker - Signal Detection
echo "🔍 WORKER BOT (Last 10 signals):"
docker logs callsbot-worker 2>&1 | grep -E "scored [7-9]|scored 10" | tail -10 | sed 's/^/  /'
echo ""

# Trader - Watch List
echo "👀 WATCH LIST (Active tracking):"
docker logs callsbot-trader 2>&1 | grep "➕ Added" | tail -10 | sed 's/^/  /'
echo ""

# Open Positions
echo "💼 OPEN POSITIONS:"
docker logs callsbot-trader 2>&1 | grep "open_positions" | tail -1 | sed 's/^/  /'
echo ""

# Wallet Balance
echo "💰 WALLET BALANCE:"
docker logs callsbot-trader 2>&1 | grep "Balance:.*SOL" | tail -1 | sed 's/^/  /'
echo ""

# Recent Rejections
echo "🚫 RECENT REJECTIONS (Last 5):"
docker logs callsbot-trader 2>&1 | grep -E "too young|dump detected|VALIDATOR.*❌" | tail -5 | sed 's/^/  /'
echo ""

# Watch Monitor Status
echo "📊 BACKGROUND MONITOR:"
docker logs callsbot-trader 2>&1 | grep "WATCH_MONITOR" | tail -2 | sed 's/^/  /'
echo ""

# Exit Loop Status  
echo "🔄 EXIT LOOP:"
docker logs callsbot-trader 2>&1 | grep "EXIT_LOOP.*Status check" | tail -1 | sed 's/^/  /'
echo ""

echo "=========================================="
echo "✅ Health check complete!"
echo "=========================================="

