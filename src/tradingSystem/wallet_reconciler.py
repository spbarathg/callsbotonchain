"""
WALLET RECONCILIATION SYSTEM
Make wallet the source of truth, not the database

PROBLEM: Database becomes stale when:
1. Manual sales outside bot (tokens disappear from wallet, DB still shows open)
2. Failed transactions (DB updated but wallet unchanged)
3. Rugged tokens (worthless but DB shows position)
4. Unknown tokens (bought outside bot, wallet has them but DB doesn't)

SOLUTION: Wallet-first reconciliation
- On startup: Scan ALL token accounts in wallet
- Compare wallet reality with database
- Auto-close positions with 0 balance
- Auto-add unknown positions (optional)
- Periodic reconciliation checks
"""
import os
import json
from typing import Dict, List, Tuple, Optional
from solana.rpc.api import Client as SolanaClient
from solders.keypair import Keypair
from solders.pubkey import Pubkey
import base58 as b58


class WalletReconciler:
    """Reconcile database positions with actual wallet holdings"""
    
    def __init__(self, rpc_url: str, wallet_secret: str):
        """
        Args:
            rpc_url: Solana RPC endpoint
            wallet_secret: Wallet private key (base58 or JSON array)
        """
        self.rpc_url = rpc_url
        self.client = SolanaClient(rpc_url)
        
        # Load keypair
        secret = wallet_secret.strip()
        if secret.startswith("["):
            arr = json.loads(secret)
            self.keypair = Keypair.from_bytes(bytes(arr))
        else:
            self.keypair = Keypair.from_bytes(b58.b58decode(secret))
        
        self.pubkey = self.keypair.pubkey()
    
    def get_all_token_holdings(self, min_value_usd: float = 0.1) -> Dict[str, float]:
        """
        Scan wallet for ALL token accounts with actual balances
        
        Args:
            min_value_usd: Minimum USD value to consider (filter out dust)
        
        Returns:
            Dict[token_address, balance_in_tokens]
        """
        print(f"[RECONCILER] ≡ƒöì Scanning wallet {str(self.pubkey)[:8]}... for all token holdings", flush=True)
        
        holdings = {}
        
        try:
            # SIMPLIFIED APPROACH: Use get_token_accounts_by_owner_json_parsed
            # This returns parsed JSON data instead of raw bytes, avoiding encoding issues
            from solana.rpc.types import TokenAccountOpts
            
            # Get all SPL token accounts (filter by SPL Token program)
            spl_program = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
            response = self.client.get_token_accounts_by_owner_json_parsed(
                self.pubkey,
                TokenAccountOpts(program_id=spl_program)
            )
            
            if not hasattr(response, 'value') or not response.value:
                print(f"[RECONCILER] No token accounts found", flush=True)
                return holdings
            
            token_accounts = response.value
            print(f"[RECONCILER] Found {len(token_accounts)} token accounts", flush=True)
            
            for account in token_accounts:
                try:
                    # With json_parsed, we get structured data directly
                    if not hasattr(account, 'account') or not account.account:
                        continue
                    
                    account_data = account.account
                    
                    # Get parsed token info
                    if hasattr(account_data, 'data') and hasattr(account_data.data, 'parsed'):
                        parsed = account_data.data.parsed
                        if isinstance(parsed, dict):
                            info = parsed.get('info', {})
                            mint_address = info.get('mint', '')
                            token_amount = info.get('tokenAmount', {})
                            
                            # Get balance
                            if isinstance(token_amount, dict):
                                ui_amount = token_amount.get('uiAmount')
                                if ui_amount is not None and ui_amount > 0:
                                    balance = float(ui_amount)
                                    holdings[mint_address] = balance
                                    print(f"[RECONCILER]   Γ£ô {mint_address[:12]}... = {balance:.4f} tokens", flush=True)
                
                except Exception as e:
                    print(f"[RECONCILER] ΓÜá∩╕Å Error processing token account: {e}", flush=True)
                    continue
            
            print(f"[RECONCILER] Γ£à Found {len(holdings)} tokens with non-zero balance", flush=True)
            return holdings
            
        except Exception as e:
            print(f"[RECONCILER] Γ¥î Error scanning wallet: {e}", flush=True)
            return holdings
    
    def reconcile_with_database(self, auto_close_missing: bool = True, auto_add_unknown: bool = False) -> Tuple[List[int], List[str]]:
        """
        Reconcile database positions with wallet reality
        
        Args:
            auto_close_missing: Automatically close DB positions with 0 wallet balance
            auto_add_unknown: Automatically add DB positions for unknown wallet tokens
        
        Returns:
            Tuple of (closed_position_ids, added_token_addresses)
        """
        print(f"\n[RECONCILER] ≡ƒöä Starting wallet reconciliation...", flush=True)
        
        # Get all tokens in wallet
        wallet_tokens = self.get_all_token_holdings(min_value_usd=0.1)
        
        # Get all open positions from database
        from .db import init, _conn, close_position
        init()
        conn = _conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, token_address, qty FROM positions WHERE status='open'")
        db_positions = cursor.fetchall()
        
        closed_ids = []
        added_tokens = []
        
        print(f"[RECONCILER] Database shows {len(db_positions)} open positions", flush=True)
        print(f"[RECONCILER] Wallet contains {len(wallet_tokens)} token accounts", flush=True)
        
        # Check each DB position against wallet
        for pid, token, db_qty in db_positions:
            wallet_qty = wallet_tokens.get(token, 0.0)
            
            if wallet_qty == 0:
                # Position in DB but not in wallet (or zero balance)
                print(f"[RECONCILER] ΓÜá∩╕Å  DB Position #{pid} ({token[:12]}...): DB={db_qty:.4f}, Wallet=0.0", flush=True)
                
                if auto_close_missing:
                    print(f"[RECONCILER] ≡ƒùæ∩╕Å  Auto-closing position #{pid} (zero wallet balance)", flush=True)
                    close_position(pid)
                    closed_ids.append(pid)
            else:
                # Check for quantity mismatch
                diff_pct = abs(wallet_qty - db_qty) / db_qty * 100 if db_qty > 0 else 100
                if diff_pct > 5:  # >5% mismatch
                    print(f"[RECONCILER] ΓÜá∩╕Å  Quantity mismatch for {token[:12]}...: DB={db_qty:.4f}, Wallet={wallet_qty:.4f} ({diff_pct:.1f}% diff)", flush=True)
                    # Could update DB qty here, but risky without knowing trade history
                else:
                    print(f"[RECONCILER] Γ£à Position #{pid} ({token[:12]}...): Verified", flush=True)
        
        # Check for unknown tokens in wallet (not in DB)
        db_tokens = {token for _, token, _ in db_positions}
        unknown_tokens = set(wallet_tokens.keys()) - db_tokens
        
        if unknown_tokens:
            print(f"[RECONCILER] ≡ƒåò Found {len(unknown_tokens)} tokens in wallet NOT in database:", flush=True)
            for token in unknown_tokens:
                balance = wallet_tokens[token]
                print(f"[RECONCILER]   - {token[:12]}... ({balance:.4f} tokens)", flush=True)
                
                if auto_add_unknown:
                    # Optionally create positions for these
                    # (Disabled by default - risky to auto-add without entry price)
                    print(f"[RECONCILER]   ΓÜá∩╕Å  Skipping auto-add (no entry price known)", flush=True)
                    added_tokens.append(token)
        
        conn.close()
        
        print(f"\n[RECONCILER] Γ£à Reconciliation complete:", flush=True)
        print(f"  - Closed {len(closed_ids)} stale positions", flush=True)
        print(f"  - Found {len(unknown_tokens)} unknown tokens", flush=True)
        
        return closed_ids, added_tokens


def reconcile_on_startup(rpc_url: str, wallet_secret: str):
    """
    Run wallet reconciliation on bot startup
    Call this from cli_optimized.py before starting trading
    """
    try:
        reconciler = WalletReconciler(rpc_url, wallet_secret)
        closed, added = reconciler.reconcile_with_database(
            auto_close_missing=True,  # Close DB positions with 0 wallet balance
            auto_add_unknown=False    # Don't auto-add unknown tokens (no entry price)
        )
        return True
    except Exception as e:
        print(f"[RECONCILER] Γ¥î Reconciliation failed: {e}", flush=True)
        return False

