#!/bin/bash
# Force-close all open positions in the database

cd "$(dirname "$0")/.."
DB_PATH="var/trading.db"

echo "Closing all open positions..."
sqlite3 "$DB_PATH" "UPDATE positions SET status='closed', closed_at=strftime('%s','now') WHERE status='open';"

COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM positions WHERE status='open';")
echo "✅ Done! Open positions remaining: $COUNT"

if [ "$COUNT" -eq 0 ]; then
    echo "🎯 All positions closed successfully!"
else
    echo "⚠️ Warning: $COUNT positions still open"
fi

