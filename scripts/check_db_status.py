#!/usr/bin/env python3
"""Check database status"""

import sqlite3

db_path = '/app/deployment/var/trading.db'

print(f"🔍 Checking: {db_path}\n")
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Check positions table
c.execute("SELECT COUNT(*) FROM positions")
total_positions = c.fetchone()[0]
print(f"📊 Total positions: {total_positions}")

c.execute("SELECT COUNT(*) FROM positions WHERE status='open'")
open_positions = c.fetchone()[0]
print(f"📊 Open positions: {open_positions}")

c.execute("SELECT COUNT(*) FROM positions WHERE status='closed'")
closed_positions = c.fetchone()[0]
print(f"📊 Closed positions: {closed_positions}")

if open_positions > 0:
    print(f"\n⚠️  Found {open_positions} OPEN positions:")
    c.execute("SELECT id, token_address, status FROM positions WHERE status='open'")
    for row in c.fetchall():
        print(f"  #{row[0]}: {row[1][:15]}... status={row[2]}")

conn.close()
print("\n✅ Done")






