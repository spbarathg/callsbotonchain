#!/usr/bin/env python3
"""
Scrape DexScreener for historical pump data to train ML
Finds tokens that pumped 2x+ in the past 1-2 weeks
"""
import requests
import time
import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# DexScreener API endpoints
DEXSCREENER_BASE = "https://api.dexscreener.com/latest/dex"
DEXSCREENER_SEARCH = f"{DEXSCREENER_BASE}/search"
DEXSCREENER_PAIRS = f"{DEXSCREENER_BASE}/pairs/solana"

def get_recent_gainers(min_age_hours: int = 24, max_age_hours: int = 336) -> List[Dict]:
    """
    Get tokens that have gained significantly in the past 1-2 weeks
    
    Args:
        min_age_hours: Minimum token age (24h = 1 day)
        max_age_hours: Maximum token age (336h = 2 weeks)
    
    Returns:
        List of token data dictionaries
    """
    print(f"\n🔍 Searching for tokens aged {min_age_hours}-{max_age_hours} hours...")
    
    gainers = []
    
    # Strategy 1: Get tokens from "gainers" endpoint
    try:
        print("\n📊 Fetching top gainers...")
        # DexScreener doesn't have a direct "gainers" API, but we can use search
        # We'll need to use their token boosts/trending data
        
        # Get tokens with high 24h volume (likely pumped recently)
        url = f"{DEXSCREENER_BASE}/tokens/solana"
        # Note: DexScreener API is limited, we'll use search with filters
        
        print("   ⚠️  DexScreener API is limited for historical data")
        print("   Using alternative approach: Recent high-volume tokens")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    return gainers


def scrape_token_history(token_address: str) -> Optional[Dict]:
    """
    Get historical data for a specific token
    
    Args:
        token_address: Solana token address
    
    Returns:
        Token data with historical metrics
    """
    try:
        url = f"{DEXSCREENER_PAIRS}/{token_address}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'pairs' in data and len(data['pairs']) > 0:
                pair = data['pairs'][0]  # Get primary pair
                
                # Extract relevant features
                token_data = {
                    'token_address': token_address,
                    'chain': 'solana',
                    'dex': pair.get('dexId', ''),
                    'pair_address': pair.get('pairAddress', ''),
                    
                    # Current metrics
                    'price_usd': float(pair.get('priceUsd', 0)),
                    'liquidity_usd': float(pair.get('liquidity', {}).get('usd', 0)),
                    'market_cap_usd': float(pair.get('fdv', 0)),  # Fully diluted valuation
                    'volume_24h': float(pair.get('volume', {}).get('h24', 0)),
                    
                    # Price changes (these are our targets!)
                    'change_5m': float(pair.get('priceChange', {}).get('m5', 0)),
                    'change_1h': float(pair.get('priceChange', {}).get('h1', 0)),
                    'change_6h': float(pair.get('priceChange', {}).get('h6', 0)),
                    'change_24h': float(pair.get('priceChange', {}).get('h24', 0)),
                    
                    # Token info
                    'token_name': pair.get('baseToken', {}).get('name', ''),
                    'token_symbol': pair.get('baseToken', {}).get('symbol', ''),
                    
                    # Timing
                    'pair_created_at': pair.get('pairCreatedAt', 0),
                    'scraped_at': int(time.time()),
                }
                
                # Calculate if it's a 2x+ winner
                # If 24h change >= 100%, it's a 2x winner
                token_data['is_2x_winner'] = token_data['change_24h'] >= 100
                
                # Calculate peak gain (use highest of all timeframes)
                max_gain = max(
                    token_data['change_5m'],
                    token_data['change_1h'],
                    token_data['change_6h'],
                    token_data['change_24h']
                )
                token_data['max_gain_percent'] = max_gain
                
                return token_data
        
        return None
        
    except Exception as e:
        print(f"   ❌ Error scraping {token_address}: {e}")
        return None


def get_trending_tokens() -> List[str]:
    """
    Get list of trending token addresses from DexScreener
    These are likely recent pumps
    """
    print("\n🔥 Fetching trending tokens...")
    
    # DexScreener trending endpoint (if available)
    # Note: This may require web scraping as API is limited
    
    # For now, we'll use a different approach:
    # Search for recently created pairs with high volume
    
    trending = []
    
    # Sample approach: Get tokens from Raydium (popular Solana DEX)
    # with recent activity
    
    print("   ℹ️  Using search-based approach for trending tokens")
    
    return trending


def scrape_from_token_list(token_file: str = "known_pumps.txt") -> List[Dict]:
    """
    Scrape data from a list of known pump tokens
    
    Args:
        token_file: File containing token addresses (one per line)
    
    Returns:
        List of scraped token data
    """
    import os
    
    if not os.path.exists(token_file):
        print(f"⚠️  Token list file not found: {token_file}")
        return []
    
    print(f"\n📋 Reading tokens from {token_file}...")
    
    with open(token_file, 'r') as f:
        tokens = [line.strip() for line in f if line.strip()]
    
    print(f"   Found {len(tokens)} tokens to scrape")
    
    scraped_data = []
    
    for i, token in enumerate(tokens, 1):
        print(f"\n   [{i}/{len(tokens)}] Scraping {token[:8]}...")
        
        data = scrape_token_history(token)
        if data:
            scraped_data.append(data)
            print(f"      ✅ Success: {data['token_symbol']} - {data['change_24h']:.1f}% (24h)")
        else:
            print(f"      ❌ Failed")
        
        # Rate limiting
        time.sleep(1.2)  # DexScreener rate limit
    
    return scraped_data


def save_to_database(scraped_data: List[Dict], db_path: str = "var/dexscreener_history.db"):
    """
    Save scraped data to SQLite database in a format compatible with ML training
    """
    print(f"\n💾 Saving {len(scraped_data)} tokens to {db_path}...")
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Create table matching our ML training format
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
        peak_volume_24h_usd REAL,
        price_change_1h REAL,
        price_change_6h REAL,
        price_change_24h REAL,
        max_gain_percent REAL,
        max_drawdown_percent REAL,
        is_rug INTEGER,
        rug_detected_at REAL,
        token_name TEXT,
        token_symbol TEXT
    )
    """)
    
    # Insert data
    for data in scraped_data:
        # Estimate "entry" metrics (assume we caught it early)
        # Use current metrics as "first" metrics
        entry_price = data['price_usd']
        entry_mcap = data['market_cap_usd']
        entry_liq = data['liquidity_usd']
        
        # Calculate peak based on max gain
        peak_multiplier = 1 + (data['max_gain_percent'] / 100)
        peak_price = entry_price * peak_multiplier
        peak_mcap = entry_mcap * peak_multiplier
        
        # Insert into alerted_tokens
        c.execute("""
        INSERT OR REPLACE INTO alerted_tokens 
        (token_address, alerted_at, final_score, smart_money_detected, conviction_type)
        VALUES (?, ?, ?, ?, ?)
        """, (
            data['token_address'],
            data['pair_created_at'] / 1000 if data['pair_created_at'] else data['scraped_at'],
            8,  # Default score
            0,  # Unknown smart money
            'DexScreener Historical'
        ))
        
        # Insert into alerted_token_stats
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
            data['pair_created_at'] / 1000 if data['pair_created_at'] else data['scraped_at'],
            data['scraped_at'],
            8, 8,
            'DexScreener Historical',
            entry_price, entry_mcap, entry_liq,
            data['price_usd'], data['market_cap_usd'], data['liquidity_usd'], data['volume_24h'],
            peak_price, peak_mcap,
            data['scraped_at'], data['scraped_at'],
            data['change_1h'], data['change_6h'], data['change_24h'],
            data['max_gain_percent'],
            0,  # Unknown drawdown
            0,  # Assume not rug if still trading
            data['token_name'], data['token_symbol']
        ))
    
    conn.commit()
    conn.close()
    
    print(f"   ✅ Saved to database")
    
    # Print summary
    winners = [d for d in scraped_data if d['is_2x_winner']]
    print(f"\n📊 Summary:")
    print(f"   Total tokens: {len(scraped_data)}")
    print(f"   2x+ winners: {len(winners)} ({100*len(winners)/len(scraped_data):.1f}%)")
    print(f"   Avg 24h change: {sum(d['change_24h'] for d in scraped_data)/len(scraped_data):.1f}%")
    print(f"   Max gain: {max(d['max_gain_percent'] for d in scraped_data):.1f}%")


def main():
    print("="*60)
    print("🔍 DEXSCREENER HISTORICAL DATA SCRAPER")
    print("="*60)
    print("\nThis tool scrapes DexScreener for tokens that pumped 2x+")
    print("to provide additional training data for ML models.")
    print("\nNote: DexScreener API is rate-limited. Be patient!")
    print("="*60)
    
    # Option 1: Scrape from a list of known pump tokens
    # You can create this list manually or from other sources
    
    # Option 2: Search for recent high-volume tokens
    # (More complex, requires web scraping)
    
    print("\n📝 To use this scraper:")
    print("   1. Create 'known_pumps.txt' with token addresses (one per line)")
    print("   2. Or modify this script to search DexScreener directly")
    print("\n   Example known_pumps.txt content:")
    print("   pump1234567890abcdefghijklmnopqrstuvwxyz")
    print("   pump9876543210zyxwvutsrqponmlkjihgfedcba")
    
    # For now, demonstrate with a small test
    print("\n🧪 Running test scrape...")
    
    # Test with a known token (replace with actual addresses)
    test_tokens = [
        # Add some real Solana token addresses here for testing
        # These should be tokens that pumped recently
    ]
    
    if test_tokens:
        scraped = []
        for token in test_tokens:
            data = scrape_token_history(token)
            if data:
                scraped.append(data)
                print(f"✅ {data['token_symbol']}: {data['change_24h']:.1f}% (24h)")
            time.sleep(1.2)
        
        if scraped:
            save_to_database(scraped)
    else:
        print("\n⚠️  No test tokens provided. Add token addresses to test.")
        print("   You can find pumping tokens on:")
        print("   - https://dexscreener.com/solana?rankBy=trendingScoreH24&order=desc")
        print("   - https://dexscreener.com/solana?rankBy=volume&order=desc")


if __name__ == "__main__":
    main()


