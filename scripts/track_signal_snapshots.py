import os
import sqlite3
import time
from datetime import datetime
import json
import urllib.request
import argparse

DB_PATH = os.getenv("TRADING_DB_PATH", "var/trading.db")

def get_db():
    if not os.path.exists(DB_PATH):
        return None
    return sqlite3.connect(DB_PATH)

def fetch_active_signals(conn):
    """Fetch signals that are less than 7 days old to track their peak prices."""
    c = conn.cursor()
    # We want signals < 7 days old
    c.execute("""
        SELECT id, token_address, timestamp, market_cap 
        FROM signals 
        WHERE timestamp > strftime('%s','now', '-7 days')
    """)
    return c.fetchall()

def fetch_token_data(token_address):
    """Fetch current token data from DexScreener (or Jupiter)."""
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read())
            if not data.get('pairs'):
                return None
            
            # Use the most liquid pair
            best_pair = max(data['pairs'], key=lambda p: p.get('liquidity', {}).get('usd', 0) if isinstance(p.get('liquidity'), dict) else 0)
            
            price = float(best_pair.get('priceUsd', 0))
            fdv = float(best_pair.get('fdv', 0))
            liquidity = float(best_pair.get('liquidity', {}).get('usd', 0))
            return {"price_usd": price, "market_cap_usd": fdv, "liquidity_usd": liquidity}
    except Exception as e:
        print(f"Error fetching data for {token_address}: {e}")
        return None

def update_signal_stats(conn, signal_id, current_mc, initial_mc, signal_timestamp, current_ts):
    """Update peak return and drawdown metrics in the signals table."""
    c = conn.cursor()
    c.execute("""
        SELECT peak_return_24h, peak_return_7d, drawdown_24h, drawdown_7d
        FROM signals WHERE id = ?
    """, (signal_id,))
    row = c.fetchone()
    if not row:
        return
    
    peak_24h, peak_7d, dd_24h, dd_7d = row
    
    # Calculate current ROI
    if initial_mc and initial_mc > 0:
        current_roi = (current_mc - initial_mc) / initial_mc
    else:
        current_roi = 0.0

    age_hours = (current_ts - signal_timestamp) / 3600.0

    new_peak_24h = peak_24h
    new_dd_24h = dd_24h
    new_peak_7d = peak_7d
    new_dd_7d = dd_7d
    time_to_peak = None # Need to track timestamp of peak, simplifying for now

    # Update 24h stats if within 24h
    if age_hours <= 24:
        if new_peak_24h is None or current_roi > new_peak_24h:
            new_peak_24h = current_roi
            # Rough proxy for time_to_peak
            time_to_peak = age_hours
        if new_dd_24h is None or current_roi < new_dd_24h:
            new_dd_24h = current_roi
            
    # Update 7d stats
    if age_hours <= 168:
        if new_peak_7d is None or current_roi > new_peak_7d:
            new_peak_7d = current_roi
            if age_hours > 24:
                time_to_peak = age_hours
        if new_dd_7d is None or current_roi < new_dd_7d:
            new_dd_7d = current_roi

    c.execute("""
        UPDATE signals 
        SET peak_return_24h=?, peak_return_7d=?, drawdown_24h=?, drawdown_7d=?, time_to_peak=COALESCE(time_to_peak, ?)
        WHERE id = ?
    """, (new_peak_24h, new_peak_7d, new_dd_24h, new_dd_7d, time_to_peak, signal_id))
    
    conn.commit()

def record_snapshot(conn, signal_id, data, current_ts):
    c = conn.cursor()
    c.execute("""
        INSERT INTO signal_price_snapshots (signal_id, timestamp, price_usd, market_cap_usd, liquidity_usd)
        VALUES (?, ?, ?, ?, ?)
    """, (signal_id, current_ts, data['price_usd'], data['market_cap_usd'], data['liquidity_usd']))
    conn.commit()

def main():
    parser = argparse.ArgumentParser(description="Track post-signal opportunity costs.")
    parser.add_argument("--continuous", action="store_true", help="Run continuously in background")
    parser.add_argument("--interval", type=int, default=300, help="Interval in seconds for continuous mode")
    args = parser.parse_args()

    while True:
        print(f"[{datetime.now().isoformat()}] Sweeping active signals...")
        conn = get_db()
        if not conn:
            print("DB not found")
            return

        active_signals = fetch_active_signals(conn)
        print(f"Found {len(active_signals)} active signals in the last 7 days.")

        # Batch token data fetching to avoid rate limits
        for i, (sig_id, token, sig_ts, initial_mc) in enumerate(active_signals):
            data = fetch_token_data(token)
            if data:
                current_ts = datetime.now().timestamp()
                record_snapshot(conn, sig_id, data, current_ts)
                update_signal_stats(conn, sig_id, data['market_cap_usd'], initial_mc, sig_ts, current_ts)
            
            time.sleep(0.5) # Prevent aggressive rate limiting

        conn.close()
        
        if not args.continuous:
            break
            
        print(f"Sleeping for {args.interval} seconds...")
        time.sleep(args.interval)

if __name__ == '__main__':
    main()
