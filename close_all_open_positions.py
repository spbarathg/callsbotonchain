"""Close all open positions in the database"""
import sqlite3

DB_PATH = "/app/var/trading.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Get all open positions
c.execute("SELECT id, token_address, qty, entry_price, usd_size FROM positions WHERE status='open'")
open_positions = c.fetchall()

if not open_positions:
    print("No open positions to close")
else:
    print(f"Found {len(open_positions)} open positions. Closing them...")
    for pos_id, token, qty, entry_price, usd_size in open_positions:
        print(f"Closing position #{pos_id}: {token[:8]}... (qty={qty:.0f}, entry=${entry_price:.8f}, cost=${usd_size:.2f})")
        c.execute("UPDATE positions SET status='closed', close_at=CURRENT_TIMESTAMP WHERE id=?", (pos_id,))
    
    conn.commit()
    print(f"✅ All {len(open_positions)} positions closed successfully")

conn.close()

