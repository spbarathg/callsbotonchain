import sqlite3

conn = sqlite3.connect('var/alerted_tokens_server.db')
c = conn.cursor()

print('\n=== 1. MARKET CAP COMPARISON ===')
print('Range                | Signals | 2x+ Winners | Win Rate | Avg Gain | Frequency')
print('-' * 85)
c.execute("""
SELECT 
    CASE 
        WHEN first_market_cap_usd < 100000 THEN '50k-100k (SUGGESTED)'
        WHEN first_market_cap_usd < 200000 THEN '100k-200k (CURRENT)'
    END as range,
    COUNT(*) as signals,
    SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) as winners,
    ROUND(CAST(SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100, 1) as pct,
    ROUND(AVG(max_gain_percent), 1) as avg,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM alerted_token_stats WHERE first_market_cap_usd >= 50000 AND first_market_cap_usd < 200000), 1) as freq_pct
FROM alerted_token_stats
WHERE first_market_cap_usd >= 50000 AND first_market_cap_usd < 200000
GROUP BY range
""")
for row in c.fetchall():
    print(f'{row[0]:20} | {row[1]:7} | {row[2]:11} | {row[3]:7}% | {row[4]:8}% | {row[5]:7}%')

print('\n=== 2. SCORE THRESHOLD COMPARISON (Current: 8 vs Suggested: 9) ===')
print('Score Range         | Signals | 2x+ Winners | Win Rate | Avg Gain')
print('-' * 75)
c.execute("""
SELECT 
    CASE 
        WHEN final_score >= 9 THEN 'Score 9-10 (SUGGESTED)'
        WHEN final_score = 8 THEN 'Score 8 (CURRENT ONLY)'
        WHEN final_score < 8 THEN 'Score <8 (REJECTED)'
    END as range,
    COUNT(*) as signals,
    SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) as winners,
    ROUND(CAST(SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100, 1) as pct,
    ROUND(AVG(max_gain_percent), 1) as avg
FROM alerted_token_stats
WHERE final_score IS NOT NULL
GROUP BY range
ORDER BY final_score DESC
""")
for row in c.fetchall():
    print(f'{row[0]:20} | {row[1]:7} | {row[2]:11} | {row[3]:8}% | {row[4]:8}%')

print('\n=== 3. 24H CHANGE THRESHOLD (Current: 300% vs Suggested: 200%) ===')
print('24h Change Range    | Signals | 2x+ Winners | Win Rate | Avg Gain')
print('-' * 75)
c.execute("""
SELECT 
    CASE 
        WHEN price_change_24h <= 200 THEN '<=200% (SUGGESTED)'
        WHEN price_change_24h <= 300 THEN '200-300% (CURRENT)'
        ELSE '>300% (REJECTED)'
    END as range,
    COUNT(*) as signals,
    SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) as winners,
    ROUND(CAST(SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100, 1) as pct,
    ROUND(AVG(max_gain_percent), 1) as avg
FROM alerted_token_stats
WHERE price_change_24h IS NOT NULL
GROUP BY range
ORDER BY price_change_24h
""")
for row in c.fetchall():
    print(f'{row[0]:20} | {row[1]:7} | {row[2]:11} | {row[3]:8}% | {row[4]:8}%')

print('\n=== 4. SOFT RANKING PREFERENCE ANALYSIS ===')
print('Condition                          | Signals | 2x+ Winners | Win Rate | Avg Gain')
print('-' * 85)
c.execute("""
SELECT 
    CASE 
        WHEN price_change_24h BETWEEN -50 AND -20 AND price_change_1h <= 0 THEN 'Dip buy: 24h[-50,-20], 1h<=0'
        WHEN price_change_24h BETWEEN 50 AND 200 AND price_change_1h <= 0 THEN 'Consolidation: 24h[50,200], 1h<=0'
        WHEN price_change_1h <= 0 THEN 'Other: 1h<=0'
        ELSE 'Pumping: 1h>0'
    END as condition,
    COUNT(*) as signals,
    SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) as winners,
    ROUND(CAST(SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100, 1) as pct,
    ROUND(AVG(max_gain_percent), 1) as avg
FROM alerted_token_stats
WHERE price_change_24h IS NOT NULL AND price_change_1h IS NOT NULL
GROUP BY condition
ORDER BY pct DESC
""")
for row in c.fetchall():
    print(f'{row[0]:35} | {row[1]:7} | {row[2]:11} | {row[3]:8}% | {row[4]:8}%')

print('\n=== SUMMARY: CURRENT vs SUGGESTED CONFIG ===')
print('\nCURRENT CONFIG (Broader):')
print('  - Market Cap: 50k-200k')
print('  - Min Score: 8')
print('  - Max 24h Change: 300%')
print('  - No soft ranking preference')
print('\nSUGGESTED CONFIG (Tighter):')
print('  - Market Cap: 50k-100k')
print('  - Min Score: 9')
print('  - Max 24h Change: 200%')
print('  - Soft ranking: prefer 24h in [-50,-20] or [50,200] with 1h<=0')

conn.close()

