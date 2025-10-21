"""
Clean up ghost positions (quantity=0) from trading database.

These are positions that were created but never filled, causing the exit loop
to spam Jupiter API with price checks and trigger rate limits.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tradingSystem.db import get_db

def cleanup_ghost_positions():
    """Close all positions with quantity=0"""
    db = get_db()
    
    # Get all open positions
    positions = db.get_open_positions()
    
    print(f"Found {len(positions)} open positions")
    
    ghost_count = 0
    for pos in positions:
        token = pos["token_address"]
        qty = pos.get("quantity", 0)
        
        if qty == 0:
            print(f"  Ghost position: {token[:12]}... (qty=0) - CLOSING")
            # Close the position in the database
            db.close_position(
                token_address=token,
                exit_price=pos.get("entry_price", 0),
                exit_reason="ghost_cleanup",
                pnl_percent=0.0
            )
            ghost_count += 1
        else:
            print(f"  Real position: {token[:12]}... (qty={qty}) - KEEPING")
    
    print(f"\nCleaned up {ghost_count} ghost positions")
    
    # Verify
    remaining = db.get_open_positions()
    print(f"Remaining open positions: {len(remaining)}")
    for pos in remaining:
        print(f"  - {pos['token_address'][:12]}... qty={pos.get('quantity', 0)}")

if __name__ == "__main__":
    cleanup_ghost_positions()

