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


def get_token_balance_simple(rpc_client: SolanaClient, wallet_pubkey: str, token_mint: str, retries: int = 3, verbose: bool = True) -> Optional[float]:
    """
    ROBUST token balance query - uses JSON-RPC to find ANY token account for this mint
    Not just the standard ATA (which can miss some tokens on Solana)
    
    CRITICAL FIX: Added retries to handle Solana public RPC inconsistency
    Public RPC (api.mainnet-beta.solana.com) is load-balanced and different nodes
    may have different data. Retrying helps get consistent results.
    
    Args:
        rpc_client: Solana RPC client
        wallet_pubkey: Wallet public key (str)
        token_mint: Token mint address (str)
        retries: Number of retry attempts (default 3)
        verbose: Print debug messages (default True)
    
    Returns balance in tokens (with decimals applied), or 0.0 if no account exists
    """
    import requests
    import time
    
    last_balance = None
    
    for attempt in range(retries):
        try:
            # Get RPC URL from the client
            rpc_url = rpc_client._provider.endpoint_uri
            
            # Method 1: Use JSON-RPC getTokenAccountsByOwner (MOST RELIABLE)
            # This finds ALL token accounts for this mint, not just standard ATA
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    wallet_pubkey,
                    {"mint": token_mint},
                    {"encoding": "jsonParsed"}
                ]
            }
            
            resp = requests.post(rpc_url, json=payload, timeout=30)
            data = resp.json()
            
            if 'result' in data and data['result']['value']:
                # Found token account(s) for this mint
                for acc in data['result']['value']:
                    info = acc['account']['data']['parsed']['info']
                    if info['mint'] == token_mint:
                        balance = info['tokenAmount']['uiAmount']
                        if balance is not None and balance > 0:
                            if verbose:
                                print(f"[BALANCE] ✅ Found {balance:.4f} tokens via JSON-RPC", flush=True)
                            return float(balance)
                # Accounts exist but 0 balance
                last_balance = 0.0
            else:
                # No accounts found - but might be RPC inconsistency
                last_balance = 0.0
            
            # If we got 0, retry with a delay (RPC load balancing issue)
            if attempt < retries - 1:
                wait_time = (attempt + 1) * 2  # 2s, 4s, 6s
                if verbose and attempt == 0:
                    print(f"[BALANCE] ⏳ No tokens found, retrying ({attempt+1}/{retries})...", flush=True)
                time.sleep(wait_time)
                continue
            
            # Final attempt still shows 0
            if verbose:
                print(f"[BALANCE] ℹ️ No token account for {token_mint[:8]}... (0 balance after {retries} checks)", flush=True)
            return 0.0
            
        except Exception as e:
            if verbose:
                print(f"[BALANCE] ❌ JSON-RPC error (attempt {attempt+1}): {e}", flush=True)
            
            if attempt < retries - 1:
                time.sleep(2)
                continue
            
            # Fallback to ATA method
            try:
                from solders.token.associated import get_associated_token_address
                
                wallet_pk = Pubkey.from_string(wallet_pubkey)
                token_pk = Pubkey.from_string(token_mint)
                ata = get_associated_token_address(wallet_pk, token_pk)
                
                balance_response = rpc_client.get_token_account_balance(ata)
                
                if hasattr(balance_response, 'value') and balance_response.value:
                    token_amount = balance_response.value
                    if hasattr(token_amount, 'ui_amount') and token_amount.ui_amount is not None:
                        balance = float(token_amount.ui_amount)
                        if verbose:
                            print(f"[BALANCE] ✅ ATA balance: {balance:.4f} tokens", flush=True)
                        return balance
                
                return 0.0
                
            except Exception as e2:
                if "could not find account" in str(e2):
                    if verbose:
                        print(f"[BALANCE] ℹ️ No ATA exists (0 balance)", flush=True)
                    return 0.0
                if verbose:
                    print(f"[BALANCE] ❌ ATA fallback error: {e2}", flush=True)
                return None
    
    return last_balance if last_balance is not None else 0.0

