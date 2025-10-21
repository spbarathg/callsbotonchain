#!/bin/bash
# ========================================
# TRADER FIX VERIFICATION SCRIPT
# ========================================
# Monitors trader performance after deployment
# Run this periodically to check if fixes are working

SERVER="root@64.227.157.221"
CONTAINER="callsbot-trader"

echo "=================================================="
echo "📊 TRADER PERFORMANCE CHECK"
echo "=================================================="
echo "Time: $(date)"
echo ""

# Function to run command on server
run_remote() {
    ssh $SERVER "$1"
}

# 1. Check container health
echo "1️⃣ Container Health:"
run_remote "docker inspect $CONTAINER --format='{{.State.Health.Status}}' 2>/dev/null || echo 'No health check configured'"
run_remote "docker ps | grep $CONTAINER | awk '{print \$7}'"
echo ""

# 2. Count buy attempts vs successes (last hour)
echo "2️⃣ Execution Success Rate (last hour):"
BUY_ATTEMPTS=$(run_remote "docker logs --since 1h $CONTAINER 2>&1 | grep -c 'market_buy called' || echo 0")
BUY_SUCCESS=$(run_remote "docker logs --since 1h $CONTAINER 2>&1 | grep -c '✅ Transaction sent' || echo 0")
echo "   Attempts: $BUY_ATTEMPTS"
echo "   Successes: $BUY_SUCCESS"
if [ "$BUY_ATTEMPTS" -gt 0 ]; then
    SUCCESS_RATE=$(echo "scale=1; $BUY_SUCCESS * 100 / $BUY_ATTEMPTS" | bc)
    echo "   Success Rate: ${SUCCESS_RATE}%"
    
    if (( $(echo "$SUCCESS_RATE >= 80" | bc -l) )); then
        echo "   ✅ EXCELLENT (target: 80%+)"
    elif (( $(echo "$SUCCESS_RATE >= 60" | bc -l) )); then
        echo "   🟡 GOOD (target: 80%+)"
    else
        echo "   ❌ NEEDS IMPROVEMENT (target: 80%+)"
    fi
else
    echo "   ⏳ No buy attempts yet (wait for signals)"
fi
echo ""

# 3. Check Jupiter errors
echo "3️⃣ Jupiter Errors (last hour):"
ERROR_1789=$(run_remote "docker logs --since 1h $CONTAINER 2>&1 | grep -c '0x1789' || echo 0")
ERROR_6025=$(run_remote "docker logs --since 1h $CONTAINER 2>&1 | grep -c '6025' || echo 0")
TOTAL_ERRORS=$((ERROR_1789 + ERROR_6025))
echo "   Slippage errors (0x1789/6025): $TOTAL_ERRORS"

if [ "$TOTAL_ERRORS" -eq 0 ]; then
    echo "   ✅ NO ERRORS"
elif [ "$TOTAL_ERRORS" -lt 3 ] && [ "$BUY_ATTEMPTS" -gt 5 ]; then
    echo "   ✅ ACCEPTABLE (<20% error rate)"
else
    echo "   ⚠️ Still seeing errors - may need to increase slippage further"
fi
echo ""

# 4. Check open positions
echo "4️⃣ Open Positions:"
OPEN_POSITIONS=$(run_remote "docker logs --since 24h $CONTAINER 2>&1 | grep -c 'Position opened:' || echo 0")
echo "   Opened in last 24h: $OPEN_POSITIONS"
if [ "$OPEN_POSITIONS" -gt 0 ]; then
    echo "   ✅ Trader is executing!"
else
    echo "   ⏳ No positions yet (wait for score 8+ signals)"
fi
echo ""

# 5. Check stop loss exits
echo "5️⃣ Stop Loss Verification:"
STOP_EXITS=$(run_remote "docker logs --since 24h $CONTAINER 2>&1 | grep 'exit_stop' || echo 'No stop losses yet'")
if [[ "$STOP_EXITS" == *"exit_stop"* ]]; then
    echo "   Stop losses triggered:"
    run_remote "docker logs --since 24h $CONTAINER 2>&1 | grep 'exit_stop' | tail -3"
    echo "   ℹ️ Verify losses are -15% (check logs above)"
else
    echo "   No stop losses triggered yet"
fi
echo ""

# 6. Check win rate (if any closed positions)
echo "6️⃣ Win Rate (if positions closed):"
run_remote "docker exec $CONTAINER python3 -c '
import sqlite3
import os
db_path = os.getenv(\"TS_DB_PATH\", \"var/trading.db\")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.execute(\"SELECT COUNT(*) FROM positions WHERE status=\\\"closed\\\"\")
    closed = cur.fetchone()[0]
    if closed > 0:
        cur = conn.execute(\"\"\"
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) as winners,
                AVG(CASE WHEN pnl_pct > 0 THEN pnl_pct ELSE NULL END) as avg_win,
                AVG(CASE WHEN pnl_pct < 0 THEN pnl_pct ELSE NULL END) as avg_loss
            FROM positions WHERE status=\\\"closed\\\"
        \"\"\")
        result = cur.fetchone()
        total, winners, avg_win, avg_loss = result
        wr = (winners/total*100) if total > 0 else 0
        print(f\"   Total closed: {total}\")
        print(f\"   Winners: {winners}\")
        print(f\"   Win rate: {wr:.1f}%\")
        if avg_win:
            print(f\"   Avg win: +{avg_win:.1f}%\")
        if avg_loss:
            print(f\"   Avg loss: {avg_loss:.1f}%\")
        
        # Verify targets
        if wr >= 30 and wr <= 45:
            print(\"   ✅ Win rate in target range (30-40%)\")
        elif wr > 0:
            print(f\"   ⏳ Win rate outside target (need more data)\")
            
        if avg_loss and avg_loss >= -16 and avg_loss <= -14:
            print(\"   ✅ Stop loss working perfectly (-15%)\")
        elif avg_loss and avg_loss < -20:
            print(\"   ❌ Stop loss not working (losses too large)\")
    else:
        print(\"   No closed positions yet\")
    conn.close()
else:
    print(\"   Trading database not found\")
' 2>/dev/null || echo '   Unable to query database'"
echo ""

# 7. Recent log sample
echo "7️⃣ Recent Activity (last 10 lines):"
run_remote "docker logs --tail 10 $CONTAINER 2>&1"
echo ""

echo "=================================================="
echo "📈 SUMMARY"
echo "=================================================="
echo ""
echo "Key Metrics:"
echo "  - Execution Success: Check #2 above (target: 80%+)"
echo "  - Jupiter Errors: Check #3 above (target: <20%)"
echo "  - Positions Opened: Check #4 above"
echo "  - Win Rate: Check #6 above (target: 30-40%)"
echo ""
echo "Next Check: Run this script again in 1-2 hours"
echo "Full Logs: ssh root@64.227.157.221 'docker logs -f $CONTAINER'"
echo "=================================================="


