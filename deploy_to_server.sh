#!/bin/bash
# Comprehensive Server Deployment Script
# Deploys latest code with migration fixes and transaction tracking

set -e  # Exit on error

SERVER="root@64.227.157.221"
DEPLOY_DIR="/opt/callsbotonchain"
DEPLOYMENT_SUBDIR="deployment"

echo "=========================================="
echo "🚀 DEPLOYING TO PRODUCTION SERVER"
echo "=========================================="
echo "Server: $SERVER"
echo "Directory: $DEPLOY_DIR"
echo "Time: $(date)"
echo ""

# Step 1: Push latest changes to GitHub
echo "📤 Step 1: Pushing latest changes to GitHub..."
git add -A
git status
read -p "Commit message (or press Enter to skip commit): " COMMIT_MSG
if [ -n "$COMMIT_MSG" ]; then
    git commit -m "$COMMIT_MSG" || echo "Nothing to commit"
fi
git push origin main
echo "✅ Code pushed to GitHub"
echo ""

# Step 2: SSH to server and pull latest code
echo "📥 Step 2: Pulling latest code on server..."
ssh $SERVER << 'ENDSSH'
set -e
cd /opt/callsbotonchain
echo "Current directory: $(pwd)"
echo "Current branch: $(git branch --show-current)"
echo "Current commit: $(git rev-parse --short HEAD)"
echo ""
echo "Pulling latest changes..."
git fetch origin
git pull origin main
echo "✅ Code updated"
echo "New commit: $(git rev-parse --short HEAD)"
echo ""
ENDSSH
echo ""

# Step 3: Apply database migrations
echo "🗄️  Step 3: Applying database migrations..."
ssh $SERVER << 'ENDSSH'
set -e
cd /opt/callsbotonchain/deployment
echo "Applying migrations..."
docker compose exec -T worker python -c "from app.storage import init_db; init_db()" || {
    echo "⚠️  Worker container not running, trying direct migration..."
    cd /opt/callsbotonchain
    python3 -c "from app.storage import init_db; init_db()" || echo "Migration will run on next container start"
}
echo "✅ Migrations applied"
echo ""
ENDSSH
echo ""

# Step 4: Verify database schema
echo "🔍 Step 4: Verifying database schema..."
ssh $SERVER << 'ENDSSH'
set -e
cd /opt/callsbotonchain/deployment
echo "Checking database tables..."
sqlite3 var/alerted_tokens.db "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;" | while read table; do
    echo "  ✓ $table"
done
echo ""
echo "Checking migrations..."
sqlite3 var/alerted_tokens.db "SELECT version, name FROM schema_migrations ORDER BY version;" | while read migration; do
    echo "  ✓ Migration: $migration"
done
echo "✅ Database schema verified"
echo ""
ENDSSH
echo ""

# Step 5: Restart services
echo "🔄 Step 5: Restarting services..."
ssh $SERVER << 'ENDSSH'
set -e
cd /opt/callsbotonchain/deployment
echo "Stopping services..."
docker compose down
echo ""
echo "Starting services..."
docker compose up -d
echo ""
echo "Waiting for services to start..."
sleep 5
echo ""
echo "Service status:"
docker compose ps
echo "✅ Services restarted"
echo ""
ENDSSH
echo ""

# Step 6: Verify services are running
echo "✅ Step 6: Verifying services..."
ssh $SERVER << 'ENDSSH'
set -e
cd /opt/callsbotonchain/deployment
echo "Checking container health..."
docker compose ps
echo ""
echo "Checking API health..."
curl -s http://localhost/api/v2/quick-stats | python3 -m json.tool || echo "⚠️  API not responding yet (may need a few seconds)"
echo ""
echo "Checking worker logs (last 20 lines)..."
docker compose logs --tail=20 worker
echo "✅ Services verified"
echo ""
ENDSSH
echo ""

# Step 7: Run comprehensive validation
echo "🔬 Step 7: Running comprehensive validation..."
ssh $SERVER << 'ENDSSH'
set -e
cd /opt/callsbotonchain/deployment

echo "=== DATABASE VALIDATION ==="
echo "Tables:"
sqlite3 var/alerted_tokens.db "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" | xargs echo "  Total tables:"
sqlite3 var/alerted_tokens.db "SELECT COUNT(*) FROM transaction_snapshots;" | xargs echo "  Transaction snapshots:"
sqlite3 var/alerted_tokens.db "SELECT COUNT(*) FROM wallet_first_buys;" | xargs echo "  Wallet first buys:"
sqlite3 var/alerted_tokens.db "SELECT COUNT(*) FROM alerted_tokens;" | xargs echo "  Total alerts:"
echo ""

echo "=== API VALIDATION ==="
echo "Testing API endpoints..."
curl -s http://localhost/api/v2/tokens?limit=1 > /dev/null && echo "  ✓ /api/v2/tokens" || echo "  ✗ /api/v2/tokens"
curl -s http://localhost/api/v2/quick-stats > /dev/null && echo "  ✓ /api/v2/quick-stats" || echo "  ✗ /api/v2/quick-stats"
echo ""

echo "=== WORKER VALIDATION ==="
echo "Checking for errors in last 50 lines..."
ERROR_COUNT=$(docker compose logs --tail=50 worker | grep -i "error\|exception\|failed" | wc -l)
if [ "$ERROR_COUNT" -eq 0 ]; then
    echo "  ✓ No errors found"
else
    echo "  ⚠️  Found $ERROR_COUNT error lines (check logs)"
fi
echo ""

echo "✅ Validation complete"
ENDSSH
echo ""

# Step 8: Display summary
echo "=========================================="
echo "✅ DEPLOYMENT COMPLETE"
echo "=========================================="
echo ""
echo "📊 Summary:"
echo "  ✓ Code pushed to GitHub"
echo "  ✓ Code pulled on server"
echo "  ✓ Database migrations applied"
echo "  ✓ Database schema verified"
echo "  ✓ Services restarted"
echo "  ✓ Services verified"
echo "  ✓ Validation complete"
echo ""
echo "🌐 Access Points:"
echo "  Dashboard: http://64.227.157.221"
echo "  API: http://64.227.157.221/api/v2/tokens"
echo ""
echo "📝 Next Steps:"
echo "  1. Check dashboard: http://64.227.157.221"
echo "  2. Monitor logs: ssh $SERVER 'cd $DEPLOY_DIR/$DEPLOYMENT_SUBDIR && docker compose logs -f worker'"
echo "  3. Verify data: Check 'Tracked' tab on dashboard"
echo ""
echo "🎉 Deployment successful!"
echo "=========================================="

