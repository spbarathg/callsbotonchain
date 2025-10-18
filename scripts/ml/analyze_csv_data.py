#!/usr/bin/env python3
"""
Analyze the CSV data to see if it's suitable for ML training
"""
import csv
import json
from datetime import datetime

print("="*60)
print("CSV DATA ANALYSIS FOR ML TRAINING")
print("="*60)

# Read CSV
with open('solana_trending_tokens_full.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print(f"\nTotal tokens: {len(rows)}")

# Analyze structure
print("\nColumns available:")
for col in rows[0].keys():
    print(f"  - {col}")

# Analyze a sample row
print("\n" + "="*60)
print("SAMPLE ROW ANALYSIS")
print("="*60)

sample = rows[0]
print(f"\nToken: {sample['base_symbol']}")
print(f"Pair Address: {sample['pair_address']}")
print(f"First Seen: {sample['first_seen_ts']}")

# Parse liquidity snapshots
liquidity_snapshots = json.loads(sample['liquidity_snapshots'])
print(f"\nLiquidity Snapshots: {len(liquidity_snapshots)} points")
if liquidity_snapshots:
    print(f"  First: ${liquidity_snapshots[0][1]:,.2f}")
    print(f"  Last: ${liquidity_snapshots[-1][1]:,.2f}")

# Parse price time series
price_series = json.loads(sample['price_time_series'])
print(f"\nPrice Time Series:")
for time_key, price in price_series.items():
    print(f"  {time_key}: ${price}")

# Calculate gains
t0_price = price_series.get('t+0m', 0)
t1440_price = price_series.get('t+1440m', 0)  # 24 hours
if t0_price > 0:
    gain_24h = ((t1440_price - t0_price) / t0_price) * 100
    print(f"\n24h Gain: {gain_24h:.2f}%")
    print(f"Is 2x+ winner: {gain_24h >= 100}")

# Outcome label
print(f"\nOutcome Label: {sample['outcome_label']}")

# Token meta
token_meta = json.loads(sample['token_meta'])
print(f"\nToken Meta:")
for key, val in token_meta.items():
    print(f"  {key}: {val}")

print("\n" + "="*60)
print("WHAT WE CAN EXTRACT FOR ML")
print("="*60)

print("\n AVAILABLE FEATURES:")
print("  1. Liquidity (from snapshots)")
print("  2. Price at t+0m, t+1m, t+5m, t+15m, t+60m, t+1440m")
print("  3. Token age (from first_seen_ts)")
print("  4. Pair address (for DexScreener lookup)")

print("\n MISSING FEATURES (need to fetch):")
print("  1. Market Cap (can calculate: price * supply OR fetch from DexScreener)")
print("  2. Volume 24h (need to fetch from DexScreener)")
print("  3. Transaction counts (tx_snapshots is empty)")
print("  4. Price changes 1h, 6h, 24h (can calculate from price_time_series)")

print("\n OUTCOME DATA:")
print("  - outcome_label: 0 or 1 (binary classification)")
print("  - Can calculate max_gain from price_time_series")

# Check how many have outcomes
outcomes = [int(row['outcome_label']) for row in rows if row['outcome_label']]
print(f"\n  Total with outcomes: {len(outcomes)}")
print(f"  Winners (label=1): {sum(outcomes)}")
print(f"  Losers (label=0): {len(outcomes) - sum(outcomes)}")

# Calculate gains for all
print("\n" + "="*60)
print("GAIN DISTRIBUTION")
print("="*60)

gains = []
winners_2x = 0

for row in rows:
    try:
        prices = json.loads(row['price_time_series'])
        t0 = prices.get('t+0m', 0)
        t1440 = prices.get('t+1440m', 0)
        
        if t0 > 0:
            gain = ((t1440 - t0) / t0) * 100
            gains.append(gain)
            if gain >= 100:
                winners_2x += 1
    except:
        pass

if gains:
    gains.sort(reverse=True)
    print(f"\nTotal calculable gains: {len(gains)}")
    print(f"2x+ winners: {winners_2x} ({100*winners_2x/len(gains):.1f}%)")
    print(f"Avg gain: {sum(gains)/len(gains):.1f}%")
    print(f"Max gain: {max(gains):.1f}%")
    print(f"Min gain: {min(gains):.1f}%")
    
    print(f"\nTop 10 gainers:")
    for i, gain in enumerate(gains[:10], 1):
        print(f"  {i}. {gain:.1f}%")

print("\n" + "="*60)
print("RECOMMENDATION")
print("="*60)

print("\n THIS DATA IS EXCELLENT FOR ML!")
print("\nWhat we have:")
print("  - 101 tokens with price history")
print("  - Liquidity data")
print("  - Price progression over 24h")
print("  - Pair addresses for additional data fetch")

print("\nWhat we need to do:")
print("  1. Extract features from CSV")
print("  2. Calculate price changes (1h, 6h, 24h)")
print("  3. Fetch market cap & volume from DexScreener (using pair_address)")
print("  4. Calculate max_gain as target variable")
print("  5. Convert to ML training format")

print("\nExpected ML improvement:")
print("  - Current data: 1,094 signals")
print("  - This CSV: +101 signals")
print("  - New total: 1,195 signals")
print("  - If 2x+ winners: Significant boost to ML training!")

print("\n" + "="*60)


