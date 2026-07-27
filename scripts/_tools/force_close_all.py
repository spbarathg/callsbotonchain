#!/usr/bin/env python3
"""Force-close all open positions to clear the slate"""

import sqlite3
import time
import os

# Connect to database
db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'var', 'trading.db')
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Get all open positions
c.execute('SELECT id, token_address FROM positions WHERE status = ?', ('open',))
positions = c.fetchall()

print(f'Found {len(positions)} open positions to force-close')

# Close all open positions
for pid, token in positions:
    c.execute('UPDATE positions SET status = ?, closed_at = ? WHERE id = ?', 
              ('closed', time.time(), pid))
    print(f'✅ Closed position #{pid} ({token[:8]}...)')

conn.commit()
conn.close()

print(f'\n🎯 All {len(positions)} positions force-closed. Bot ready for fresh signals!')

