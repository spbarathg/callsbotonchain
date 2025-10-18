"""
Model Training for Adaptive Signal Detection
Trains ML models to predict signal performance
"""
import os
import sys
import json
from datetime import datetime
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import GradientBoostingRegressor, RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import mean_squared_error, r2_score, accuracy_score, classification_report

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from scripts.ml.feature_engineer import extract_features, get_feature_list, summarize_dataset


def train_gain_predictor(df: pd.DataFrame, features: list) -> Tuple[object, Dict]:
    """
    Train regression model to predict max_gain_percent
    
    Returns: (model, metrics)
    """
    print("\n" + "="*60)
    print("🎯 TRAINING GAIN PREDICTOR (Regression)")
    print("="*60)
    
    # CRITICAL FIX: Remove rugs from training data (they're not tradeable!)
    df_clean = df[df['is_rug'] == 0].copy()
    print(f"📊 Removed {len(df) - len(df_clean)} rugs from training data")
    print(f"   Clean samples: {len(df_clean)}/{len(df)} ({100*len(df_clean)/len(df):.1f}%)")
    
    if len(df_clean) < 50:
        print(f"⚠️  ERROR: Not enough clean samples ({len(df_clean)} < 50)")
        print("   Wait for more non-rug signals to accumulate")
        # Fall back to full dataset if not enough clean data
        df_clean = df
        print("   Using full dataset (including rugs) as fallback")
    
    X = df_clean[features].fillna(0)
    y = df_clean['target_gain']
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    print(f"\nTrain samples: {len(X_train)}")
    print(f"Test samples: {len(X_test)}")
    
    # IMPROVED MODEL: Stronger regularization to prevent overfitting
    model = GradientBoostingRegressor(
        n_estimators=100,          # Reduced from 150 (less complex)
        max_depth=3,               # Reduced from 6 (prevent overfitting!)
        learning_rate=0.1,         # Increased from 0.05 (faster, more stable)
        min_samples_split=20,      # Increased from 10 (more conservative)
        min_samples_leaf=10,       # Increased from 5 (prevent overfitting)
        subsample=0.7,             # Reduced from 0.8 (more regularization)
        max_features='sqrt',       # Add feature sampling (prevent overfitting)
        random_state=42
    )
    
    print("\nTraining with stronger regularization...")
    model.fit(X_train, y_train)
    
    # Evaluate on test set
    train_pred = model.predict(X_train)
    test_pred = model.predict(X_test)
    
    train_r2 = r2_score(y_train, train_pred)
    test_r2 = r2_score(y_test, test_pred)
    train_rmse = np.sqrt(mean_squared_error(y_train, train_pred))
    test_rmse = np.sqrt(mean_squared_error(y_test, test_pred))
    
    # Cross-validation to check generalization
    print("\nRunning 5-fold cross-validation...")
    cv_scores = cross_val_score(model, X, y, cv=5, scoring='r2', n_jobs=-1)
    cv_r2_mean = cv_scores.mean()
    cv_r2_std = cv_scores.std()
    
    print("\n📊 Results:")
    print(f"  Train R²: {train_r2:.3f}")
    print(f"  Test R²:  {test_r2:.3f}")
    print(f"  CV R² (5-fold): {cv_r2_mean:.3f} ± {cv_r2_std:.3f}")
    print(f"  Train RMSE: {train_rmse:.1f}%")
    print(f"  Test RMSE:  {test_rmse:.1f}%")
    
    # Check for overfitting
    if train_r2 - test_r2 > 0.2:
        print(f"  ⚠️  WARNING: Overfitting detected! (Train-Test gap: {train_r2 - test_r2:.3f})")
    elif test_r2 > 0.3:
        print("  ✅ Good generalization!")
    else:
        print("  ⚠️  Poor predictive power (Test R² < 0.3)")
    
    # Feature importance
    importance = dict(zip(features, model.feature_importances_))
    print("\n🔍 Top 10 Most Important Features:")
    for feat, imp in sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {feat:30s}: {imp:.3f}")
    
    metrics = {
        'train_r2': train_r2,
        'test_r2': test_r2,
        'cv_r2_mean': cv_r2_mean,
        'cv_r2_std': cv_r2_std,
        'train_rmse': train_rmse,
        'test_rmse': test_rmse,
        'feature_importance': importance,
        'trained_at': datetime.now().isoformat(),
        'samples': len(df_clean),
        'rugs_removed': len(df) - len(df_clean)
    }
    
    return model, metrics


def train_winner_classifier(df: pd.DataFrame, features: list, threshold='2x') -> Tuple[object, Dict]:
    """
    Train classifier to predict winner/loser
    
    Args:
        threshold: '1.5x', '2x', '5x', or '10x'
    
    Returns: (model, metrics)
    """
    print("\n" + "="*60)
    print(f"🎯 TRAINING WINNER CLASSIFIER ({threshold}+)")
    print("="*60)
    
    # CRITICAL FIX: Remove rugs from training data
    df_clean = df[df['is_rug'] == 0].copy()
    print(f"📊 Removed {len(df) - len(df_clean)} rugs from training data")
    print(f"   Clean samples: {len(df_clean)}/{len(df)} ({100*len(df_clean)/len(df):.1f}%)")
    
    if len(df_clean) < 50:
        print(f"⚠️  ERROR: Not enough clean samples ({len(df_clean)} < 50)")
        df_clean = df
        print("   Using full dataset (including rugs) as fallback")
    
    target_map = {
        '1.5x': 'is_winner_1.5x',
        '2x': 'is_winner_2x',
        '5x': 'is_winner_5x',
        '10x': 'is_winner_10x'
    }
    
    X = df_clean[features].fillna(0)
    y = df_clean[target_map[threshold]]
    
    # Check class balance
    pos_rate = y.mean()
    print(f"\nPositive rate: {pos_rate:.1%}")
    
    if pos_rate < 0.05 or pos_rate > 0.95:
        print("⚠️  Warning: Highly imbalanced dataset")
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    print(f"Train samples: {len(X_train)} (positive: {y_train.sum()})")
    print(f"Test samples: {len(X_test)} (positive: {y_test.sum()})")
    
    # IMPROVED MODEL: Stronger regularization + balanced weighting
    model = RandomForestClassifier(
        n_estimators=100,            # Reduced from 150 (less complex)
        max_depth=5,                 # Reduced from 12 (prevent overfitting!)
        min_samples_split=25,        # Increased from 15 (more conservative)
        min_samples_leaf=10,         # Increased from 5 (prevent overfitting)
        max_features='sqrt',         # Feature sampling (prevent overfitting)
        class_weight='balanced',     # Handle imbalanced data
        random_state=42,
        n_jobs=-1
    )
    
    print("\nTraining with stronger regularization...")
    model.fit(X_train, y_train)
    
    # Evaluate
    train_pred = model.predict(X_train)
    test_pred = model.predict(X_test)
    # Probabilities available but not currently used in metrics
    # train_proba = model.predict_proba(X_train)[:, 1]
    # test_proba = model.predict_proba(X_test)[:, 1]
    
    train_acc = accuracy_score(y_train, train_pred)
    test_acc = accuracy_score(y_test, test_pred)
    
    # Cross-validation to check generalization
    print("\nRunning 5-fold cross-validation...")
    cv_scores = cross_val_score(model, X, y, cv=5, scoring='accuracy', n_jobs=-1)
    cv_acc_mean = cv_scores.mean()
    cv_acc_std = cv_scores.std()
    
    print("\n📊 Results:")
    print(f"  Train Accuracy: {train_acc:.3f}")
    print(f"  Test Accuracy:  {test_acc:.3f}")
    print(f"  CV Accuracy (5-fold): {cv_acc_mean:.3f} ± {cv_acc_std:.3f}")
    
    # Check for overfitting
    if train_acc - test_acc > 0.15:
        print(f"  ⚠️  WARNING: Overfitting detected! (Train-Test gap: {train_acc - test_acc:.3f})")
    elif test_acc > 0.75:
        print("  ✅ Good generalization!")
    else:
        print("  ⚠️  Poor predictive power (Test Acc < 0.75)")
    
    print("\n📋 Test Set Classification Report:")
    print(classification_report(y_test, test_pred, target_names=['Loser', 'Winner']))
    
    metrics = {
        'train_accuracy': train_acc,
        'test_accuracy': test_acc,
        'cv_accuracy_mean': cv_acc_mean,
        'cv_accuracy_std': cv_acc_std,
        'threshold': threshold,
        'positive_rate': pos_rate,
        'trained_at': datetime.now().isoformat(),
        'samples': len(df_clean),
        'rugs_removed': len(df) - len(df_clean)
    }
    
    return model, metrics


def save_models(gain_model, gain_metrics, winner_model, winner_metrics, features):
    """Save trained models and metadata"""
    
    os.makedirs('var/models', exist_ok=True)
    
    # Save models
    joblib.dump(gain_model, 'var/models/gain_predictor.pkl')
    joblib.dump(winner_model, 'var/models/winner_classifier.pkl')
    joblib.dump(features, 'var/models/features.pkl')
    
    # Save metadata
    metadata = {
        'gain_predictor': gain_metrics,
        'winner_classifier': winner_metrics,
        'features': features,
        'model_version': '1.0'
    }
    
    with open('var/models/metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # Save training timestamp
    with open('var/models/last_retrain.txt', 'w') as f:
        f.write(datetime.now().isoformat())
    
    print("\n✅ Models saved to var/models/")


def main():
    """Main training pipeline"""
    print("🤖 ADAPTIVE SIGNAL DETECTION - MODEL TRAINING")
    print("="*60)
    
    # Load and engineer features
    df = extract_features()
    
    if len(df) < 50:
        print(f"\n⚠️  ERROR: Need at least 50 samples to train. Current: {len(df)}")
        print("   Wait for more signals to accumulate, then try again.")
        return
    
    summarize_dataset(df)
    features = get_feature_list()
    
    # Train models
    gain_model, gain_metrics = train_gain_predictor(df, features)
    winner_model, winner_metrics = train_winner_classifier(df, features, threshold='2x')
    
    # Save everything
    save_models(gain_model, gain_metrics, winner_model, winner_metrics, features)
    
    print("\n" + "="*60)
    print("✅ TRAINING COMPLETE!")
    print("="*60)
    print("\n📝 Next Steps:")
    print("  1. Review model performance above")
    print("  2. Test predictions: python scripts/ml/test_predictions.py")
    print("  3. Enable in bot: Set ML_SCORING_ENABLED=true in .env")
    print("\n🔄 Models will auto-retrain weekly as more data accumulates")


if __name__ == '__main__':
    main()

