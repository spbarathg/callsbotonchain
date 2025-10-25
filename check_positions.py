import sqlite3
conn = sqlite3.connect('/app/var/trading.db')
c = conn.cursor()

print('=== ALL POSITIONS (Last 30) ===')
c.execute("""
    SELECT id, token_address, qty, entry_price, usd_size, peak_price, status, open_at
    FROM positions 
    ORDER BY id DESC LIMIT 30
""")
for row in c.fetchall():
    pos_id, token, qty, entry_price, entry_cost, peak, status, open_at = row
    print(f'#{pos_id} {token[:8]}... qty={qty:.0f} entry=${entry_price:.8f} cost=${entry_cost:.2f} peak=${peak:.2f} status={status}')

print()
print('=== OPEN POSITIONS ===')
c.execute("""
    SELECT id, token_address, qty, entry_price, usd_size, peak_price, open_at
    FROM positions 
    WHERE status='open'
    ORDER BY id DESC
""")
for row in c.fetchall():
    pos_id, token, qty, entry_price, entry_cost, peak, open_at = row
    print(f'#{pos_id} {token[:8]}... qty={qty:.0f} entry=${entry_price:.8f} cost=${entry_cost:.2f} peak=${peak:.2f}')

print()
print('=== FILLS (Last 30) ===')
c.execute("""
    SELECT position_id, side, qty, price, proceeds, created_at
    FROM fills
    ORDER BY id DESC LIMIT 30
""")
for row in c.fetchall():
    pos_id, side, qty, price, proceeds, created = row
    print(f'Pos #{pos_id} {side} qty={qty:.0f} price=${price:.8f} proceeds=${proceeds:.2f}')

conn.close()

