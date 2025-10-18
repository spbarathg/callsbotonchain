#!/bin/bash
# Automated ML Model Retraining Script
# Retrains models weekly as new signal data accumulates

set -e

echo "=========================================="
echo "🤖 ML Model Auto-Retraining"
echo "=========================================="
echo "Started: $(date)"

# Navigate to project root
cd /opt/callsbotonchain

# Check if we have enough new data to retrain
SIGNAL_COUNT=$(docker exec callsbot-worker sqlite3 var/alerted_tokens.db "SELECT COUNT(*) FROM alerted_token_stats WHERE max_gain_percent IS NOT NULL")
echo "📊 Current signal count: $SIGNAL_COUNT"

if [ "$SIGNAL_COUNT" -lt 100 ]; then
    echo "⚠️  Not enough signals yet ($SIGNAL_COUNT < 100). Skipping retraining."
    exit 0
fi

# Check when we last retrained
LAST_RETRAIN=""
if docker exec callsbot-worker test -f var/models/last_retrain.txt; then
    LAST_RETRAIN=$(docker exec callsbot-worker cat var/models/last_retrain.txt)
    echo "📅 Last retrain: $LAST_RETRAIN"
fi

# Retrain models
echo ""
echo "🔄 Retraining ML models..."
docker exec callsbot-worker python scripts/ml/train_model.py

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Retraining successful!"
    echo "🔄 Restarting worker to load new models..."
    
    cd deployment
    docker compose restart worker
    
    echo ""
    echo "✅ Worker restarted with new models"
    echo "Completed: $(date)"
    echo "=========================================="
else
    echo ""
    echo "❌ Retraining failed!"
    echo "Completed: $(date)"
    echo "=========================================="
    exit 1
fi

