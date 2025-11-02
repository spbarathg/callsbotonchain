#!/usr/bin/env python3
"""Check trading history for a specific token"""

import sqlite3
import sys

db_path = '/app/var/trading.db'
token = 'SPeoKNTCG4knwrCC2pgAS98CMqnpy8AY1PyHmKyV7fE'

print(f"🔍 Searching for token: {token[:15]}...\n")

conn = sqlite3.connect(db_path)
c = conn.cursor()

# Check positions table
c.execute("SELECT * FROM positions WHERE token_address LIKE ?", (f"{token[:8]}%",))
positions = c.fetchall()

if positions:
    print(f"📊 Found {len(positions)} position(s):\n")
    for pos in positions:
        print(f"  Position #{pos[0]}:")
        print(f"    Token: {pos[1]}")
        print(f"    Strategy: {pos[2]}")
        print(f"    Entry Price: ${pos[3]}")
        print(f"    Qty: {pos[4]}")
        print(f"    USD Size: ${pos[5]}")
        print(f"    Opened: {pos[6]}")
        print(f"    Peak Price: ${pos[7]}")
        print(f"    Trail %: {pos[8]}")
        print(f"    Status: {pos[9]}")
        print()
        
        # Get fills for this position
        c.execute("SELECT * FROM fills WHERE position_id=?", (pos[0],))
        fills = c.fetchall()
        if fills:
            print(f"  Fills ({len(fills)}):")
            for fill in fills:
                print(f"    {fill[2]}: {fill[4]} tokens @ ${fill[3]} = ${fill[5]} ({fill[6]})")
            print()
else:
    print(f"❌ No positions found for {token[:15]}...")

conn.close()






