#!/usr/bin/env python3
"""
Enrich Token Data with Cielo API

Fetches missing transaction and wallet data from Cielo API for all tokens.
ONE-TIME ENRICHMENT - Uses credits carefully.

Strategy:
1. Only fetch for tokens that don't have transaction/wallet data
2. Batch requests efficiently
3. Use budget tracking to avoid overuse
4. Save progress incrementally
"""
import sys
import os
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config_unified import CIELO_API_KEY
from app.http_client import request_json
from app.storage import record_transaction_snapshot, record_wallet_first_buy
from app.database_config import DatabasePaths
from app.budget import get_budget
import sqlite3


def get_token_transactions_cielo(token_address: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Fetch recent transactions from Cielo API.
    
    Endpoint: GET /api/v1/token/{address}/transactions
    or similar - trying common patterns
    """
    if not CIELO_API_KEY:
        print("❌ No Cielo API key found!")
        return []
    
    # Try multiple endpoint patterns
    endpoints = [
        f"https://api.cielo.finance/api/v1/token/{token_address}/transactions",
        f"https://feed-api.cielo.finance/api/v1/token/{token_address}/transactions",
        f"https://api.cielo.finance/api/v1/tokens/{token_address}/trades",
        f"https://feed-api.cielo.finance/api/v1/tokens/{token_address}/trades",
    ]
    
    headers = {"X-API-Key": CIELO_API_KEY}
    params = {"limit": limit, "chain": "solana"}
    
    for endpoint in endpoints:
        try:
            result = request_json("GET", endpoint, headers=headers, params=params, timeout=10)
            
            if result.get("status_code") == 200:
                data = result.get("json") or {}
                
                # Try different response formats
                transactions = (
                    data.get("transactions") or 
                    data.get("trades") or 
                    data.get("data", {}).get("transactions") or
                    data.get("data", {}).get("trades") or
                    []
                )
                
                if transactions:
                    print(f"  ✅ Found {len(transactions)} transactions from Cielo")
                    return transactions
                    
        except Exception as e:
            continue
    
    return []


def get_token_holders_cielo(token_address: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Fetch top holders/buyers from Cielo API.
    
    Endpoint: GET /api/v1/token/{address}/holders
    or similar
    """
    if not CIELO_API_KEY:
        return []
    
    # Try multiple endpoint patterns
    endpoints = [
        f"https://api.cielo.finance/api/v1/token/{token_address}/holders",
        f"https://feed-api.cielo.finance/api/v1/token/{token_address}/holders",
        f"https://api.cielo.finance/api/v1/tokens/{token_address}/buyers",
        f"https://feed-api.cielo.finance/api/v1/tokens/{token_address}/buyers",
    ]
    
    headers = {"X-API-Key": CIELO_API_KEY}
    params = {"limit": limit, "chain": "solana"}
    
    for endpoint in endpoints:
        try:
            result = request_json("GET", endpoint, headers=headers, params=params, timeout=10)
            
            if result.get("status_code") == 200:
                data = result.get("json") or {}
                
                # Try different response formats
                holders = (
                    data.get("holders") or 
                    data.get("buyers") or 
                    data.get("data", {}).get("holders") or
                    data.get("data", {}).get("buyers") or
                    []
                )
                
                if holders:
                    print(f"  ✅ Found {len(holders)} holders from Cielo")
                    return holders
                    
        except Exception as e:
            continue
    
    return []


def enrich_token_data(token_address: str, token_name: str = None) -> Dict[str, int]:
    """
    Enrich a single token with transaction and wallet data from Cielo.
    
    Returns dict with counts: {tx_added: int, wallets_added: int}
    """
    stats = {"tx_added": 0, "wallets_added": 0}
    
    # Check if already has data
    conn = sqlite3.connect(DatabasePaths.SIGNALS_DB)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM transaction_snapshots WHERE token_address = ?", (token_address,))
    existing_txs = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM wallet_first_buys WHERE token_address = ?", (token_address,))
    existing_wallets = c.fetchone()[0]
    
    conn.close()
    
    # Skip if already enriched
    if existing_txs >= 10 and existing_wallets >= 10:
        print(f"  ⏭️  Already enriched ({existing_txs} txs, {existing_wallets} wallets)")
        return stats
    
    print(f"  🔍 Enriching {token_name or token_address[:8]}...")
    
    # Fetch transactions
    if existing_txs < 10:
        transactions = get_token_transactions_cielo(token_address, limit=50)
        
        for tx in transactions:
            try:
                # Parse transaction data (format may vary)
                signature = tx.get("signature") or tx.get("tx_hash") or tx.get("hash")
                timestamp = tx.get("timestamp") or tx.get("block_time") or time.time()
                from_wallet = tx.get("from") or tx.get("from_wallet") or tx.get("wallet")
                to_wallet = tx.get("to") or tx.get("to_wallet")
                amount = tx.get("amount") or tx.get("token_amount")
                amount_usd = tx.get("amount_usd") or tx.get("usd_value") or tx.get("value_usd")
                tx_type = tx.get("type") or tx.get("tx_type") or "swap"
                dex = tx.get("dex") or tx.get("exchange") or "unknown"
                is_smart = tx.get("smart_money") or tx.get("is_smart_money") or False
                
                if signature and from_wallet:
                    record_transaction_snapshot(
                        token_address=token_address,
                        tx_signature=signature,
                        timestamp=timestamp,
                        from_wallet=from_wallet,
                        to_wallet=to_wallet,
                        amount=amount,
                        amount_usd=amount_usd,
                        tx_type=tx_type,
                        dex=dex,
                        is_smart_money=is_smart
                    )
                    stats["tx_added"] += 1
                    
            except Exception as e:
                print(f"    ⚠️  Error recording transaction: {e}")
                continue
    
    # Fetch holders/buyers
    if existing_wallets < 10:
        holders = get_token_holders_cielo(token_address, limit=20)
        
        for holder in holders:
            try:
                # Parse holder data (format may vary)
                wallet = holder.get("wallet") or holder.get("address") or holder.get("holder")
                timestamp = holder.get("first_buy_time") or holder.get("timestamp") or time.time()
                amount = holder.get("amount") or holder.get("balance")
                amount_usd = holder.get("amount_usd") or holder.get("value_usd")
                price_usd = holder.get("price_usd") or holder.get("entry_price")
                is_smart = holder.get("smart_money") or holder.get("is_smart_money") or False
                pnl = holder.get("pnl") or holder.get("total_pnl_usd")
                
                if wallet:
                    record_wallet_first_buy(
                        token_address=token_address,
                        wallet_address=wallet,
                        timestamp=timestamp,
                        amount=amount,
                        amount_usd=amount_usd,
                        price_usd=price_usd,
                        is_smart_money=is_smart,
                        wallet_pnl_history=pnl
                    )
                    stats["wallets_added"] += 1
                    
            except Exception as e:
                print(f"    ⚠️  Error recording wallet: {e}")
                continue
    
    if stats["tx_added"] > 0 or stats["wallets_added"] > 0:
        print(f"  ✅ Added {stats['tx_added']} txs, {stats['wallets_added']} wallets")
    
    return stats


def enrich_all_tokens(max_tokens: int = 100):
    """
    Enrich all tokens that don't have transaction/wallet data.
    
    Args:
        max_tokens: Maximum number of tokens to enrich (to control API usage)
    """
    # Check budget first
    try:
        budget = get_budget()
        if not budget.can_spend("stats"):
            print("❌ Budget exhausted! Cannot enrich data.")
            return
    except Exception as e:
        print(f"⚠️  Budget check failed: {e}")
        print("Proceeding with caution...")
    
    print("🔍 Finding tokens that need enrichment...")
    
    # Get tokens that don't have much transaction/wallet data
    conn = sqlite3.connect(DatabasePaths.SIGNALS_DB)
    c = conn.cursor()
    
    c.execute("""
        SELECT 
            a.token_address,
            s.token_name,
            s.token_symbol,
            COUNT(DISTINCT t.id) as tx_count,
            COUNT(DISTINCT w.id) as wallet_count
        FROM alerted_tokens a
        LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
        LEFT JOIN transaction_snapshots t ON a.token_address = t.token_address
        LEFT JOIN wallet_first_buys w ON a.token_address = w.token_address
        GROUP BY a.token_address
        HAVING tx_count < 10 OR wallet_count < 10
        ORDER BY a.alerted_at DESC
        LIMIT ?
    """, (max_tokens,))
    
    tokens = c.fetchall()
    conn.close()
    
    if not tokens:
        print("✅ All tokens already enriched!")
        return
    
    print(f"📊 Found {len(tokens)} tokens to enrich (max {max_tokens})")
    print(f"⚠️  This will use Cielo API credits. Proceeding carefully...\n")
    
    total_stats = {"tx_added": 0, "wallets_added": 0, "tokens_enriched": 0}
    
    for i, (token_address, name, symbol, tx_count, wallet_count) in enumerate(tokens, 1):
        print(f"\n[{i}/{len(tokens)}] {name or symbol or token_address[:8]}...")
        print(f"  Current: {tx_count} txs, {wallet_count} wallets")
        
        try:
            stats = enrich_token_data(token_address, name or symbol)
            
            if stats["tx_added"] > 0 or stats["wallets_added"] > 0:
                total_stats["tx_added"] += stats["tx_added"]
                total_stats["wallets_added"] += stats["wallets_added"]
                total_stats["tokens_enriched"] += 1
            
            # Rate limiting - be gentle with API
            time.sleep(2)
            
            # Check budget every 10 tokens
            if i % 10 == 0:
                try:
                    budget = get_budget()
                    if not budget.can_spend("stats"):
                        print("\n⚠️  Budget limit reached! Stopping enrichment.")
                        break
                except:
                    pass
                    
        except Exception as e:
            print(f"  ❌ Error: {e}")
            continue
    
    # Summary
    print("\n" + "="*60)
    print("📊 ENRICHMENT SUMMARY")
    print("="*60)
    print(f"Tokens processed: {len(tokens)}")
    print(f"Tokens enriched: {total_stats['tokens_enriched']}")
    print(f"Transactions added: {total_stats['tx_added']}")
    print(f"Wallets added: {total_stats['wallets_added']}")
    print("="*60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Enrich token data with Cielo API")
    parser.add_argument("--max-tokens", type=int, default=100, help="Maximum tokens to enrich (default: 100)")
    parser.add_argument("--token", type=str, help="Enrich specific token address")
    
    args = parser.parse_args()
    
    if args.token:
        print(f"🔍 Enriching single token: {args.token}")
        stats = enrich_token_data(args.token)
        print(f"\n✅ Added {stats['tx_added']} txs, {stats['wallets_added']} wallets")
    else:
        enrich_all_tokens(max_tokens=args.max_tokens)

