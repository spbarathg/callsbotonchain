#!/bin/bash
# Setup automatic database cleanup via cron
# Run this script once to install the cron job

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🔧 Setting up automatic database cleanup..."
echo "Project directory: $PROJECT_DIR"

# Create cron job that runs daily at 3 AM
CRON_CMD="0 3 * * * cd $PROJECT_DIR && /usr/bin/python3 scripts/cleanup_database.py >> var/cleanup.log 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "cleanup_database.py"; then
    echo "⚠️  Cron job already exists. Skipping..."
else
    # Add cron job
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    echo "✅ Cron job installed successfully!"
    echo "   Schedule: Daily at 3:00 AM"
    echo "   Log file: $PROJECT_DIR/var/cleanup.log"
fi

echo ""
echo "Current crontab:"
crontab -l | grep cleanup_database.py || echo "  (none)"

echo ""
echo "To manually run cleanup now:"
echo "  cd $PROJECT_DIR && python3 scripts/cleanup_database.py"

echo ""
echo "To remove the cron job:"
echo "  crontab -e"
echo "  (then delete the line containing 'cleanup_database.py')"