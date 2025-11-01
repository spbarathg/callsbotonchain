#!/usr/bin/env python3
"""
Backtest Data Collector
Collects historical signal and price data for backtesting
"""

import json
import sys
import os
import time
from datetime import datetime, timedelta
from typing import List, Dict
import requests

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.config_unified import CIELO_API_KEY


def collect_signals_from_logs(log_path: str, start_date: str, end_date: str) -> List[Dict]:
    """
    Extract signals from trading logs
    
    Args:
        log_path: Path to trading.jsonl
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
    
    Returns:
        List of signal dictionaries
    """
    signals = []
    
    start_dt = datetime.fromisoformat(start_date)
    end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
    
    try:
        with open(log_path, 'r') as f:
            for line in f:
                try:
                    log = json.loads(line)
                    
                    # Look for open_position events
                    if log.get("event") == "open_position":
                        ts = log.get("ts", "")
                        if ts:
                            log_dt = datetime.fromisoformat(ts.replace("Z", ""))
                            
                            if start_dt <= log_dt < end_dt:
                                signal = {
                                    "timestamp": ts,
                                    "token_address": log.get("token"),
                                    "entry_price": log.get("price"),
                                    "strategy": log.get("strategy"),
                                    "position_id": log.get("pid"),
                                }
                                signals.append(signal)
                
                except json.JSONDecodeError:
                    continue
    
    except FileNotFoundError:
        print(f"Error: Log file not found: {log_path}")
        return []
    
    return signals


def fetch_price_history_dexscreener(token_address: str, start_timestamp: int, end_timestamp: int) -> List[Dict]:
    """
    Fetch price history from DexScreener API
    
    Args:
        token_address: Token mint address
        start_timestamp: Start timestamp (seconds)
        end_timestamp: End timestamp (seconds)
    
    Returns:
        List of price candles
    """
    # DexScreener doesn't have historical bars API, only current data
    # We'll need to use alternative approaches:
    # 1. Birdeye API (has historical OHLCV)
    # 2. Reconstruct from transaction history
    # 3. Use Jupiter historical quotes (if available)
    
    # For now, return empty (implement with Birdeye or similar)
    print(f"Note: Historical price data not available via DexScreener for {token_address[:8]}")
    print(f"Consider using Birdeye API or transaction history reconstruction")
    
    return []


def fetch_price_history_birdeye(token_address: str, start_timestamp: int, end_timestamp: int, 
                                 interval: str = "5m") -> List[Dict]:
    """
    Fetch price history from Birdeye API (requires API key)
    
    Args:
        token_address: Token mint address  
        start_timestamp: Start timestamp (seconds)
        end_timestamp: End timestamp (seconds)
        interval: Candle interval (1m, 5m, 15m, 1H, 1D)
    
    Returns:
        List of price candles
    """
    # Birdeye API endpoint (requires API key)
    # https://docs.birdeye.so/
    
    api_key = os.getenv("BIRDEYE_API_KEY", "")
    if not api_key:
        print("Warning: BIRDEYE_API_KEY not set. Cannot fetch historical prices.")
        return []
    
    url = f"https://public-api.birdeye.so/defi/ohlcv"
    params = {
        "address": token_address,
        "type": interval,
        "time_from": start_timestamp,
        "time_to": end_timestamp,
    }
    headers = {
        "X-API-KEY": api_key
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("success"):
            candles = data.get("data", {}).get("items", [])
            return candles
        else:
            print(f"Birdeye API error: {data.get('message')}")
            return []
    
    except Exception as e:
        print(f"Error fetching from Birdeye: {e}")
        return []


def save_signals(signals: List[Dict], output_path: str):
    """Save signals to JSONL file"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w') as f:
        for signal in signals:
            f.write(json.dumps(signal) + "\n")
    
    print(f"✅ Saved {len(signals)} signals to {output_path}")


def save_price_history(token_address: str, candles: List[Dict], output_dir: str):
    """Save price history to file"""
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, f"{token_address}.jsonl")
    
    with open(output_path, 'w') as f:
        for candle in candles:
            f.write(json.dumps(candle) + "\n")
    
    print(f"✅ Saved {len(candles)} candles for {token_address[:8]} to {output_path}")


def main():
    """Main data collection script"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Collect backtest data")
    parser.add_argument("--log-path", default="data/logs/trading.jsonl", 
                       help="Path to trading log file")
    parser.add_argument("--start-date", required=True, 
                       help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, 
                       help="End date (YYYY-MM-DD)")
    parser.add_argument("--output-signals", default="data/backtest/signals.jsonl", 
                       help="Output path for signals")
    parser.add_argument("--output-prices", default="data/backtest/prices", 
                       help="Output directory for price data")
    parser.add_argument("--fetch-prices", action="store_true", 
                       help="Fetch historical prices (requires Birdeye API key)")
    
    args = parser.parse_args()
    
    print("="*60)
    print("  Backtest Data Collector")
    print("="*60)
    print(f"Date range: {args.start_date} to {args.end_date}")
    print()
    
    # Step 1: Collect signals from logs
    print("Step 1: Collecting signals from logs...")
    signals = collect_signals_from_logs(args.log_path, args.start_date, args.end_date)
    
    if not signals:
        print("❌ No signals found in log file")
        return
    
    print(f"Found {len(signals)} signals")
    
    # Save signals
    save_signals(signals, args.output_signals)
    
    # Step 2: Fetch price history (if requested)
    if args.fetch_prices:
        print("\nStep 2: Fetching historical prices...")
        
        # Get unique tokens
        tokens = list(set(s["token_address"] for s in signals if s.get("token_address")))
        print(f"Found {len(tokens)} unique tokens")
        
        start_ts = int(datetime.fromisoformat(args.start_date).timestamp())
        end_ts = int(datetime.fromisoformat(args.end_date).timestamp())
        
        for i, token in enumerate(tokens, 1):
            print(f"[{i}/{len(tokens)}] Fetching prices for {token[:8]}...")
            
            candles = fetch_price_history_birdeye(token, start_ts, end_ts, interval="5m")
            
            if candles:
                save_price_history(token, candles, args.output_prices)
            else:
                print(f"  No price data available")
            
            # Rate limiting
            if i < len(tokens):
                time.sleep(1)  # Be nice to the API
    else:
        print("\nStep 2: Skipped (use --fetch-prices to enable)")
    
    print("\n" + "="*60)
    print("✅ Data collection complete!")
    print(f"Signals: {args.output_signals}")
    if args.fetch_prices:
        print(f"Prices: {args.output_prices}/")
    print("="*60)


if __name__ == "__main__":
    main()








