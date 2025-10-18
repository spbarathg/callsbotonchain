#!/usr/bin/env python3
"""
Automated scraper for DexScreener trending page
Extracts pair addresses directly from the webpage
"""
import requests
import time
import re
from typing import List, Dict, Tuple
from bs4 import BeautifulSoup

def scrape_trending_pairs(
    min_age_hours: int = 1,
    max_age_hours: int = 336,  # 2 weeks
    min_gain_24h: float = 50.0,  # Minimum 50% gain
    max_pairs: int = 100
) -> List[Tuple[str, Dict]]:
    """
    Scrape trending pairs from DexScreener
    
    Returns:
        List of (pair_address, metadata) tuples
    """
    print("="*60)
    print("AUTOMATED DEXSCREENER SCRAPER")
    print("="*60)
    print(f"\nFilters:")
    print(f"  Age: {min_age_hours}h - {max_age_hours}h ({max_age_hours//24} days)")
    print(f"  Min 24h gain: {min_gain_24h}%")
    print(f"  Max pairs: {max_pairs}")
    print("\nScraping DexScreener trending page...")
    
    # Use DexScreener API instead of web scraping (more reliable)
    # Get latest pairs from Solana
    api_url = "https://api.dexscreener.com/latest/dex/tokens/solana"
    
    pairs_data = []
    
    # Try multiple strategies to get data
    strategies = [
        ("trending", "https://api.dexscreener.com/latest/dex/search?q=solana"),
        ("volume", "https://api.dexscreener.com/latest/dex/search?q=pump"),
    ]
    
    for strategy_name, url in strategies:
        try:
            print(f"\n  Trying strategy: {strategy_name}...")
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            if response.status_code == 200:
                data = response.json()
                if 'pairs' in data:
                    print(f"    Found {len(data['pairs'])} pairs")
                    pairs_data.extend(data['pairs'])
            
            time.sleep(2)  # Rate limiting
            
        except Exception as e:
            print(f"    Error: {e}")
    
    # Remove duplicates
    unique_pairs = {}
    for pair in pairs_data:
        pair_addr = pair.get('pairAddress')
        if pair_addr and pair_addr not in unique_pairs:
            unique_pairs[pair_addr] = pair
    
    print(f"\n  Total unique pairs found: {len(unique_pairs)}")
    
    # Filter pairs
    filtered_pairs = []
    
    for pair_addr, pair in unique_pairs.items():
        # Check chain
        if pair.get('chainId') != 'solana':
            continue
        
        # Check age
        created_at = pair.get('pairCreatedAt', 0)
        if created_at:
            age_hours = (time.time() - (created_at / 1000)) / 3600
            if not (min_age_hours <= age_hours <= max_age_hours):
                continue
        
        # Check 24h gain
        change_24h = float(pair.get('priceChange', {}).get('h24', 0))
        if change_24h < min_gain_24h:
            continue
        
        # Get metadata
        metadata = {
            'symbol': pair.get('baseToken', {}).get('symbol', 'UNKNOWN'),
            'name': pair.get('baseToken', {}).get('name', 'UNKNOWN'),
            'change_24h': change_24h,
            'change_1h': float(pair.get('priceChange', {}).get('h1', 0)),
            'liquidity': float(pair.get('liquidity', {}).get('usd', 0)),
            'market_cap': float(pair.get('fdv', 0)),
            'volume_24h': float(pair.get('volume', {}).get('h24', 0)),
            'age_hours': age_hours if created_at else 0,
        }
        
        filtered_pairs.append((pair_addr, metadata))
    
    # Sort by 24h gain (highest first)
    filtered_pairs.sort(key=lambda x: x[1]['change_24h'], reverse=True)
    
    # Limit to max_pairs
    filtered_pairs = filtered_pairs[:max_pairs]
    
    print(f"\n  Filtered to {len(filtered_pairs)} pairs matching criteria")
    
    return filtered_pairs


def display_pairs(pairs: List[Tuple[str, Dict]]):
    """Display found pairs in a nice format"""
    
    print("\n" + "="*60)
    print("FOUND PAIRS")
    print("="*60)
    
    if not pairs:
        print("\nNo pairs found matching criteria.")
        print("\nTry adjusting filters:")
        print("  - Increase max_age_hours (e.g., 720 for 1 month)")
        print("  - Decrease min_gain_24h (e.g., 20 for 20%+ gain)")
        return
    
    print(f"\n{'#':<4} {'SYMBOL':<12} {'24h%':<10} {'1h%':<10} {'AGE':<8} {'MCAP':<12} {'LIQ':<12}")
    print("-" * 80)
    
    for i, (pair_addr, meta) in enumerate(pairs, 1):
        age_str = f"{meta['age_hours']:.0f}h"
        if meta['age_hours'] > 48:
            age_str = f"{meta['age_hours']/24:.1f}d"
        
        mcap_str = f"${meta['market_cap']/1000:.0f}k" if meta['market_cap'] else "N/A"
        liq_str = f"${meta['liquidity']/1000:.0f}k" if meta['liquidity'] else "N/A"
        
        print(f"{i:<4} {meta['symbol']:<12} {meta['change_24h']:>8.1f}% {meta['change_1h']:>8.1f}% {age_str:<8} {mcap_str:<12} {liq_str:<12}")
    
    print("\n" + "="*60)


def save_to_pair_list(pairs: List[Tuple[str, Dict]], filename: str = "pair_list.txt"):
    """Save pair addresses to file"""
    
    print(f"\nSaving {len(pairs)} pair addresses to {filename}...")
    
    with open(filename, 'w') as f:
        f.write("# Auto-generated pair list from DexScreener\n")
        f.write(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Total pairs: {len(pairs)}\n")
        f.write("#\n")
        f.write("# Format: pair_address  # SYMBOL (24h%, 1h%, age, mcap, liq)\n")
        f.write("#\n\n")
        
        for pair_addr, meta in pairs:
            age_str = f"{meta['age_hours']:.0f}h"
            if meta['age_hours'] > 48:
                age_str = f"{meta['age_hours']/24:.1f}d"
            
            mcap_str = f"${meta['market_cap']/1000:.0f}k" if meta['market_cap'] else "N/A"
            liq_str = f"${meta['liquidity']/1000:.0f}k" if meta['liquidity'] else "N/A"
            
            comment = f"# {meta['symbol']} ({meta['change_24h']:.1f}%, {meta['change_1h']:.1f}%, {age_str}, {mcap_str}, {liq_str})"
            f.write(f"{pair_addr}  {comment}\n")
    
    print(f"  Saved successfully!")
    print(f"\nNext step:")
    print(f"  python scripts/ml/scrape_dexscreener_trending.py")


def main():
    """Main function"""
    
    # Configuration
    MIN_AGE_HOURS = 1        # At least 1 hour old
    MAX_AGE_HOURS = 720      # Max 1 month old (30 days)
    MIN_GAIN_24H = 10.0      # At least 10% gain in 24h (capture more)
    MAX_PAIRS = 100          # Limit to top 100
    
    # Scrape pairs
    pairs = scrape_trending_pairs(
        min_age_hours=MIN_AGE_HOURS,
        max_age_hours=MAX_AGE_HOURS,
        min_gain_24h=MIN_GAIN_24H,
        max_pairs=MAX_PAIRS
    )
    
    # Display results
    display_pairs(pairs)
    
    # Save to file
    if pairs:
        save_to_pair_list(pairs)
        
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        print(f"\nFound {len(pairs)} pairs matching criteria:")
        print(f"  - Age: {MIN_AGE_HOURS}h - {MAX_AGE_HOURS}h")
        print(f"  - Min 24h gain: {MIN_GAIN_24H}%")
        
        # Stats
        avg_gain = sum(p[1]['change_24h'] for p in pairs) / len(pairs)
        max_gain = max(p[1]['change_24h'] for p in pairs)
        winners_2x = sum(1 for p in pairs if p[1]['change_24h'] >= 100)
        
        print(f"\nStats:")
        print(f"  Avg 24h gain: {avg_gain:.1f}%")
        print(f"  Max 24h gain: {max_gain:.1f}%")
        print(f"  2x+ winners: {winners_2x} ({100*winners_2x/len(pairs):.1f}%)")
        
        print(f"\nPair addresses saved to: pair_list.txt")
        print(f"\nNext: Run the scraper to get full data")
        print(f"  python scripts/ml/scrape_dexscreener_trending.py")
    else:
        print("\n" + "="*60)
        print("NO PAIRS FOUND")
        print("="*60)
        print("\nTry adjusting filters in the script:")
        print("  - Increase MAX_AGE_HOURS (e.g., 720 for 1 month)")
        print("  - Decrease MIN_GAIN_24H (e.g., 20 for 20%+ gain)")


if __name__ == "__main__":
    main()

