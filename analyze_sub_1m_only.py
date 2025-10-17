#!/usr/bin/env python3
"""
Re-analyze performance for SUB-$1M tokens only with 2x+ win rate
"""
import sqlite3

DB_PATH = "/opt/callsbotonchain/deployment/var/alerted_tokens.db"

def analyze_sub_1m():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    print("="*80)
    print("SUB-$1M TOKEN PERFORMANCE ANALYSIS (2x+ Win Rate)")
    print("="*80)
    print()
    
    # 1. Overall for sub-$1M tokens
    print("1. SUB-$1M TOKENS ONLY (Your Target Range)")
    print("-" * 80)
    c.execute("""
        SELECT 
            COUNT(*) as total_signals,
            ROUND(AVG(max_gain_percent), 2) as avg_gain,
            SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) as wins_2x,
            SUM(CASE WHEN max_gain_percent >= 200 THEN 1 ELSE 0 END) as wins_3x,
            SUM(CASE WHEN max_gain_percent >= 400 THEN 1 ELSE 0 END) as wins_5x,
            SUM(CASE WHEN is_rug = 1 THEN 1 ELSE 0 END) as rugs,
            SUM(CASE WHEN max_gain_percent < -20 THEN 1 ELSE 0 END) as big_losses
        FROM alerted_token_stats
        WHERE first_market_cap_usd < 1000000
    """)
    row = c.fetchone()
    total = row['total_signals']
    wins_2x = row['wins_2x']
    wins_3x = row['wins_3x']
    wins_5x = row['wins_5x']
    rugs = row['rugs']
    big_losses = row['big_losses']
    
    print(f"Total Sub-$1M Signals: {total}")
    print(f"Average Gain: {row['avg_gain']:.2f}%")
    print(f"2x+ Win Rate: {wins_2x}/{total} ({wins_2x/total*100:.1f}%)")
    print(f"3x+ Win Rate: {wins_3x}/{total} ({wins_3x/total*100:.1f}%)")
    print(f"5x+ Win Rate: {wins_5x}/{total} ({wins_5x/total*100:.1f}%)")
    print(f"Rug Rate: {rugs}/{total} ({rugs/total*100:.1f}%)")
    print(f"Big Losses (>-20%): {big_losses}/{total} ({big_losses/total*100:.1f}%)")
    print()
    
    # 2. Breakdown by market cap range (sub-$1M only)
    print("2. MARKET CAP BREAKDOWN (Sub-$1M Only)")
    print("-" * 80)
    c.execute("""
        SELECT 
            CASE 
                WHEN first_market_cap_usd < 50000 THEN '<$50k'
                WHEN first_market_cap_usd < 100000 THEN '$50k-$100k'
                WHEN first_market_cap_usd < 200000 THEN '$100k-$200k'
                WHEN first_market_cap_usd < 500000 THEN '$200k-$500k'
                ELSE '$500k-$1M'
            END as mcap_bucket,
            COUNT(*) as count,
            ROUND(AVG(max_gain_percent), 2) as avg_gain,
            SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) as wins_2x,
            SUM(CASE WHEN is_rug = 1 THEN 1 ELSE 0 END) as rugs
        FROM alerted_token_stats
        WHERE first_market_cap_usd < 1000000
        GROUP BY mcap_bucket
        ORDER BY MIN(first_market_cap_usd)
    """)
    print(f"{'Market Cap':<15} {'Count':<8} {'Avg Gain':<12} {'2x+ Rate':<12} {'Rug Rate'}")
    for row in c.fetchall():
        mcap = row['mcap_bucket']
        count = row['count']
        avg_gain = row['avg_gain']
        wins = row['wins_2x']
        rugs = row['rugs']
        win_rate = wins / count * 100 if count > 0 else 0
        rug_rate = rugs / count * 100 if count > 0 else 0
        print(f"{mcap:<15} {count:<8} {avg_gain:<12.2f} {win_rate:<12.1f} {rug_rate:.1f}%")
    print()
    
    # 3. Liquidity breakdown (sub-$1M only)
    print("3. LIQUIDITY BREAKDOWN (Sub-$1M Only)")
    print("-" * 80)
    c.execute("""
        SELECT 
            CASE 
                WHEN first_liquidity_usd < 20000 THEN '<$20k'
                WHEN first_liquidity_usd < 30000 THEN '$20k-$30k'
                WHEN first_liquidity_usd < 50000 THEN '$30k-$50k'
                WHEN first_liquidity_usd < 75000 THEN '$50k-$75k'
                ELSE '$75k+'
            END as liq_bucket,
            COUNT(*) as count,
            ROUND(AVG(max_gain_percent), 2) as avg_gain,
            SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) as wins_2x,
            SUM(CASE WHEN is_rug = 1 THEN 1 ELSE 0 END) as rugs
        FROM alerted_token_stats
        WHERE first_market_cap_usd < 1000000
        GROUP BY liq_bucket
        ORDER BY MIN(first_liquidity_usd)
    """)
    print(f"{'Liquidity':<15} {'Count':<8} {'Avg Gain':<12} {'2x+ Rate':<12} {'Rug Rate'}")
    for row in c.fetchall():
        liq = row['liq_bucket']
        count = row['count']
        avg_gain = row['avg_gain']
        wins = row['wins_2x']
        rugs = row['rugs']
        win_rate = wins / count * 100 if count > 0 else 0
        rug_rate = rugs / count * 100 if count > 0 else 0
        print(f"{liq:<15} {count:<8} {avg_gain:<12.2f} {win_rate:<12.1f} {rug_rate:.1f}%")
    print()
    
    # 4. Compare 2x+ winners vs rugs (sub-$1M only)
    print("4. 2X+ WINNERS vs RUGS (Sub-$1M Only)")
    print("-" * 80)
    c.execute("""
        SELECT 
            '2x+ Winners' as category,
            COUNT(*) as count,
            ROUND(AVG(first_liquidity_usd), 0) as avg_liq,
            ROUND(AVG(first_market_cap_usd), 0) as avg_mcap,
            ROUND(AVG(first_volume_24h_usd), 0) as avg_vol,
            ROUND(AVG(max_gain_percent), 2) as avg_gain
        FROM alerted_token_stats
        WHERE first_market_cap_usd < 1000000 
        AND max_gain_percent >= 100
        
        UNION ALL
        
        SELECT 
            'Rugs' as category,
            COUNT(*) as count,
            ROUND(AVG(first_liquidity_usd), 0) as avg_liq,
            ROUND(AVG(first_market_cap_usd), 0) as avg_mcap,
            ROUND(AVG(first_volume_24h_usd), 0) as avg_vol,
            ROUND(AVG(max_gain_percent), 2) as avg_gain
        FROM alerted_token_stats
        WHERE first_market_cap_usd < 1000000 
        AND is_rug = 1
    """)
    print(f"{'Category':<15} {'Count':<8} {'Avg Liq':<15} {'Avg MCap':<15} {'Avg Vol':<15} {'Avg Gain'}")
    for row in c.fetchall():
        print(f"{row['category']:<15} {row['count']:<8} ${row['avg_liq']:>12,} ${row['avg_mcap']:>12,} ${row['avg_vol']:>12,} {row['avg_gain']:>6.1f}%")
    print()
    
    # 5. Recent performance (last 7 days, sub-$1M only)
    print("5. RECENT PERFORMANCE (Last 7 Days, Sub-$1M Only)")
    print("-" * 80)
    import time
    from datetime import datetime, timedelta
    seven_days_ago = (datetime.now() - timedelta(days=7)).timestamp()
    c.execute("""
        SELECT 
            COUNT(*) as recent,
            ROUND(AVG(max_gain_percent), 2) as avg_gain,
            SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) as wins_2x,
            SUM(CASE WHEN is_rug = 1 THEN 1 ELSE 0 END) as rugs
        FROM alerted_token_stats
        WHERE first_market_cap_usd < 1000000
        AND first_alert_at >= ?
    """, (seven_days_ago,))
    row = c.fetchone()
    recent = row['recent']
    recent_wins = row['wins_2x']
    recent_rugs = row['rugs']
    
    print(f"Recent Signals (7d): {recent}")
    print(f"2x+ Win Rate: {recent_wins}/{recent} ({recent_wins/recent*100:.1f}%)")
    print(f"Rug Rate: {recent_rugs}/{recent} ({recent_rugs/recent*100:.1f}%)")
    print(f"Average Gain: {row['avg_gain']:.2f}%")
    print()
    
    # 6. CRITICAL: How many signals are OVER $1M?
    print("6. MARKET CAP FILTER ENFORCEMENT")
    print("-" * 80)
    c.execute("""
        SELECT 
            COUNT(*) as over_1m,
            ROUND(MIN(first_market_cap_usd), 0) as min_mcap,
            ROUND(MAX(first_market_cap_usd), 0) as max_mcap,
            ROUND(AVG(first_market_cap_usd), 0) as avg_mcap
        FROM alerted_token_stats
        WHERE first_market_cap_usd >= 1000000
    """)
    row = c.fetchone()
    over_1m = row['over_1m']
    
    print(f"❌ Signals OVER $1M: {over_1m} (should be 0!)")
    if over_1m > 0:
        print(f"   Min: ${row['min_mcap']:,.0f}")
        print(f"   Max: ${row['max_mcap']:,.0f}")
        print(f"   Avg: ${row['avg_mcap']:,.0f}")
        print()
        print("   Recent examples:")
        c.execute("""
            SELECT 
                substr(token_address, 1, 8) as token,
                ROUND(first_market_cap_usd, 0) as mcap,
                ROUND(first_liquidity_usd, 0) as liq,
                final_score,
                datetime(first_alert_at, 'unixepoch') as alerted
            FROM alerted_token_stats s
            WHERE first_market_cap_usd >= 1000000
            ORDER BY first_alert_at DESC
            LIMIT 10
        """)
        for row in c.fetchall():
            print(f"   {row['token']}: ${row['mcap']:>10,} mcap, ${row['liq']:>10,} liq, score {row['final_score']}, {row['alerted']}")
    print()
    
    # 7. KEY RECOMMENDATIONS
    print("="*80)
    print("KEY FINDINGS & RECOMMENDATIONS")
    print("="*80)
    print()
    
    # Calculate optimal range
    c.execute("""
        SELECT 
            CASE 
                WHEN first_liquidity_usd < 30000 THEN '<$30k'
                WHEN first_liquidity_usd < 50000 THEN '$30k-$50k'
                WHEN first_liquidity_usd < 75000 THEN '$50k-$75k'
                ELSE '$75k+'
            END as liq_range,
            SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate_2x,
            SUM(CASE WHEN is_rug = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as rug_rate
        FROM alerted_token_stats
        WHERE first_market_cap_usd < 1000000
        GROUP BY liq_range
        HAVING COUNT(*) >= 20
        ORDER BY win_rate_2x DESC
        LIMIT 1
    """)
    best_liq = c.fetchone()
    
    c.execute("""
        SELECT 
            CASE 
                WHEN first_market_cap_usd < 100000 THEN '<$100k'
                WHEN first_market_cap_usd < 200000 THEN '$100k-$200k'
                ELSE '$200k-$1M'
            END as mcap_range,
            SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate_2x,
            SUM(CASE WHEN is_rug = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as rug_rate
        FROM alerted_token_stats
        WHERE first_market_cap_usd < 1000000
        GROUP BY mcap_range
        HAVING COUNT(*) >= 20
        ORDER BY win_rate_2x DESC
        LIMIT 1
    """)
    best_mcap = c.fetchone()
    
    print(f"1. Current 2x+ Win Rate: {wins_2x/total*100:.1f}% (Target: >30%)")
    print(f"2. Current Rug Rate: {rugs/total*100:.1f}% (Target: <30%)")
    print()
    print(f"3. Best Liquidity Range: {best_liq['liq_range']}")
    print(f"   - 2x+ Win Rate: {best_liq['win_rate_2x']:.1f}%")
    print(f"   - Rug Rate: {best_liq['rug_rate']:.1f}%")
    print()
    print(f"4. Best Market Cap Range: {best_mcap['mcap_range']}")
    print(f"   - 2x+ Win Rate: {best_mcap['win_rate_2x']:.1f}%")
    print(f"   - Rug Rate: {best_mcap['rug_rate']:.1f}%")
    print()
    print(f"5. CRITICAL BUG: {over_1m} signals exceeded $1M market cap limit!")
    print()
    
    conn.close()

if __name__ == "__main__":
    analyze_sub_1m()

