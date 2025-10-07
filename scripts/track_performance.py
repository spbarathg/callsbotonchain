#!/usr/bin/env python3
"""
Price Performance Tracker for Alerted Tokens
Runs continuously to track price movements and detect rugs

OPTIMIZED FOR ZERO CREDIT USAGE:
- Uses only FREE APIs (DexScreener, Jupiter, GeckoTerminal)
- Never touches Cielo API
- Perfect for historical performance tracking
"""
import sys
import os
import time
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.storage import (
    get_alerted_tokens_for_tracking,
    record_price_snapshot,
    update_token_performance,
    get_performance_summary
)
from app.logger_utils import _out


def get_token_price_free(token_address: str) -> dict:
    """
    Get token price using ONLY free APIs (no Cielo credits burned).
    Tries multiple sources for reliability.
    
    Returns dict with price data in the same format as get_token_stats()
    """
    from app.http_client import request_json
    
    # Try 1: DexScreener (most reliable for Solana)
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        result = request_json("GET", url, timeout=10)
        
        if result.get("status_code") == 200:
            data = result.get("json") or {}
            pairs = data.get("pairs") or []
            
            if pairs:
                # Pick the most liquid pair
                best_pair = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
                
                price_usd = float(best_pair.get("priceUsd", 0))
                if price_usd > 0:
                    price_change = best_pair.get("priceChange") or {}
                    volume = best_pair.get("volume") or {}
                    
                    return {
                        "price": {
                            "price_usd": price_usd,
                            "price_change_1h": float(price_change.get("h1", 0) or 0),
                            "price_change_6h": float(price_change.get("h6", 0) or 0),
                            "price_change_24h": float(price_change.get("h24", 0) or 0),
                        },
                        "volume": {
                            "volume_24h": float(volume.get("h24", 0) or 0),
                        },
                        "liquidity": {
                            "liquidity_usd": float(best_pair.get("liquidity", {}).get("usd", 0) or 0),
                        },
                        "market_cap_usd": best_pair.get("marketCap"),
                        "source": "dexscreener_free"
                    }
    except Exception as e:
        _out(f"DexScreener free API failed: {e}")
    
    # Try 2: Jupiter Price API (free, no key needed)
    try:
        url = f"https://price.jup.ag/v4/price?ids={token_address}"
        result = request_json("GET", url, timeout=8)
        
        if result.get("status_code") == 200:
            data = result.get("json") or {}
            price_data = data.get("data", {}).get(token_address)
            
            if price_data:
                price_usd = float(price_data.get("price", 0))
                if price_usd > 0:
                    return {
                        "price": {
                            "price_usd": price_usd,
                            "price_change_1h": 0,  # Jupiter doesn't provide historical
                            "price_change_6h": 0,
                            "price_change_24h": 0,
                        },
                        "source": "jupiter_free"
                    }
    except Exception as e:
        _out(f"Jupiter free API failed: {e}")
    
    # Try 3: GeckoTerminal (free, good for trending tokens)
    try:
        url = f"https://api.geckoterminal.com/api/v2/networks/solana/tokens/{token_address}"
        result = request_json("GET", url, timeout=10)
        
        if result.get("status_code") == 200:
            data = result.get("json") or {}
            attrs = (data.get("data") or {}).get("attributes") or {}
            
            price_usd = float(attrs.get("price_usd", 0) or 0)
            if price_usd > 0:
                return {
                    "price": {
                        "price_usd": price_usd,
                        "price_change_1h": float(attrs.get("price_change_percentage_1h", 0) or 0),
                        "price_change_6h": float(attrs.get("price_change_percentage_6h", 0) or 0),
                        "price_change_24h": float(attrs.get("price_change_percentage_24h", 0) or 0),
                    },
                    "volume": {
                        "volume_24h": float(attrs.get("volume_usd_24h", 0) or 0),
                    },
                    "market_cap_usd": attrs.get("market_cap_usd"),
                    "source": "geckoterminal_free"
                }
    except Exception as e:
        _out(f"GeckoTerminal free API failed: {e}")
    
    return {}


def track_token_performance(token_address: str, retry_count: int = 0) -> bool:
    """
    Fetch current stats for a token and update performance metrics.
    Returns True if successful, False if token no longer exists.
    
    For very new pump.fun tokens, they may not appear on DexScreener for 5-30 minutes.
    We handle this gracefully and keep trying.
    """
    try:
        # TRACKER OPTIMIZATION: Use ONLY free APIs (no Cielo credits)
        # This is perfect for historical tracking where we just need basic price data
        stats = get_token_price_free(token_address)
        
        if not stats:
            # For very new tokens, this is expected - they're not indexed yet
            # We'll keep trying on subsequent cycles
            return False
        
        # Check if we actually have price data
        price_data = stats.get('price', {})
        current_price = price_data.get('price_usd', 0)
        
        if not current_price or current_price == 0:
            # Token exists on API but no price data yet
            return False
        
        # Record snapshot for historical tracking
        record_price_snapshot(token_address, stats)
        
        # Update performance metrics
        update_token_performance(token_address, stats)
        
        # Log significant movements
        change_1h = price_data.get('price_change_1h', 0)
        
        if abs(change_1h or 0) > 20:
            emoji = "🚀" if change_1h > 0 else "💥"
            _out(f"{emoji} {token_address[:8]}... {change_1h:+.1f}% (1h) | ${current_price:.8f}")
        
        return True
        
    except Exception as e:
        # Only log unexpected errors (not expected API failures)
        if "404" not in str(e) and "not found" not in str(e).lower():
            _out(f"❌ Error tracking {token_address[:8]}...: {e}")
        return False


def print_summary():
    """Print performance summary"""
    try:
        summary = get_performance_summary()
        
        print("\n" + "="*60)
        print("📊 PERFORMANCE SUMMARY")
        print("="*60)
        
        total = summary.get('total_alerts', 0)
        if total == 0:
            print("No alerted tokens tracked yet.")
            return
        
        print(f"\n📈 Overall Statistics:")
        print(f"  Total Alerts: {total}")
        print(f"  Avg Max Gain: {summary.get('avg_max_gain', 0):.1f}%")
        print(f"  Avg 1h Change: {summary.get('avg_1h', 0):.1f}%")
        print(f"  Avg 6h Change: {summary.get('avg_6h', 0):.1f}%")
        print(f"  Avg 24h Change: {summary.get('avg_24h', 0):.1f}%")
        
        print(f"\n🎯 Success Metrics:")
        print(f"  50%+ Pumps: {summary.get('pumps_50plus', 0)} ({summary.get('pumps_50plus', 0)/total*100:.1f}%)")
        print(f"  100%+ Pumps: {summary.get('pumps_100plus', 0)} ({summary.get('pumps_100plus', 0)/total*100:.1f}%)")
        print(f"  Rugs: {summary.get('rugs', 0)} ({summary.get('rugs', 0)/total*100:.1f}%)")
        print(f"  -20%+ Dumps: {summary.get('dumps_20plus', 0)} ({summary.get('dumps_20plus', 0)/total*100:.1f}%)")
        
        print(f"\n🏆 Performance by Conviction Type:")
        for conv_type, data in summary.get('by_conviction', {}).items():
            print(f"  {conv_type}:")
            print(f"    Count: {data['count']}")
            print(f"    Avg Gain: {data.get('avg_gain', 0):.1f}%")
            print(f"    Rugs: {data['rug_count']}")
        
        print(f"\n🔍 Feature Performance:")
        for feature in ['smart_money_involved', 'lp_locked', 'mint_revoked', 'passed_senior_strict']:
            key = f'{feature}_performance'
            if key in summary:
                data = summary[key]
                print(f"  {feature.replace('_', ' ').title()}:")
                total = data.get('total', 0)
                avg_gain = data.get('avg_gain', 0)
                rug_count = data.get('rug_count', 0)
                
                # Safe formatting with None checks
                print(f"    Total: {total if total is not None else 0}")
                print(f"    Avg Gain: {avg_gain if avg_gain is not None else 0:.1f}%")
                if total and total > 0:
                    print(f"    Rugs: {rug_count} ({rug_count/total*100:.1f}%)")
                else:
                    print(f"    Rugs: {rug_count} (0.0%)")
        
        print("="*60)
        
    except Exception as e:
        _out(f"Error printing summary: {e}")


def main():
    """Main tracking loop"""
    _out("🔍 Starting Price Performance Tracker...")
    _out("Tracking alerted tokens from last 24 hours...")
    _out("✅ ZERO CREDIT MODE: Using only FREE APIs (DexScreener, Jupiter, GeckoTerminal)")
    _out("⏱️  Checking every 10 minutes for price movements")
    
    cycle = 0
    consecutive_failures = 0
    
    while True:
        try:
            cycle += 1
            _out(f"\n📊 Tracking Cycle #{cycle} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Get tokens to track
            tokens = get_alerted_tokens_for_tracking()
            
            if not tokens:
                _out("No tokens to track.")
            else:
                _out(f"Tracking {len(tokens)} tokens...")
                
                success_count = 0
                failed_count = 0
                for token in tokens:
                    if track_token_performance(token):
                        success_count += 1
                        consecutive_failures = 0  # Reset on success
                    else:
                        failed_count += 1
                    # Increased delay between tokens to avoid rate limits
                    time.sleep(5)
                
                if success_count > 0:
                    _out(f"✅ Updated {success_count}/{len(tokens)} tokens")
                
                # Detect persistent API failures and back off
                if failed_count == len(tokens) and len(tokens) > 10:
                    consecutive_failures += 1
                    _out(f"⚠️  Warning: 0/{len(tokens)} tokens updated - possible API issue (failure #{consecutive_failures})")
                    
                    # If API is persistently failing, increase backoff
                    if consecutive_failures >= 3:
                        backoff_time = min(1800, 600 * consecutive_failures)  # Max 30 min
                        _out(f"🛑 API appears down. Backing off for {backoff_time//60} minutes...")
                        time.sleep(backoff_time)
                        consecutive_failures = 0
                        continue
                elif failed_count > 0:
                    _out(f"ℹ️  {failed_count} tokens not yet indexed (too new for DexScreener)")
            
            # Print summary every 6 cycles (roughly every hour)
            if cycle % 6 == 0:
                print_summary()
            
            # OPTIMIZED: 10 minute interval to save API credits while still capturing movements
            # Uses cache (15min) so most calls won't hit external APIs
            _out("Sleeping for 10 minutes...")
            time.sleep(600)
            
        except KeyboardInterrupt:
            _out("\n👋 Tracker stopped by user")
            print_summary()
            break
        except Exception as e:
            _out(f"❌ Error in tracking loop: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()
