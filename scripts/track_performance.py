#!/usr/bin/env python3
"""
Price Performance Tracker for Alerted Tokens
Runs continuously to track price movements and detect rugs
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
from app.analyze_token import get_token_stats
from app.logger_utils import _out


def track_token_performance(token_address: str, retry_count: int = 0) -> bool:
    """
    Fetch current stats for a token and update performance metrics.
    Returns True if successful, False if token no longer exists.
    
    For very new pump.fun tokens, they may not appear on DexScreener for 5-30 minutes.
    We handle this gracefully and keep trying.
    """
    try:
        # Force refresh to get live price data (bypass 15min cache for tracking)
        
        stats = get_token_stats(token_address, force_refresh=True)
        
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
                print(f"    Total: {data['total']}")
                print(f"    Avg Gain: {data.get('avg_gain', 0):.1f}%")
                print(f"    Rugs: {data['rug_count']} ({data['rug_count']/data['total']*100:.1f}%)")
        
        print("="*60)
        
    except Exception as e:
        _out(f"Error printing summary: {e}")


def main():
    """Main tracking loop"""
    _out("🔍 Starting Price Performance Tracker...")
    _out("Tracking alerted tokens from last 48 hours...")
    _out("IMPROVED: Tracking every 30 seconds to capture pump speed data better")
    
    cycle = 0
    
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
                    else:
                        failed_count += 1
                    time.sleep(1)  # Rate limiting
                
                if success_count > 0:
                    _out(f"✅ Updated {success_count}/{len(tokens)} tokens")
                
                # Only warn if ALL tokens failed (might indicate API issue)
                if failed_count == len(tokens) and len(tokens) > 10:
                    _out(f"⚠️  Warning: 0/{len(tokens)} tokens updated - possible API issue")
                elif failed_count > 0:
                    _out(f"ℹ️  {failed_count} tokens not yet indexed (too new for DexScreener)")
            
            # Print summary every 20 cycles (roughly every 10 minutes)
            if cycle % 20 == 0:
                print_summary()
            
            # IMPROVED: Sleep for 30 seconds instead of 60 to capture timing data better
            # Analysis showed we were missing 86% of timing data - this will help
            _out("Sleeping for 30 seconds...")
            time.sleep(30)
            
        except KeyboardInterrupt:
            _out("\n👋 Tracker stopped by user")
            print_summary()
            break
        except Exception as e:
            _out(f"❌ Error in tracking loop: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()
