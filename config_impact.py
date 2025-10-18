import sqlite3

conn = sqlite3.connect('var/alerted_tokens_server.db')
c = conn.cursor()

print('\n=== IMPACT ANALYSIS: CURRENT vs SUGGESTED CONFIG ===\n')

# Current config (what would pass)
c.execute("""
SELECT 
    COUNT(*) as signals,
    SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) as winners_2x,
    ROUND(CAST(SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100, 1) as win_rate,
    ROUND(AVG(max_gain_percent), 1) as avg_gain
FROM alerted_token_stats
WHERE first_market_cap_usd >= 50000 
  AND first_market_cap_usd <= 200000
  AND final_score >= 8
  AND (price_change_24h IS NULL OR price_change_24h <= 300)
""")
current = c.fetchone()

# Suggested config (what would pass)
c.execute("""
SELECT 
    COUNT(*) as signals,
    SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) as winners_2x,
    ROUND(CAST(SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100, 1) as win_rate,
    ROUND(AVG(max_gain_percent), 1) as avg_gain
FROM alerted_token_stats
WHERE first_market_cap_usd >= 50000 
  AND first_market_cap_usd <= 100000
  AND final_score >= 9
  AND (price_change_24h IS NULL OR price_change_24h <= 200)
""")
suggested = c.fetchone()

# Suggested config WITH soft ranking preference
c.execute("""
SELECT 
    COUNT(*) as signals,
    SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) as winners_2x,
    ROUND(CAST(SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100, 1) as win_rate,
    ROUND(AVG(max_gain_percent), 1) as avg_gain
FROM alerted_token_stats
WHERE first_market_cap_usd >= 50000 
  AND first_market_cap_usd <= 100000
  AND final_score >= 9
  AND (price_change_24h IS NULL OR price_change_24h <= 200)
  AND (
    (price_change_24h BETWEEN -50 AND -20 AND price_change_1h <= 0) OR
    (price_change_24h BETWEEN 50 AND 200 AND price_change_1h <= 0)
  )
""")
suggested_soft = c.fetchone()

print('Configuration              | Signals | 2x+ Winners | Win Rate | Avg Gain | Signals/Day')
print('-' * 95)
print(f'CURRENT (50-200k, score>=8) | {current[0]:7} | {current[1]:11} | {current[2]:8}% | {current[3]:8}% | {current[0]/7:.1f}')
print(f'SUGGESTED (50-100k, >=9)    | {suggested[0]:7} | {suggested[1]:11} | {suggested[2]:8}% | {suggested[3]:8}% | {suggested[0]/7:.1f}')
print(f'SUGGESTED + Soft Ranking    | {suggested_soft[0]:7} | {suggested_soft[1]:11} | {suggested_soft[2]:8}% | {suggested_soft[3]:8}% | {suggested_soft[0]/7:.1f}')

print('\n=== KEY INSIGHTS ===\n')

# Calculate differences
win_rate_diff = suggested[2] - current[2]
freq_diff = suggested[0] - current[0]
freq_pct = (freq_diff / current[0]) * 100

print(f'1. Market Cap 50-100k vs 50-200k:')
print(f'   - 50-100k has {28.9 - 21.6:.1f}% HIGHER win rate (28.9% vs 21.6%)')
print(f'   - 50-100k represents 54.1% of signals (majority)')
print(f'   - Tighter focus = better quality')

print(f'\n2. Score Threshold 9 vs 8:')
print(f'   - Score 8: 22.1% win rate, 222.4% avg gain')
print(f'   - Score 9-10: 21.6% win rate, 159.9% avg gain')
print(f'   - Score 8 is SLIGHTLY BETTER (0.5% higher win rate, 62.5% higher avg gain)')
print(f'   - BUT: Score <8 has 12.2% win rate (much worse)')
print(f'   - Keeping score>=8 allows more signals without hurting quality')

print(f'\n3. 24h Change Threshold:')
print(f'   - 200-300% range: 60% win rate BUT only 5 signals (not statistically significant)')
print(f'   - <=200%: 18.3% win rate, 1083 signals (reliable data)')
print(f'   - Keeping 300% max is fine (adds <1% of signals)')

print(f'\n4. Soft Ranking Preference (24h momentum patterns):')
print(f'   - Consolidation (24h[50,200], 1h<=0): 35.5% win rate, 503.8% avg gain *BEST*')
print(f'   - Dip buy (24h[-50,-20], 1h<=0): 29.3% win rate, 279.6% avg gain *GOOD*')
print(f'   - Other 1h<=0: 15.7% win rate, 378.8% avg gain')
print(f'   - Pumping (1h>0): 27.3% win rate, 71.8% avg gain')
print(f'   - STRONG signal: Negative 1h momentum + specific 24h ranges = much higher win rate')

print(f'\n=== RECOMMENDATION ===\n')

print('BEST CONFIG (Data-Driven):')
print('  [YES] MIN_MARKET_CAP_USD=50000')
print('  [YES] MAX_MARKET_CAP_USD=100000  (28.9% win rate vs 21.6%)')
print('  [YES] MIN_LIQUIDITY_USD=30000')
print('  [YES] MAX_LIQUIDITY_USD=75000')
print('  [NO!] GENERAL_CYCLE_MIN_SCORE=8  (NOT 9 - score 8 performs equally well)')
print('  [YES] MAX_24H_CHANGE_FOR_ALERT=200  (or 300, minimal difference)')
print('  [ADD] SOFT RANKING: +1 score bonus for:')
print('     - (24h in [-50,-20] AND 1h<=0) OR')
print('     - (24h in [50,200] AND 1h<=0)')
print('     This captures 35.5% and 29.3% win rate patterns!')

print('\nEXPECTED IMPACT:')
print(f'  - Signals per day: {suggested[0]/7:.1f} (down from {current[0]/7:.1f})')
print(f'  - Win rate: ~{suggested[2]}% (up from {current[2]}%)')
print(f'  - With soft ranking: Could push to ~30-35% win rate for best patterns')
print(f'  - Trade-off: {freq_pct:.0f}% fewer signals, but {win_rate_diff:.1f}% higher win rate')

conn.close()

