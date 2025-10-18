#!/usr/bin/env python3
"""Check ML status on server."""
import sqlite3
from datetime import datetime, timedelta

# Connect to database
conn = sqlite3.connect('var/alerted_tokens.db')

# Check recent signals
cursor = conn.execute("""
    SELECT COUNT(*) 
    FROM alerted_tokens 
    WHERE alerted_at > strftime('%s', 'now') - 86400
""")
signals_24h = cursor.fetchone()[0]

cursor = conn.execute("SELECT COUNT(*) FROM alerted_tokens")
total_signals = cursor.fetchone()[0]

# Check ML predictions
cursor = conn.execute("""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN ml_gain_prediction IS NOT NULL THEN 1 ELSE 0 END) as with_ml_gain,
        SUM(CASE WHEN ml_winner_probability IS NOT NULL THEN 1 ELSE 0 END) as with_ml_winner
    FROM alerted_tokens
    WHERE alerted_at > strftime('%s', 'now') - 86400
""")
row = cursor.fetchone()
ml_stats = {
    'total': row[0],
    'with_ml_gain': row[1] or 0,
    'with_ml_winner': row[2] or 0
}

# Get recent signals with ML data
cursor = conn.execute("""
    SELECT 
        datetime(alerted_at, 'unixepoch') as time,
        substr(token_address, 1, 12) as token,
        final_score,
        ml_gain_prediction,
        ml_winner_probability
    FROM alerted_tokens
    ORDER BY alerted_at DESC
    LIMIT 5
""")
recent_signals = cursor.fetchall()

conn.close()

# Print results
print("=" * 60)
print("ML STATUS REPORT")
print("=" * 60)
print(f"\n📊 SIGNAL STATISTICS:")
print(f"  Total Signals: {total_signals}")
print(f"  Last 24h: {signals_24h}")

print(f"\n🤖 ML PREDICTIONS (Last 24h):")
print(f"  Signals with ML Gain Prediction: {ml_stats['with_ml_gain']}/{ml_stats['total']}")
print(f"  Signals with ML Winner Probability: {ml_stats['with_ml_winner']}/{ml_stats['total']}")

if ml_stats['with_ml_gain'] > 0 or ml_stats['with_ml_winner'] > 0:
    print(f"  ✅ ML IS ACTIVE")
else:
    print(f"  ⚠️  ML PREDICTIONS NOT FOUND IN RECENT SIGNALS")

print(f"\n📝 RECENT SIGNALS:")
print(f"{'Time':<20} {'Token':<14} {'Score':<6} {'ML Gain':<10} {'ML Win %':<10}")
print("-" * 60)
for signal in recent_signals:
    time, token, score, ml_gain, ml_winner = signal
    ml_gain_str = f"{ml_gain:.1f}" if ml_gain else "-"
    ml_winner_str = f"{ml_winner*100:.1f}%" if ml_winner else "-"
    print(f"{time:<20} {token:<14} {score:<6.1f} {ml_gain_str:<10} {ml_winner_str:<10}")

print("=" * 60)

