"""
Token Balance Query - Get Actual On-Chain Token Balances
Prevents Error 6025 by querying real balance before selling
"""
from solana.rpc.api import Client as SolanaClient
from solders.pubkey import Pubkey
from typing import Optional
import base58


def get_token_balance(rpc_client: SolanaClient, wallet_pubkey: str, token_mint: str) -> Optional[float]:
    """
    Get the ACTUAL token balance from on-chain data
    
    Args:
        rpc_client: Solana RPC client
        wallet_pubkey: Wallet public key (str)
        token_mint: Token mint address (str)
        
    Returns:
        Actual token balance (float) or None if not found
    """
    try:
        wallet_pk = Pubkey.from_string(wallet_pubkey)
        token_pk = Pubkey.from_string(token_mint)
        
        # Get all token accounts for this wallet
        response = rpc_client.get_token_accounts_by_owner(
            wallet_pk,
            {"mint": token_pk}
        )
        
        if not hasattr(response, 'value') or not response.value:
            print(f"[BALANCE] No token account found for {token_mint[:8]}...", flush=True)
            return None
        
        # Usually there's only one token account per mint
        token_accounts = response.value
        if len(token_accounts) == 0:
            return None
        
        # Get balance from first account (should be only one)
        account = token_accounts[0]
        
        # The account data contains the token balance
        if hasattr(account, 'account') and hasattr(account.account, 'data'):
            # Parse token account data
            # Token account layout: https://spl.solana.com/token#account-layout
            # We need to call getAccountInfo to get full data
            account_pubkey = account.pubkey
            account_info = rpc_client.get_account_info(account_pubkey)
            
            if hasattr(account_info, 'value') and account_info.value:
                # Parse the account data
                # For SPL tokens, amount is at bytes 64-72 (u64 little-endian)
                data = account_info.value.data
                if len(data) >= 72:
                    # Extract amount (u64 at offset 64)
                    amount_bytes = data[64:72]
                    amount_raw = int.from_bytes(amount_bytes, 'little')
                    
                    # Get decimals
                    # We'll return raw amount and let caller handle decimals
                    return float(amount_raw)
        
        # Fallback: try to get balance from tokenAmount if available
        if hasattr(account, 'account') and hasattr(account.account, 'data'):
            # Try JSON RPC response format
            try:
                response_json = rpc_client.get_token_account_balance(token_accounts[0].pubkey)
                if hasattr(response_json, 'value'):
                    token_amount = response_json.value
                    if hasattr(token_amount, 'ui_amount') and token_amount.ui_amount is not None:
                        return float(token_amount.ui_amount)
                    if hasattr(token_amount, 'amount') and hasattr(token_amount, 'decimals'):
                        raw_amount = int(token_amount.amount)
                        decimals = int(token_amount.decimals)
                        return float(raw_amount) / (10 ** decimals)
            except Exception as e:
                print(f"[BALANCE] Error getting token account balance: {e}", flush=True)
        
        return None
        
    except Exception as e:
        print(f"[BALANCE] Error querying token balance: {e}", flush=True)
        return None


def get_token_balance_simple(rpc_client: SolanaClient, wallet_pubkey: str, token_mint: str) -> Optional[float]:
    """
    Simplified token balance query using Associated Token Account (ATA)
    
    Returns balance in tokens (with decimals applied), or 0.0 if no account exists
    """
    try:
        from solders.token.associated import get_associated_token_address
        
        wallet_pk = Pubkey.from_string(wallet_pubkey)
        token_pk = Pubkey.from_string(token_mint)
        
        # Get the Associated Token Account (ATA) for this wallet+mint
        # This is the standard way to find a token account
        ata = get_associated_token_address(wallet_pk, token_pk)
        
        # Query the balance for that specific account
        balance_response = rpc_client.get_token_account_balance(ata)
        
        if hasattr(balance_response, 'value') and balance_response.value:
            token_amount = balance_response.value
            
            # Try ui_amount first (human-readable with decimals)
            if hasattr(token_amount, 'ui_amount') and token_amount.ui_amount is not None:
                balance = float(token_amount.ui_amount)
                print(f"[BALANCE] ✅ On-chain balance: {balance:.4f} tokens", flush=True)
                return balance
            
            # Fallback to manual calculation
            if hasattr(token_amount, 'amount') and hasattr(token_amount, 'decimals'):
                raw = int(token_amount.amount)
                decimals = int(token_amount.decimals)
                balance = float(raw) / (10 ** decimals)
                print(f"[BALANCE] ✅ On-chain balance: {balance:.4f} tokens (calculated)", flush=True)
                return balance
        
        print(f"[BALANCE] ⚠️ Could not parse balance response", flush=True)
        return 0.0
        
    except Exception as e:
        error_msg = str(e)
        if "could not find account" in error_msg:
            # Token account doesn't exist = 0 balance
            print(f"[BALANCE] ℹ️ No token account exists (0 balance)", flush=True)
            return 0.0
        else:
            print(f"[BALANCE] ❌ Error: {e}", flush=True)
            return None  # Unknown error, fall back to database

