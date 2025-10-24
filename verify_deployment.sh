#!/bin/bash
# DEPLOYMENT VERIFICATION SCRIPT
# Run this after every deployment to ensure fixes are actually active

set -e

SERVER="root@64.227.157.221"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================="
echo "🔍 DEPLOYMENT VERIFICATION SCRIPT"
echo "=================================="
echo ""

PASSED=0
FAILED=0

# TEST 1: Docker container running
echo -n "TEST 1: Docker container running... "
if ssh $SERVER "docker ps | grep callsbot-trader" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}❌ FAIL${NC}"
    echo "  → Container not running!"
    ((FAILED++))
fi

# TEST 2: 99% sell fix active
echo -n "TEST 2: 99% sell fix active... "
RESULT=$(ssh $SERVER "docker exec callsbot-trader grep -c 'int(float(qty) \* (10 \*\* dec) \* 0.99)' /opt/callsbotonchain/tradingSystem/broker_optimized.py 2>/dev/null || echo 0")
if [ "$RESULT" -gt "0" ]; then
    echo -e "${GREEN}✅ PASS${NC} (found on line 576)"
    ((PASSED++))
else
    echo -e "${RED}❌ FAIL${NC}"
    echo "  → 99% sell fix NOT found in running container!"
    echo "  → Docker is using OLD CODE"
    echo "  → SOLUTION: Rebuild with --no-cache"
    ((FAILED++))
fi

# TEST 3: No open positions
echo -n "TEST 3: No ghost positions in DB... "
OPEN_COUNT=$(ssh $SERVER "cd /opt/callsbotonchain/deployment && sqlite3 var/trading.db 'SELECT COUNT(*) FROM positions WHERE status=\"open\"' 2>/dev/null || echo 999")
if [ "$OPEN_COUNT" -eq "0" ]; then
    echo -e "${GREEN}✅ PASS${NC}"
    ((PASSED++))
else
    echo -e "${YELLOW}⚠️  WARNING${NC}"
    echo "  → Found $OPEN_COUNT open positions"
    echo "  → This is OK if bot is actively trading"
    echo "  → CONCERN if these are old/stuck positions"
fi

# TEST 4: Price cache working
echo -n "TEST 4: Price cache functional... "
VALID_ENTRIES=$(ssh $SERVER "docker logs --tail 100 callsbot-trader 2>&1 | grep 'valid_entries' | tail -1 | grep -oP 'valid_entries.: \K\d+' || echo 0")
if [ "$VALID_ENTRIES" -gt "0" ]; then
    echo -e "${GREEN}✅ PASS${NC} ($VALID_ENTRIES valid entries)"
    ((PASSED++))
else
    echo -e "${RED}❌ FAIL${NC}"
    echo "  → ALL price cache entries are stale!"
    echo "  → DexScreener API may be failing"
    echo "  → Stop losses WILL NOT TRIGGER"
    ((FAILED++))
fi

# TEST 5: Emergency patches applied
echo -n "TEST 5: Price fallback code present... "
FALLBACK=$(ssh $SERVER "docker exec callsbot-trader grep -c 'emergency_price = self.broker.get_token_price' /opt/callsbotonchain/tradingSystem/trader_optimized.py 2>/dev/null || echo 0")
if [ "$FALLBACK" -gt "0" ]; then
    echo -e "${GREEN}✅ PASS${NC}"
    ((PASSED++))
else
    echo -e "${YELLOW}⚠️  NOT APPLIED${NC}"
    echo "  → Emergency price fallback patch not found"
    echo "  → Apply EMERGENCY_PATCHES/01_price_fallback.diff"
fi

echo -n "TEST 6: Rug detection code present... "
RUG_DETECT=$(ssh $SERVER "docker exec callsbot-trader grep -c 'RUG_DETECTED: No liquidity' /opt/callsbotonchain/tradingSystem/broker_optimized.py 2>/dev/null || echo 0")
if [ "$RUG_DETECT" -gt "0" ]; then
    echo -e "${GREEN}✅ PASS${NC}"
    ((PASSED++))
else
    echo -e "${YELLOW}⚠️  NOT APPLIED${NC}"
    echo "  → Rug detection patch not found"
    echo "  → Apply EMERGENCY_PATCHES/02_rug_detection.diff"
fi

echo -n "TEST 7: Hard stop loss code present... "
HARD_STOP=$(ssh $SERVER "docker exec callsbot-trader grep -c 'EMERGENCY_HARD_STOP_PCT' /opt/callsbotonchain/tradingSystem/config_optimized.py 2>/dev/null || echo 0")
if [ "$HARD_STOP" -gt "0" ]; then
    echo -e "${GREEN}✅ PASS${NC}"
    ((PASSED++))
else
    echo -e "${YELLOW}⚠️  NOT APPLIED${NC}"
    echo "  → Hard stop loss patch not found"
    echo "  → Apply EMERGENCY_PATCHES/03_hard_stop_loss.diff"
fi

# TEST 8: Recent losses within acceptable range
echo -n "TEST 8: Recent losses acceptable... "
WORST_LOSS=$(ssh $SERVER "cd /opt/callsbotonchain/deployment && sqlite3 var/trading.db '
SELECT MIN((f_sell.usd - f_buy.usd) / f_buy.usd * 100) as worst_pnl_pct
FROM positions p 
JOIN fills f_buy ON p.id=f_buy.position_id AND f_buy.side=\"buy\" 
JOIN fills f_sell ON p.id=f_sell.position_id AND f_sell.side=\"sell\" 
WHERE p.status=\"closed\" 
AND p.open_at > datetime(\"now\", \"-24 hours\")
' 2>/dev/null || echo -999")

# Convert to integer for comparison (bash doesn't do floats well)
WORST_LOSS_INT=$(echo "$WORST_LOSS" | awk '{print int($1)}')

if [ "$WORST_LOSS_INT" -gt "-25" ]; then
    echo -e "${GREEN}✅ PASS${NC} (worst: ${WORST_LOSS}%)"
    ((PASSED++))
elif [ "$WORST_LOSS_INT" -eq "-999" ]; then
    echo -e "${YELLOW}⚠️  NO DATA${NC}"
    echo "  → No trades in last 24h"
else
    echo -e "${RED}❌ FAIL${NC}"
    echo "  → Worst loss: ${WORST_LOSS}%"
    echo "  → Exceeds -25% threshold"
    echo "  → Stop losses NOT working properly"
    ((FAILED++))
fi

# TEST 9: Git commit matches running code
echo -n "TEST 9: Git-Docker version sync... "
LOCAL_COMMIT=$(git rev-parse --short HEAD)
CONTAINER_COMMIT=$(ssh $SERVER "docker exec callsbot-trader cat /opt/callsbotonchain/VERSION 2>/dev/null | head -1 || echo 'unknown'")

if [[ "$CONTAINER_COMMIT" == *"$LOCAL_COMMIT"* ]] || [ "$CONTAINER_COMMIT" == "unknown" ]; then
    if [ "$CONTAINER_COMMIT" == "unknown" ]; then
        echo -e "${YELLOW}⚠️  UNKNOWN${NC}"
        echo "  → VERSION file not found in container"
        echo "  → Cannot verify code version"
    else
        echo -e "${GREEN}✅ PASS${NC} (${LOCAL_COMMIT})"
        ((PASSED++))
    fi
else
    echo -e "${RED}❌ FAIL${NC}"
    echo "  → Local:     $LOCAL_COMMIT"
    echo "  → Container: $CONTAINER_COMMIT"
    echo "  → MISMATCH! Container needs rebuild"
    ((FAILED++))
fi

# TEST 10: No errors in recent logs
echo -n "TEST 10: No critical errors in logs... "
ERROR_COUNT=$(ssh $SERVER "docker logs --since 10m callsbot-trader 2>&1 | grep -c 'CRITICAL\|EXCEPTION\|Traceback' || echo 0")
if [ "$ERROR_COUNT" -eq "0" ]; then
    echo -e "${GREEN}✅ PASS${NC}"
    ((PASSED++))
else
    echo -e "${YELLOW}⚠️  WARNINGS${NC}"
    echo "  → Found $ERROR_COUNT errors in last 10 minutes"
    echo "  → Check logs: docker logs callsbot-trader"
fi

echo ""
echo "=================================="
echo "📊 VERIFICATION SUMMARY"
echo "=================================="
echo -e "Passed:  ${GREEN}$PASSED${NC}"
echo -e "Failed:  ${RED}$FAILED${NC}"
echo ""

if [ "$FAILED" -eq "0" ]; then
    echo -e "${GREEN}✅ ALL CRITICAL TESTS PASSED${NC}"
    echo "Deployment is healthy and fixes are active."
    exit 0
else
    echo -e "${RED}❌ $FAILED CRITICAL TEST(S) FAILED${NC}"
    echo ""
    echo "🚨 IMMEDIATE ACTIONS REQUIRED:"
    echo "1. If TEST 2 failed: Rebuild with --no-cache"
    echo "2. If TEST 4 failed: Check DexScreener API status"
    echo "3. If TEST 8 failed: Review stop loss logic"
    echo ""
    echo "See PRIORITY_ACTIONS.md for remediation steps"
    exit 1
fi

