#!/bin/bash
# Server Storage Cleanup Script
# Safely removes unused Docker images, old logs, and temporary files

set -e

echo "=========================================="
echo "🧹 Server Storage Cleanup"
echo "=========================================="
echo "Started: $(date)"
echo ""

# Show current disk usage
echo "📊 Current Disk Usage:"
df -h / | grep -v Filesystem
echo ""

# 1. Clean up unused Docker images (biggest space saver)
echo "🐳 Cleaning up unused Docker images..."
BEFORE_IMAGES=$(docker images -q | wc -l)
docker image prune -a -f
AFTER_IMAGES=$(docker images -q | wc -l)
REMOVED_IMAGES=$((BEFORE_IMAGES - AFTER_IMAGES))
echo "   Removed $REMOVED_IMAGES unused images"
echo ""

# 2. Clean up Docker build cache
echo "🏗️  Cleaning Docker build cache..."
docker builder prune -a -f
echo ""

# 3. Clean up stopped containers (if any)
echo "📦 Cleaning stopped containers..."
docker container prune -f
echo ""

# 4. Clean up unused volumes
echo "💾 Cleaning unused volumes..."
docker volume prune -f
echo ""

# 5. Clean up old journal logs (keep last 7 days)
echo "📝 Cleaning old journal logs..."
journalctl --vacuum-time=7d
echo ""

# 6. Clean up old auth logs
echo "🔐 Cleaning old auth logs..."
if [ -f /var/log/auth.log.1 ]; then
    rm -f /var/log/auth.log.{2..10}* 2>/dev/null || true
    echo "   Removed old auth logs"
fi
echo ""

# 7. Clean up old btmp logs (failed login attempts)
echo "🚫 Cleaning btmp logs..."
if [ -f /var/log/btmp ]; then
    > /var/log/btmp
    echo "   Cleared btmp log"
fi
echo ""

# 8. Clean up old backups (keep last 3)
echo "💼 Cleaning old backups..."
cd /opt/callsbotonchain/backups
if [ -d /opt/callsbotonchain/backups ]; then
    BACKUP_COUNT=$(ls -1 | wc -l)
    if [ $BACKUP_COUNT -gt 3 ]; then
        ls -t | tail -n +4 | xargs rm -rf
        echo "   Kept 3 most recent backups, removed $(($BACKUP_COUNT - 3))"
    else
        echo "   Only $BACKUP_COUNT backups, keeping all"
    fi
fi
cd /opt/callsbotonchain
echo ""

# 9. Clean up temporary files
echo "🗑️  Cleaning temporary files..."
rm -rf /tmp/* 2>/dev/null || true
rm -rf /var/tmp/* 2>/dev/null || true
echo "   Cleared /tmp and /var/tmp"
echo ""

# 10. Clean up APT cache
echo "📦 Cleaning APT cache..."
apt-get clean
echo "   Cleared APT cache"
echo ""

# Show final disk usage
echo "=========================================="
echo "✅ Cleanup Complete!"
echo "=========================================="
echo ""
echo "📊 Final Disk Usage:"
df -h / | grep -v Filesystem
echo ""

# Calculate space recovered
echo "💾 Space Analysis:"
docker system df
echo ""

echo "Completed: $(date)"
echo "=========================================="

