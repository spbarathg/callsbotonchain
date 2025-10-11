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
    
    X = df[features].fillna(0)
    y = df['target_gain']
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    print(f"Train samples: {len(X_train)}")
    print(f"Test samples: {len(X_test)}")
    
    # Train model
    model = GradientBoostingRegressor(
        n_estimators=150,
        max_depth=6,
        learning_rate=0.05,
        min_samples_split=10,
        min_samples_leaf=5,
        subsample=0.8,
        random_state=42
    )
    
    print("\nTraining...")
    model.fit(X_train, y_train)
    
    # Evaluate
    train_pred = model.predict(X_train)
    test_pred = model.predict(X_test)
    
    train_r2 = r2_score(y_train, train_pred)
    test_r2 = r2_score(y_test, test_pred)
    train_rmse = np.sqrt(mean_squared_error(y_train, train_pred))
    test_rmse = np.sqrt(mean_squared_error(y_test, test_pred))
    
    print(f"\n📊 Results:")
    print(f"  Train R²: {train_r2:.3f}")
    print(f"  Test R²:  {test_r2:.3f}")
    print(f"  Train RMSE: {train_rmse:.1f}%")
    print(f"  Test RMSE:  {test_rmse:.1f}%")
    
    # Feature importance
    importance = dict(zip(features, model.feature_importances_))
    print(f"\n🔍 Top 10 Most Important Features:")
    for feat, imp in sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {feat:30s}: {imp:.3f}")
    
    metrics = {
        'train_r2': train_r2,
        'test_r2': test_r2,
        'train_rmse': train_rmse,
        'test_rmse': test_rmse,
        'feature_importance': importance,
        'trained_at': datetime.now().isoformat(),
        'samples': len(df)
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
    
    target_map = {
        '1.5x': 'is_winner_1.5x',
        '2x': 'is_winner_2x',
        '5x': 'is_winner_5x',
        '10x': 'is_winner_10x'
    }
    
    X = df[features].fillna(0)
    y = df[target_map[threshold]]
    
    # Check class balance
    pos_rate = y.mean()
    print(f"Positive rate: {pos_rate:.1%}")
    
    if pos_rate < 0.05 or pos_rate > 0.95:
        print("⚠️  Warning: Highly imbalanced dataset")
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    print(f"Train samples: {len(X_train)} (positive: {y_train.sum()})")
    print(f"Test samples: {len(X_test)} (positive: {y_test.sum()})")
    
    # Train model
    model = RandomForestClassifier(
        n_estimators=150,
        max_depth=12,
        min_samples_split=15,
        min_samples_leaf=5,
        class_weight='balanced',  # Handle imbalanced data
        random_state=42,
        n_jobs=-1
    )
    
    print("\nTraining...")
    model.fit(X_train, y_train)
    
    # Evaluate
    train_pred = model.predict(X_train)
    test_pred = model.predict(X_test)
    train_proba = model.predict_proba(X_train)[:, 1]
    test_proba = model.predict_proba(X_test)[:, 1]
    
    train_acc = accuracy_score(y_train, train_pred)
    test_acc = accuracy_score(y_test, test_pred)
    
    print(f"\n📊 Results:")
    print(f"  Train Accuracy: {train_acc:.3f}")
    print(f"  Test Accuracy:  {test_acc:.3f}")
    
    print(f"\n📋 Test Set Classification Report:")
    print(classification_report(y_test, test_pred, target_names=['Loser', 'Winner']))
    
    metrics = {
        'train_accuracy': train_acc,
        'test_accuracy': test_acc,
        'threshold': threshold,
        'positive_rate': pos_rate,
        'trained_at': datetime.now().isoformat(),
        'samples': len(df)
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

