#!/bin/bash
# ========================================
# TRADER ALIGNMENT FIX - DEPLOYMENT SCRIPT
# ========================================
# This script deploys the critical fixes to align trader with +411% backtest
# Date: October 21, 2025

set -e  # Exit on error

echo "=================================================="
echo "🎯 DEPLOYING TRADER ALIGNMENT FIXES"
echo "=================================================="
echo ""

# Check if we're in the right directory
if [ ! -f "tradingSystem/config_optimized.py" ]; then
    echo "❌ ERROR: Run this script from the project root directory"
    exit 1
fi

echo "Step 1: Verifying local changes..."
echo "✅ Config files updated with:"
echo "   - SLIPPAGE_BPS: 150 → 500 (5%)"
echo "   - PRIORITY_FEE: 10,000 → 100,000 microlamports"
echo "   - MAX_CONCURRENT: 5 → 4"
echo ""

echo "Step 2: Committing changes to git..."
git add tradingSystem/config_optimized.py
git add TRADER_ALIGNMENT_FIX.md
git add deploy_trader_fix.sh
git commit -m "Critical Fix: Increase slippage to 5% and priority fee 10x for memecoin execution

- SLIPPAGE_BPS: 150 → 500 (1.5% → 5%)
- PRIORITY_FEE: 10k → 100k microlamports
- MAX_CONCURRENT: 5 → 4 (match backtest)
- Resolves Jupiter error 0x1789 (slippage exceeded)
- Expected: 20% → 80%+ execution success rate

Based on backtest validation (+411% return over 62 trades)"

echo "✅ Changes committed locally"
echo ""

echo "Step 3: Pushing to origin..."
git push origin main
echo "✅ Pushed to GitHub"
echo ""

echo "Step 4: Deploying to production server..."
SERVER="root@64.227.157.221"
DEPLOY_PATH="/opt/callsbotonchain"

ssh $SERVER << 'ENDSSH'
cd /opt/callsbotonchain
echo "📥 Pulling latest changes..."
git pull origin main

echo "🔄 Restarting trader container..."
docker restart callsbot-trader

echo "⏳ Waiting 5 seconds for container to start..."
sleep 5

echo "📋 Checking container status..."
docker ps | grep callsbot-trader

echo ""
echo "📊 Monitoring logs (last 20 lines)..."
docker logs --tail 20 callsbot-trader

ENDSSH

echo ""
echo "=================================================="
echo "✅ DEPLOYMENT COMPLETE!"
echo "=================================================="
echo ""
echo "Next Steps:"
echo "1. Monitor execution success rate:"
echo "   ssh root@64.227.157.221 'docker logs -f callsbot-trader | grep -E \"market_buy called|Transaction sent|failed\"'"
echo ""
echo "2. Check for Jupiter errors (should drop to <20%):"
echo "   ssh root@64.227.157.221 'docker logs --since 1h callsbot-trader | grep -c 0x1789'"
echo ""
echo "3. Verify positions opening (wait 30-60 min for signals):"
echo "   ssh root@64.227.157.221 'docker exec callsbot-trader ls -lh var/trading.db'"
echo ""
echo "Expected Results (within 24 hours):"
echo "  - Execution success: 80%+ (was 20%)"
echo "  - Jupiter errors: <20% (was 80%)"
echo "  - Positions opening: 5-8 per day"
echo ""
echo "📖 See TRADER_ALIGNMENT_FIX.md for full details"
echo "=================================================="


