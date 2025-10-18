import sqlite3
conn = sqlite3.connect('var/alerted_tokens.db')
cursor = conn.execute("PRAGMA table_info(alerted_tokens)")
cols = [row[1] for row in cursor.fetchall()]
print("Columns:", ', '.join(cols))
cursor = conn.execute("SELECT COUNT(*) FROM alerted_tokens")
print(f"Total signals: {cursor.fetchone()[0]}")

