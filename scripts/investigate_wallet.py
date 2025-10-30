#!/usr/bin/env python3
"""
Investigate wallet transaction history to find missing $8
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solders.keypair import Keypair
from solana.rpc.api import Client
from base58 import b58decode, b58encode
import json

def main():
    wallet_key = os.getenv("TS_WALLET_SECRET") or os.getenv("WALLET_KEY")
    if not wallet_key:
        print("❌ ERROR: TS_WALLET_SECRET or WALLET_KEY not set")
        return
    
    kp = Keypair.from_bytes(b58decode(wallet_key))
    wallet_address = str(kp.pubkey())
    
    print("=" * 80)
    print(f"INVESTIGATING WALLET: {wallet_address}")
    print("=" * 80)
    
    # Connect to RPC
    rpc_url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    client = Client(rpc_url)
    
    # Get recent signatures
    print("\n🔍 Fetching transaction history...")
    try:
        signatures_response = client.get_signatures_for_address(kp.pubkey(), limit=20)
        signatures = signatures_response.value
        
        print(f"\n✅ Found {len(signatures)} recent transactions\n")
        
        for i, sig_info in enumerate(signatures, 1):
            sig = str(sig_info.signature)
            slot = sig_info.slot
            err = sig_info.err
            block_time = sig_info.block_time
            
            status = "❌ FAILED" if err else "✅ SUCCESS"
            
            print(f"{i}. {status}")
            print(f"   Signature: {sig}")
            print(f"   Slot: {slot}")
            print(f"   Time: {block_time}")
            
            # Get transaction details
            try:
                tx_response = client.get_transaction(
                    sig_info.signature,
                    encoding="jsonParsed",
                    max_supported_transaction_version=0
                )
                
                if tx_response.value:
                    tx = tx_response.value
                    meta = tx.transaction.meta
                    
                    # Get SOL balance changes
                    if meta and meta.pre_balances and meta.post_balances:
                        pre_sol = meta.pre_balances[0] / 1e9
                        post_sol = meta.post_balances[0] / 1e9
                        sol_change = post_sol - pre_sol
                        
                        print(f"   SOL Change: {sol_change:.6f} SOL")
                        print(f"   Pre:  {pre_sol:.6f} SOL")
                        print(f"   Post: {post_sol:.6f} SOL")
                    
                    # Check if HvSPeTtLYcv99wTpJyUyVuB177AJvKkNVw6uJ3uVW8ZB is involved
                    target_address = "HvSPeTtLYcv99wTpJyUyVuB177AJvKkNVw6uJ3uVW8ZB"
                    tx_str = str(tx)
                    if target_address in tx_str:
                        print(f"   🚨 CONTAINS ADDRESS: {target_address}")
                    
            except Exception as e:
                print(f"   ⚠️ Could not fetch details: {e}")
            
            print()
    
    except Exception as e:
        print(f"❌ Error fetching signatures: {e}")
    
    # Get current balance
    print("\n" + "=" * 80)
    print("CURRENT WALLET BALANCE")
    print("=" * 80)
    try:
        balance_response = client.get_balance(kp.pubkey())
        balance_sol = balance_response.value / 1e9
        print(f"SOL Balance: {balance_sol:.6f} SOL (~${balance_sol * 197:.2f} @ $197/SOL)")
    except Exception as e:
        print(f"❌ Error fetching balance: {e}")

if __name__ == "__main__":
    main()

