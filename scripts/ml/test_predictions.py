"""
Test ML Predictions
Shows sample predictions on recent signals to validate model performance
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.ml_scorer import get_ml_scorer
import sqlite3


def test_recent_signals(limit=10):
    """Test ML predictions on most recent signals"""
    
    print("🧪 TESTING ML PREDICTIONS ON RECENT SIGNALS")
    print("="*80)
    
    # Get recent signals
    con = sqlite3.connect('var/alerted_tokens.db')
    cur = con.execute("""
        SELECT 
            a.token_address,
            a.final_score,
            a.conviction_type,
            a.smart_money_detected,
            s.first_liquidity_usd,
            s.last_volume_24h_usd,
            s.first_market_cap_usd,
            s.max_gain_percent
        FROM alerted_tokens a
        LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
        ORDER BY a.alerted_at DESC
        LIMIT ?
    """, [limit])
    
    signals = cur.fetchall()
    con.close()
    
    if not signals:
        print("No signals found in database")
        return
    
    # Initialize ML scorer
    ml_scorer = get_ml_scorer()
    
    if not ml_scorer.is_available():
        print("\n⚠️  ML models not trained yet!")
        print("   Run: python scripts/ml/train_model.py")
        return
    
    print(f"\nTesting on {len(signals)} recent signals:\n")
    
    for i, (token, score, conviction, smart, liq, vol, mcap, actual_gain) in enumerate(signals, 1):
        # Build stats dict
        stats = {
            'liquidity_usd': liq or 0,
            'volume': {'24h': {'volume_usd': vol or 0}},
            'market_cap_usd': mcap or 0
        }
        
        # Get ML predictions
        predicted_gain = ml_scorer.predict_gain(stats, score, bool(smart), conviction or "")
        winner_prob = ml_scorer.predict_winner_probability(stats, score, bool(smart), conviction or "")
        enhanced_score, reason = ml_scorer.enhance_score(score, stats, bool(smart), conviction or "")
        
        # Format actual outcome
        if actual_gain is not None:
            actual_str = f"{actual_gain:>6.0f}%"
            error = abs(predicted_gain - actual_gain) if predicted_gain else 0
            error_str = f"(err: {error:>5.0f}%)" if predicted_gain else ""
        else:
            actual_str = "  N/A "
            error_str = ""
        
        print(f"{i:2d}. Token: {token[:8]}...")
        print(f"    Rule Score: {score}/10 → ML Score: {enhanced_score}/10")
        print(f"    Predicted Gain: {predicted_gain:6.0f}% | Win Prob: {winner_prob:.1%}")
        print(f"    Actual Gain:    {actual_str} {error_str}")
        print(f"    Reason: {reason}")
        print()
    
    print("="*80)
    print("\n✅ Test complete!")


def show_model_stats():
    """Show current model statistics"""
    import json
    
    try:
        with open('var/models/metadata.json', 'r') as f:
            metadata = json.load(f)
        
        print("\n📊 MODEL STATISTICS")
        print("="*80)
        
        gain_meta = metadata.get('gain_predictor', {})
        print("\n🎯 Gain Predictor (Regression):")
        print(f"  Test R²: {gain_meta.get('test_r2', 0):.3f}")
        print(f"  Test RMSE: {gain_meta.get('test_rmse', 0):.1f}%")
        print(f"  Trained: {gain_meta.get('trained_at', 'Unknown')}")
        print(f"  Samples: {gain_meta.get('samples', 0)}")
        
        winner_meta = metadata.get('winner_classifier', {})
        print("\n🏆 Winner Classifier:")
        print(f"  Test Accuracy: {winner_meta.get('test_accuracy', 0):.3f}")
        print(f"  Threshold: {winner_meta.get('threshold', 'N/A')}")
        print(f"  Positive Rate: {winner_meta.get('positive_rate', 0):.1%}")
        
        print("\n✨ Top 5 Feature Importance:")
        importance = gain_meta.get('feature_importance', {})
        for feat, imp in sorted(importance.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {feat:30s}: {imp:.3f}")
        
        print("="*80)
        
    except FileNotFoundError:
        print("\n⚠️  No model metadata found. Train models first.")


if __name__ == '__main__':
    show_model_stats()
    print()
    test_recent_signals(limit=10)

