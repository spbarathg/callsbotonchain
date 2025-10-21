#!/usr/bin/env python3
"""Close ghost positions (open positions with no fills)"""
import sqlite3
import sys

DB_PATH = "/app/var/trading.db"

try:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Find and close positions with no buy fills
    c.execute("""
        UPDATE positions 
        SET status='closed' 
        WHERE id IN (
            SELECT p.id 
            FROM positions p 
            LEFT JOIN fills f ON p.id=f.position_id 
            WHERE p.status='open' 
            GROUP BY p.id 
            HAVING COALESCE(SUM(CASE WHEN f.side='buy' THEN f.qty ELSE 0 END),0) = 0
        )
    """)
    
    count = c.rowcount
    conn.commit()
    conn.close()
    
    print(f"✅ Closed {count} ghost positions")
    sys.exit(0)
    
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

