#!/bin/bash
# Setup cron job for weekly ML model retraining

echo "Setting up ML auto-retraining cron job..."

# Make the retrain script executable
chmod +x /opt/callsbotonchain/scripts/ml/auto_retrain.sh

# Create cron job that runs every Sunday at 3 AM
CRON_JOB="0 3 * * 0 /opt/callsbotonchain/scripts/ml/auto_retrain.sh >> /opt/callsbotonchain/data/logs/ml_retrain.log 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "auto_retrain.sh"; then
    echo "⚠️  Cron job already exists. Updating..."
    # Remove old job
    crontab -l 2>/dev/null | grep -v "auto_retrain.sh" | crontab -
fi

# Add new cron job
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

echo "✅ Cron job installed successfully!"
echo ""
echo "📅 Schedule: Every Sunday at 3:00 AM"
echo "📝 Logs: /opt/callsbotonchain/data/logs/ml_retrain.log"
echo ""
echo "Current crontab:"
crontab -l | grep "auto_retrain"

