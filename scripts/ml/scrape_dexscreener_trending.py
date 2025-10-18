#!/usr/bin/env python3
"""
Scrape trending tokens from DexScreener website
More reliable than API for finding recent pumps
"""
import requests
import time
import sqlite3
import json
from typing import List, Dict
from datetime import datetime

DEXSCREENER_API = "https://api.dexscreener.com/latest/dex"


def get_token_data_from_pair(pair_address: str, chain: str = "solana") -> Dict:
    """
    Get token data from a specific pair address
    """
    try:
        url = f"{DEXSCREENER_API}/pairs/{chain}/{pair_address}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'pair' in data:
                return data['pair']
            elif 'pairs' in data and len(data['pairs']) > 0:
                return data['pairs'][0]
        
        return None
        
    except Exception as e:
        print(f"   Error: {e}")
        return None


def convert_pair_to_ml_format(pair: Dict) -> Dict:
    """Convert DexScreener pair to ML training format"""
    
    # Extract token info
    token_address = pair.get('baseToken', {}).get('address', '')
    token_name = pair.get('baseToken', {}).get('name', '')
    token_symbol = pair.get('baseToken', {}).get('symbol', '')
    
    # Current metrics
    price_usd = float(pair.get('priceUsd', 0))
    market_cap = float(pair.get('fdv', 0))
    liquidity = float(pair.get('liquidity', {}).get('usd', 0))
    volume_24h = float(pair.get('volume', {}).get('h24', 0))
    
    # Price changes
    change_5m = float(pair.get('priceChange', {}).get('m5', 0))
    change_1h = float(pair.get('priceChange', {}).get('h1', 0))
    change_6h = float(pair.get('priceChange', {}).get('h6', 0))
    change_24h = float(pair.get('priceChange', {}).get('h24', 0))
    
    # Calculate max gain
    max_gain = max(change_5m, change_1h, change_6h, change_24h)
    
    # Estimate entry metrics (assume caught at start of pump)
    if change_24h > 0:
        entry_multiplier = 100 / (100 + change_24h)
        entry_price = price_usd * entry_multiplier
        entry_mcap = market_cap * entry_multiplier
    else:
        entry_price = price_usd
        entry_mcap = market_cap
    
    # Peak metrics
    peak_multiplier = 1 + (max_gain / 100)
    peak_price = entry_price * peak_multiplier
    peak_mcap = entry_mcap * peak_multiplier
    
    # Timestamps
    pair_created = pair.get('pairCreatedAt', 0)
    alert_time = pair_created / 1000 if pair_created else int(time.time())
    
    return {
        'token_address': token_address,
        'token_name': token_name,
        'token_symbol': token_symbol,
        'pair_address': pair.get('pairAddress', ''),
        'dex': pair.get('dexId', ''),
        'alert_time': alert_time,
        'entry_price': entry_price,
        'entry_mcap': entry_mcap,
        'entry_liquidity': liquidity,
        'current_price': price_usd,
        'current_mcap': market_cap,
        'current_liquidity': liquidity,
        'volume_24h': volume_24h,
        'peak_price': peak_price,
        'peak_mcap': peak_mcap,
        'change_5m': change_5m,
        'change_1h': change_1h,
        'change_6h': change_6h,
        'change_24h': change_24h,
        'max_gain': max_gain,
        'is_2x_winner': max_gain >= 100,
    }


def scrape_from_pair_list(pair_addresses: List[str], chain: str = "solana") -> List[Dict]:
    """
    Scrape data from a list of pair addresses
    
    Args:
        pair_addresses: List of DexScreener pair addresses
        chain: Blockchain (default: solana)
    
    Returns:
        List of ML-formatted token data
    """
    print(f"\nScraping {len(pair_addresses)} pairs...")
    
    ml_data = []
    
    for i, pair_addr in enumerate(pair_addresses, 1):
        print(f"   [{i}/{len(pair_addresses)}] {pair_addr[:8]}...", end=" ")
        
        pair = get_token_data_from_pair(pair_addr, chain)
        
        if pair:
            ml_format = convert_pair_to_ml_format(pair)
            ml_data.append(ml_format)
            
            symbol = ml_format['token_symbol']
            gain = ml_format['max_gain']
            winner = "[2x+]" if ml_format['is_2x_winner'] else ""
            print(f"{symbol} ({gain:.1f}%) {winner}")
        else:
            print("Failed")
        
        # Rate limiting
        time.sleep(1.2)
    
    return ml_data


def save_to_ml_database(ml_data: List[Dict], db_path: str = "var/dexscreener_ml_data.db"):
    """Save scraped data to ML training database"""
    
    print(f"\nSaving {len(ml_data)} tokens to {db_path}...")
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Create tables
    c.execute("""
    CREATE TABLE IF NOT EXISTS alerted_tokens (
        token_address TEXT PRIMARY KEY,
        alerted_at REAL,
        final_score INTEGER,
        smart_money_detected INTEGER,
        conviction_type TEXT
    )
    """)
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS alerted_token_stats (
        token_address TEXT PRIMARY KEY,
        first_alert_at REAL,
        last_checked_at REAL,
        preliminary_score INTEGER,
        final_score INTEGER,
        conviction_type TEXT,
        first_price_usd REAL,
        first_market_cap_usd REAL,
        first_liquidity_usd REAL,
        last_price_usd REAL,
        last_market_cap_usd REAL,
        last_liquidity_usd REAL,
        last_volume_24h_usd REAL,
        peak_price_usd REAL,
        peak_market_cap_usd REAL,
        peak_price_at REAL,
        peak_market_cap_at REAL,
        price_change_1h REAL,
        price_change_6h REAL,
        price_change_24h REAL,
        max_gain_percent REAL,
        max_drawdown_percent REAL,
        is_rug INTEGER,
        token_name TEXT,
        token_symbol TEXT
    )
    """)
    
    # Insert data
    for data in ml_data:
        c.execute("""
        INSERT OR REPLACE INTO alerted_tokens 
        (token_address, alerted_at, final_score, smart_money_detected, conviction_type)
        VALUES (?, ?, ?, ?, ?)
        """, (
            data['token_address'],
            data['alert_time'],
            8,
            0,
            'DexScreener Historical'
        ))
        
        c.execute("""
        INSERT OR REPLACE INTO alerted_token_stats
        (token_address, first_alert_at, last_checked_at, preliminary_score, final_score,
         conviction_type, first_price_usd, first_market_cap_usd, first_liquidity_usd,
         last_price_usd, last_market_cap_usd, last_liquidity_usd, last_volume_24h_usd,
         peak_price_usd, peak_market_cap_usd, peak_price_at, peak_market_cap_at,
         price_change_1h, price_change_6h, price_change_24h, max_gain_percent,
         max_drawdown_percent, is_rug, token_name, token_symbol)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['token_address'],
            data['alert_time'],
            int(time.time()),
            8, 8,
            'DexScreener Historical',
            data['entry_price'], data['entry_mcap'], data['entry_liquidity'],
            data['current_price'], data['current_mcap'], data['current_liquidity'],
            data['volume_24h'],
            data['peak_price'], data['peak_mcap'],
            data['alert_time'], data['alert_time'],
            data['change_1h'], data['change_6h'], data['change_24h'],
            data['max_gain'],
            0, 0,
            data['token_name'], data['token_symbol']
        ))
    
    conn.commit()
    conn.close()
    
    print("   Saved successfully!")


def analyze_patterns(ml_data: List[Dict]):
    """Analyze patterns in the scraped data"""
    
    if not ml_data:
        print("\nNo data to analyze")
        return
    
    winners = [d for d in ml_data if d['is_2x_winner']]
    
    print("\n" + "="*60)
    print("ANALYSIS OF SCRAPED DATA")
    print("="*60)
    
    print(f"\nTotal tokens: {len(ml_data)}")
    print(f"2x+ winners: {len(winners)} ({100*len(winners)/len(ml_data):.1f}%)")
    
    if winners:
        print(f"\nWINNERS (2x+) CHARACTERISTICS:")
        
        avg_mcap = sum(d['entry_mcap'] for d in winners) / len(winners)
        avg_liq = sum(d['entry_liquidity'] for d in winners) / len(winners)
        avg_vol = sum(d['volume_24h'] for d in winners) / len(winners)
        avg_gain = sum(d['max_gain'] for d in winners) / len(winners)
        
        print(f"   Avg Entry Market Cap: ${avg_mcap:,.0f}")
        print(f"   Avg Entry Liquidity: ${avg_liq:,.0f}")
        print(f"   Avg 24h Volume: ${avg_vol:,.0f}")
        print(f"   Avg Max Gain: {avg_gain:.1f}%")
        
        # Find sweet spots
        mcaps = sorted([d['entry_mcap'] for d in winners])
        liqs = sorted([d['entry_liquidity'] for d in winners])
        
        print(f"\nSWEET SPOTS:")
        print(f"   Market Cap Range: ${mcaps[0]:,.0f} - ${mcaps[-1]:,.0f}")
        print(f"   Median Market Cap: ${mcaps[len(mcaps)//2]:,.0f}")
        print(f"   Liquidity Range: ${liqs[0]:,.0f} - ${liqs[-1]:,.0f}")
        print(f"   Median Liquidity: ${liqs[len(liqs)//2]:,.0f}")


def main():
    print("="*60)
    print("DEXSCREENER TRENDING SCRAPER")
    print("="*60)
    print("\nThis tool scrapes DexScreener pair data for ML training")
    print("\nTo use:")
    print("1. Go to https://dexscreener.com/solana?rankBy=trendingScoreH24&order=desc")
    print("2. Copy pair addresses of tokens that pumped 2x+")
    print("3. Create 'pair_list.txt' with one pair address per line")
    print("4. Run this script")
    print("="*60)
    
    # Check for pair list file
    pair_file = "pair_list.txt"
    
    try:
        with open(pair_file, 'r') as f:
            pair_addresses = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
        
        if not pair_addresses:
            print(f"\nERROR: {pair_file} is empty")
            print("\nExample pair_list.txt content:")
            print("7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU")
            print("58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2")
            return
        
        print(f"\nFound {len(pair_addresses)} pairs in {pair_file}")
        
        # Scrape data
        ml_data = scrape_from_pair_list(pair_addresses)
        
        if not ml_data:
            print("\nNo data collected")
            return
        
        # Analyze
        analyze_patterns(ml_data)
        
        # Save
        save_to_ml_database(ml_data)
        
        print("\n" + "="*60)
        print("COMPLETE!")
        print("="*60)
        print(f"\nNext steps:")
        print(f"1. Review var/dexscreener_ml_data.db")
        print(f"2. Train ML: python scripts/ml/train_model.py var/dexscreener_ml_data.db")
        
    except FileNotFoundError:
        print(f"\nERROR: {pair_file} not found")
        print("\nCreate this file with pair addresses from DexScreener")
        print("\nExample:")
        print("  1. Visit: https://dexscreener.com/solana?rankBy=trendingScoreH24")
        print("  2. Click on a token")
        print("  3. Copy the pair address from the URL")
        print("  4. Add to pair_list.txt (one per line)")


if __name__ == "__main__":
    main()

