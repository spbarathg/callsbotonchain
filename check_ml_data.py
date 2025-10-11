#!/usr/bin/env python3
"""
Quick diagnostic script to check ML data quality
"""
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('var/alerted_tokens.db')
c = conn.cursor()

print("="*70)
print("ML DATA DIAGNOSTIC REPORT")
print("="*70)
print()

# 1. Total records
c.execute("SELECT COUNT(*) FROM alerted_tokens")
total_alerts = c.fetchone()[0]

c.execute("SELECT COUNT(*) FROM alerted_token_stats")
total_stats = c.fetchone()[0]

print(f"1. RECORD COUNTS:")
print(f"   alerted_tokens: {total_alerts}")
print(f"   alerted_token_stats: {total_stats}")
print()

# 2. Data completeness in stats
c.execute("""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN first_price_usd IS NOT NULL THEN 1 ELSE 0 END) as has_first_price,
        SUM(CASE WHEN peak_price_usd IS NOT NULL THEN 1 ELSE 0 END) as has_peak_price,
        SUM(CASE WHEN max_gain_percent IS NOT NULL THEN 1 ELSE 0 END) as has_max_gain,
        SUM(CASE WHEN last_checked_at IS NOT NULL AND last_checked_at > 0 THEN 1 ELSE 0 END) as has_been_tracked
    FROM alerted_token_stats
""")
row = c.fetchone()

print(f"2. DATA COMPLETENESS:")
print(f"   Total stats records: {row[0]}")
print(f"   Has first_price: {row[1]} ({row[1]/row[0]*100:.1f}%)")
print(f"   Has peak_price: {row[2]} ({row[2]/row[0]*100:.1f}%)")
print(f"   Has max_gain_percent: {row[3]} ({row[3]/row[0]*100:.1f}%)")
print(f"   Has been tracked: {row[4]} ({row[4]/row[0]*100:.1f}%)")
print()

# 3. ML readiness
print(f"3. ML TRAINING READINESS:")
print(f"   Required: 50 samples with outcomes")
print(f"   Available: {row[3]} samples")
if row[3] >= 50:
    print(f"   Status: ✅ READY FOR TRAINING")
else:
    print(f"   Status: ⏳ NEED {50 - row[3]} MORE SAMPLES")
print()

# 4. Recent tracking activity (last hour)
one_hour_ago = (datetime.now() - timedelta(hours=1)).timestamp()
c.execute("""
    SELECT COUNT(*) 
    FROM alerted_token_stats 
    WHERE last_checked_at >= ?
""", (one_hour_ago,))
recent_updates = c.fetchone()[0]

print(f"4. RECENT ACTIVITY (Last hour):")
print(f"   Tokens updated: {recent_updates}")
print()

# 5. Problem tokens (have price but no gain)
c.execute("""
    SELECT COUNT(*)
    FROM alerted_token_stats
    WHERE first_price_usd IS NOT NULL
      AND peak_price_usd IS NOT NULL
      AND max_gain_percent IS NULL
""")
problem_count = c.fetchone()[0]

print(f"5. DATA QUALITY ISSUES:")
print(f"   Tokens with price but NO max_gain: {problem_count}")
if problem_count > 0:
    print(f"   ⚠️  This is a BUG! These should have max_gain calculated!")
    
    # Show examples
    c.execute("""
        SELECT token_address, first_price_usd, peak_price_usd, last_price_usd
        FROM alerted_token_stats
        WHERE first_price_usd IS NOT NULL
          AND peak_price_usd IS NOT NULL
          AND max_gain_percent IS NULL
        LIMIT 5
    """)
    print()
    print(f"   Examples:")
    for row in c.fetchall():
        token = row[0][:12]
        expected_gain = ((row[2] - row[1]) / row[1] * 100) if row[1] > 0 else 0
        print(f"   - {token}: first=${row[1]:.8f}, peak=${row[2]:.8f}, should be {expected_gain:.1f}%")
else:
    print(f"   ✅ All tokens with price have max_gain calculated")
print()

# 6. Timeline
one_day_ago = (datetime.now() - timedelta(hours=24)).timestamp()
c.execute("""
    SELECT COUNT(*)
    FROM alerted_tokens
    WHERE alerted_at >= ?
""", (one_day_ago,))
alerts_24h = c.fetchone()[0]

print(f"6. RECENT SIGNALS (Last 24h):")
print(f"   New alerts: {alerts_24h}")
print(f"   Should be tracked: {alerts_24h}")
print(f"   Tracker shows: 13 tokens")
if alerts_24h > 13:
    print(f"   ⚠️  Gap: {alerts_24h - 13} tokens not being picked up!")
print()

print("="*70)
print()

# SUMMARY
print("SUMMARY:")
print("-" * 70)
if row[3] >= 50:
    print("✅ ML system ready for training")
else:
    print(f"⏳ ML system needs {50 - row[3]} more samples (estimated {(50 - row[3]) * 10} minutes)")

if problem_count > 0:
    print(f"❌ BUG: {problem_count} tokens missing max_gain despite having price data")
    print("   → Check update_token_performance() function")

if alerts_24h > 13:
    print(f"⚠️  Tracker not picking up all tokens ({alerts_24h} available, only 13 tracked)")
    print("   → Check get_alerted_tokens_for_tracking() function")

conn.close()

