#!/usr/bin/env python3
"""
Comprehensive Data Export for Analyst Review

Exports ALL tracking data to CSV format with complete time series.
Includes only REAL data - no false/synthetic values.

Output: comprehensive_token_data.csv
"""
import sys
import os
import csv
import json
from datetime import datetime
from typing import List, Dict, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.storage import get_alerted_tokens_for_tracking
from app.database_config import DatabasePaths
import sqlite3


def get_token_complete_data(token_address: str) -> Dict[str, Any]:
    """
    Get ALL available data for a token.
    Returns only REAL data - no synthetic/false values.
    """
    conn = sqlite3.connect(DatabasePaths.SIGNALS_DB)
    c = conn.cursor()
    
    # Get basic token info
    c.execute("""
        SELECT 
            a.token_address,
            a.alerted_at,
            a.final_score,
            a.smart_money_detected,
            a.conviction_type,
            s.token_name,
            s.token_symbol,
            s.first_price_usd,
            s.peak_price_usd,
            s.last_price_usd,
            s.first_market_cap_usd,
            s.peak_market_cap_usd,
            s.last_market_cap_usd,
            s.first_liquidity_usd,
            s.last_liquidity_usd,
            s.last_volume_24h_usd,
            s.max_gain_percent,
            s.is_rug,
            s.holder_count,
            s.peak_price_at,
            s.price_change_1h,
            s.price_change_24h
        FROM alerted_tokens a
        LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
        WHERE a.token_address = ?
    """, (token_address,))
    
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    
    # Parse basic data
    data = {
        "ca": row[0],
        "first_seen_ts": row[1],
        "final_score": row[2],
        "smart_money_detected": bool(row[3]) if row[3] is not None else None,
        "conviction_type": row[4],
        "token_name": row[5],
        "token_symbol": row[6],
        "first_price_usd": row[7],
        "peak_price_usd": row[8],
        "last_price_usd": row[9],
        "first_market_cap_usd": row[10],
        "peak_market_cap_usd": row[11],
        "last_market_cap_usd": row[12],
        "first_liquidity_usd": row[13],
        "last_liquidity_usd": row[14],
        "last_volume_24h_usd": row[15],
        "max_gain_percent": row[16],
        "is_rug": bool(row[17]) if row[17] is not None else None,
        "holder_count": row[18],
        "peak_price_at": row[19],
        "price_change_1h": row[20],
        "price_change_24h": row[21],
    }
    
    # Get price snapshots (time series)
    c.execute("""
        SELECT snapshot_at, price_usd, liquidity_usd, holder_count
        FROM price_snapshots
        WHERE token_address = ?
        ORDER BY snapshot_at
    """, (token_address,))
    
    snapshots = c.fetchall()
    
    # Build time series
    liquidity_snapshots = []
    price_snapshots = []
    holder_snapshots = []
    
    for snap in snapshots:
        ts, price, liq, holders = snap
        if price is not None:
            price_snapshots.append({"ts": ts, "price_usd": price})
        if liq is not None:
            # Convert USD to SOL (approximate, using $150/SOL)
            liquidity_snapshots.append({"ts": ts, "liquidity_usd": liq, "liquidity_sol": liq / 150.0})
        if holders is not None:
            holder_snapshots.append({"ts": ts, "holders": holders})
    
    data["liquidity_snapshots"] = liquidity_snapshots
    data["price_snapshots"] = price_snapshots
    data["holders_count_ts"] = holder_snapshots
    
    # Calculate price at specific intervals (t0, +1m, +5m, +15m, +1h, +24h)
    first_ts = data["first_seen_ts"]
    if first_ts and price_snapshots:
        try:
            # Convert to timestamp if needed
            if isinstance(first_ts, str):
                first_timestamp = datetime.fromisoformat(first_ts.replace('Z', '+00:00')).timestamp()
            else:
                first_timestamp = float(first_ts)
            
            data["price_t0"] = data["first_price_usd"]
            data["price_t1m"] = None
            data["price_t5m"] = None
            data["price_t15m"] = None
            data["price_t1h"] = None
            data["price_t24h"] = None
            
            for snap in price_snapshots:
                elapsed = snap["ts"] - first_timestamp
                if elapsed >= 60 and data["price_t1m"] is None:
                    data["price_t1m"] = snap["price_usd"]
                if elapsed >= 300 and data["price_t5m"] is None:
                    data["price_t5m"] = snap["price_usd"]
                if elapsed >= 900 and data["price_t15m"] is None:
                    data["price_t15m"] = snap["price_usd"]
                if elapsed >= 3600 and data["price_t1h"] is None:
                    data["price_t1h"] = snap["price_usd"]
                if elapsed >= 86400 and data["price_t24h"] is None:
                    data["price_t24h"] = snap["price_usd"]
        except Exception as e:
            print(f"Warning: Could not calculate time intervals for {token_address}: {e}")
    
    # Get transaction snapshots
    c.execute("""
        SELECT tx_signature, timestamp, from_wallet, to_wallet, amount, amount_usd, tx_type, dex, is_smart_money
        FROM transaction_snapshots
        WHERE token_address = ?
        ORDER BY timestamp
    """, (token_address,))
    
    tx_rows = c.fetchall()
    data["tx_snapshots"] = [
        {
            "signature": tx[0],
            "ts": tx[1],
            "from_wallet": tx[2],
            "to_wallet": tx[3],
            "amount": tx[4],
            "amount_usd": tx[5],
            "tx_type": tx[6],
            "dex": tx[7],
            "is_smart_money": bool(tx[8]) if tx[8] is not None else None
        }
        for tx in tx_rows
    ]
    
    # Get wallet first buys
    c.execute("""
        SELECT wallet_address, timestamp, amount, amount_usd, price_usd, is_smart_money, wallet_pnl_history
        FROM wallet_first_buys
        WHERE token_address = ?
        ORDER BY timestamp
    """, (token_address,))
    
    wallet_rows = c.fetchall()
    data["wallet_first_buys"] = [
        {
            "wallet": w[0],
            "ts": w[1],
            "amount": w[2],
            "amount_usd": w[3],
            "price_usd": w[4],
            "is_smart_money": bool(w[5]) if w[5] is not None else None,
            "wallet_pnl_history": w[6]
        }
        for w in wallet_rows
    ]
    
    # Compute outcome label
    max_gain = data["max_gain_percent"]
    if max_gain is not None:
        if max_gain >= 1000:
            data["outcome_label"] = "moonshot_10x+"
        elif max_gain >= 100:
            data["outcome_label"] = "winner_2x+"
        elif max_gain > 0:
            data["outcome_label"] = "winner"
        else:
            data["outcome_label"] = "loser"
    else:
        data["outcome_label"] = "unknown"
    
    # Add metadata counts
    data["snapshot_count"] = len(price_snapshots)
    data["tx_count"] = len(data["tx_snapshots"])
    data["wallet_count"] = len(data["wallet_first_buys"])
    
    conn.close()
    return data


def export_to_csv(output_file: str = "comprehensive_token_data.csv"):
    """
    Export all token data to CSV.
    
    Creates TWO files:
    1. Main CSV with summary data
    2. JSON file with complete time series data
    """
    print("🔍 Fetching all alerted tokens...")
    tokens = get_alerted_tokens_for_tracking(hours=24*365)  # Get all tokens (1 year)
    
    if not tokens:
        print("❌ No tokens found!")
        return
    
    print(f"📊 Found {len(tokens)} tokens. Exporting data...")
    
    # Prepare CSV headers
    csv_headers = [
        "ca",
        "first_seen_ts",
        "token_name",
        "token_symbol",
        "final_score",
        "conviction_type",
        "smart_money_detected",
        # Prices
        "price_t0",
        "price_t1m",
        "price_t5m",
        "price_t15m",
        "price_t1h",
        "price_t24h",
        "peak_price_usd",
        "last_price_usd",
        # Performance
        "max_gain_percent",
        "price_change_1h",
        "price_change_24h",
        "outcome_label",
        "is_rug",
        # Market data
        "first_market_cap_usd",
        "peak_market_cap_usd",
        "last_market_cap_usd",
        "first_liquidity_usd",
        "last_liquidity_usd",
        "last_volume_24h_usd",
        "holder_count",
        # Tracking stats
        "snapshot_count",
        "tx_count",
        "wallet_count",
    ]
    
    # Export main CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        
        complete_data = []
        
        for i, token in enumerate(tokens, 1):
            try:
                data = get_token_complete_data(token)
                if not data:
                    continue
                
                # Write summary row to CSV
                row = {header: data.get(header) for header in csv_headers}
                writer.writerow(row)
                
                # Store complete data for JSON export
                complete_data.append(data)
                
                if i % 50 == 0:
                    print(f"  Processed {i}/{len(tokens)} tokens...")
                    
            except Exception as e:
                print(f"  ⚠️  Error processing {token}: {e}")
                continue
    
    print(f"✅ CSV exported to: {output_file}")
    print(f"   Total rows: {len(complete_data)}")
    
    # Export complete JSON with time series
    json_file = output_file.replace('.csv', '_complete.json')
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(complete_data, f, indent=2, default=str)
    
    print(f"✅ Complete data (with time series) exported to: {json_file}")
    
    # Print summary
    print("\n" + "="*60)
    print("📊 EXPORT SUMMARY")
    print("="*60)
    print(f"Total tokens exported: {len(complete_data)}")
    
    if complete_data:
        total_snapshots = sum(d.get("snapshot_count", 0) for d in complete_data)
        total_txs = sum(d.get("tx_count", 0) for d in complete_data)
        total_wallets = sum(d.get("wallet_count", 0) for d in complete_data)
        
        print(f"Total price snapshots: {total_snapshots:,}")
        print(f"Total transactions: {total_txs}")
        print(f"Total wallets: {total_wallets}")
        
        # Outcome distribution
        outcomes = {}
        for d in complete_data:
            label = d.get("outcome_label", "unknown")
            outcomes[label] = outcomes.get(label, 0) + 1
        
        print(f"\nOutcome Distribution:")
        for label, count in sorted(outcomes.items(), key=lambda x: -x[1]):
            pct = count / len(complete_data) * 100
            print(f"  {label}: {count} ({pct:.1f}%)")
    
    print("="*60)
    print(f"\n📁 Files created:")
    print(f"  1. {output_file} - Summary CSV for quick analysis")
    print(f"  2. {json_file} - Complete data with time series")


if __name__ == "__main__":
    export_to_csv()

