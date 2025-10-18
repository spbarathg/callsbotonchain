#!/usr/bin/env python3
"""
Automatically find tokens that pumped 2x+ from DexScreener
Uses web scraping to get trending/top gainers
"""
import requests
import time
import json
from typing import List, Dict, Optional
from datetime import datetime, timedelta

DEXSCREENER_BASE = "https://api.dexscreener.com/latest/dex"


def get_top_pairs_by_volume(chain: str = "solana", limit: int = 100) -> List[Dict]:
    """
    Get top pairs by 24h volume
    These often include recent pumps
    """
    print(f"\n📊 Fetching top {limit} pairs by volume on {chain}...")
    
    # DexScreener doesn't have a direct "top by volume" API endpoint
    # But we can search and filter
    
    # Alternative: Use their search with filters
    url = f"{DEXSCREENER_BASE}/search"
    
    pairs = []
    
    # Try multiple search strategies
    strategies = [
        {"q": "pump", "chain": chain},
        {"q": "moon", "chain": chain},
        {"q": "new", "chain": chain},
    ]
    
    for strategy in strategies:
        try:
            response = requests.get(url, params=strategy, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'pairs' in data:
                    pairs.extend(data['pairs'])
                    print(f"   Found {len(data['pairs'])} pairs with query '{strategy['q']}'")
            time.sleep(1.5)  # Rate limiting
        except Exception as e:
            print(f"   ⚠️  Error with strategy {strategy}: {e}")
    
    # Remove duplicates
    unique_pairs = {p['pairAddress']: p for p in pairs}.values()
    
    print(f"   Total unique pairs: {len(unique_pairs)}")
    
    return list(unique_pairs)[:limit]


def filter_recent_pumps(pairs: List[Dict], min_age_hours: int = 24, max_age_hours: int = 336) -> List[Dict]:
    """
    Filter pairs to find recent pumps (1-2 weeks old, 2x+ gains)
    
    Args:
        pairs: List of pair data from DexScreener
        min_age_hours: Minimum age (24h = 1 day)
        max_age_hours: Maximum age (336h = 2 weeks)
    
    Returns:
        Filtered list of pumping tokens
    """
    print(f"\n🔍 Filtering for pumps (age: {min_age_hours}-{max_age_hours}h, gain: 2x+)...")
    
    now = int(time.time())
    min_age_seconds = min_age_hours * 3600
    max_age_seconds = max_age_hours * 3600
    
    pumps = []
    
    for pair in pairs:
        # Check age
        created_at = pair.get('pairCreatedAt', 0)
        if created_at:
            age_seconds = now - (created_at / 1000)  # Convert ms to seconds
            
            if not (min_age_seconds <= age_seconds <= max_age_seconds):
                continue
        
        # Check if it pumped 2x+ (100%+)
        price_change_24h = pair.get('priceChange', {}).get('h24', 0)
        
        if price_change_24h >= 100:  # 2x+
            pumps.append(pair)
    
    print(f"   Found {len(pumps)} tokens that pumped 2x+ in target age range")
    
    return pumps


def extract_features_from_pair(pair: Dict) -> Dict:
    """
    Extract ML training features from a DexScreener pair
    """
    # Get base token address
    token_address = pair.get('baseToken', {}).get('address', '')
    
    # Extract all relevant features
    features = {
        'token_address': token_address,
        'pair_address': pair.get('pairAddress', ''),
        'chain': pair.get('chainId', 'solana'),
        'dex': pair.get('dexId', ''),
        
        # Price and market metrics
        'price_usd': float(pair.get('priceUsd', 0)),
        'liquidity_usd': float(pair.get('liquidity', {}).get('usd', 0)),
        'market_cap_usd': float(pair.get('fdv', 0)),  # Fully diluted valuation
        'volume_24h': float(pair.get('volume', {}).get('h24', 0)),
        
        # Price changes (KEY for ML!)
        'change_5m': float(pair.get('priceChange', {}).get('m5', 0)),
        'change_1h': float(pair.get('priceChange', {}).get('h1', 0)),
        'change_6h': float(pair.get('priceChange', {}).get('h6', 0)),
        'change_24h': float(pair.get('priceChange', {}).get('h24', 0)),
        
        # Liquidity metrics
        'liquidity_base': float(pair.get('liquidity', {}).get('base', 0)),
        'liquidity_quote': float(pair.get('liquidity', {}).get('quote', 0)),
        
        # Volume metrics
        'volume_5m': float(pair.get('volume', {}).get('m5', 0)),
        'volume_1h': float(pair.get('volume', {}).get('h1', 0)),
        'volume_6h': float(pair.get('volume', {}).get('h6', 0)),
        
        # Transactions
        'txns_5m_buys': pair.get('txns', {}).get('m5', {}).get('buys', 0),
        'txns_5m_sells': pair.get('txns', {}).get('m5', {}).get('sells', 0),
        'txns_1h_buys': pair.get('txns', {}).get('h1', {}).get('buys', 0),
        'txns_1h_sells': pair.get('txns', {}).get('h1', {}).get('sells', 0),
        'txns_24h_buys': pair.get('txns', {}).get('h24', {}).get('buys', 0),
        'txns_24h_sells': pair.get('txns', {}).get('h24', {}).get('sells', 0),
        
        # Token info
        'token_name': pair.get('baseToken', {}).get('name', ''),
        'token_symbol': pair.get('baseToken', {}).get('symbol', ''),
        
        # Timing
        'pair_created_at': pair.get('pairCreatedAt', 0),
        'scraped_at': int(time.time()),
    }
    
    # Calculate derived features
    features['max_gain_percent'] = max(
        features['change_5m'],
        features['change_1h'],
        features['change_6h'],
        features['change_24h']
    )
    
    features['is_2x_winner'] = features['change_24h'] >= 100
    
    # Buy/sell ratio (indicator of momentum)
    if features['txns_24h_sells'] > 0:
        features['buy_sell_ratio_24h'] = features['txns_24h_buys'] / features['txns_24h_sells']
    else:
        features['buy_sell_ratio_24h'] = features['txns_24h_buys']
    
    # Volume to liquidity ratio (indicator of activity)
    if features['liquidity_usd'] > 0:
        features['volume_to_liquidity'] = features['volume_24h'] / features['liquidity_usd']
    else:
        features['volume_to_liquidity'] = 0
    
    return features


def analyze_pump_patterns(pumps: List[Dict]) -> Dict:
    """
    Analyze patterns in pumping tokens to identify decisive factors
    """
    print("\n🔬 Analyzing pump patterns...")
    
    if not pumps:
        print("   ⚠️  No pumps to analyze")
        return {}
    
    # Extract features from all pumps
    features_list = [extract_features_from_pair(p) for p in pumps]
    
    # Calculate statistics
    stats = {
        'total_pumps': len(features_list),
        'avg_gain': sum(f['max_gain_percent'] for f in features_list) / len(features_list),
        'median_gain': sorted([f['max_gain_percent'] for f in features_list])[len(features_list)//2],
        'max_gain': max(f['max_gain_percent'] for f in features_list),
        
        # Market cap analysis
        'avg_market_cap': sum(f['market_cap_usd'] for f in features_list) / len(features_list),
        'median_market_cap': sorted([f['market_cap_usd'] for f in features_list])[len(features_list)//2],
        
        # Liquidity analysis
        'avg_liquidity': sum(f['liquidity_usd'] for f in features_list) / len(features_list),
        'median_liquidity': sorted([f['liquidity_usd'] for f in features_list])[len(features_list)//2],
        
        # Volume analysis
        'avg_volume_24h': sum(f['volume_24h'] for f in features_list) / len(features_list),
        'median_volume_24h': sorted([f['volume_24h'] for f in features_list])[len(features_list)//2],
        
        # Momentum analysis
        'avg_change_1h': sum(f['change_1h'] for f in features_list) / len(features_list),
        'avg_change_24h': sum(f['change_24h'] for f in features_list) / len(features_list),
    }
    
    print(f"\n📊 PUMP PATTERN ANALYSIS:")
    print(f"   Total 2x+ pumps: {stats['total_pumps']}")
    print(f"   Avg gain: {stats['avg_gain']:.1f}%")
    print(f"   Max gain: {stats['max_gain']:.1f}%")
    print(f"\n   💰 Market Cap:")
    print(f"      Avg: ${stats['avg_market_cap']:,.0f}")
    print(f"      Median: ${stats['median_market_cap']:,.0f}")
    print(f"\n   💧 Liquidity:")
    print(f"      Avg: ${stats['avg_liquidity']:,.0f}")
    print(f"      Median: ${stats['median_liquidity']:,.0f}")
    print(f"\n   📈 Volume (24h):")
    print(f"      Avg: ${stats['avg_volume_24h']:,.0f}")
    print(f"      Median: ${stats['median_volume_24h']:,.0f}")
    print(f"\n   🚀 Momentum:")
    print(f"      Avg 1h change: {stats['avg_change_1h']:.1f}%")
    print(f"      Avg 24h change: {stats['avg_change_24h']:.1f}%")
    
    return stats


def main():
    print("="*60)
    print("🤖 AUTO PUMP FINDER - DexScreener")
    print("="*60)
    print("\nFinding tokens that pumped 2x+ in the past 1-2 weeks...")
    print("This data will be used to train ML models.")
    print("="*60)
    
    # Step 1: Get top pairs by volume
    pairs = get_top_pairs_by_volume(chain="solana", limit=100)
    
    if not pairs:
        print("\n❌ No pairs found. DexScreener API may be rate-limiting.")
        print("   Try again in a few minutes.")
        return
    
    # Step 2: Filter for recent pumps
    pumps = filter_recent_pumps(pairs, min_age_hours=24, max_age_hours=336)
    
    if not pumps:
        print("\n⚠️  No recent 2x+ pumps found in the data.")
        print("   This could mean:")
        print("   1. Market is slow right now")
        print("   2. Need to search more pairs")
        print("   3. API returned limited data")
        return
    
    # Step 3: Analyze patterns
    stats = analyze_pump_patterns(pumps)
    
    # Step 4: Save data
    print(f"\n💾 Saving {len(pumps)} pump tokens...")
    
    # Save to JSON for review
    output_file = "dexscreener_pumps.json"
    pump_data = [extract_features_from_pair(p) for p in pumps]
    
    with open(output_file, 'w') as f:
        json.dump({
            'scraped_at': datetime.now().isoformat(),
            'total_pumps': len(pump_data),
            'stats': stats,
            'pumps': pump_data
        }, f, indent=2)
    
    print(f"   ✅ Saved to {output_file}")
    
    # Print token addresses for manual review
    print(f"\n📋 Token addresses (for manual verification):")
    for i, pump in enumerate(pump_data[:10], 1):  # Show first 10
        print(f"   {i}. {pump['token_symbol']}: {pump['token_address'][:8]}... ({pump['change_24h']:.1f}%)")
    
    if len(pump_data) > 10:
        print(f"   ... and {len(pump_data)-10} more")
    
    print("\n" + "="*60)
    print("✅ COMPLETE!")
    print("="*60)
    print("\nNext steps:")
    print("1. Review dexscreener_pumps.json")
    print("2. Run scripts/ml/scrape_dexscreener_history.py to get full data")
    print("3. Merge with existing database")
    print("4. Retrain ML models with expanded dataset")


if __name__ == "__main__":
    main()


