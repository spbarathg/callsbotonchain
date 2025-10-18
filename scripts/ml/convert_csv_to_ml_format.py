#!/usr/bin/env python3
"""
Convert pump_triggers_ml_features_clean.csv to ML training database format
"""
import pandas as pd
import sqlite3
import time
from datetime import datetime

print("="*60)
print("CONVERTING CSV TO ML TRAINING FORMAT")
print("="*60)

# Read CSV
print("\nReading CSV...")
df = pd.read_csv('pump_triggers_ml_features_clean.csv')
print(f"  Loaded {len(df)} tokens")

# Create database
db_path = 'var/csv_ml_data.db'
print(f"\nCreating database: {db_path}")

conn = sqlite3.connect(db_path)
c = conn.cursor()

# Create tables matching ML training schema
c.execute("""
CREATE TABLE IF NOT EXISTS alerted_tokens (
    token_address TEXT PRIMARY KEY,
    alerted_at REAL,
    final_score INTEGER,
    smart_money_detected INTEGER,
    conviction_type TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS alerted_token_stats (
    token_address TEXT PRIMARY KEY,
    first_alert_at REAL,
    last_checked_at REAL,
    preliminary_score INTEGER,
    final_score INTEGER,
    conviction_type TEXT,
    first_price_usd REAL,
    first_market_cap_usd REAL,
    first_liquidity_usd REAL,
    last_price_usd REAL,
    last_market_cap_usd REAL,
    last_liquidity_usd REAL,
    last_volume_24h_usd REAL,
    peak_price_usd REAL,
    peak_market_cap_usd REAL,
    peak_price_at REAL,
    peak_market_cap_at REAL,
    price_change_1h REAL,
    price_change_6h REAL,
    price_change_24h REAL,
    max_gain_percent REAL,
    max_drawdown_percent REAL,
    is_rug INTEGER,
    token_name TEXT,
    token_symbol TEXT
)
""")

print("  Tables created")

# Convert each row
print("\nConverting tokens...")
now = int(time.time())

for idx, row in df.iterrows():
    # Extract data
    token_address = row['contract_address']
    token_symbol = row['base_symbol']
    token_name = row['token_name']
    
    # Prices
    current_price = row['current_price_usd']
    estimated_low = row['estimated_low_24h']
    
    # Calculate peak price
    gain_multiple = row['gain_multiple']
    peak_price = current_price  # Current is peak in this data
    
    # Liquidity
    liquidity = row['liquidity_usd']
    
    # Volume
    volume_24h = row['volume_h24']
    
    # Price changes
    price_change_1h = row['price_change_h1']
    price_change_6h = row['price_change_h6']
    price_change_24h = row['price_change_h24']
    
    # Gain
    max_gain = row['gain_percent']
    
    # Outcome
    is_winner = row['outcome_label']
    
    # Estimate market cap (price * typical supply, or use liquidity as proxy)
    # Since we don't have supply, use liquidity * 5 as rough estimate
    estimated_mcap = liquidity * 5
    
    # Calculate preliminary and final scores based on features
    # Use a simple heuristic for now
    prelim_score = 6  # Base score
    final_score = 8   # Base final score
    
    # Adjust based on liquidity
    if 50000 <= liquidity <= 150000:
        final_score += 1
    
    # Adjust based on buy/sell ratio
    if 'buy_sell_ratio_h24' in row and row['buy_sell_ratio_h24'] > 3:
        final_score += 1
    
    # Adjust based on momentum
    if price_change_6h > 20:
        final_score += 1
    
    # Cap at 10
    final_score = min(final_score, 10)
    
    # Estimate alert time (use pair age to calculate)
    pair_age_hours = row['pair_age_hours']
    alert_time = now - int(pair_age_hours * 3600)
    
    # Insert into alerted_tokens
    c.execute("""
    INSERT OR REPLACE INTO alerted_tokens 
    (token_address, alerted_at, final_score, smart_money_detected, conviction_type)
    VALUES (?, ?, ?, ?, ?)
    """, (
        token_address,
        alert_time,
        final_score,
        0,  # Unknown smart money
        'CSV Historical Data'
    ))
    
    # Insert into alerted_token_stats
    c.execute("""
    INSERT OR REPLACE INTO alerted_token_stats
    (token_address, first_alert_at, last_checked_at, preliminary_score, final_score,
     conviction_type, first_price_usd, first_market_cap_usd, first_liquidity_usd,
     last_price_usd, last_market_cap_usd, last_liquidity_usd, last_volume_24h_usd,
     peak_price_usd, peak_market_cap_usd, peak_price_at, peak_market_cap_at,
     price_change_1h, price_change_6h, price_change_24h, max_gain_percent,
     max_drawdown_percent, is_rug, token_name, token_symbol)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        token_address,
        alert_time,
        now,
        prelim_score,
        final_score,
        'CSV Historical Data',
        estimated_low,  # First price (estimated low)
        estimated_mcap * (estimated_low / current_price),  # First mcap
        liquidity,
        current_price,  # Last price (current)
        estimated_mcap,  # Last mcap
        liquidity,
        volume_24h,
        peak_price,
        estimated_mcap,  # Peak mcap
        alert_time,
        alert_time,
        price_change_1h,
        price_change_6h,
        price_change_24h,
        max_gain,
        0,  # Unknown drawdown
        0,  # Not rugged (still trading)
        token_name,
        token_symbol
    ))
    
    if (idx + 1) % 10 == 0:
        print(f"  Converted {idx + 1}/{len(df)} tokens...")

conn.commit()

# Verify
c.execute("SELECT COUNT(*) FROM alerted_tokens")
total_tokens = c.fetchone()[0]

c.execute("SELECT COUNT(*) FROM alerted_token_stats WHERE max_gain_percent >= 100")
winners_2x = c.fetchone()[0]

print(f"\nConversion complete!")
print(f"  Total tokens: {total_tokens}")
print(f"  2x+ winners: {winners_2x}")

conn.close()

print(f"\nDatabase saved to: {db_path}")
print("\nNext step:")
print(f"  python scripts/ml/train_model.py {db_path}")

print("\n" + "="*60)

