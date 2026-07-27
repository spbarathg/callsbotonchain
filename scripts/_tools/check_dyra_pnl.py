#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.tradingSystem.db import _conn

TOKEN = "DyRAaLJMT7MbJE3HVxjTsUo186yDgwGkSWpiTmdzpump"
conn = _conn()

# Get position
cur = conn.execute("SELECT id, status FROM positions WHERE token_address = ? ORDER BY id DESC LIMIT 1", (TOKEN,))
pos = cur.fetchone()

if not pos:
    print("No position found")
    sys.exit(1)

pos_id, status = pos
print(f"Position #{pos_id}: {status}")

# Get all fills
cur = conn.execute("SELECT side, price, qty, usd, at FROM fills WHERE position_id = ? ORDER BY at", (pos_id,))
fills = cur.fetchall()

buy_qty = buy_usd = sell_qty = sell_usd = 0

for side, price, qty, usd, at in fills:
    print(f"  {side.upper():4} {qty:,.2f} @ ${price:.10f} = ${usd:.2f} [{at}]")
    if side.lower() == 'buy':
        buy_qty += qty
        buy_usd += usd
    else:
        sell_qty += qty
        sell_usd += usd

if buy_qty > 0:
    print(f"\nBought: {buy_qty:,.2f} tokens for ${buy_usd:.2f}")
if sell_qty > 0:
    print(f"Sold: {sell_qty:,.2f} tokens for ${sell_usd:.2f}")
    pnl = sell_usd - buy_usd
    pnl_pct = (pnl / buy_usd * 100) if buy_usd > 0 else 0
    print(f"\n💰 P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")
    
    # Calculate entry and exit points
    avg_entry = buy_usd / buy_qty if buy_qty > 0 else 0
    avg_exit = sell_usd / sell_qty if sell_qty > 0 else 0
    print(f"\nAvg Entry: ${avg_entry:.10f}")
    print(f"Avg Exit:  ${avg_exit:.10f}")
    print(f"Price Change: {((avg_exit - avg_entry) / avg_entry * 100):+.2f}%")

