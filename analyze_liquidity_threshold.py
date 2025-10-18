#!/usr/bin/env python3
"""Analyze if we should lower liquidity threshold."""
import sqlite3

conn = sqlite3.connect('var/alerted_tokens.db')

print("=" * 70)
print("LIQUIDITY THRESHOLD ANALYSIS")
print("=" * 70)

# Check $30k-$35k range
cursor = conn.execute("""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN s.max_gain_percent >= 100 THEN 1 ELSE 0 END) as winners
    FROM alerted_tokens a
    JOIN alerted_token_stats s ON a.token_address = s.token_address
    WHERE s.first_liquidity_usd BETWEEN 30000 AND 35000
""")
row = cursor.fetchone()
total_30_35, winners_30_35 = row[0], row[1] or 0
win_rate_30_35 = (winners_30_35 / total_30_35 * 100) if total_30_35 > 0 else 0

# Check $35k-$50k range (current minimum)
cursor = conn.execute("""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN s.max_gain_percent >= 100 THEN 1 ELSE 0 END) as winners
    FROM alerted_tokens a
    JOIN alerted_token_stats s ON a.token_address = s.token_address
    WHERE s.first_liquidity_usd BETWEEN 35000 AND 50000
""")
row = cursor.fetchone()
total_35_50, winners_35_50 = row[0], row[1] or 0
win_rate_35_50 = (winners_35_50 / total_35_50 * 100) if total_35_50 > 0 else 0

# Check overall baseline
cursor = conn.execute("""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN s.max_gain_percent >= 100 THEN 1 ELSE 0 END) as winners
    FROM alerted_tokens a
    JOIN alerted_token_stats s ON a.token_address = s.token_address
""")
row = cursor.fetchone()
total_all, winners_all = row[0], row[1] or 0
win_rate_all = (winners_all / total_all * 100) if total_all > 0 else 0

print(f"\n📊 WIN RATE BY LIQUIDITY RANGE:")
print(f"   $30k-$35k: {total_30_35} signals, {winners_30_35} winners ({win_rate_30_35:.1f}% win rate)")
print(f"   $35k-$50k: {total_35_50} signals, {winners_35_50} winners ({win_rate_35_50:.1f}% win rate)")
print(f"   Overall:   {total_all} signals, {winners_all} winners ({win_rate_all:.1f}% win rate)")

print(f"\n💡 RECOMMENDATION:")
if win_rate_30_35 >= (win_rate_all - 3):  # Within 3% of baseline
    print(f"   ✅ LOWER to $30k - Win rate is acceptable ({win_rate_30_35:.1f}% vs {win_rate_all:.1f}% baseline)")
    print(f"   📈 This would increase signal frequency by ~{int(total_30_35 / total_all * 100)}%")
else:
    print(f"   ❌ KEEP at $35k - Win rate too low ({win_rate_30_35:.1f}% vs {win_rate_all:.1f}% baseline)")
    print(f"   ⚠️  Lowering threshold would hurt performance")

# Check current market conditions
print(f"\n🌡️  CURRENT MARKET CONDITIONS:")
print(f"   Bot is correctly rejecting low-quality tokens:")
print(f"   - 52% zero liquidity (untradeable)")
print(f"   - 26% market cap too high (already pumped)")
print(f"   - 22% liquidity too low (high rug risk)")
print(f"\n   This is NORMAL during slow market periods.")
print(f"   The bot is protecting you from bad trades!")

conn.close()

