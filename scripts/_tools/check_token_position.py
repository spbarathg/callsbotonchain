#!/usr/bin/env python3
"""Check position status for a specific token"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tradingSystem.db import _conn

TOKEN = "2k9LnRAWJJBmmEzgXARwSEzoU1DorBYQHTXZtxusbonk"

conn = _conn()

# Get position details (using actual schema columns)
cur = conn.execute(
    """
    SELECT id, status, entry_price, qty, usd_size, 
           peak_price, trail_pct, open_at
    FROM positions
    WHERE token_address = ?
    ORDER BY id DESC
    LIMIT 1
    """,
    (TOKEN,)
)

row = cur.fetchone()

if not row:
    print(f"❌ Position NOT FOUND for {TOKEN[:8]}...")
else:
    pos_id, status, entry_price, qty, usd_size, peak_price, trail_pct, open_at = row
    
    print(f"\n{'='*60}")
    print(f"📊 POSITION DETAILS: {TOKEN[:8]}...")
    print(f"{'='*60}")
    print(f"ID:           #{pos_id}")
    print(f"Status:       {status.upper()}")
    print(f"Entry Price:  ${entry_price}")
    print(f"Peak Price:   ${peak_price if peak_price else 'N/A'}")
    print(f"Quantity:     {qty:,.2f}")
    print(f"Position Size: ${usd_size:.2f}")
    print(f"Trail %:      {trail_pct}%")
    print(f"Opened At:    {open_at}")
    
    # Calculate current P&L if we have peak price
    if peak_price and entry_price and usd_size:
        peak_usd = qty * peak_price
        pnl_usd = peak_usd - usd_size
        pnl_pct = (pnl_usd / usd_size * 100) if usd_size > 0 else 0
        print(f"\n💰 PEAK P&L: ${pnl_usd:.2f} ({pnl_pct:.2f}%)")
    
    print(f"{'='*60}\n")
    
    # Get fills for this position
    fills_cur = conn.execute(
        """
        SELECT side, price, qty, timestamp
        FROM fills
        WHERE position_id = ?
        ORDER BY timestamp DESC
        """,
        (pos_id,)
    )
    
    fills = fills_cur.fetchall()
    if fills:
        print(f"📜 FILLS HISTORY:")
        print(f"{'='*60}")
        for side, price, fill_qty, timestamp in fills:
            print(f"{side.upper()}: {fill_qty:,.2f} @ ${price} | {timestamp}")
        print(f"{'='*60}\n")

