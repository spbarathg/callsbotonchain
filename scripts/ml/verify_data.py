"""
Verify Database Schema and Data Quality
Checks if the database structure matches what ML system expects
"""
import sqlite3
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


def check_database():
    """Verify database structure and data availability"""
    
    db_path = 'var/alerted_tokens.db'
    
    if not os.path.exists(db_path):
        print(f"❌ ERROR: Database not found at {db_path}")
        return False
    
    print("="*60)
    print("DATABASE VERIFICATION")
    print("="*60)
    
    con = sqlite3.connect(db_path)
    
    # Check tables exist
    cur = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]
    
    print("\nTables found:")
    for table in tables:
        print(f"   - {table}")
    
    required_tables = ['alerted_tokens', 'alerted_token_stats']
    missing = [t for t in required_tables if t not in tables]
    if missing:
        print(f"\n❌ ERROR: Missing tables: {missing}")
        return False
    
    # Check record counts
    print("\nRecord counts:")
    
    cur = con.execute("SELECT COUNT(*) FROM alerted_tokens")
    total_signals = cur.fetchone()[0]
    print(f"   Alerted tokens: {total_signals}")
    
    cur = con.execute("SELECT COUNT(*) FROM alerted_token_stats")
    tracked_stats = cur.fetchone()[0]
    print(f"   Tracked stats: {tracked_stats}")
    
    cur = con.execute("SELECT COUNT(*) FROM alerted_token_stats WHERE max_gain_percent IS NOT NULL")
    with_outcomes = cur.fetchone()[0]
    print(f"   With outcome data: {with_outcomes}")
    
    # Check required columns in alerted_token_stats
    print("\nChecking alerted_token_stats columns:")
    cur = con.execute("PRAGMA table_info(alerted_token_stats)")
    columns = [row[1] for row in cur.fetchall()]
    
    required_cols = [
        'token_address', 'first_alert_at', 'preliminary_score', 'final_score',
        'conviction_type', 'smart_money_involved',
        'first_price_usd', 'first_market_cap_usd', 'first_liquidity_usd',
        'max_gain_percent', 'peak_price_usd', 'is_rug'
    ]
    
    for col in required_cols:
        if col in columns:
            print(f"   [OK] {col}")
        else:
            print(f"   [MISSING] {col}")
    
    # Show sample data
    print("\nSample data from alerted_token_stats:")
    cur = con.execute("""
        SELECT 
            token_address,
            preliminary_score,
            first_liquidity_usd,
            max_gain_percent,
            is_rug
        FROM alerted_token_stats
        WHERE token_address IS NOT NULL
        LIMIT 5
    """)
    
    print(f"   {'Token':<12} {'Score':<7} {'Liquidity':<12} {'Gain%':<10} {'Rug':<5}")
    print(f"   {'-'*50}")
    
    for row in cur.fetchall():
        token = row[0][:8] + "..." if row[0] else "None"
        score = row[1] if row[1] is not None else "N/A"
        liq = f"${row[2]:,.0f}" if row[2] else "None"
        gain = f"{row[3]:.1f}%" if row[3] is not None else "None"
        rug = "Yes" if row[4] else "No"
        print(f"   {token:<12} {str(score):<7} {liq:<12} {gain:<10} {rug:<5}")
    
    con.close()
    
    # Assessment
    print("\n" + "="*60)
    print("ASSESSMENT")
    print("="*60)
    
    if with_outcomes == 0:
        print("\nWARNING: No outcome data available yet!")
        print("   Reasons:")
        print("   1. Tracking system hasn't run yet (needs 30+ sec after alert)")
        print("   2. Tokens too new (need time to pump/dump)")
        print("   3. max_gain_percent calculation may need debugging")
        print("\n   Solution:")
        print("   - Wait for tracking system to update stats")
        print("   - Check: docker logs callsbot-tracker --tail 50")
        print("   - Or run: scripts/track_performance.py manually")
        return False
    elif with_outcomes < 50:
        print(f"\nWARNING: Only {with_outcomes} samples with outcomes")
        print("   Need at least 50 for reliable ML training")
        print("   Wait for more signals to accumulate.")
        return False
    else:
        print(f"\nSUCCESS: {with_outcomes} samples ready for ML training!")
        print("   You can now train models with:")
        print("   python scripts/ml/train_model.py")
        return True


if __name__ == '__main__':
    success = check_database()
    sys.exit(0 if success else 1)

