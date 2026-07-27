#!/usr/bin/env python3
"""
Diagnose and fix ghost positions issue
"""
import sqlite3
import os

# CRITICAL FIX: Bot uses deployment/var/, not root var/
db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'deployment', 'var', 'trading.db')

print(f"Connecting to: {db_path}")
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Check all positions
print("\n=== ALL POSITIONS ===")
c.execute("SELECT id, token_address, status FROM positions ORDER BY id DESC LIMIT 20")
for row in c.fetchall():
    pid, token, status = row
    print(f"  #{pid}: {token[:8]}... status={status}")

# Count open positions
c.execute("SELECT COUNT(*) FROM positions WHERE status='open'")
open_count = c.fetchone()[0]
print(f"\n=== OPEN POSITIONS COUNT: {open_count} ===")

if open_count > 0:
    print("\n=== OPEN POSITIONS DETAILS ===")
    c.execute("SELECT id, token_address FROM positions WHERE status='open'")
    open_positions = c.fetchall()
    for pid, token in open_positions:
        print(f"  #{pid}: {token}")
    
    print(f"\n=== CLOSING {open_count} OPEN POSITIONS ===")
    c.execute("UPDATE positions SET status='closed' WHERE status='open'")
    conn.commit()
    print(f"✅ Closed {c.rowcount} positions")
    
    # Verify
    c.execute("SELECT COUNT(*) FROM positions WHERE status='open'")
    remaining = c.fetchone()[0]
    print(f"\n=== VERIFICATION: {remaining} open positions remaining ===")
    
    if remaining == 0:
        print("🎯 SUCCESS! All positions closed")
    else:
        print(f"⚠️ WARNING: {remaining} positions still open")
else:
    print("✅ No open positions found in database")

conn.close()

