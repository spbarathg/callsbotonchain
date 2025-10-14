#!/usr/bin/env python3
"""
Fetch Complete Token Data using Cielo Pro API

Uses Cielo Pro endpoints to get:
- Transaction history (tx_snapshots)
- Wallet first buys (wallet_first_buys)
- Token metadata (decimals, total_supply)

For all 770 tokens.
"""
import sys
import os
import time
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Get API key from environment
CIELO_API_KEY = os.getenv("CIELO_API_KEY")

try:
    from app.http_client import request_json
except:
    # Fallback if http_client not available
    import requests
    def request_json(method, url, headers=None, params=None, timeout=10):
        resp = requests.request(method, url, headers=headers, params=params, timeout=timeout)
        return {"status_code": resp.status_code, "json": resp.json() if resp.ok else {}}


def fetch_token_transactions_cielo_pro(token_address: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Fetch transaction history from Cielo Pro API.
    
    Cielo Pro endpoints to try:
    - /api/v1/token/transactions
    - /api/v1/trades
    """
    if not CIELO_API_KEY:
        print("❌ No Cielo API key!")
        return []
    
    headers = {"X-API-Key": CIELO_API_KEY}
    
    # Try different endpoint patterns for Cielo Pro
    endpoints = [
        ("https://api.cielo.finance/api/v1/token/transactions", {"token_address": token_address, "chain": "solana", "limit": limit}),
        ("https://feed-api.cielo.finance/api/v1/token/transactions", {"token_address": token_address, "chain": "solana", "limit": limit}),
        ("https://api.cielo.finance/api/v1/trades", {"token": token_address, "chain": "solana", "limit": limit}),
        ("https://api.cielo.finance/api/v1/token/trades", {"token_address": token_address, "chain": "solana", "limit": limit}),
    ]
    
    for url, params in endpoints:
        try:
            result = request_json("GET", url, headers=headers, params=params, timeout=15)
            
            if result.get("status_code") == 200:
                data = result.get("json") or {}
                
                # Try different response structures
                transactions = (
                    data.get("data", {}).get("transactions") or
                    data.get("data", {}).get("trades") or
                    data.get("transactions") or
                    data.get("trades") or
                    data.get("data", {}).get("items") or
                    []
                )
                
                if transactions and len(transactions) > 0:
                    return transactions
                    
        except Exception as e:
            continue
    
    return []


def fetch_token_holders_cielo_pro(token_address: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Fetch token holders from Cielo Pro API.
    """
    if not CIELO_API_KEY:
        return []
    
    headers = {"X-API-Key": CIELO_API_KEY}
    
    endpoints = [
        ("https://api.cielo.finance/api/v1/token/holders", {"token_address": token_address, "chain": "solana", "limit": limit}),
        ("https://feed-api.cielo.finance/api/v1/token/holders", {"token_address": token_address, "chain": "solana", "limit": limit}),
        ("https://api.cielo.finance/api/v1/token/top-holders", {"token_address": token_address, "chain": "solana", "limit": limit}),
    ]
    
    for url, params in endpoints:
        try:
            result = request_json("GET", url, headers=headers, params=params, timeout=15)
            
            if result.get("status_code") == 200:
                data = result.get("json") or {}
                
                holders = (
                    data.get("data", {}).get("holders") or
                    data.get("holders") or
                    data.get("data", {}).get("items") or
                    []
                )
                
                if holders and len(holders) > 0:
                    return holders
                    
        except Exception as e:
            continue
    
    return []


def fetch_token_metadata_cielo_pro(token_address: str) -> Dict[str, Any]:
    """
    Fetch token metadata (decimals, total_supply) from Cielo Pro.
    """
    if not CIELO_API_KEY:
        return {}
    
    headers = {"X-API-Key": CIELO_API_KEY}
    params = {"token_address": token_address, "chain": "solana"}
    
    endpoints = [
        "https://api.cielo.finance/api/v1/token/info",
        "https://feed-api.cielo.finance/api/v1/token/info",
        "https://api.cielo.finance/api/v1/token/metadata",
    ]
    
    for url in endpoints:
        try:
            result = request_json("GET", url, headers=headers, params=params, timeout=10)
            
            if result.get("status_code") == 200:
                data = result.get("json") or {}
                info = data.get("data") or data
                
                if info:
                    return {
                        "decimals": info.get("decimals"),
                        "total_supply": info.get("total_supply") or info.get("supply"),
                    }
                    
        except Exception as e:
            continue
    
    return {}


def enrich_token_complete(token_address: str, token_name: str = None) -> Dict[str, Any]:
    """
    Fetch ALL missing data for a token from Cielo Pro.
    
    Returns:
        {
            "tx_snapshots": [...],
            "wallet_first_buys": [...],
            "token_meta": {...}
        }
    """
    print(f"  🔍 Fetching data for {token_name or token_address[:8]}...")
    
    result = {
        "tx_snapshots": [],
        "wallet_first_buys": [],
        "token_meta": {}
    }
    
    # Fetch transactions
    print(f"    Fetching transactions...")
    transactions = fetch_token_transactions_cielo_pro(token_address, limit=100)
    
    if transactions:
        print(f"    ✅ Found {len(transactions)} transactions")
        for tx in transactions:
            try:
                # Parse transaction (adapt to actual Cielo Pro response format)
                result["tx_snapshots"].append({
                    "ts": tx.get("timestamp") or tx.get("block_time") or tx.get("time"),
                    "signature": tx.get("signature") or tx.get("tx_hash") or tx.get("hash"),
                    "from_wallet": tx.get("from") or tx.get("from_wallet") or tx.get("wallet"),
                    "to_wallet": tx.get("to") or tx.get("to_wallet"),
                    "amount": tx.get("amount") or tx.get("token_amount"),
                    "amount_usd": tx.get("amount_usd") or tx.get("usd_value") or tx.get("value_usd"),
                    "tx_type": tx.get("type") or tx.get("tx_type") or "swap",
                    "dex": tx.get("dex") or tx.get("exchange") or "unknown",
                    "is_smart_money": tx.get("smart_money") or tx.get("is_smart_money") or False
                })
            except Exception as e:
                continue
    else:
        print(f"    ⚠️  No transactions found")
    
    # Fetch holders/buyers
    print(f"    Fetching holders...")
    holders = fetch_token_holders_cielo_pro(token_address, limit=50)
    
    if holders:
        print(f"    ✅ Found {len(holders)} holders")
        for holder in holders:
            try:
                # Parse holder (adapt to actual Cielo Pro response format)
                result["wallet_first_buys"].append({
                    "wallet": holder.get("wallet") or holder.get("address") or holder.get("holder"),
                    "ts": holder.get("first_buy_time") or holder.get("timestamp") or holder.get("time"),
                    "amount": holder.get("amount") or holder.get("balance"),
                    "amount_usd": holder.get("amount_usd") or holder.get("value_usd"),
                    "price_usd": holder.get("price_usd") or holder.get("entry_price"),
                    "is_smart_money": holder.get("smart_money") or holder.get("is_smart_money") or False
                })
            except Exception as e:
                continue
    else:
        print(f"    ⚠️  No holders found")
    
    # Fetch metadata
    print(f"    Fetching metadata...")
    metadata = fetch_token_metadata_cielo_pro(token_address)
    
    if metadata:
        print(f"    ✅ Found metadata")
        result["token_meta"] = metadata
    else:
        print(f"    ⚠️  No metadata found")
    
    return result


def enrich_all_tokens():
    """
    Enrich all 770 tokens with Cielo Pro data.
    """
    print("🔍 Loading existing data...")
    
    # Load current JSON export
    with open("comprehensive_token_data_complete.json", "r", encoding="utf-8") as f:
        tokens = json.load(f)
    
    print(f"📊 Found {len(tokens)} tokens to enrich")
    print(f"⚠️  This will use Cielo Pro API credits\n")
    
    enriched_count = 0
    
    for i, token in enumerate(tokens, 1):
        token_address = token["ca"]
        token_name = token.get("token_name") or token.get("token_symbol")
        
        print(f"\n[{i}/{len(tokens)}] {token_name or token_address[:8]}...")
        
        # Check if already has data
        existing_txs = len(token.get("tx_snapshots", []))
        existing_wallets = len(token.get("wallet_first_buys", []))
        
        print(f"  Current: {existing_txs} txs, {existing_wallets} wallets")
        
        # Skip if already enriched
        if existing_txs >= 10 and existing_wallets >= 10:
            print(f"  ⏭️  Already enriched, skipping")
            continue
        
        try:
            # Fetch from Cielo Pro
            cielo_data = enrich_token_complete(token_address, token_name)
            
            # Merge with existing data
            if cielo_data["tx_snapshots"]:
                token["tx_snapshots"] = cielo_data["tx_snapshots"]
            
            if cielo_data["wallet_first_buys"]:
                token["wallet_first_buys"] = cielo_data["wallet_first_buys"]
            
            if cielo_data["token_meta"]:
                if "token_meta" not in token:
                    token["token_meta"] = {}
                token["token_meta"].update(cielo_data["token_meta"])
            
            enriched_count += 1
            
            # Save progress every 10 tokens
            if i % 10 == 0:
                print(f"\n💾 Saving progress...")
                with open("comprehensive_token_data_complete.json", "w", encoding="utf-8") as f:
                    json.dump(tokens, f, indent=2, default=str)
            
            # Rate limiting
            time.sleep(1)
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            continue
    
    # Final save
    print(f"\n💾 Saving final data...")
    with open("comprehensive_token_data_complete.json", "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2, default=str)
    
    # Summary
    print("\n" + "="*60)
    print("📊 ENRICHMENT COMPLETE")
    print("="*60)
    print(f"Tokens processed: {len(tokens)}")
    print(f"Tokens enriched: {enriched_count}")
    
    # Count totals
    total_txs = sum(len(t.get("tx_snapshots", [])) for t in tokens)
    total_wallets = sum(len(t.get("wallet_first_buys", [])) for t in tokens)
    
    print(f"Total transactions: {total_txs:,}")
    print(f"Total wallets: {total_wallets:,}")
    print("="*60)
    print(f"\n✅ Updated file: comprehensive_token_data_complete.json")


if __name__ == "__main__":
    enrich_all_tokens()

