#!/usr/bin/env python3
"""
Analyze pump_triggers_ml_features_clean.csv for ML training
"""
import csv
import pandas as pd

print("="*60)
print("PUMP TRIGGERS CSV ANALYSIS")
print("="*60)

# Read CSV
df = pd.read_csv('pump_triggers_ml_features_clean.csv')

print(f"\nTotal tokens: {len(df)}")
print(f"Total features: {len(df.columns)}")

# Show all columns
print("\nALL AVAILABLE FEATURES:")
for i, col in enumerate(df.columns, 1):
    print(f"  {i}. {col}")

# Analyze outcomes
print("\n" + "="*60)
print("OUTCOME ANALYSIS")
print("="*60)

winners = df[df['outcome_label'] == 1]
losers = df[df['outcome_label'] == 0]

print(f"\nTotal tokens: {len(df)}")
print(f"2x+ Winners (label=1): {len(winners)} ({100*len(winners)/len(df):.1f}%)")
print(f"Non-winners (label=0): {len(losers)} ({100*len(losers)/len(df):.1f}%)")

# Analyze gains
print("\n" + "="*60)
print("GAIN DISTRIBUTION")
print("="*60)

print(f"\nGain Multiple Stats:")
print(f"  Min: {df['gain_multiple'].min():.2f}x")
print(f"  Max: {df['gain_multiple'].max():.2f}x")
print(f"  Mean: {df['gain_multiple'].mean():.2f}x")
print(f"  Median: {df['gain_multiple'].median():.2f}x")

print(f"\nGain Percent Stats:")
print(f"  Min: {df['gain_percent'].min():.1f}%")
print(f"  Max: {df['gain_percent'].max():.1f}%")
print(f"  Mean: {df['gain_percent'].mean():.1f}%")
print(f"  Median: {df['gain_percent'].median():.1f}%")

# Top gainers
print(f"\nTop 10 Gainers:")
top_gainers = df.nlargest(10, 'gain_percent')[['base_symbol', 'gain_percent', 'gain_multiple', 'outcome_label']]
for idx, row in top_gainers.iterrows():
    winner_mark = "2x+" if row['outcome_label'] == 1 else ""
    print(f"  {row['base_symbol']}: {row['gain_percent']:.0f}% ({row['gain_multiple']:.1f}x) {winner_mark}")

# Feature completeness
print("\n" + "="*60)
print("FEATURE COMPLETENESS")
print("="*60)

critical_features = [
    'current_price_usd',
    'estimated_low_24h',
    'gain_multiple',
    'gain_percent',
    'price_change_h1',
    'price_change_h6',
    'price_change_h24',
    'volume_h24',
    'liquidity_usd',
    'buys_h24',
    'sells_h24',
    'outcome_label'
]

print("\nCritical Features Check:")
for feat in critical_features:
    if feat in df.columns:
        non_null = df[feat].notna().sum()
        print(f"  {feat}: {non_null}/{len(df)} ({100*non_null/len(df):.1f}%)")
    else:
        print(f"  {feat}: MISSING")

# Compare winners vs losers
print("\n" + "="*60)
print("WINNERS VS LOSERS COMPARISON")
print("="*60)

comparison_features = [
    'liquidity_usd',
    'volume_h24',
    'price_change_h1',
    'price_change_h6',
    'price_change_h24',
    'buy_sell_ratio_h24',
    'pair_age_hours'
]

print("\nFeature Averages:")
print(f"{'Feature':<25} {'Winners':<15} {'Losers':<15} {'Difference'}")
print("-" * 70)

for feat in comparison_features:
    if feat in df.columns:
        winner_avg = winners[feat].mean()
        loser_avg = losers[feat].mean()
        diff = winner_avg - loser_avg
        print(f"{feat:<25} {winner_avg:>14.2f} {loser_avg:>14.2f} {diff:>14.2f}")

# ML Readiness
print("\n" + "="*60)
print("ML TRAINING READINESS")
print("="*60)

print("\nREADINESS CHECK:")

checks = {
    "Has outcome labels": 'outcome_label' in df.columns,
    "Has 2x+ winners": len(winners) > 0,
    "Has price data": 'current_price_usd' in df.columns,
    "Has liquidity data": 'liquidity_usd' in df.columns,
    "Has volume data": 'volume_h24' in df.columns,
    "Has momentum data": 'price_change_h24' in df.columns,
    "Has buy/sell data": 'buys_h24' in df.columns,
    "Sufficient samples": len(df) >= 50,
    "Balanced dataset": len(winners) >= 5 and len(losers) >= 5
}

all_ready = True
for check, passed in checks.items():
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {check}")
    if not passed:
        all_ready = False

print("\n" + "="*60)
print("FINAL VERDICT")
print("="*60)

if all_ready:
    print("\nEXCELLENT! This CSV is PERFECT for ML training!")
    print("\nWhat you have:")
    print(f"  - {len(df)} tokens with complete data")
    print(f"  - {len(winners)} 2x+ winners ({100*len(winners)/len(df):.1f}%)")
    print(f"  - {len(df.columns)} features per token")
    print(f"  - Price, volume, liquidity, momentum, buy/sell ratios")
    print(f"  - Clear outcome labels (0 or 1)")
    
    print("\nExpected ML Impact:")
    print(f"  - Current bot data: 1,094 signals")
    print(f"  - This CSV: +{len(df)} signals")
    print(f"  - New total: {1094 + len(df)} signals")
    print(f"  - 2x+ winners: 204 + {len(winners)} = {204 + len(winners)}")
    print(f"  - New win rate: {100*(204+len(winners))/(1094+len(df)):.1f}%")
    
    if len(winners) >= 10:
        print("\n  ML WILL SIGNIFICANTLY IMPROVE!")
    else:
        print("\n  ML will have modest improvement")
    
    print("\nNext steps:")
    print("  1. Convert CSV to ML training format")
    print("  2. Merge with existing bot database")
    print("  3. Retrain ML models")
    print("  4. Evaluate performance improvement")
    print("  5. Deploy to server if improved")
else:
    print("\nWARNING: Some checks failed!")
    print("Review the failed checks above.")

print("\n" + "="*60)


