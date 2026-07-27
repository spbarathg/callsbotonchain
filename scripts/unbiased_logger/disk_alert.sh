#!/bin/bash
# A simple script to alert if the disk space used by logs exceeds 85%
# Setup via crontab: 0 * * * * /opt/yesv2/callsbotonchain/scripts/unbiased_logger/disk_alert.sh

PARTITION="/"
THRESHOLD=85

CURRENT_USAGE=$(df -h $PARTITION | awk 'NR==2 {print $5}' | sed 's/%//')

if [ "$CURRENT_USAGE" -gt "$THRESHOLD" ]; then
    # In a real environment, send a telegram message or webhook here
    # Example: curl -X POST -d "text=URGENT: Disk at ${CURRENT_USAGE}%" https://api.telegram.org/bot<token>/sendMessage?chat_id=<id>
    
    echo "URGENT: Disk usage is at ${CURRENT_USAGE}%. Logging pipeline may fail!" | logger -t antbot_disk_alert
    
    # Write to a visible alert file in the logs directory
    echo "$(date): CRITICAL - Disk usage at ${CURRENT_USAGE}%" >> /opt/yesv2/callsbotonchain/scripts/unbiased_logger/logs/disk_critical_alert.log
fi
