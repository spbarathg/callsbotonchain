#!/usr/bin/env python3
"""Quick performance analysis of tracked tokens"""
import sqlite3
from datetime import datetime, timedelta

DB_PATH = "var/alerted_tokens.db"

def analyze():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    print("\n" + "="*80)
    print("TOKEN PERFORMANCE ANALYSIS")
    print("="*80)
    
    # Get tokens with tracking data
    c.execute("""
        SELECT 
            ats.token_address,
            ats.first_alert_at as alerted_at,
            at.final_score,
            at.conviction_type,
            ats.first_price_usd,
            ats.peak_price_usd,
            ats.last_price_usd,
            ats.peak_market_cap_usd,
            ats.first_market_cap_usd,
            ats.smart_money_involved,
            ats.outcome,
            ats.token_age_minutes,
            ats.unique_traders_15m,
            ats.velocity_score_15m,
            ats.top10_concentration as top_10_concentration_percent,
            ats.lp_locked as is_lp_locked,
            ats.mint_revoked as is_mint_revoked
        FROM alerted_token_stats ats
        LEFT JOIN alerted_tokens at ON ats.token_address = at.token_address
        WHERE ats.first_price_usd IS NOT NULL
        ORDER BY ats.first_alert_at DESC
        LIMIT 50
    """)
    
    tokens = c.fetchall()
    
    if not tokens:
        print("\n❌ No tracking data available yet. Tracker needs more time to collect prices.")
        conn.close()
        return
    
    print(f"\n📊 TRACKED TOKENS: {len(tokens)}")
    print("-"*80)
    
    pumps = []
    dumps = []
    neutral = []
    
    for token in tokens:
        first_price = token['first_price_usd']
        peak_price = token['peak_price_usd']
        last_price = token['last_price_usd']
        
        if not first_price or not peak_price:
            continue
            
        peak_gain = ((peak_price - first_price) / first_price) * 100
        
        if last_price and first_price:
            current_pnl = ((last_price - first_price) / first_price) * 100
        else:
            current_pnl = None
        
        token_data = {
            'address': token['token_address'][:12] + '...',
            'alerted_at': token['alerted_at'],
            'score': token['final_score'],
            'smart_money': token['smart_money_involved'],
            'conviction': token['conviction_type'],
            'peak_gain': peak_gain,
            'current_pnl': current_pnl,
            'first_mcap': token['first_market_cap_usd'],
            'peak_mcap': token['peak_market_cap_usd'],
            'outcome': token['outcome'],
            'token_age': token['token_age_minutes'],
            'traders_15m': token['unique_traders_15m'],
            'top10_pct': token['top_10_concentration_percent'],
            'lp_locked': token['is_lp_locked'],
            'mint_revoked': token['is_mint_revoked']
        }
        
        if peak_gain >= 50:
            pumps.append(token_data)
        elif peak_gain < -20:
            dumps.append(token_data)
        else:
            neutral.append(token_data)
    
    total = len(pumps) + len(dumps) + len(neutral)
    
    print(f"\n🎯 PERFORMANCE BREAKDOWN:")
    print(f"  🚀 PUMPED (≥50% gain):  {len(pumps):3d} ({len(pumps)/total*100:5.1f}%)")
    print(f"  📉 DUMPED (<-20%):      {len(dumps):3d} ({len(dumps)/total*100:5.1f}%)")
    print(f"  ⚖️  NEUTRAL:             {len(neutral):3d} ({len(neutral)/total*100:5.1f}%)")
    
    if pumps:
        print(f"\n{'='*80}")
        print(f"🚀 TOP PERFORMERS (Pumped ≥50%)")
        print(f"{'='*80}")
        pumps_sorted = sorted(pumps, key=lambda x: x['peak_gain'], reverse=True)[:10]
        
        for i, t in enumerate(pumps_sorted, 1):
            print(f"\n{i}. {t['address']}")
            print(f"   Peak Gain: {t['peak_gain']:+.1f}% | Current: {t['current_pnl']:+.1f}% if t['current_pnl'] else 'N/A'")
            print(f"   Score: {t['score']}/10 | Smart Money: {'✅' if t['smart_money'] else '❌'}")
            print(f"   MCap: ${t['first_mcap']:,.0f} → ${t['peak_mcap']:,.0f}" if t['first_mcap'] and t['peak_mcap'] else "")
            print(f"   Token Age: {t['token_age']:.0f}m" if t['token_age'] else "   Token Age: N/A")
            print(f"   Top10: {t['top10_pct']:.1f}%" if t['top10_pct'] else "")
            print(f"   LP Locked: {'✅' if t['lp_locked'] else '❌' if t['lp_locked'] is False else '❓'}")
    
    if dumps:
        print(f"\n{'='*80}")
        print(f"📉 POOR PERFORMERS (Dumped <-20%)")
        print(f"{'='*80}")
        dumps_sorted = sorted(dumps, key=lambda x: x['peak_gain'])[:10]
        
        for i, t in enumerate(dumps_sorted, 1):
            print(f"\n{i}. {t['address']}")
            print(f"   Peak Loss: {t['peak_gain']:+.1f}% | Current: {t['current_pnl']:+.1f}% if t['current_pnl'] else 'N/A'")
            print(f"   Score: {t['score']}/10 | Smart Money: {'✅' if t['smart_money'] else '❌'}")
            print(f"   Top10: {t['top10_pct']:.1f}%" if t['top10_pct'] else "")
    
    # Factor analysis
    print(f"\n{'='*80}")
    print(f"📊 FACTOR ANALYSIS")
    print(f"{'='*80}")
    
    # Smart money analysis
    smart_pumps = [t for t in pumps if t['smart_money']]
    non_smart_pumps = [t for t in pumps if not t['smart_money']]
    smart_dumps = [t for t in dumps if t['smart_money']]
    non_smart_dumps = [t for t in dumps if not t['smart_money']]
    
    print(f"\n🎯 Smart Money Performance:")
    print(f"   Pumps: {len(smart_pumps)}")
    print(f"   Dumps: {len(smart_dumps)}")
    print(f"   Win Rate: {len(smart_pumps)/(len(smart_pumps)+len(smart_dumps))*100:.1f}%" if (len(smart_pumps)+len(smart_dumps)) > 0 else "   Win Rate: N/A")
    
    print(f"\n🌐 General Cycle Performance:")
    print(f"   Pumps: {len(non_smart_pumps)}")
    print(f"   Dumps: {len(non_smart_dumps)}")
    print(f"   Win Rate: {len(non_smart_pumps)/(len(non_smart_pumps)+len(non_smart_dumps))*100:.1f}%" if (len(non_smart_pumps)+len(non_smart_dumps)) > 0 else "   Win Rate: N/A")
    
    # Avg peak gain by smart money
    if smart_pumps:
        avg_smart_gain = sum(t['peak_gain'] for t in smart_pumps) / len(smart_pumps)
        print(f"\n   Smart Money Avg Peak Gain: {avg_smart_gain:+.1f}%")
    if non_smart_pumps:
        avg_general_gain = sum(t['peak_gain'] for t in non_smart_pumps) / len(non_smart_pumps)
        print(f"   General Cycle Avg Peak Gain: {avg_general_gain:+.1f}%")
    
    conn.close()
    print(f"\n{'='*80}\n")

if __name__ == "__main__":
    analyze()
