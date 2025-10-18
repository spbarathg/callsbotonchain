#!/usr/bin/env python3
"""
Merge CSV data with server database for combined ML training
"""
import sqlite3
import shutil
import os

print("="*60)
print("MERGING CSV DATA WITH SERVER DATABASE")
print("="*60)

# Paths
server_db = 'var/alerted_tokens.db'
csv_db = 'var/csv_ml_data.db'
merged_db = 'var/merged_ml_data.db'

# Check files exist
if not os.path.exists(server_db):
    print(f"\nERROR: {server_db} not found!")
    print("Please copy from server first.")
    exit(1)

if not os.path.exists(csv_db):
    print(f"\nERROR: {csv_db} not found!")
    print("Run convert_csv_to_ml_format.py first.")
    exit(1)

# Create merged database (copy of server db)
print(f"\nCreating merged database...")
shutil.copy(server_db, merged_db)
print(f"  Copied {server_db} -> {merged_db}")

# Open databases
print(f"\nMerging data...")
conn = sqlite3.connect(merged_db)
c = conn.cursor()

# Attach CSV database
conn.execute(f"ATTACH DATABASE '{csv_db}' AS csv")

# Get counts before merge
c.execute("SELECT COUNT(*) FROM alerted_tokens")
before_count = c.fetchone()[0]

c.execute("SELECT COUNT(*) FROM csv.alerted_tokens")
csv_count = c.fetchone()[0]

print(f"  Server data: {before_count} tokens")
print(f"  CSV data: {csv_count} tokens")

# Merge alerted_tokens (ignore duplicates)
c.execute("""
INSERT OR IGNORE INTO alerted_tokens 
SELECT * FROM csv.alerted_tokens
""")
merged_tokens = c.rowcount
print(f"  Merged {merged_tokens} new tokens into alerted_tokens")

# Merge alerted_token_stats (ignore duplicates, match columns)
# Get common columns
c.execute("PRAGMA table_info(alerted_token_stats)")
main_cols = [row[1] for row in c.fetchall()]

c.execute("PRAGMA csv.table_info(alerted_token_stats)")
csv_cols = [row[1] for row in c.fetchall()]

common_cols = [col for col in csv_cols if col in main_cols]
cols_str = ', '.join(common_cols)

print(f"  Merging {len(common_cols)} common columns...")

c.execute(f"""
INSERT OR IGNORE INTO alerted_token_stats ({cols_str})
SELECT {cols_str} FROM csv.alerted_token_stats
""")
merged_stats = c.rowcount
print(f"  Merged {merged_stats} new stats into alerted_token_stats")

# Get counts after merge
c.execute("SELECT COUNT(*) FROM alerted_tokens")
after_count = c.fetchone()[0]

c.execute("SELECT COUNT(*) FROM alerted_token_stats WHERE max_gain_percent >= 100")
winners_2x = c.fetchone()[0]

c.execute("SELECT COUNT(*) FROM alerted_token_stats WHERE is_rug = 1")
rugs = c.fetchone()[0]

conn.commit()
conn.close()

print(f"\nMerge complete!")
print(f"  Total tokens: {after_count} (was {before_count}, added {after_count - before_count})")
print(f"  2x+ winners: {winners_2x}")
print(f"  Rugs: {rugs}")

print(f"\nMerged database saved to: {merged_db}")
print("\nNext step:")
print(f"  python scripts/ml/train_model.py {merged_db}")

print("\n" + "="*60)

