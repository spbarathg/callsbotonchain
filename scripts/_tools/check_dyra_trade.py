#!/usr/bin/env python3
"""Check complete trading history for DyRAaLJM token"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tradingSystem.db import _conn

TOKEN = "DyRAaLJMT7MbJE3HVxjTsUo186yDgwGkSWpiTmdzpump"

conn = _conn()

# Get ALL positions for this token
cur = conn.execute(
    """
    SELECT id, status, entry_price, qty, usd_size, peak_price, 
           trail_pct, open_at, strategy
    FROM positions
    WHERE token_address = ?
    ORDER BY id DESC
    """,
    (TOKEN,)
)

positions = cur.fetchall()

print(f"\n{'='*80}")
print(f"TRADING HISTORY: {TOKEN[:8]}...")
print(f"{'='*80}\n")

if not positions:
    print("❌ No trades found for this token")
else:
    for pos_id, status, entry_price, qty, usd_size, peak_price, trail_pct, open_at, strategy in positions:
        print(f"Position #{pos_id}")
        print(f"  Status:       {status.upper()}")
        print(f"  Strategy:     {strategy}")
        print(f"  Entry:        ${entry_price:.10f} ({open_at})")
        print(f"  Size:         ${usd_size:.2f}")
        print(f"  Quantity:     {qty:,.2f} tokens")
        print(f"  Trail Stop:   {trail_pct}%")
        
        if peak_price and entry_price:
            peak_pnl = ((peak_price - entry_price) / entry_price * 100)
            print(f"  Peak Price:   ${peak_price:.10f}")
            print(f"  Peak P&L:     {peak_pnl:+.2f}%")
        
        # Get fills
        fills_cur = conn.execute(
            """
            SELECT side, price, qty, usd, at
            FROM fills
            WHERE position_id = ?
            ORDER BY at ASC
            """,
            (pos_id,)
        )
        
        fills = fills_cur.fetchall()
        if fills:
            print(f"\n  Fills:")
            total_bought = 0
            total_sold = 0
            buy_usd = 0
            sell_usd = 0
            
            for side, price, fill_qty, fill_usd, at in fills:
                print(f"    {side.upper():4} {fill_qty:15,.2f} tokens @ ${price:.10f} = ${fill_usd:.2f} | {at}")
                if side.lower() == 'buy':
                    total_bought += fill_qty
                    buy_usd += fill_usd
                else:
                    total_sold += fill_qty
                    sell_usd += fill_usd
            
            if total_bought > 0 and total_sold > 0:
                realized_pnl = sell_usd - buy_usd
                realized_pnl_pct = (realized_pnl / buy_usd * 100) if buy_usd > 0 else 0
                print(f"\n  💰 REALIZED P&L: ${realized_pnl:.2f} ({realized_pnl_pct:+.2f}%)")
                print(f"     Bought: {total_bought:,.2f} tokens for ${buy_usd:.2f}")
                print(f"     Sold:   {total_sold:,.2f} tokens for ${sell_usd:.2f}")
        
        print(f"\n{'-'*80}\n")

conn.close()

