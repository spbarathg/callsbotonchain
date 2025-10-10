#!/usr/bin/env python3
"""
Monitor the impact of liquidity filter changes
Tracks win rate, signal volume, and liquidity quality
"""
import sqlite3
import sys
import os
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'var', 'alerted_tokens.db')

def analyze_recent_signals(hours=48):
    """Analyze signals from the last N hours"""
    
    if not os.path.exists(DB_PATH):
        print(f"Database not found: {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Calculate cutoff time
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    
    print("=" * 70)
    print(f"LIQUIDITY FILTER IMPACT ANALYSIS (Last {hours} hours)")
    print("=" * 70)
    print()
    
    # Get all signals in period
    total = c.execute("""
        SELECT COUNT(*) 
        FROM alerted_tokens 
        WHERE datetime(alerted_at) >= datetime(?)
    """, (cutoff,)).fetchone()[0]
    
    # Get signals with liquidity data
    results = c.execute("""
        SELECT 
            COUNT(*) as total_with_data,
            SUM(CASE WHEN s.first_liquidity_usd >= 15000 THEN 1 ELSE 0 END) as passed_15k,
            SUM(CASE WHEN s.first_liquidity_usd >= 50000 THEN 1 ELSE 0 END) as passed_50k,
            SUM(CASE WHEN s.first_liquidity_usd < 15000 AND s.first_liquidity_usd > 0 THEN 1 ELSE 0 END) as below_15k,
            SUM(CASE WHEN s.first_liquidity_usd = 0 OR s.first_liquidity_usd IS NULL THEN 1 ELSE 0 END) as zero_liq,
            AVG(s.first_liquidity_usd) as avg_liq,
            AVG(CASE WHEN s.first_liquidity_usd >= 15000 THEN s.first_liquidity_usd ELSE NULL END) as avg_liq_passed
        FROM alerted_tokens a
        LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
        WHERE datetime(a.alerted_at) >= datetime(?)
    """, (cutoff,)).fetchone()
    
    total_with_data, passed_15k, passed_50k, below_15k, zero_liq, avg_liq, avg_liq_passed = results
    
    # Get winner data
    winner_stats = c.execute("""
        SELECT 
            COUNT(*) as total_signals,
            SUM(CASE WHEN s.max_gain_percent >= 100 THEN 1 ELSE 0 END) as winners_2x,
            SUM(CASE WHEN s.max_gain_percent >= 400 THEN 1 ELSE 0 END) as winners_5x,
            AVG(CASE WHEN s.max_gain_percent IS NOT NULL THEN s.max_gain_percent ELSE 0 END) as avg_peak_gain
        FROM alerted_tokens a
        LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
        WHERE datetime(a.alerted_at) >= datetime(?)
          AND s.first_liquidity_usd >= 15000
    """, (cutoff,)).fetchone()
    
    signals_passed, winners_2x, winners_5x, avg_peak = winner_stats
    
    # Display results
    print("📊 SIGNAL VOLUME:")
    print(f"  Total Signals: {total}")
    print(f"  With Data: {total_with_data}")
    print()
    
    print("💧 LIQUIDITY DISTRIBUTION:")
    print(f"  ✅ Passed $15k filter: {passed_15k} ({passed_15k/total*100:.1f}%)")
    print(f"  ⭐ Excellent ($50k+): {passed_50k} ({passed_50k/total*100:.1f}%)")
    print(f"  ⚠️  Below $15k: {below_15k} ({below_15k/total*100:.1f}%)")
    print(f"  ❌ Zero/Missing: {zero_liq} ({zero_liq/total*100:.1f}%)")
    print()
    
    print("💰 LIQUIDITY AVERAGES:")
    print(f"  All Signals: ${avg_liq:,.0f}" if avg_liq else "  All Signals: N/A")
    print(f"  Signals $15k+: ${avg_liq_passed:,.0f}" if avg_liq_passed else "  Signals $15k+: N/A")
    print()
    
    print("🎯 PERFORMANCE (Signals with $15k+ liquidity):")
    print(f"  Signals: {signals_passed}")
    
    if signals_passed > 0:
        win_rate_2x = (winners_2x / signals_passed) * 100
        win_rate_5x = (winners_5x / signals_passed) * 100
        
        print(f"  Winners (2x+): {winners_2x} ({win_rate_2x:.1f}%)")
        print(f"  Winners (5x+): {winners_5x} ({win_rate_5x:.1f}%)")
        print(f"  Avg Peak Gain: {avg_peak:.1f}%")
        print()
        
        # Impact analysis
        print("📈 EXPECTED IMPACT:")
        baseline_win_rate = 14.3  # From analysis
        
        if win_rate_2x > baseline_win_rate:
            improvement = win_rate_2x - baseline_win_rate
            multiplier = win_rate_2x / baseline_win_rate
            print(f"  ✅ Win Rate Improvement: +{improvement:.1f} percentage points")
            print(f"  ✅ Win Rate Multiplier: {multiplier:.2f}x better")
        else:
            print(f"  ⚠️  Win rate: {win_rate_2x:.1f}% (baseline: {baseline_win_rate}%)")
            print(f"     Need more time/data for filter to show impact")
    else:
        print(f"  ⚠️  No signals passed $15k filter in this period")
    
    print()
    
    # Filter effectiveness
    print("🔍 FILTER EFFECTIVENESS:")
    would_be_filtered = below_15k + zero_liq
    filter_rate = (would_be_filtered / total) * 100 if total > 0 else 0
    signal_reduction = 100 - ((passed_15k / total) * 100) if total > 0 else 0
    
    print(f"  Signals Filtered: {would_be_filtered}/{total} ({filter_rate:.1f}%)")
    print(f"  Signal Reduction: {signal_reduction:.1f}%")
    print(f"  Quality Signals: {passed_15k}/{total} ({100-signal_reduction:.1f}%)")
    
    conn.close()
    
    print()
    print("=" * 70)
    print("💡 INTERPRETATION:")
    print("=" * 70)
    
    if passed_15k > 0 and signals_passed > 0:
        if win_rate_2x > 25:
            print("✅ EXCELLENT: Filter is working! Win rate significantly improved.")
        elif win_rate_2x > 20:
            print("✅ GOOD: Filter showing positive impact. Continue monitoring.")
        elif win_rate_2x > 15:
            print("⚠️  MARGINAL: Small improvement. May need more time or threshold adjustment.")
        else:
            print("⚠️  BELOW TARGET: Consider adjusting threshold or check for other issues.")
    else:
        print("⏳ INSUFFICIENT DATA: Need more signals/time to evaluate impact.")
    
    print()
    print(f"Run this script daily to monitor filter effectiveness.")
    print()

if __name__ == "__main__":
    # Default to 48 hours, or accept command line argument
    hours = 48
    if len(sys.argv) > 1:
        try:
            hours = int(sys.argv[1])
        except ValueError:
            print(f"Invalid hours argument: {sys.argv[1]}")
            sys.exit(1)
    
    analyze_recent_signals(hours)



