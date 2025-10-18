#!/usr/bin/env python3
"""Deep signal analysis - why are signals low?"""
import sqlite3
from datetime import datetime, timedelta
from collections import Counter

conn = sqlite3.connect('var/alerted_tokens.db')

print("=" * 80)
print("DEEP SIGNAL ANALYSIS")
print("=" * 80)

# Check signal counts by time period
print("\n1. SIGNAL FREQUENCY:")
periods = [
    ("Last 1 hour", 3600),
    ("Last 6 hours", 21600),
    ("Last 24 hours", 86400),
    ("Last 7 days", 604800)
]

for label, seconds in periods:
    cursor = conn.execute(f"""
        SELECT COUNT(*) FROM alerted_tokens 
        WHERE alerted_at > strftime('%s', 'now') - {seconds}
    """)
    count = cursor.fetchone()[0]
    rate_per_hour = count / (seconds / 3600)
    print(f"   {label}: {count} signals ({rate_per_hour:.1f}/hour)")

# Check most recent signals
cursor = conn.execute("""
    SELECT 
        datetime(alerted_at, 'unixepoch') as time,
        substr(token_address, 1, 8) as token,
        final_score
    FROM alerted_tokens
    ORDER BY alerted_at DESC
    LIMIT 10
""")
recent = cursor.fetchall()

print(f"\n2. MOST RECENT SIGNALS:")
if recent:
    print(f"   {'Time':<20} {'Token':<10} {'Score':<6}")
    print(f"   {'-'*36}")
    for time, token, score in recent:
        print(f"   {time:<20} {token:<10} {score:<6}")
    
    # Calculate time since last signal
    last_signal_time = datetime.strptime(recent[0][0], '%Y-%m-%d %H:%M:%S')
    time_since = datetime.now() - last_signal_time
    hours_since = time_since.total_seconds() / 3600
    print(f"\n   ⚠️  Last signal was {hours_since:.1f} hours ago!")
else:
    print(f"   ❌ NO SIGNALS FOUND!")

# Check score distribution
cursor = conn.execute("""
    SELECT final_score, COUNT(*) as count
    FROM alerted_tokens
    WHERE alerted_at > strftime('%s', 'now') - 604800
    GROUP BY final_score
    ORDER BY final_score DESC
""")
scores = cursor.fetchall()

print(f"\n3. SCORE DISTRIBUTION (Last 7 days):")
if scores:
    for score, count in scores:
        bar = "█" * int(count / 10)
        print(f"   Score {score}: {count:4d} {bar}")
else:
    print(f"   No signals in last 7 days")

# Check market cap distribution of recent tokens
cursor = conn.execute("""
    SELECT 
        CASE 
            WHEN first_market_cap_usd < 50000 THEN '<$50k'
            WHEN first_market_cap_usd < 100000 THEN '$50k-$100k'
            WHEN first_market_cap_usd < 130000 THEN '$100k-$130k'
            WHEN first_market_cap_usd < 200000 THEN '$130k-$200k'
            ELSE '>$200k'
        END as range,
        COUNT(*) as count
    FROM alerted_token_stats
    WHERE first_alert_at > strftime('%s', 'now') - 604800
    GROUP BY range
    ORDER BY range
""")
mcap_dist = cursor.fetchall()

print(f"\n4. MARKET CAP DISTRIBUTION (Signals Last 7 days):")
if mcap_dist:
    for range_label, count in mcap_dist:
        print(f"   {range_label}: {count}")
else:
    print(f"   No data")

# Check liquidity distribution
cursor = conn.execute("""
    SELECT 
        CASE 
            WHEN first_liquidity_usd < 35000 THEN '<$35k (rejected)'
            WHEN first_liquidity_usd < 50000 THEN '$35k-$50k'
            WHEN first_liquidity_usd < 75000 THEN '$50k-$75k'
            ELSE '>$75k (rejected)'
        END as range,
        COUNT(*) as count
    FROM alerted_token_stats
    WHERE first_alert_at > strftime('%s', 'now') - 604800
    GROUP BY range
    ORDER BY range
""")
liq_dist = cursor.fetchall()

print(f"\n5. LIQUIDITY DISTRIBUTION (Signals Last 7 days):")
if liq_dist:
    for range_label, count in liq_dist:
        print(f"   {range_label}: {count}")
else:
    print(f"   No data")

conn.close()

print("\n" + "=" * 80)
print("CHECKING LIVE LOGS FOR REJECTION REASONS...")
print("=" * 80)

