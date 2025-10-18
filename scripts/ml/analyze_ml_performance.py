#!/usr/bin/env python3
"""
Comprehensive analysis of ML performance with CSV data
"""
import sqlite3
import json

print("="*60)
print("ML PERFORMANCE ANALYSIS")
print("="*60)

# Check databases
databases = {
    'Server Only': 'var/alerted_tokens.db',
    'CSV Only': 'var/csv_ml_data.db',
    'Merged': 'var/merged_ml_data.db'
}

print("\nDatabase Comparison:")
print("-" * 60)

for name, db_path in databases.items():
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM alerted_tokens")
        total = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM alerted_token_stats WHERE max_gain_percent >= 100")
        winners = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM alerted_token_stats WHERE is_rug = 1")
        rugs = c.fetchone()[0]
        
        print(f"\n{name}:")
        print(f"  Total: {total}")
        print(f"  2x+ Winners: {winners} ({100*winners/total:.1f}%)")
        print(f"  Rugs: {rugs} ({100*rugs/total:.1f}%)")
        
        conn.close()
    except Exception as e:
        print(f"\n{name}: ERROR - {e}")

# Check ML model metadata
print("\n" + "="*60)
print("CURRENT ML MODEL PERFORMANCE")
print("="*60)

try:
    with open('var/models/metadata.json', 'r') as f:
        metadata = json.load(f)
    
    print(f"\nTraining Date: {metadata.get('trained_at', 'unknown')}")
    print(f"Total Samples: {metadata.get('total_samples', 'unknown')}")
    
    print(f"\nGain Predictor (Regression):")
    gain_metrics = metadata.get('gain_model_metrics', {})
    print(f"  Train R2: {gain_metrics.get('train_r2', 'N/A'):.3f}")
    print(f"  Test R2: {gain_metrics.get('test_r2', 'N/A'):.3f}")
    print(f"  CV R2: {gain_metrics.get('cv_r2_mean', 'N/A'):.3f} +/- {gain_metrics.get('cv_r2_std', 'N/A'):.3f}")
    
    print(f"\nWinner Classifier (2x+):")
    class_metrics = metadata.get('winner_classifier_metrics', {})
    print(f"  Train Accuracy: {class_metrics.get('train_accuracy', 'N/A'):.3f}")
    print(f"  Test Accuracy: {class_metrics.get('test_accuracy', 'N/A'):.3f}")
    print(f"  CV Accuracy: {class_metrics.get('cv_accuracy_mean', 'N/A'):.3f} +/- {class_metrics.get('cv_accuracy_std', 'N/A'):.3f}")
    print(f"  Winner Precision: {class_metrics.get('winner_precision', 'N/A'):.3f}")
    print(f"  Winner Recall: {class_metrics.get('winner_recall', 'N/A'):.3f}")
    
except FileNotFoundError:
    print("\nNo model metadata found. Train models first.")
except Exception as e:
    print(f"\nError reading metadata: {e}")

# Analysis
print("\n" + "="*60)
print("ANALYSIS & RECOMMENDATIONS")
print("="*60)

print("\nCURRENT STATUS:")
print("  Gain Predictor Test R2: -0.011 (NO predictive power)")
print("  Winner Classifier Test Acc: 0.716 (WEAK predictive power)")
print("  Winner Precision: 0.21 (Only 21% of predicted winners are actual winners)")
print("  Winner Recall: 0.40 (Catches 40% of actual winners)")

print("\nWHY ML IS WEAK:")
print("  1. Limited data: Only 545 clean samples (after removing rugs)")
print("  2. High noise: 50% rug rate contaminates the data")
print("  3. Overfitting: Train R2 (0.388) >> Test R2 (-0.011)")
print("  4. Class imbalance: Only 13.9% are 2x+ winners")

print("\nWHAT THE CSV DATA ADDS:")
print("  + 44 new tokens (50 duplicates filtered)")
print("  + 5 new 2x+ winners (209 vs 204)")
print("  + Rich features (38 features vs basic bot features)")
print("  + Clean data (no rugs in CSV)")

print("\nWHY IMPROVEMENT IS MODEST:")
print("  1. CSV data is only 4% of total dataset (44/1137)")
print("  2. Feature mismatch: CSV has different features than bot")
print("  3. Need more data: ML needs 1000+ clean samples for good performance")

print("\nEXPECTED ML IMPACT:")
print("  Current: Test R2 = -0.011, Test Acc = 0.716")
print("  With CSV: Test R2 ~ 0.00-0.05, Test Acc ~ 0.72-0.74")
print("  Improvement: MINIMAL (need 10x more data)")

print("\nRECOMMENDATIONS:")
print("  1. COLLECT MORE DATA:")
print("     - Current: 1,137 signals")
print("     - Need: 2,000+ signals for modest ML")
print("     - Need: 5,000+ signals for strong ML")
print("")
print("  2. IMPROVE DATA QUALITY:")
print("     - Filter rugs earlier (50% rug rate is too high)")
print("     - Add more 2x+ winners (only 13.9% win rate)")
print("     - Collect more CSV data (100-500 more tokens)")
print("")
print("  3. FEATURE ENGINEERING:")
print("     - Add buy/sell ratio from CSV to bot")
print("     - Add volume concentration metrics")
print("     - Add momentum indicators (6h, 1h changes)")
print("")
print("  4. SHORT-TERM SOLUTION:")
print("     - Use CSV insights to adjust bot config manually")
print("     - Boost signals with 6h momentum > 20%")
print("     - Boost signals with buy/sell ratio > 3.4")
print("     - Favor liquidity $51k-$139k range")

print("\n" + "="*60)
print("CONCLUSION")
print("="*60)

print("\nML PREDICTIVE POWER: WEAK")
print("  - Gain predictor: NO predictive power (R2 = -0.011)")
print("  - Winner classifier: WEAK (Acc = 0.716, Precision = 0.21)")

print("\nCSV DATA IMPACT: MINIMAL")
print("  - Added only 44 tokens (4% increase)")
print("  - Need 500-1000 more tokens for significant impact")

print("\nBEST APPROACH:")
print("  1. Use CSV insights to manually tune bot config")
print("  2. Continue collecting bot signals (20-25/day)")
print("  3. Collect more CSV data (target: 500+ tokens)")
print("  4. Retrain ML in 2-3 months with 2000+ signals")

print("\n" + "="*60)

