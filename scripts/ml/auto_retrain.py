"""
Automatic Model Retraining
Checks if enough new data has accumulated and retrains models
Run this via cron weekly/daily
"""
import os
import sys
import sqlite3
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


def get_last_retrain_time() -> datetime:
    """Get timestamp of last retrain"""
    try:
        with open('var/models/last_retrain.txt', 'r') as f:
            timestamp = f.read().strip()
            return datetime.fromisoformat(timestamp)
    except FileNotFoundError:
        return datetime(2020, 1, 1)  # Very old date if never trained


def count_new_samples(since: datetime, db_path='var/alerted_tokens.db') -> int:
    """Count new samples since last retrain"""
    con = sqlite3.connect(db_path)
    cur = con.execute("""
        SELECT COUNT(*) 
        FROM alerted_tokens a
        JOIN alerted_token_stats s ON a.token_address = s.token_address
        WHERE a.alerted_at > ?
        AND s.max_gain_percent IS NOT NULL
    """, [since.timestamp()])
    
    count = cur.fetchone()[0]
    con.close()
    return count


def should_retrain(min_new_samples=50) -> tuple:
    """
    Check if retraining is needed
    
    Returns:
        (should_retrain: bool, new_samples: int, last_retrain: datetime)
    """
    last_retrain = get_last_retrain_time()
    new_samples = count_new_samples(last_retrain)
    
    return (new_samples >= min_new_samples, new_samples, last_retrain)


def backup_models():
    """Backup current models before retraining"""
    import shutil
    
    if os.path.exists('var/models'):
        backup_path = f'var/models.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        shutil.copytree('var/models', backup_path)
        print(f"📦 Backed up models to: {backup_path}")
        return backup_path
    return None


def retrain():
    """Run retraining script"""
    print("🔄 Starting retraining...")
    
    result = subprocess.run(
        [sys.executable, 'scripts/ml/train_model.py'],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print("✅ Retraining successful!")
        print(result.stdout)
        return True
    else:
        print("❌ Retraining failed!")
        print(result.stderr)
        return False


def compare_performance(backup_path: str):
    """Compare new model vs old model performance"""
    import json
    
    try:
        # Load new metadata
        with open('var/models/metadata.json', 'r') as f:
            new_meta = json.load(f)
        
        # Load old metadata
        old_meta_path = f'{backup_path}/metadata.json'
        if os.path.exists(old_meta_path):
            with open(old_meta_path, 'r') as f:
                old_meta = json.load(f)
            
            print("\n📊 PERFORMANCE COMPARISON")
            print("="*60)
            
            # Gain predictor
            old_r2 = old_meta.get('gain_predictor', {}).get('test_r2', 0)
            new_r2 = new_meta.get('gain_predictor', {}).get('test_r2', 0)
            diff_r2 = new_r2 - old_r2
            
            print("Gain Predictor R²:")
            print(f"  Old: {old_r2:.3f}")
            print(f"  New: {new_r2:.3f}")
            print(f"  Δ:   {diff_r2:+.3f} {'📈' if diff_r2 > 0 else '📉'}")
            
            # Winner classifier
            old_acc = old_meta.get('winner_classifier', {}).get('test_accuracy', 0)
            new_acc = new_meta.get('winner_classifier', {}).get('test_accuracy', 0)
            diff_acc = new_acc - old_acc
            
            print("\nWinner Classifier Accuracy:")
            print(f"  Old: {old_acc:.3f}")
            print(f"  New: {new_acc:.3f}")
            print(f"  Δ:   {diff_acc:+.3f} {'📈' if diff_acc > 0 else '📉'}")
            
            print("="*60)
    except Exception as e:
        print(f"⚠️  Could not compare performance: {e}")


def main():
    """Main auto-retrain logic"""
    print("🤖 AUTO-RETRAIN CHECK")
    print("="*60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check if retraining needed
    needs_retrain, new_samples, last_retrain = should_retrain(min_new_samples=50)
    
    print(f"\nLast retrain: {last_retrain.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"New samples since then: {new_samples}")
    
    if not needs_retrain:
        print(f"\n⏸️  Not enough new data (need 50, have {new_samples})")
        print("   Skipping retrain.")
        return
    
    print(f"\n✅ Ready to retrain with {new_samples} new samples!")
    
    # Backup current models
    backup_path = backup_models()
    
    # Retrain
    success = retrain()
    
    if success and backup_path:
        # Compare performance
        compare_performance(backup_path)
        
        print("\n🎉 Retraining complete!")
        print("   New models are now active.")
        print(f"   Old models backed up to: {backup_path}")
    elif not success and backup_path:
        print("\n⚠️  Retraining failed, old models still active")
        print("   Check logs for errors")
    
    print("="*60)


if __name__ == '__main__':
    main()

