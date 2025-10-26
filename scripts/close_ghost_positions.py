#!/usr/bin/env python3
"""
Force-close ghost positions (database shows tokens but wallet has 0 balance)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tradingSystem.db import close_position, list_open_positions

def main():
    """Force-close ghost positions"""
    print("=" * 80)
    print("GHOST POSITION CLEANUP")
    print("=" * 80)
    
    # Ghost positions identified from logs:
    # 1. mcQH5ehZ - Shows tokens but wallet has 0 balance
    # 2. 2VRC6F23 - Shows tokens but wallet has 0 balance (failed partial sell)
    
    ghost_tokens = [
        "mcQH5ehZHCaC6MNdv1fy9ZrntxqWmZBYnk8CM8rxRoX",
        "2VRC6F23CjLv3nBHnNw41ua21jACWKcFmbWH4KohNKWU"
    ]
    
    print(f"\n🔍 Searching for ghost positions...")
    
    # Get all open positions
    open_positions = list_open_positions()
    
    for pos in open_positions:
        token = pos.get("token", "")
        pos_id = pos.get("id")
        qty = pos.get("qty", 0)
        entry_price = pos.get("entry_price", 0)
        
        if token in ghost_tokens:
            print(f"\n🚨 GHOST POSITION FOUND:")
            print(f"   Position ID: {pos_id}")
            print(f"   Token: {token[:8]}...")
            print(f"   Database qty: {qty:.4f} tokens")
            print(f"   Entry price: ${entry_price:.8f}")
            print(f"   ⚠️ Wallet balance: 0 tokens (GHOST)")
            
            # Force close with 0 exit price (ghost position, no actual sale)
            print(f"   ✅ Force-closing position #{pos_id}...")
            close_position(
                pid=pos_id,
                exit_price=0.0,
                exit_type="ghost_cleanup",
                reason="Ghost position: Database showed tokens but wallet had 0 balance"
            )
            print(f"   ✅ Position #{pos_id} closed successfully")
    
    print("\n" + "=" * 80)
    print("✅ GHOST CLEANUP COMPLETE")
    print("=" * 80)
    print("\nAll ghost positions have been removed from the database.")
    print("Future ghost buys will be prevented by the new balance verification logic.")

if __name__ == "__main__":
    main()

