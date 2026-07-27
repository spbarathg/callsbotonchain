#!/usr/bin/env python3
"""Emergency script to close ghost positions causing infinite loops"""

import sqlite3
import os

# Use correct database path for Docker container
# CRITICAL: Bot uses var/trading.db (relative to /app), NOT deployment/var/
db_path = '/app/var/trading.db'

print(f"🔍 Checking database: {db_path}")
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Check open positions
c.execute("SELECT id, token_address, status FROM positions WHERE status='open'")
open_positions = c.fetchall()

if not open_positions:
    print("✅ No open positions found")
else:
    print(f"\n📊 Found {len(open_positions)} open positions:")
    for pid, token, status in open_positions:
        print(f"  #{pid}: {token[:15]}... status={status}")
    
    print("\n🧹 Force-closing all ghost positions...")
    c.execute("UPDATE positions SET status='closed' WHERE status='open'")
    conn.commit()
    print(f"✅ Closed {c.rowcount} positions")

conn.close()
print("\n✅ Database cleanup complete!")

