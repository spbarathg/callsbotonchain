#!/usr/bin/env python3
"""Force close all open positions (orphaned from old wallet)"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tradingSystem.db import _conn

def main():
    conn = _conn()
    cur = conn.cursor()
    
    # Get all open positions
    cur.execute("SELECT id, token_address FROM positions WHERE status=?", ("open",))
    positions = cur.fetchall()
    
    if not positions:
        print("✅ No open positions found.")
        return
    
    print(f"🧹 Closing {len(positions)} orphaned positions from old wallet...\n")
    
    for pid, token in positions:
        cur.execute(
            "UPDATE positions SET status=? WHERE id=?",
            ("closed", pid)
        )
        print(f"  ✅ Closed position #{pid} - {token[:12]}...")
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ All {len(positions)} positions closed!")
    print("🎯 Bot ready for fresh start with new wallet!")

if __name__ == "__main__":
    main()

