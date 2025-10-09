#!/bin/bash
# Daily Performance Report Runner
# Run this script to generate a comprehensive bot performance report

cd /opt/callsbotonchain || exit 1

echo "📊 Running Daily Performance Report..."
echo "======================================="
echo ""

# Run the report
python3 scripts/daily_performance_report.py

# Optional: Send to Telegram (if configured)
if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
    echo ""
    echo "📤 Sending summary to Telegram..."
    
    # Extract key metrics from latest report
    LATEST_REPORT="analytics/latest_daily_report.json"
    
    if [ -f "$LATEST_REPORT" ]; then
        TOTAL_SIGNALS=$(jq -r '.signal_performance.total_signals // 0' "$LATEST_REPORT")
        WIN_RATE=$(jq -r '.signal_performance.win_rate_pct // 0' "$LATEST_REPORT")
        AVG_GAIN=$(jq -r '.signal_performance.avg_gain_pct // 0' "$LATEST_REPORT")
        BOT_STATUS=$(jq -r '.health.overall_status // "UNKNOWN"' "$LATEST_REPORT")
        
        MESSAGE="🤖 *CallsBotOnChain - Daily Report*\n\n"
        MESSAGE+="📊 *Signals:* $TOTAL_SIGNALS (24h)\n"
        MESSAGE+="📈 *Win Rate:* ${WIN_RATE}%\n"
        MESSAGE+="💰 *Avg Gain:* ${AVG_GAIN}%\n"
        MESSAGE+="🏥 *Bot Status:* $BOT_STATUS\n\n"
        MESSAGE+="📄 Full report: /opt/callsbotonchain/$LATEST_REPORT"
        
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d chat_id="${TELEGRAM_CHAT_ID}" \
            -d text="$MESSAGE" \
            -d parse_mode="Markdown" > /dev/null
        
        echo "✅ Report sent to Telegram"
    fi
fi

echo ""
echo "✅ Daily report complete!"

