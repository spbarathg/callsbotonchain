"""
Database Migration: Add Missing Columns to alerted_token_stats
Fixes schema mismatch between storage.py definition and actual database
"""
import sqlite3
import os


def migrate_database():
    """Add missing columns to alerted_token_stats"""
    
    db_path = 'var/alerted_tokens.db'
    
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path}")
        return False
    
    print("="*60)
    print("DATABASE MIGRATION")
    print("="*60)
    
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    
    # Get existing columns
    cur.execute("PRAGMA table_info(alerted_token_stats)")
    existing_cols = {row[1] for row in cur.fetchall()}
    
    print("\nChecking for missing columns...")
    
    # Columns that should exist based on storage.py
    migrations = [
        ("final_score", "INTEGER"),
        ("conviction_type", "TEXT"),
    ]
    
    applied = []
    for col_name, col_type in migrations:
        if col_name not in existing_cols:
            print(f"   Adding column: {col_name} ({col_type})")
            try:
                cur.execute(f"ALTER TABLE alerted_token_stats ADD COLUMN {col_name} {col_type}")
                applied.append(col_name)
            except Exception as e:
                print(f"   ERROR adding {col_name}: {e}")
        else:
            print(f"   [OK] {col_name} already exists")
    
    if applied:
        # Populate final_score and conviction_type from alerted_tokens
        print("\nPopulating new columns from alerted_tokens...")
        try:
            cur.execute("""
                UPDATE alerted_token_stats
                SET 
                    final_score = (SELECT final_score FROM alerted_tokens WHERE alerted_tokens.token_address = alerted_token_stats.token_address),
                    conviction_type = (SELECT conviction_type FROM alerted_tokens WHERE alerted_tokens.token_address = alerted_token_stats.token_address)
                WHERE EXISTS (SELECT 1 FROM alerted_tokens WHERE alerted_tokens.token_address = alerted_token_stats.token_address)
            """)
            rows_updated = cur.rowcount
            print(f"   Updated {rows_updated} rows")
        except Exception as e:
            print(f"   ERROR updating: {e}")
    
    con.commit()
    con.close()
    
    print("\n" + "="*60)
    if applied:
        print("SUCCESS: Migration complete!")
        print(f"Added columns: {', '.join(applied)}")
    else:
        print("INFO: No migration needed, all columns exist")
    print("="*60)
    
    return True


if __name__ == '__main__':
    migrate_database()

