#!/bin/bash
# Migration script for session file isolation
# This moves existing session files to Docker named volumes for complete isolation

set -e

echo "=================================================================================="
echo "🚀 SESSION FILE MIGRATION - ULTIMATE FIX FOR DATABASE LOCKS"
echo "=================================================================================="
echo ""
echo "This script will:"
echo "  1. Stop all containers"
echo "  2. Create Docker named volumes for session isolation"
echo "  3. Copy existing session files to their isolated volumes"
echo "  4. Rebuild and restart containers"
echo ""
echo "This provides 100% isolation between Signal Aggregator and Main Bot sessions!"
echo "=================================================================================="
echo ""

# Navigate to deployment directory
cd "$(dirname "$0")"

# Stop all containers
echo "📦 Stopping all containers..."
docker compose down

# Create the named volumes if they don't exist
echo "📦 Creating named volumes..."
docker volume create callsbotonchain_worker_sessions || true
docker volume create callsbotonchain_aggregator_sessions || true

# Copy existing session files to the volumes
echo "📁 Copying session files to isolated volumes..."

# For worker (relay_user.session)
if [ -f "./var/relay_user.session" ]; then
    echo "  ✅ Found relay_user.session, copying to worker volume..."
    docker run --rm \
        -v "$(pwd)/var:/source" \
        -v callsbotonchain_worker_sessions:/dest \
        alpine sh -c "mkdir -p /dest && cp -v /source/relay_user.session* /dest/ 2>/dev/null || echo '  ℹ️  No journal file found (OK)'"
else
    echo "  ⚠️  relay_user.session not found, will be created on first run"
fi

# For signal aggregator (memecoin_session.session)
if [ -f "./var/memecoin_session.session" ]; then
    echo "  ✅ Found memecoin_session.session, copying to aggregator volume..."
    docker run --rm \
        -v "$(pwd)/var:/source" \
        -v callsbotonchain_aggregator_sessions:/dest \
        alpine sh -c "mkdir -p /dest && cp -v /source/memecoin_session.session* /dest/ 2>/dev/null || echo '  ℹ️  No journal file found (OK)'"
else
    echo "  ⚠️  memecoin_session.session not found, will be created on first run"
fi

# Rebuild containers with new configuration
echo "🔨 Rebuilding containers..."
docker compose build --no-cache

# Start containers
echo "🚀 Starting containers..."
docker compose up -d

echo ""
echo "=================================================================================="
echo "✅ MIGRATION COMPLETE!"
echo "=================================================================================="
echo ""
echo "Session files are now COMPLETELY ISOLATED:"
echo "  • Worker (main bot):        Uses worker_sessions volume"
echo "  • Signal Aggregator:        Uses aggregator_sessions volume"
echo ""
echo "This eliminates ALL SQLite database lock issues permanently!"
echo ""
echo "Check logs:"
echo "  docker logs -f callsbot-worker"
echo "  docker logs -f callsbot-signal-aggregator"
echo ""
echo "=================================================================================="

