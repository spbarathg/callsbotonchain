#!/bin/bash

# Security Fixes Verification Script
# Tests all 4 security fixes to ensure they're working correctly

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0
WARNINGS=0

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Security Fixes Verification Script                    ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Function to print test result
print_result() {
    local test_name="$1"
    local result="$2"
    local message="$3"
    
    if [ "$result" = "PASS" ]; then
        echo -e "${GREEN}✓${NC} $test_name: ${GREEN}PASSED${NC}"
        [ -n "$message" ] && echo -e "  ${message}"
        ((PASSED++))
    elif [ "$result" = "FAIL" ]; then
        echo -e "${RED}✗${NC} $test_name: ${RED}FAILED${NC}"
        [ -n "$message" ] && echo -e "  ${RED}${message}${NC}"
        ((FAILED++))
    else
        echo -e "${YELLOW}⚠${NC} $test_name: ${YELLOW}WARNING${NC}"
        [ -n "$message" ] && echo -e "  ${YELLOW}${message}${NC}"
        ((WARNINGS++))
    fi
}

# Get credentials from .env if available
if [ -f "deployment/.env" ]; then
    source deployment/.env
fi

# Prompt for credentials if not set
if [ -z "$DASHBOARD_USERNAME" ]; then
    read -p "Enter dashboard username (default: admin): " DASHBOARD_USERNAME
    DASHBOARD_USERNAME=${DASHBOARD_USERNAME:-admin}
fi

if [ -z "$DASHBOARD_PASSWORD" ]; then
    read -sp "Enter dashboard password: " DASHBOARD_PASSWORD
    echo ""
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Test 1: Container Health${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

# Check if all containers are running
CONTAINERS=("callsbot-web" "callsbot-tracker" "callsbot-trader" "callsbot-worker" "callsbot-redis" "callsbot-proxy")
ALL_RUNNING=true

for container in "${CONTAINERS[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        print_result "$container" "PASS" "Running"
    else
        print_result "$container" "FAIL" "Not running"
        ALL_RUNNING=false
    fi
done

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Test 2: HTTPS Enforcement${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

# Test HTTP redirect
HTTP_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1/ 2>/dev/null || echo "000")
if [ "$HTTP_RESPONSE" = "301" ] || [ "$HTTP_RESPONSE" = "308" ]; then
    print_result "HTTP to HTTPS redirect" "PASS" "HTTP $HTTP_RESPONSE redirect working"
elif [ "$HTTP_RESPONSE" = "000" ]; then
    print_result "HTTP to HTTPS redirect" "WARN" "Could not connect to HTTP port"
else
    print_result "HTTP to HTTPS redirect" "FAIL" "Expected 301/308, got $HTTP_RESPONSE"
fi

# Test HTTPS is accessible
HTTPS_RESPONSE=$(curl -k -s -o /dev/null -w "%{http_code}" https://127.0.0.1/ 2>/dev/null || echo "000")
if [ "$HTTPS_RESPONSE" = "401" ] || [ "$HTTPS_RESPONSE" = "200" ]; then
    print_result "HTTPS accessible" "PASS" "HTTPS responding (HTTP $HTTPS_RESPONSE)"
elif [ "$HTTPS_RESPONSE" = "000" ]; then
    print_result "HTTPS accessible" "FAIL" "Could not connect to HTTPS port"
else
    print_result "HTTPS accessible" "WARN" "Unexpected response: $HTTPS_RESPONSE"
fi

# Check security headers
HEADERS=$(curl -k -s -I https://127.0.0.1/ 2>/dev/null || echo "")
if echo "$HEADERS" | grep -qi "Strict-Transport-Security"; then
    print_result "HSTS header" "PASS" "Strict-Transport-Security present"
else
    print_result "HSTS header" "WARN" "HSTS header not found"
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Test 3: Authentication${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

# Test without credentials
NO_AUTH_RESPONSE=$(curl -k -s -o /dev/null -w "%{http_code}" https://127.0.0.1/ 2>/dev/null || echo "000")
if [ "$NO_AUTH_RESPONSE" = "401" ]; then
    print_result "Unauthorized access blocked" "PASS" "Returns 401 without credentials"
elif [ "$NO_AUTH_RESPONSE" = "200" ]; then
    print_result "Unauthorized access blocked" "WARN" "Authentication may be disabled"
else
    print_result "Unauthorized access blocked" "FAIL" "Expected 401, got $NO_AUTH_RESPONSE"
fi

# Test with credentials
if [ -n "$DASHBOARD_PASSWORD" ]; then
    AUTH_RESPONSE=$(curl -k -s -o /dev/null -w "%{http_code}" -u "$DASHBOARD_USERNAME:$DASHBOARD_PASSWORD" https://127.0.0.1/ 2>/dev/null || echo "000")
    if [ "$AUTH_RESPONSE" = "200" ]; then
        print_result "Authorized access" "PASS" "Login successful with credentials"
    elif [ "$AUTH_RESPONSE" = "401" ]; then
        print_result "Authorized access" "FAIL" "Login failed - check credentials"
    else
        print_result "Authorized access" "WARN" "Unexpected response: $AUTH_RESPONSE"
    fi
    
    # Test API endpoint
    API_RESPONSE=$(curl -k -s -u "$DASHBOARD_USERNAME:$DASHBOARD_PASSWORD" https://127.0.0.1/api/v2/quick-stats 2>/dev/null || echo "")
    if echo "$API_RESPONSE" | grep -q "total_signals\|total_alerts"; then
        print_result "API endpoint" "PASS" "API returning valid data"
    else
        print_result "API endpoint" "WARN" "API response unexpected"
    fi
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Test 4: Tracker Format Fix${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

# Check tracker logs for format errors
TRACKER_ERRORS=$(docker logs callsbot-tracker --tail 100 2>&1 | grep -i "unsupported format string\|NoneType.__format__" | wc -l)
if [ "$TRACKER_ERRORS" -eq 0 ]; then
    print_result "No format errors" "PASS" "No format errors in last 100 log lines"
else
    print_result "No format errors" "FAIL" "Found $TRACKER_ERRORS format errors in logs"
fi

# Check if tracker is running
TRACKER_RUNNING=$(docker logs callsbot-tracker --tail 20 2>&1 | grep -i "tracking\|updating\|processing" | wc -l)
if [ "$TRACKER_RUNNING" -gt 0 ]; then
    print_result "Tracker active" "PASS" "Tracker is processing data"
else
    print_result "Tracker active" "WARN" "No recent tracker activity"
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Test 5: Database Cleanup${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

# Check if cleanup script exists
if [ -f "scripts/cleanup_database.py" ]; then
    print_result "Cleanup script exists" "PASS" "scripts/cleanup_database.py found"
else
    print_result "Cleanup script exists" "FAIL" "scripts/cleanup_database.py not found"
fi

# Check if cron job is installed
if crontab -l 2>/dev/null | grep -q "cleanup_database.py"; then
    CRON_SCHEDULE=$(crontab -l 2>/dev/null | grep "cleanup_database.py" | awk '{print $1, $2, $3, $4, $5}')
    print_result "Cleanup cron job" "PASS" "Scheduled: $CRON_SCHEDULE"
else
    print_result "Cleanup cron job" "WARN" "Cron job not installed - run setup_cleanup_cron.sh"
fi

# Test cleanup script (dry run)
if [ -f "scripts/cleanup_database.py" ]; then
    CLEANUP_TEST=$(python3 scripts/cleanup_database.py --dry-run 2>&1 || echo "ERROR")
    if echo "$CLEANUP_TEST" | grep -q "Would delete\|No old snapshots"; then
        print_result "Cleanup script works" "PASS" "Dry run successful"
    else
        print_result "Cleanup script works" "WARN" "Dry run had issues"
    fi
fi

# Check database size
if [ -f "var/callsbot.db" ]; then
    DB_SIZE=$(du -h var/callsbot.db | awk '{print $1}')
    print_result "Database size" "PASS" "Current size: $DB_SIZE"
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Test 6: Bot Functionality${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

# Check if bot is processing signals
if [ -n "$DASHBOARD_PASSWORD" ]; then
    STATS=$(curl -k -s -u "$DASHBOARD_USERNAME:$DASHBOARD_PASSWORD" https://127.0.0.1/api/v2/quick-stats 2>/dev/null || echo "{}")
    
    TOTAL_SIGNALS=$(echo "$STATS" | grep -o '"total_signals":[0-9]*' | grep -o '[0-9]*' || echo "0")
    TOTAL_ALERTS=$(echo "$STATS" | grep -o '"total_alerts":[0-9]*' | grep -o '[0-9]*' || echo "0")
    TRACKED_TOKENS=$(echo "$STATS" | grep -o '"tracked_tokens":[0-9]*' | grep -o '[0-9]*' || echo "0")
    
    if [ "$TOTAL_SIGNALS" -gt 0 ]; then
        print_result "Signal processing" "PASS" "$TOTAL_SIGNALS signals processed"
    else
        print_result "Signal processing" "WARN" "No signals processed yet"
    fi
    
    if [ "$TOTAL_ALERTS" -gt 0 ]; then
        print_result "Alert generation" "PASS" "$TOTAL_ALERTS alerts generated"
    else
        print_result "Alert generation" "WARN" "No alerts generated yet"
    fi
    
    if [ "$TRACKED_TOKENS" -gt 0 ]; then
        print_result "Token tracking" "PASS" "$TRACKED_TOKENS tokens tracked"
    else
        print_result "Token tracking" "WARN" "No tokens being tracked"
    fi
fi

# Check worker logs
WORKER_ERRORS=$(docker logs callsbot-worker --tail 50 2>&1 | grep -i "error\|exception\|failed" | grep -v "No error" | wc -l)
if [ "$WORKER_ERRORS" -eq 0 ]; then
    print_result "Worker errors" "PASS" "No errors in last 50 log lines"
else
    print_result "Worker errors" "WARN" "Found $WORKER_ERRORS error messages"
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Summary${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

TOTAL=$((PASSED + FAILED + WARNINGS))
echo -e "Total Tests: $TOTAL"
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo -e "${YELLOW}Warnings: $WARNINGS${NC}"

echo ""

if [ $FAILED -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✓ ALL TESTS PASSED - Security fixes working perfectly!   ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    exit 0
elif [ $FAILED -eq 0 ]; then
    echo -e "${YELLOW}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║  ⚠ TESTS PASSED WITH WARNINGS - Review warnings above     ║${NC}"
    echo -e "${YELLOW}╚════════════════════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${RED}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ✗ SOME TESTS FAILED - Review failures above              ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════╝${NC}"
    exit 1
fi