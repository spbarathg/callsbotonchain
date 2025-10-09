#!/usr/bin/env bash
set -e

echo "================================================================================"
echo "🛡️  BULLETPROOF TRADING SYSTEM DEPLOYMENT"
echo "================================================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SERVER="root@64.227.157.221"
REMOTE_DIR="/opt/callsbotonchain/deployment"
LOCAL_DIR="$(pwd)"

echo "📋 Pre-deployment checklist:"
echo ""
read -p "Have you reviewed BULLETPROOF_TRADING_SYSTEM.md? (yes/no): " reviewed
if [ "$reviewed" != "yes" ]; then
    echo "❌ Please review the documentation first!"
    exit 1
fi

read -p "Are you ready to deploy the bulletproof system? (yes/no): " ready
if [ "$ready" != "yes" ]; then
    echo "❌ Deployment cancelled"
    exit 1
fi

echo ""
echo "${YELLOW}Step 1: Backing up current system on server...${NC}"
ssh $SERVER "cd $REMOTE_DIR && cp -r tradingSystem tradingSystem.backup.$(date +%Y%m%d_%H%M%S)"
echo "${GREEN}✅ Backup created${NC}"

echo ""
echo "${YELLOW}Step 2: Uploading bulletproof modules...${NC}"
scp tradingSystem/broker_safe.py $SERVER:$REMOTE_DIR/tradingSystem/broker_safe.py
scp tradingSystem/trader_safe.py $SERVER:$REMOTE_DIR/tradingSystem/trader_safe.py
scp tradingSystem/strategy_safe.py $SERVER:$REMOTE_DIR/tradingSystem/strategy_safe.py
scp tradingSystem/cli_safe.py $SERVER:$REMOTE_DIR/tradingSystem/cli_safe.py
echo "${GREEN}✅ Files uploaded${NC}"

echo ""
echo "${YELLOW}Step 3: Creating deployment script on server...${NC}"
ssh $SERVER "cat > $REMOTE_DIR/activate_bulletproof.sh << 'EOF'
#!/usr/bin/env bash
set -e

cd $REMOTE_DIR/tradingSystem

echo \"Deploying bulletproof system...\"

# Replace old modules with safe versions
cp broker_safe.py broker.py
cp trader_safe.py trader.py
cp strategy_safe.py strategy.py
cp cli_safe.py cli.py

echo \"✅ Bulletproof modules activated\"

# Restart trader in dry-run mode
cd $REMOTE_DIR
docker compose restart trader

echo \"✅ Trader restarted in DRY-RUN mode\"
echo \"\"
echo \"Monitor logs with: docker logs -f callsbot-trader\"
EOF
chmod +x $REMOTE_DIR/activate_bulletproof.sh"
echo "${GREEN}✅ Deployment script created${NC}"

echo ""
echo "${YELLOW}Step 4: Activating bulletproof system...${NC}"
read -p "Continue with activation? (yes/no): " activate
if [ "$activate" != "yes" ]; then
    echo "❌ Activation cancelled. Files uploaded but not activated."
    echo "To activate later, run on server: $REMOTE_DIR/activate_bulletproof.sh"
    exit 0
fi

ssh $SERVER "$REMOTE_DIR/activate_bulletproof.sh"
echo "${GREEN}✅ System activated${NC}"

echo ""
echo "${YELLOW}Step 5: Verifying deployment...${NC}"
sleep 5
echo "Checking trader logs..."
ssh $SERVER "docker logs callsbot-trader --tail 30"

echo ""
echo "================================================================================"
echo "${GREEN}✅ DEPLOYMENT COMPLETE${NC}"
echo "================================================================================"
echo ""
echo "📊 Next steps:"
echo "1. Monitor logs: ssh $SERVER 'docker logs -f callsbot-trader'"
echo "2. Check for errors: ssh $SERVER \"docker logs callsbot-trader | grep '⚠️\\|❌\\|🚨'\""
echo "3. Let run in DRY-RUN for 24 hours"
echo "4. Review BULLETPROOF_TRADING_SYSTEM.md for live trading checklist"
echo ""
echo "⚠️  IMPORTANT: System is in DRY-RUN mode (no real trades)"
echo "To enable live trading, follow steps in BULLETPROOF_TRADING_SYSTEM.md"
echo ""

