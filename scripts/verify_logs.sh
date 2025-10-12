#!/bin/bash
# Log Verification Script
# Ensures logs are being written to the correct location

set -e

echo "=================================================="
echo "📋 LOG VERIFICATION SCRIPT"
echo "=================================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Correct log directory
ACTIVE_LOGS="/opt/callsbotonchain/deployment/data/logs"
OLD_LOGS="/opt/callsbotonchain/data/logs"

echo "🔍 Checking log directories..."
echo ""

# Check active logs
echo "✅ ACTIVE LOGS: $ACTIVE_LOGS"
if [ -d "$ACTIVE_LOGS" ]; then
    echo -e "${GREEN}   Directory exists${NC}"
    echo "   Files:"
    ls -lh "$ACTIVE_LOGS" | grep -v "^total" | grep -v "README" | awk '{printf "   - %-20s %8s  %s %s %s\n", $9, $5, $6, $7, $8}'
    echo ""
    
    # Check if files are being updated
    echo "   Recent activity:"
    STDOUT_AGE=$(find "$ACTIVE_LOGS/stdout.log" -mmin +5 2>/dev/null && echo "OLD" || echo "RECENT")
    if [ "$STDOUT_AGE" = "RECENT" ]; then
        echo -e "   ${GREEN}✓ stdout.log updated in last 5 minutes${NC}"
    else
        echo -e "   ${YELLOW}⚠ stdout.log not updated recently${NC}"
    fi
    
    PROCESS_AGE=$(find "$ACTIVE_LOGS/process.jsonl" -mmin +5 2>/dev/null && echo "OLD" || echo "RECENT")
    if [ "$PROCESS_AGE" = "RECENT" ]; then
        echo -e "   ${GREEN}✓ process.jsonl updated in last 5 minutes${NC}"
    else
        echo -e "   ${YELLOW}⚠ process.jsonl not updated recently${NC}"
    fi
else
    echo -e "${RED}   Directory does not exist!${NC}"
fi

echo ""
echo "---"
echo ""

# Check old logs
echo "❌ OLD LOGS (DEPRECATED): $OLD_LOGS"
if [ -d "$OLD_LOGS" ]; then
    FILE_COUNT=$(ls -1 "$OLD_LOGS" 2>/dev/null | grep -v "README" | wc -l)
    if [ "$FILE_COUNT" -eq 0 ]; then
        echo -e "${GREEN}   ✓ Directory is empty (correct)${NC}"
    else
        echo -e "${YELLOW}   ⚠ Contains $FILE_COUNT old files${NC}"
        ls -lh "$OLD_LOGS" | grep -v "^total" | grep -v "README" | awk '{printf "   - %-20s %8s  %s %s %s\n", $9, $5, $6, $7, $8}'
    fi
else
    echo -e "${GREEN}   Directory does not exist (OK)${NC}"
fi

echo ""
echo "=================================================="
echo "🐳 DOCKER CONTAINER STATUS"
echo "=================================================="
echo ""

docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep callsbot || echo "No containers running"

echo ""
echo "=================================================="
echo "📊 LOG CONTENT SAMPLES"
echo "=================================================="
echo ""

# Show last few lines of stdout.log
if [ -f "$ACTIVE_LOGS/stdout.log" ]; then
    echo "Last 5 lines of stdout.log:"
    tail -n 5 "$ACTIVE_LOGS/stdout.log" | sed 's/^/  /'
    echo ""
fi

# Show last alert
if [ -f "$ACTIVE_LOGS/alerts.jsonl" ]; then
    echo "Last alert:"
    tail -n 1 "$ACTIVE_LOGS/alerts.jsonl" | jq -r '  "  Token: " + .symbol + " (" + .token[0:8] + "...)"' 2>/dev/null || tail -n 1 "$ACTIVE_LOGS/alerts.jsonl" | sed 's/^/  /'
    echo ""
fi

echo "=================================================="
echo "🌐 API HEALTH CHECK"
echo "=================================================="
echo ""

# Check API via Caddy
API_RESPONSE=$(curl -s http://localhost/api/v2/quick-stats 2>/dev/null || echo "ERROR")
if [ "$API_RESPONSE" != "ERROR" ]; then
    echo -e "${GREEN}✓ API is accessible${NC}"
    echo "$API_RESPONSE" | jq '.' 2>/dev/null || echo "$API_RESPONSE"
else
    echo -e "${RED}✗ API is not accessible${NC}"
fi

echo ""
echo "=================================================="
echo "✅ VERIFICATION COMPLETE"
echo "=================================================="
echo ""
echo "📖 For more information, see:"
echo "   /opt/callsbotonchain/LOG_LOCATIONS.md"
echo ""

