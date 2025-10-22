"""
Dynamic Wallet Balance Reader
Reads actual SOL/USDC balance from wallet instead of using hardcoded values
"""
import json
import os
import time
import base58 as b58
from solana.rpc.api import Client as SolanaClient
from solders.keypair import Keypair
from solders.pubkey import Pubkey
import requests
from typing import Optional


def get_wallet_balance_usd(rpc_url: str, wallet_secret: str, usdc_mint: str) -> float:
    """
    Get current wallet balance in USD.
    
    Args:
        rpc_url: Solana RPC endpoint
        wallet_secret: Wallet private key (base58 or JSON array)
        usdc_mint: USDC mint address
    
    Returns:
        Total balance in USD (SOL + USDC converted to USD)
    """
    try:
        # Load keypair
        secret = wallet_secret.strip()
        if secret.startswith("["):
            arr = json.loads(secret)
            kp = Keypair.from_bytes(bytes(arr))
        else:
            kp = Keypair.from_bytes(b58.b58decode(secret))
        
        pubkey = kp.pubkey()
        client = SolanaClient(rpc_url)
        
        # Get SOL balance
        sol_balance_lamports = client.get_balance(pubkey).value
        sol_balance = sol_balance_lamports / 1e9  # Convert lamports to SOL
        
        # Get SOL price in USD
        sol_price_usd = get_sol_price_usd()
        sol_value_usd = sol_balance * sol_price_usd
        
        # Get USDC balance (SPL token)
        usdc_balance_usd = 0.0
        try:
            # Get token accounts for USDC
            from spl.token.instructions import get_associated_token_address
            usdc_pubkey = Pubkey.from_string(usdc_mint)
            
            # Get the associated token address
            ata = get_associated_token_address(pubkey, usdc_pubkey)
            
            # Get token account balance
            token_account_info = client.get_token_account_balance(ata)
            if token_account_info and token_account_info.value:
                usdc_balance_usd = float(token_account_info.value.ui_amount or 0)
                print(f"[WALLET] USDC balance: ${usdc_balance_usd:.2f}")
        except Exception as e:
            print(f"[WALLET] Could not fetch USDC balance: {e}")
        
        total_usd = sol_value_usd + usdc_balance_usd
        
        print(f"[WALLET] Balance: {sol_balance:.4f} SOL (${sol_value_usd:.2f}) + ${usdc_balance_usd:.2f} USDC = ${total_usd:.2f} total")
        
        return total_usd
        
    except Exception as e:
        print(f"[WALLET] Error reading balance: {e}")
        # Return 0 to prevent trading without knowing balance
        return 0.0


def get_sol_price_usd() -> float:
    """Get current SOL price in USD"""
    try:
        # Try CoinGecko (free, no API key)
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
            timeout=5
        )
        if resp.status_code == 200:
            price = float(resp.json()["solana"]["usd"])
            return price
    except Exception:
        pass
    
    # Fallback to conservative estimate
    return 180.0


def get_cached_balance(cache_file: str = "var/wallet_balance_cache.json") -> Optional[float]:
    """Get cached balance (for rate limiting)"""
    try:
        import os
        if os.path.exists(cache_file):
            import time
            stat = os.stat(cache_file)
            age = time.time() - stat.st_mtime
            
            # Cache valid for 60 seconds
            if age < 60:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    return data.get('balance_usd')
    except Exception:
        pass
    return None


def cache_balance(balance_usd: float, cache_file: str = "var/wallet_balance_cache.json"):
    """Cache balance to reduce RPC calls"""
    try:
        import os
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, 'w') as f:
            json.dump({
                'balance_usd': balance_usd,
                'timestamp': time.time()
            }, f)
    except Exception:
        pass


def get_wallet_balance_cached(rpc_url: str, wallet_secret: str, usdc_mint: str) -> float:
    """Get wallet balance with caching (preferred method)"""
    # Try cache first
    cached = get_cached_balance()
    if cached is not None:
        return cached
    
    # Fetch fresh balance
    balance = get_wallet_balance_usd(rpc_url, wallet_secret, usdc_mint)
    
    # Cache it
    cache_balance(balance)
    
    return balance

