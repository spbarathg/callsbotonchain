#!/usr/bin/env python3
"""Quick check of signal timestamps"""
import sqlite3
from datetime import datetime

conn = sqlite3.connect('var/alerted_tokens.db')
c = conn.cursor()

print("="*60)
print("SIGNAL TIMESTAMP CHECK")
print("="*60)

# Get total signals
c.execute("SELECT COUNT(*) FROM alerted_tokens")
total = c.fetchone()[0]
print(f"\nTotal signals in database: {total}")

# Get min and max timestamps
c.execute("SELECT MIN(alerted_at), MAX(alerted_at) FROM alerted_tokens")
min_ts, max_ts = c.fetchone()

print(f"\nTimestamp range:")
print(f"  Min: {min_ts}")
print(f"  Max: {max_ts}")

# Try to parse them
if min_ts:
    try:
        # Try as unix timestamp
        min_dt = datetime.fromtimestamp(float(min_ts))
        max_dt = datetime.fromtimestamp(float(max_ts))
        print(f"\nAs Unix timestamps:")
        print(f"  Min: {min_dt}")
        print(f"  Max: {max_dt}")
    except:
        print(f"\nNot unix timestamps, trying as strings...")
        print(f"  Min: {min_ts}")
        print(f"  Max: {max_ts}")

# Get last 10 signals with their timestamps
c.execute("""
SELECT 
    alerted_at,
    substr(token_address, 1, 8) as token,
    final_score
FROM alerted_tokens
ORDER BY ROWID DESC
LIMIT 10
""")

print(f"\nLast 10 signals:")
print(f"{'Timestamp':<25} {'Token':<10} {'Score'}")
print("-" * 45)

for row in c.fetchall():
    ts, token, score = row
    print(f"{str(ts):<25} {token:<10} {score}")

# Check current time
now = datetime.now().timestamp()
print(f"\nCurrent time (unix): {now}")
print(f"Current time (readable): {datetime.now()}")

# Check how many signals in different time ranges
print(f"\nSignals by time range:")

# Last hour
c.execute("SELECT COUNT(*) FROM alerted_tokens WHERE CAST(alerted_at AS REAL) > ?", (now - 3600,))
print(f"  Last 1 hour: {c.fetchone()[0]}")

# Last 24 hours  
c.execute("SELECT COUNT(*) FROM alerted_tokens WHERE CAST(alerted_at AS REAL) > ?", (now - 86400,))
print(f"  Last 24 hours: {c.fetchone()[0]}")

# Last 7 days
c.execute("SELECT COUNT(*) FROM alerted_tokens WHERE CAST(alerted_at AS REAL) > ?", (now - 604800,))
print(f"  Last 7 days: {c.fetchone()[0]}")

conn.close()

print("\n" + "="*60)

