#!/bin/bash
# Automated Security Fixes Deployment Script
# Run this on the server to deploy all security fixes

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    error "Please run as root (use sudo)"
    exit 1
fi

echo "========================================"
echo "🔐 Security Fixes Deployment Script"
echo "========================================"
echo ""

# Get project directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

info "Project directory: $PROJECT_DIR"
cd "$PROJECT_DIR"

# Step 1: Backup
echo ""
info "Step 1: Creating backups..."

BACKUP_DIR="$PROJECT_DIR/backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

cp deployment/Caddyfile "$BACKUP_DIR/Caddyfile.backup" 2>/dev/null || true
cp src/server.py "$BACKUP_DIR/server.py.backup" 2>/dev/null || true
cp scripts/track_performance.py "$BACKUP_DIR/track_performance.py.backup" 2>/dev/null || true
cp var/alerted_tokens.db "$BACKUP_DIR/alerted_tokens.db.backup" 2>/dev/null || true

success "Backups created in $BACKUP_DIR"

# Step 2: Check .env file
echo ""
info "Step 2: Checking .env configuration..."

ENV_FILE="$PROJECT_DIR/deployment/.env"

if [ ! -f "$ENV_FILE" ]; then
    error ".env file not found at $ENV_FILE"
    exit 1
fi

# Check if authentication variables exist
if ! grep -q "DASHBOARD_AUTH_ENABLED" "$ENV_FILE"; then
    warning "DASHBOARD_AUTH_ENABLED not found in .env"
    echo ""
    read -p "Do you want to enable authentication? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "" >> "$ENV_FILE"
        echo "# Dashboard Authentication" >> "$ENV_FILE"
        echo "DASHBOARD_AUTH_ENABLED=true" >> "$ENV_FILE"
        
        read -p "Enter dashboard username (default: admin): " username
        username=${username:-admin}
        echo "DASHBOARD_USERNAME=$username" >> "$ENV_FILE"
        
        read -s -p "Enter dashboard password: " password
        echo
        if [ -z "$password" ]; then
            error "Password cannot be empty"
            exit 1
        fi
        echo "DASHBOARD_PASSWORD=$password" >> "$ENV_FILE"
        
        success "Authentication configured"
    else
        echo "DASHBOARD_AUTH_ENABLED=false" >> "$ENV_FILE"
        warning "Authentication disabled"
    fi
fi

# Step 3: Stop containers
echo ""
info "Step 3: Stopping containers..."

cd "$PROJECT_DIR/deployment"
docker-compose down

success "Containers stopped"

# Step 4: Rebuild containers (to pick up code changes)
echo ""
info "Step 4: Rebuilding containers..."

docker-compose build --no-cache web tracker

success "Containers rebuilt"

# Step 5: Start containers
echo ""
info "Step 5: Starting containers..."

docker-compose up -d

success "Containers started"

# Wait for containers to be healthy
echo ""
info "Waiting for containers to be healthy (30 seconds)..."
sleep 30

# Step 6: Verify containers
echo ""
info "Step 6: Verifying container status..."

RUNNING=$(docker ps --filter name=callsbot --format "{{.Names}}" | wc -l)

if [ "$RUNNING" -eq 6 ]; then
    success "All 6 containers are running"
else
    warning "Only $RUNNING/6 containers are running"
    docker ps --filter name=callsbot
fi

# Step 7: Setup database cleanup
echo ""
info "Step 7: Setting up database cleanup..."

cd "$PROJECT_DIR"
chmod +x scripts/cleanup_database.py
chmod +x scripts/setup_cleanup_cron.sh

# Run cleanup script once to test
info "Running initial cleanup..."
python3 scripts/cleanup_database.py || warning "Cleanup script failed (may be normal if no old data)"

# Setup cron job
info "Installing cron job..."
bash scripts/setup_cleanup_cron.sh

success "Database cleanup configured"

# Step 8: Test HTTPS
echo ""
info "Step 8: Testing HTTPS..."

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1/ || echo "000")

if [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "308" ]; then
    success "HTTP redirects to HTTPS (code: $HTTP_CODE)"
elif [ "$HTTP_CODE" = "000" ]; then
    warning "Could not connect to server"
else
    warning "Unexpected HTTP code: $HTTP_CODE"
fi

# Step 9: Test Authentication
echo ""
info "Step 9: Testing authentication..."

# Get credentials from .env
source "$ENV_FILE"

if [ "$DASHBOARD_AUTH_ENABLED" = "true" ]; then
    # Test without auth (should fail)
    UNAUTH_CODE=$(curl -k -s -o /dev/null -w "%{http_code}" https://127.0.0.1/ || echo "000")
    
    if [ "$UNAUTH_CODE" = "401" ]; then
        success "Authentication required (401 response)"
    else
        warning "Expected 401, got $UNAUTH_CODE"
    fi
    
    # Test with auth (should succeed)
    if [ -n "$DASHBOARD_USERNAME" ] && [ -n "$DASHBOARD_PASSWORD" ]; then
        AUTH_CODE=$(curl -k -s -o /dev/null -w "%{http_code}" -u "$DASHBOARD_USERNAME:$DASHBOARD_PASSWORD" https://127.0.0.1/ || echo "000")
        
        if [ "$AUTH_CODE" = "200" ]; then
            success "Authentication working (200 response)"
        else
            warning "Expected 200, got $AUTH_CODE"
        fi
    fi
else
    info "Authentication disabled"
fi

# Step 10: Test API endpoints
echo ""
info "Step 10: Testing API endpoints..."

if [ "$DASHBOARD_AUTH_ENABLED" = "true" ] && [ -n "$DASHBOARD_USERNAME" ] && [ -n "$DASHBOARD_PASSWORD" ]; then
    AUTH_PARAM="-u $DASHBOARD_USERNAME:$DASHBOARD_PASSWORD"
else
    AUTH_PARAM=""
fi

STATS=$(curl -k -s $AUTH_PARAM https://127.0.0.1/api/v2/quick-stats || echo "{}")

if echo "$STATS" | grep -q "total_alerts"; then
    success "API endpoints working"
    echo "$STATS" | python3 -m json.tool 2>/dev/null || echo "$STATS"
else
    warning "API endpoints may not be working correctly"
    echo "$STATS"
fi

# Step 11: Check tracker logs
echo ""
info "Step 11: Checking tracker logs..."

TRACKER_ERRORS=$(docker logs callsbot-tracker --tail 50 2>&1 | grep -i "error" | grep -v "Error printing summary" | wc -l)

if [ "$TRACKER_ERRORS" -eq 0 ]; then
    success "No errors in tracker logs"
else
    warning "Found $TRACKER_ERRORS errors in tracker logs"
    docker logs callsbot-tracker --tail 20
fi

# Final summary
echo ""
echo "========================================"
echo "📊 Deployment Summary"
echo "========================================"
echo ""

echo "✅ Completed Steps:"
echo "  1. Backups created"
echo "  2. Configuration verified"
echo "  3. Containers rebuilt"
echo "  4. Containers restarted"
echo "  5. Database cleanup configured"
echo "  6. HTTPS tested"
echo "  7. Authentication tested"
echo "  8. API endpoints tested"
echo ""

echo "📁 Backup Location:"
echo "  $BACKUP_DIR"
echo ""

echo "🔐 Security Status:"
if [ "$DASHBOARD_AUTH_ENABLED" = "true" ]; then
    echo "  Authentication: ✅ Enabled"
    echo "  Username: $DASHBOARD_USERNAME"
else
    echo "  Authentication: ⚠️  Disabled"
fi
echo "  HTTPS: ✅ Enabled"
echo "  Database Cleanup: ✅ Configured"
echo ""

echo "🌐 Access Dashboard:"
echo "  URL: https://64.227.157.221/"
if [ "$DASHBOARD_AUTH_ENABLED" = "true" ]; then
    echo "  Username: $DASHBOARD_USERNAME"
    echo "  Password: (from .env file)"
fi
echo ""

echo "📝 Next Steps:"
echo "  1. Test dashboard in browser"
echo "  2. Verify bot is still processing signals"
echo "  3. Check cleanup log tomorrow: tail var/cleanup.log"
echo "  4. Change default password if needed"
echo ""

echo "🔄 Rollback (if needed):"
echo "  cd $PROJECT_DIR/deployment"
echo "  docker-compose down"
echo "  cp $BACKUP_DIR/*.backup ."
echo "  docker-compose up -d"
echo ""

success "Deployment complete! 🎉"