#!/usr/bin/env python3
import sqlite3
import requests
import time

db_path = '/app/var/trading.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== CHECKING EXIT CONDITIONS FOR OPEN POSITIONS ===\n")

c.execute('''SELECT token_address, entry_price, qty, usd_size, open_at, peak_price, trail_pct 
             FROM positions WHERE status="open"''')
positions = c.fetchall()

for pos in positions:
    token = pos[0]
    entry_price = pos[1]
    qty = pos[2]
    cost = pos[3]
    opened = pos[4]
    peak_price = pos[5] or entry_price
    trail_pct = pos[6]
    
    print(f"Token: {token[:12]}...")
    print(f"  Entry Price: ${entry_price:.8f}")
    print(f"  Peak Price: ${peak_price:.8f}")
    print(f"  Cost: ${cost:.2f}")
    print(f"  Quantity: {qty:.2f}")
    print(f"  Opened: {opened}")
    print(f"  Trail %: {trail_pct}%")
    
    # Fetch current price from DexScreener
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('pairs'):
                pair = data['pairs'][0]
                current_price = float(pair['priceUsd'])
                
                # Calculate metrics
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
                from_peak_pct = ((current_price - peak_price) / peak_price) * 100
                stop_loss_price = entry_price * 0.85  # -15%
                trail_price = peak_price * (1 - trail_pct/100)
                
                print(f"  Current Price: ${current_price:.8f}")
                print(f"  PnL: {pnl_pct:+.2f}%")
                print(f"  From Peak: {from_peak_pct:+.2f}%")
                print(f"  Stop Loss Price: ${stop_loss_price:.8f}")
                print(f"  Trail Price: ${trail_price:.8f}")
                
                # Check exit conditions
                if current_price <= stop_loss_price:
                    print(f"  ⚠️  SHOULD EXIT: Stop loss hit!")
                elif current_price <= trail_price:
                    print(f"  ⚠️  SHOULD EXIT: Trailing stop hit!")
                elif current_price > peak_price:
                    print(f"  ✅ Should update peak price to ${current_price:.8f}")
                else:
                    print(f"  ✅ Position OK, monitoring...")
            else:
                print(f"  ❌ No price data from DexScreener")
        else:
            print(f"  ❌ DexScreener API error: {resp.status_code}")
    except Exception as e:
        print(f"  ❌ Error fetching price: {e}")
    
    print()
    time.sleep(0.5)  # Rate limit

conn.close()

