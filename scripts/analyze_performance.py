#!/usr/bin/env python3
"""
Performance Analysis Script - Understand WHY tokens pump or dump
Analyzes correlation between features and token performance
"""
import sys
import os
import sqlite3
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_FILE


def get_conn():
    return sqlite3.connect(DB_FILE, timeout=10)


def analyze_feature_performance() -> Dict[str, any]:
    """Analyze which features correlate with pumps vs rugs"""
    conn = get_conn()
    c = conn.cursor()
    
    print("\n" + "="*80)
    print("🔍 FEATURE PERFORMANCE ANALYSIS")
    print("="*80)
    
    # Get all tracked tokens
    c.execute("""
        SELECT 
            token_address, token_name, token_symbol,
            preliminary_score, final_score, conviction_type,
            max_gain_percent, is_rug,
            smart_money_involved, velocity_score_15m, velocity_bonus,
            passed_junior_strict, passed_senior_strict, passed_debate,
            lp_locked, mint_revoked,
            top10_concentration, bundlers_percent, insiders_percent,
            token_age_minutes, unique_traders_15m,
            price_change_1h, price_change_6h, price_change_24h
        FROM alerted_token_stats
        WHERE last_checked_at IS NOT NULL
    """)
    
    tokens = []
    for row in c.fetchall():
        tokens.append({
            'address': row[0], 'name': row[1], 'symbol': row[2],
            'prelim_score': row[3], 'final_score': row[4], 'conviction': row[5],
            'max_gain': row[6], 'is_rug': bool(row[7]),
            'smart_money': bool(row[8]), 'velocity': row[9], 'velocity_bonus': row[10],
            'jr_strict': bool(row[11]), 'sr_strict': bool(row[12]), 'debate': bool(row[13]),
            'lp_locked': bool(row[14]), 'mint_revoked': bool(row[15]),
            'top10': row[16], 'bundlers': row[17], 'insiders': row[18],
            'age': row[19], 'traders': row[20],
            'change_1h': row[21], 'change_6h': row[22], 'change_24h': row[23],
        })
    
    if not tokens:
        print("⚠️  No tracked tokens found. Need to wait for price tracking data.")
        conn.close()
        return {}
    
    print(f"\n📊 Total Tracked Tokens: {len(tokens)}")
    
    # Categorize performance
    pumps = [t for t in tokens if (t['max_gain'] or 0) > 50]
    moderate = [t for t in tokens if 0 < (t['max_gain'] or 0) <= 50]
    dumps = [t for t in tokens if (t['max_gain'] or 0) <= 0]
    rugs = [t for t in tokens if t['is_rug']]
    
    print(f"\n🎯 Performance Distribution:")
    print(f"  🚀 50%+ Pumps: {len(pumps)} ({len(pumps)/len(tokens)*100:.1f}%)")
    print(f"  📈 Moderate Gains (0-50%): {len(moderate)} ({len(moderate)/len(tokens)*100:.1f}%)")
    print(f"  📉 Dumps (<0%): {len(dumps)} ({len(dumps)/len(tokens)*100:.1f}%)")
    print(f"  💀 Rugs: {len(rugs)} ({len(rugs)/len(tokens)*100:.1f}%)")
    
    # Feature correlation analysis
    print(f"\n🔬 FEATURE CORRELATION WITH PUMPS (>50% gain)")
    print("="*80)
    
    features = [
        ('smart_money', 'Smart Money Involved'),
        ('jr_strict', 'Passed Junior Strict'),
        ('sr_strict', 'Passed Senior Strict'),
        ('debate', 'Passed Debate Gate'),
        ('lp_locked', 'LP Locked'),
        ('mint_revoked', 'Mint Revoked'),
    ]
    
    for feature_key, feature_name in features:
        with_feature = [t for t in tokens if t.get(feature_key)]
        without_feature = [t for t in tokens if not t.get(feature_key)]
        
        if with_feature:
            pump_rate_with = len([t for t in with_feature if (t['max_gain'] or 0) > 50]) / len(with_feature) * 100
            rug_rate_with = len([t for t in with_feature if t['is_rug']]) / len(with_feature) * 100
            avg_gain_with = sum([t['max_gain'] or 0 for t in with_feature]) / len(with_feature)
        else:
            pump_rate_with = rug_rate_with = avg_gain_with = 0
        
        if without_feature:
            pump_rate_without = len([t for t in without_feature if (t['max_gain'] or 0) > 50]) / len(without_feature) * 100
            rug_rate_without = len([t for t in without_feature if t['is_rug']]) / len(without_feature) * 100
            avg_gain_without = sum([t['max_gain'] or 0 for t in without_feature]) / len(without_feature)
        else:
            pump_rate_without = rug_rate_without = avg_gain_without = 0
        
        print(f"\n{feature_name}:")
        print(f"  With Feature ({len(with_feature)} tokens):")
        print(f"    Pump Rate: {pump_rate_with:.1f}%")
        print(f"    Rug Rate: {rug_rate_with:.1f}%")
        print(f"    Avg Gain: {avg_gain_with:+.1f}%")
        print(f"  Without Feature ({len(without_feature)} tokens):")
        print(f"    Pump Rate: {pump_rate_without:.1f}%")
        print(f"    Rug Rate: {rug_rate_without:.1f}%")
        print(f"    Avg Gain: {avg_gain_without:+.1f}%")
        
        # Determine if feature is protective or risky
        if pump_rate_with > pump_rate_without and rug_rate_with < rug_rate_without:
            print(f"  ✅ POSITIVE SIGNAL (increases pumps, reduces rugs)")
        elif pump_rate_with < pump_rate_without or rug_rate_with > rug_rate_without:
            print(f"  ⚠️  NEGATIVE/NEUTRAL SIGNAL")
        else:
            print(f"  ➖ NEUTRAL")
    
    # Numeric feature analysis
    print(f"\n\n🔢 NUMERIC FEATURE ANALYSIS")
    print("="*80)
    
    numeric_features = [
        ('prelim_score', 'Preliminary Score'),
        ('final_score', 'Final Score'),
        ('velocity', 'Velocity Score'),
        ('velocity_bonus', 'Velocity Bonus'),
        ('top10', 'Top 10 Concentration %'),
        ('age', 'Token Age (minutes)'),
        ('traders', 'Unique Traders (15m)'),
    ]
    
    for feature_key, feature_name in numeric_features:
        pump_values = [t[feature_key] for t in pumps if t[feature_key] is not None]
        rug_values = [t[feature_key] for t in rugs if t[feature_key] is not None]
        
        if pump_values and rug_values:
            avg_pump = sum(pump_values) / len(pump_values)
            avg_rug = sum(rug_values) / len(rug_values)
            
            print(f"\n{feature_name}:")
            print(f"  Pumps Avg: {avg_pump:.2f}")
            print(f"  Rugs Avg: {avg_rug:.2f}")
            print(f"  Difference: {avg_pump - avg_rug:+.2f}")
            
            if abs(avg_pump - avg_rug) > (avg_pump * 0.2):  # >20% difference
                if avg_pump > avg_rug:
                    print(f"  ✅ Higher values correlate with PUMPS")
                else:
                    print(f"  ⚠️  Higher values correlate with RUGS")
    
    # Conviction type analysis
    print(f"\n\n🏆 CONVICTION TYPE PERFORMANCE")
    print("="*80)
    
    conviction_types = {}
    for token in tokens:
        conv = token['conviction']
        if conv not in conviction_types:
            conviction_types[conv] = []
        conviction_types[conv].append(token)
    
    for conv_type, conv_tokens in conviction_types.items():
        pump_count = len([t for t in conv_tokens if (t['max_gain'] or 0) > 50])
        rug_count = len([t for t in conv_tokens if t['is_rug']])
        avg_gain = sum([t['max_gain'] or 0 for t in conv_tokens]) / len(conv_tokens)
        
        print(f"\n{conv_type} ({len(conv_tokens)} tokens):")
        print(f"  Pump Rate: {pump_count/len(conv_tokens)*100:.1f}%")
        print(f"  Rug Rate: {rug_count/len(conv_tokens)*100:.1f}%")
        print(f"  Avg Gain: {avg_gain:+.1f}%")
    
    # Best and worst performers
    print(f"\n\n🌟 BEST PERFORMERS")
    print("="*80)
    
    best = sorted(tokens, key=lambda t: t['max_gain'] or 0, reverse=True)[:5]
    for i, token in enumerate(best, 1):
        print(f"\n{i}. {token['name']} (${token['symbol']})")
        print(f"   Max Gain: {token['max_gain']:+.1f}%")
        print(f"   Score: {token['prelim_score']}/10 → {token['final_score']}/10")
        print(f"   Smart Money: {'✅' if token['smart_money'] else '❌'}")
        print(f"   Velocity: {token['velocity'] or 0}")
        print(f"   Top10: {token['top10'] or 0:.1f}%")
    
    print(f"\n\n💀 WORST PERFORMERS (Rugs)")
    print("="*80)
    
    worst = sorted(rugs, key=lambda t: t['max_gain'] or 0)[:5]
    for i, token in enumerate(worst, 1):
        print(f"\n{i}. {token['name']} (${token['symbol']})")
        print(f"   Max Loss: {token['max_gain']:+.1f}%")
        print(f"   Score: {token['prelim_score']}/10 → {token['final_score']}/10")
        print(f"   Smart Money: {'✅' if token['smart_money'] else '❌'}")
        print(f"   LP Locked: {'✅' if token['lp_locked'] else '❌'}")
        print(f"   Mint Revoked: {'✅' if token['mint_revoked'] else '❌'}")
    
    print("\n" + "="*80)
    
    conn.close()
    
    return {
        'total': len(tokens),
        'pumps': len(pumps),
        'rugs': len(rugs),
        'best': best[:3] if best else [],
        'worst': worst[:3] if worst else [],
    }


def generate_recommendations():
    """Generate configuration recommendations based on performance data"""
    conn = get_conn()
    c = conn.cursor()
    
    print("\n\n🎯 CONFIGURATION RECOMMENDATIONS")
    print("="*80)
    
    # Check if we have enough data
    c.execute("SELECT COUNT(*) FROM alerted_token_stats WHERE last_checked_at IS NOT NULL")
    total = c.fetchone()[0]
    
    if total < 20:
        print(f"⚠️  Only {total} tracked tokens. Need at least 20 for reliable recommendations.")
        print("   Continue running the tracker for more data.")
        conn.close()
        return
    
    # Analyze current performance
    c.execute("""
        SELECT 
            AVG(max_gain_percent) as avg_gain,
            COUNT(CASE WHEN max_gain_percent > 50 THEN 1 END) * 1.0 / COUNT(*) as pump_rate,
            COUNT(CASE WHEN is_rug = 1 THEN 1 END) * 1.0 / COUNT(*) as rug_rate,
            COUNT(*) as total
        FROM alerted_token_stats
        WHERE last_checked_at IS NOT NULL
    """)
    
    row = c.fetchone()
    avg_gain, pump_rate, rug_rate, total = row
    
    print(f"\n📊 Current Performance:")
    print(f"  Total Alerts Tracked: {total}")
    print(f"  Average Gain: {avg_gain:+.1f}%")
    print(f"  Pump Rate (>50%): {pump_rate*100:.1f}%")
    print(f"  Rug Rate: {rug_rate*100:.1f}%")
    
    recommendations = []
    
    # Recommendation 1: Pump rate
    if pump_rate < 0.15:  # Less than 15% pump rate
        recommendations.append({
            'priority': 'HIGH',
            'issue': 'Low pump rate (<15%)',
            'action': 'Consider LOWERING HIGH_CONFIDENCE_SCORE from 8 to 7',
            'reason': 'More signals may capture early movers we\'re missing'
        })
    elif pump_rate > 0.40:  # More than 40% pump rate
        recommendations.append({
            'priority': 'LOW',
            'issue': 'Very high pump rate (>40%)',
            'action': 'System is performing excellently, no changes needed',
            'reason': 'Current filtering is optimal'
        })
    
    # Recommendation 2: Rug rate
    if rug_rate > 0.15:  # More than 15% rug rate
        recommendations.append({
            'priority': 'HIGH',
            'issue': f'High rug rate ({rug_rate*100:.1f}%)',
            'action': 'Enable REQUIRE_LP_LOCKED and REQUIRE_MINT_REVOKED strictly',
            'reason': 'Too many unsafe tokens passing filters'
        })
    
    # Recommendation 3: Smart money performance
    c.execute("""
        SELECT 
            AVG(CASE WHEN smart_money_involved = 1 THEN max_gain_percent END) as smart_avg,
            AVG(CASE WHEN smart_money_involved = 0 THEN max_gain_percent END) as general_avg,
            COUNT(CASE WHEN smart_money_involved = 1 THEN 1 END) as smart_count,
            COUNT(CASE WHEN smart_money_involved = 0 THEN 1 END) as general_count
        FROM alerted_token_stats
        WHERE last_checked_at IS NOT NULL
    """)
    
    row = c.fetchone()
    smart_avg, general_avg, smart_count, general_count = row
    
    if smart_count == 0:
        recommendations.append({
            'priority': 'MEDIUM',
            'issue': 'No general cycle alerts (100% smart money)',
            'action': 'Consider disabling REQUIRE_SMART_MONEY_FOR_ALERT',
            'reason': 'Missing potentially good general cycle tokens'
        })
    elif smart_avg and general_avg and general_avg > smart_avg * 1.2:
        recommendations.append({
            'priority': 'MEDIUM',
            'issue': f'General cycle outperforming smart money ({general_avg:.1f}% vs {smart_avg:.1f}%)',
            'action': 'Reduce CIELO_MIN_WALLET_PNL or disable smart money requirement',
            'reason': 'Smart money filter may be too strict'
        })
    
    # Display recommendations
    print(f"\n\n💡 Recommendations:")
    if not recommendations:
        print("  ✅ No changes needed - system is performing optimally!")
    else:
        for i, rec in enumerate(recommendations, 1):
            print(f"\n  {i}. [{rec['priority']} PRIORITY]")
            print(f"     Issue: {rec['issue']}")
            print(f"     Action: {rec['action']}")
            print(f"     Reason: {rec['reason']}")
    
    print("\n" + "="*80)
    
    conn.close()


if __name__ == "__main__":
    analyze_feature_performance()
    generate_recommendations()
