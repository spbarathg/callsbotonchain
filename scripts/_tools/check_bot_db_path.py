#!/usr/bin/env python3
"""Check what database the bot is using"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tradingSystem.config_optimized import DB_PATH
import sqlite3

print(f"🔍 Bot's DB_PATH: {DB_PATH}\n")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("SELECT COUNT(*) FROM positions WHERE status='open'")
open_count = c.fetchone()[0]
print(f"📊 Open positions in bot's database: {open_count}")

if open_count > 0:
    print(f"\n⚠️  Found {open_count} OPEN positions:")
    c.execute("SELECT id, token_address, status, open_at FROM positions WHERE status='open' ORDER BY id DESC")
    for row in c.fetchall():
        print(f"  #{row[0]}: {row[1][:15]}... status={row[2]} opened={row[3]}")

conn.close()






