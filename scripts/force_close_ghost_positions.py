#!/usr/bin/env python3
"""
Force-close ghost positions that can't be sold
"""
import sys
import os
import sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tradingSystem.db import _conn

def main():
    """Force-close ghost positions"""
    print("=" * 80)
    print("GHOST POSITION CLEANUP")
    print("=" * 80)
    
    # These positions show as "open" but have no liquidity or negligible dust
    ghost_tokens = [
        "HRDHMH8LGR4do6rv2Hgd16y85R18xUeio1YFygKzpump",  # RUG - no liquidity
        "GHTsyY8doW5vziZXgpmkDdfAypMeFjeaVZ9HYpU7sYK9",  # RUG - no liquidity  
        "6bD71gqiAkdh4SVCVqy6X2F7o96n1RXL5JaWYU9xpump",  # Already sold - $95 profit
        "zgQnq6GEUWuEEa2QvqT69amJtKaj7oU4nKDP4cTpump",  # Mostly sold - $180 recovered, dust remaining
    ]
    
    conn = _conn()
    
    print(f"\n🔍 Searching for ghost positions...")
    
    for token in ghost_tokens:
        cur = conn.execute(
            "SELECT id, token_address, qty, entry_price, entry_usd, status FROM positions WHERE token_address = ? AND status = 'open'",
            (token,)
        )
        row = cur.fetchone()
        
        if row:
            pos_id, token_addr, qty, entry_price, entry_usd, status = row
            print(f"\n🚨 GHOST POSITION FOUND:")
            print(f"   Position ID: {pos_id}")
            print(f"   Token: {token_addr[:12]}...")
            print(f"   Database qty: {qty:.4f} tokens")
            print(f"   Entry: ${entry_usd:.2f}")
            print(f"   Status: {status}")
            print(f"   ⚠️ Marking as closed (ghost/rugged)")
            
            # Mark as closed with 0 exit (rugged/ghost position)
            conn.execute(
                "UPDATE positions SET status = 'closed', exit_price = 0, exit_usd = 0, exit_type = 'ghost_cleanup' WHERE id = ?",
                (pos_id,)
            )
            conn.commit()
            print(f"   ✅ Position #{pos_id} closed")
    
    print("\n" + "=" * 80)
    print("✅ GHOST CLEANUP COMPLETE")
    print("=" * 80)
    
    # Show remaining open positions
    cur = conn.execute("SELECT COUNT(*) FROM positions WHERE status = 'open'")
    remaining = cur.fetchone()[0]
    print(f"\nRemaining open positions: {remaining}")

if __name__ == "__main__":
    main()

