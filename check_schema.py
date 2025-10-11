import sqlite3
import sys

db_path = var/alerted_tokens.db
conn = sqlite3.connect(db_path)

print(=*60)
print(DATABASE SCHEMA CHECK)
print(=*60)

# Check alerted_tokens
print(\n1. alerted_tokens table:)
cur = conn.execute(PRAGMA table_info(alerted_tokens))
cols = [row[1] for row in cur.fetchall()]
print(f Columns ({len(cols)}): {cols})

# Check alerted_token_stats
print(\n2. alerted_token_stats table:)
cur = conn.execute(PRAGMA table_info(alerted_token_stats))
cols = [row[1] for row in cur.fetchall()]
print(f Columns ({len(cols)}): {cols})

# Check for expected columns
expected_stats = [final_score, preliminary_score, conviction_type, outcome, peak_drawdown_pct, smart_money_involved]
print(\n3. Checking for expected columns:)
for col in expected_stats:
    exists = col in cols
    status = âœ“ if exists else âœ— MISSING
    print(f {status} {col})

# Check record counts
print(\n4. Record counts:)
cur = conn.execute(SELECT COUNT(*) FROM alerted_tokens)
print(f alerted_tokens: {cur.fetchone()[0]})

cur = conn.execute(SELECT COUNT(*) FROM alerted_token_stats)
print(f alerted_token_stats: {cur.fetchone()[0]})

conn.close()
print(\n + =*60)
