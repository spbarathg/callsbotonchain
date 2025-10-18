#!/usr/bin/env python3
"""
Check if rejected signals (prelim score but no alert) are losers or missed winners
"""
import sqlite3
from datetime import datetime, timedelta

print("="*60)
print("REJECTED SIGNALS ANALYSIS")
print("="*60)
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")

conn = sqlite3.connect('var/alerted_tokens.db')
c = conn.cursor()

# Check if we have prelim data (tokens that were evaluated but not alerted)
# This would be in a separate table or log
# For now, let's check the alerted tokens and their scores

print("\n1. SIGNAL FREQUENCY CHECK:")
print("-" * 40)

# Get signals per day for last 7 days
now = datetime.now().timestamp()
for days_ago in range(7):
    day_start = now - (days_ago + 1) * 86400
    day_end = now - days_ago * 86400
    
    c.execute("""
    SELECT COUNT(*) 
    FROM alerted_tokens 
    WHERE alerted_at BETWEEN ? AND ?
    """, (day_start, day_end))
    
    count = c.fetchone()[0]
    date_str = datetime.fromtimestamp(day_end).strftime('%Y-%m-%d')
    print(f"  {date_str}: {count} signals")

# Check score distribution
print("\n2. SCORE DISTRIBUTION (Last 24 hours):")
print("-" * 40)

yesterday = now - 86400

c.execute("""
SELECT 
    a.final_score,
    COUNT(*) as count,
    SUM(CASE WHEN s.max_gain_percent >= 100 THEN 1 ELSE 0 END) as winners_2x,
    AVG(s.max_gain_percent) as avg_gain
FROM alerted_tokens a
LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
WHERE a.alerted_at > ?
GROUP BY a.final_score
ORDER BY a.final_score DESC
""", (yesterday,))

print(f"{'Score':<8} {'Count':<8} {'2x+ Wins':<12} {'Avg Gain':<12}")
print("-" * 45)

for row in c.fetchall():
    score, count, winners, avg_gain = row
    winners = winners or 0
    avg_gain = avg_gain or 0
    print(f"{score:<8} {count:<8} {winners:<12} {avg_gain:<12.1f}%")

# Check minimum score over time
print("\n3. MINIMUM SCORE TREND (Last 7 days):")
print("-" * 40)

for days_ago in range(7):
    day_start = now - (days_ago + 1) * 86400
    day_end = now - days_ago * 86400
    
    c.execute("""
    SELECT MIN(final_score), AVG(final_score), MAX(final_score)
    FROM alerted_tokens 
    WHERE alerted_at BETWEEN ? AND ?
    """, (day_start, day_end))
    
    min_score, avg_score, max_score = c.fetchone()
    date_str = datetime.fromtimestamp(day_end).strftime('%Y-%m-%d')
    
    if min_score:
        print(f"  {date_str}: Min={min_score}, Avg={avg_score:.1f}, Max={max_score}")
    else:
        print(f"  {date_str}: No signals")

# Check config settings
print("\n4. CURRENT BOT CONFIG:")
print("-" * 40)

# These would normally come from environment or config
# For now, we'll note what to check
print("  Check these in .env or config:")
print("    - GENERAL_CYCLE_MIN_SCORE (current: 8)")
print("    - MAX_MARKET_CAP_USD (current: 100000)")
print("    - MIN_LIQUIDITY_USD (current: 30000)")
print("    - MAX_LIQUIDITY_USD (current: 75000)")
print("    - MAX_24H_CHANGE_FOR_ALERT (current: 200)")

# Check if there are tokens in stats but not in alerted_tokens
# This would indicate tokens that were tracked but not alerted
print("\n5. TRACKED BUT NOT ALERTED (Potential Missed Signals):")
print("-" * 40)

c.execute("""
SELECT COUNT(*)
FROM alerted_token_stats s
WHERE NOT EXISTS (
    SELECT 1 FROM alerted_tokens a 
    WHERE a.token_address = s.token_address
)
""")

not_alerted = c.fetchone()[0]
print(f"  Tokens tracked but not alerted: {not_alerted}")

if not_alerted > 0:
    print("\n  Analyzing these tokens...")
    
    c.execute("""
    SELECT 
        s.token_symbol,
        s.first_market_cap_usd,
        s.first_liquidity_usd,
        s.max_gain_percent,
        s.is_rug
    FROM alerted_token_stats s
    WHERE NOT EXISTS (
        SELECT 1 FROM alerted_tokens a 
        WHERE a.token_address = s.token_address
    )
    AND s.max_gain_percent IS NOT NULL
    ORDER BY s.max_gain_percent DESC
    LIMIT 20
    """)
    
    print(f"\n  {'Symbol':<12} {'Market Cap':<15} {'Liquidity':<15} {'Max Gain':<12} {'Status'}")
    print("  " + "-" * 70)
    
    missed_2x = 0
    for row in c.fetchall():
        symbol, mcap, liq, gain, is_rug = row
        
        if gain >= 100:
            missed_2x += 1
            status = "2x+ MISSED!" if not is_rug else "2x+ (rug)"
        elif is_rug:
            status = "Rug"
        else:
            status = f"{gain:.0f}%"
        
        mcap_str = f"${mcap:,.0f}" if mcap else "N/A"
        liq_str = f"${liq:,.0f}" if liq else "N/A"
        
        print(f"  {symbol:<12} {mcap_str:<15} {liq_str:<15} {gain:<12.1f} {status}")
    
    if missed_2x > 0:
        print(f"\n  WARNING: {missed_2x} tokens with 2x+ gains were NOT alerted!")
        print(f"  This suggests filters might be too strict.")

# Check recent hour signal rate
print("\n6. SIGNAL RATE (Last 6 hours):")
print("-" * 40)

for hours_ago in range(6):
    hour_start = now - (hours_ago + 1) * 3600
    hour_end = now - hours_ago * 3600
    
    c.execute("""
    SELECT COUNT(*) 
    FROM alerted_tokens 
    WHERE alerted_at BETWEEN ? AND ?
    """, (hour_start, hour_end))
    
    count = c.fetchone()[0]
    hour_str = f"{hours_ago+1}h ago"
    print(f"  {hour_str:<10}: {count} signals")

total_6h = sum([c.execute("SELECT COUNT(*) FROM alerted_tokens WHERE alerted_at > ?", (now - 3600 * (i+1),)).fetchone()[0] for i in range(6)])
print(f"\n  Total last 6h: {total_6h} signals ({total_6h/6:.1f} per hour)")
print(f"  Expected: 20-25 signals/day = 0.8-1.0 per hour")

if total_6h / 6 < 0.5:
    print(f"  WARNING: Signal rate is LOW! ({total_6h/6:.1f}/hour)")
    print(f"  Expected: 0.8-1.0/hour")
    print(f"  Possible causes:")
    print(f"    - MIN_SCORE too high (check if it's 8 or higher)")
    print(f"    - Market is slow right now")
    print(f"    - Filters are too strict")

conn.close()

print("\n" + "="*60)
print("RECOMMENDATIONS:")
print("="*60)

print("\nIf signal frequency is low:")
print("  1. Check MIN_SCORE - if it's 9+, consider lowering to 8")
print("  2. Check MAX_LIQUIDITY_USD - if it's 75k, consider 100k-140k")
print("  3. Check if market is slow (check DexScreener)")
print("  4. Review if ML is penalizing too many signals")

print("\nIf missing 2x+ winners:")
print("  1. Filters are too strict - need to relax")
print("  2. Consider lowering MIN_SCORE")
print("  3. Consider increasing MAX_LIQUIDITY_USD")
print("  4. Check if MAX_24H_CHANGE is rejecting early pumps")

print("\n" + "="*60)

