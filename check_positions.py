import sqlite3

conn = sqlite3.connect('/app/var/trading.db')
cur = conn.cursor()

print("=== RECENT POSITIONS ===")
rows = cur.execute('SELECT id, token, qty, entry_price_usd, usd_size, status, created_at FROM positions ORDER BY id DESC LIMIT 5').fetchall()
for r in rows:
    print(r)

print("\n=== OPEN POSITIONS ===")
rows = cur.execute("SELECT id, token, qty, entry_price_usd, usd_size, status FROM positions WHERE status='open'").fetchall()
for r in rows:
    print(r)

conn.close()


