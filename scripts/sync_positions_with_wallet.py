#!/usr/bin/env python3
"""
One-time script to sync database positions with actual on-chain balances.

This fixes the phantom position bug where DB shows 6,980 tokens but wallet has 0.87.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tradingSystem.db import _conn, update_position_qty, close_position
from src.tradingSystem.token_balance import get_token_balance_simple
from solders.keypair import Keypair  # type: ignore
from base58 import b58decode
import time

def main():
    print("=" * 80)
    print("POSITION SYNC SCRIPT - Fixing Database Quantity Mismatches")
    print("=" * 80)
    
    # Connect to database
    conn = _conn()
    cur = conn.cursor()
    
    # Get all open positions
    cur.execute("SELECT id, token_address, qty FROM positions WHERE status=?", ("open",))
    positions = cur.fetchall()
    
    if not positions:
        print("\n✅ No open positions found. Nothing to sync.")
        return
    
    print(f"\nFound {len(positions)} open positions. Checking on-chain balances...\n")
    
    # Get wallet address from environment
    wallet_key = os.getenv("WALLET_KEY")
    if not wallet_key:
        print("❌ ERROR: WALLET_KEY environment variable not set!")
        return
    
    kp = Keypair.from_bytes(b58decode(wallet_key))
    wallet_address = str(kp.pubkey())
    
    # Use Solana mainnet RPC
    rpc_url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    
    synced = 0
    closed = 0
    errors = 0
    
    for pos_id, token, db_qty in positions:
        try:
            print(f"Position #{pos_id} - {token[:12]}...")
            print(f"  DB quantity: {db_qty:.4f} tokens")
            
            # Get actual on-chain balance
            actual_qty = get_token_balance_simple(rpc_url, wallet_address, token)
            
            if actual_qty is None:
                print(f"  ⚠️ Could not fetch balance (token may be invalid)")
                errors += 1
                time.sleep(0.5)
                continue
            
            print(f"  Wallet balance: {actual_qty:.4f} tokens")
            
            # Calculate difference
            diff_pct = abs(actual_qty - db_qty) / db_qty * 100 if db_qty > 0 else 0
            
            if diff_pct < 5:
                # Close enough (< 5% difference)
                print(f"  ✅ Quantities match (diff: {diff_pct:.1f}%)")
            elif actual_qty < 0.01:
                # Dust or zero balance - close position
                print(f"  🧹 CLOSING: Dust/zero balance ({actual_qty:.6f} tokens)")
                close_position(pos_id)
                closed += 1
            else:
                # Significant difference - update database
                print(f"  🔧 SYNCING: {db_qty:.4f} → {actual_qty:.4f} (diff: {diff_pct:.1f}%)")
                update_position_qty(pos_id, actual_qty)
                synced += 1
            
            time.sleep(0.5)  # Rate limit
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            errors += 1
    
    conn.close()
    
    print("\n" + "=" * 80)
    print("SYNC COMPLETE")
    print("=" * 80)
    print(f"✅ Synced: {synced} positions")
    print(f"🧹 Closed: {closed} dust positions")
    print(f"❌ Errors: {errors} positions")
    print("=" * 80)
    
    if synced > 0 or closed > 0:
        print("\n🎯 Database is now synced with wallet!")
        print("📊 Trader bot will now monitor with correct quantities.")
    

if __name__ == "__main__":
    main()

