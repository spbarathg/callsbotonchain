import asyncio
import sys
import os
import json
from pprint import pprint

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.analyze_token import get_token_stats, calculate_preliminary_score, score_token
from app.http_client import request_json

async def fetch_latest_solana_tokens():
    # DexScreener new pairs API or search API
    # Since DexScreener doesn't have a public "latest" endpoint without filters easily available,
    # let's just search for a common string or use the DexScreener profiles API.
    # Alternatively, we can use Birdeye trending if available.
    # We will search "pump" on Solana
    import requests
    url = "https://api.dexscreener.com/latest/dex/search?q=sol/usdc"
    response = requests.get(url)
    data = response.json() if response.status_code == 200 else {}
    
    if not data or "pairs" not in data:
        print("Failed to fetch pairs")
        return []
        
    pairs = data.get("pairs", [])
    # Filter for solana
    solana_pairs = [p for p in pairs if p.get("chainId") == "solana"]
    
    results = []
    
    print(f"Found {len(solana_pairs)} Solana pairs. Analyzing the top 5 by volume...")
    
    # Sort by 24h volume
    solana_pairs.sort(key=lambda x: x.get("volume", {}).get("h24", 0), reverse=True)
    
    for pair in solana_pairs[:10]:
        token_address = pair.get("baseToken", {}).get("address")
        token_symbol = pair.get("baseToken", {}).get("symbol")
        
        print(f"\n--- Analyzing {token_symbol} ({token_address}) ---")
        
        # 1. Fetch token stats
        stats = get_token_stats(token_address)
        if not stats:
            print("Failed to get token stats.")
            continue
            
        print(f"Market Cap: ${stats.get('market_cap', 0):,.2f}")
        print(f"Liquidity: ${stats.get('liquidity_usd', 0):,.2f}")
        print(f"Volume 24h: ${stats.get('volume_24h', 0):,.2f}")
        
        # 2. Preliminary score
        prelim_score = calculate_preliminary_score(stats)
        print(f"Preliminary Score: {prelim_score}")
        
        # 3. Full score
        score, flags = score_token(stats, False, token_address)
        print(f"Final Score: {score}/10")
        print(f"Flags: {flags}")
        
        results.append({
            "symbol": token_symbol,
            "address": token_address,
            "market_cap": stats.get('market_cap', 0),
            "liquidity": stats.get('liquidity_usd', 0),
            "volume_24h": stats.get('volume_24h', 0),
            "prelim_score": prelim_score,
            "final_score": score,
            "flags": flags
        })
        
    # Write results to json
    with open("var/test_report.json", "w") as f:
        json.dump(results, f, indent=4)
        
if __name__ == "__main__":
    asyncio.run(fetch_latest_solana_tokens())
