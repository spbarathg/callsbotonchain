#!/usr/bin/env python3
"""Comprehensive database audit."""
import sqlite3

conn = sqlite3.connect('var/alerted_tokens.db')

print("=" * 70)
print("DATABASE SCHEMA AUDIT")
print("=" * 70)

# Check alerted_tokens schema
print("\n📋 alerted_tokens table:")
cursor = conn.execute("PRAGMA table_info(alerted_tokens)")
cols = cursor.fetchall()
for col in cols:
    print(f"  - {col[1]} ({col[2]})")

# Check alerted_token_stats schema
print("\n📋 alerted_token_stats table:")
cursor = conn.execute("PRAGMA table_info(alerted_token_stats)")
cols = cursor.fetchall()
col_names = [col[1] for col in cols]
for col in cols:
    print(f"  - {col[1]} ({col[2]})")

# Check for ML columns
print("\n🤖 ML Column Check:")
ml_cols = ['ml_gain_prediction', 'ml_winner_probability', 'ml_score_adjustment']
for ml_col in ml_cols:
    exists = ml_col in col_names
    status = "✅ EXISTS" if exists else "❌ MISSING"
    print(f"  {ml_col}: {status}")

# Check signal counts
cursor = conn.execute("SELECT COUNT(*) FROM alerted_tokens")
total_signals = cursor.fetchone()[0]

cursor = conn.execute("SELECT COUNT(*) FROM alerted_token_stats")
total_stats = cursor.fetchone()[0]

print(f"\n📊 Record Counts:")
print(f"  alerted_tokens: {total_signals}")
print(f"  alerted_token_stats: {total_stats}")

# Check recent signals
cursor = conn.execute("""
    SELECT 
        datetime(a.alerted_at, 'unixepoch') as time,
        substr(a.token_address, 1, 12) as token,
        a.final_score,
        s.preliminary_score,
        s.conviction_type
    FROM alerted_tokens a
    LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
    ORDER BY a.alerted_at DESC
    LIMIT 5
""")

print(f"\n📝 Recent Signals:")
print(f"{'Time':<20} {'Token':<14} {'Final':<6} {'Prelim':<6} {'Conviction':<15}")
print("-" * 70)
for row in cursor.fetchall():
    time, token, final, prelim, conviction = row
    final_str = f"{final:.1f}" if final else "-"
    prelim_str = f"{prelim:.1f}" if prelim else "-"
    conviction_str = conviction or "-"
    print(f"{time:<20} {token:<14} {final_str:<6} {prelim_str:<6} {conviction_str:<15}")

conn.close()
print("=" * 70)

