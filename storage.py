# storage.py
import sqlite3
from datetime import datetime, timedelta

DB_FILE = "alerted_tokens.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Tokens that have been alerted
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerted_tokens (
            token_address TEXT PRIMARY KEY,
            alerted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            final_score INTEGER,
            smart_money_detected BOOLEAN
        )
    """)
    
    # Token activity tracking for velocity detection
    c.execute("""
        CREATE TABLE IF NOT EXISTS token_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT,
            observed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            usd_value REAL,
            transaction_count INTEGER,
            smart_money_involved BOOLEAN,
            preliminary_score INTEGER
        )
    """)
    
    conn.commit()
    conn.close()

def has_been_alerted(token_address):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM alerted_tokens WHERE token_address = ?", (token_address,))
    result = c.fetchone()
    conn.close()
    return result is not None

def mark_as_alerted(token_address, score=0, smart_money_detected=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO alerted_tokens 
        (token_address, final_score, smart_money_detected) 
        VALUES (?, ?, ?)
    """, (token_address, score, smart_money_detected))
    conn.commit()
    conn.close()

def record_token_activity(token_address, usd_value, tx_count, smart_money_involved, prelim_score):
    """Record token activity for velocity tracking"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO token_activity 
        (token_address, usd_value, transaction_count, smart_money_involved, preliminary_score)
        VALUES (?, ?, ?, ?, ?)
    """, (token_address, usd_value, tx_count, smart_money_involved, prelim_score))
    conn.commit()
    conn.close()

def get_token_velocity(token_address, minutes_back=30):
    """Calculate token velocity - activity increase over time"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    cutoff_time = datetime.now() - timedelta(minutes=minutes_back)
    # Format cutoff to ISO string for consistent SQLite comparison
    cutoff_iso = cutoff_time.strftime('%Y-%m-%d %H:%M:%S')
    c.execute("""
        SELECT COUNT(*), AVG(usd_value), MAX(transaction_count), 
               COUNT(CASE WHEN smart_money_involved = 1 THEN 1 END)
        FROM token_activity 
        WHERE token_address = ? AND observed_at > ?
    """, (token_address, cutoff_iso))
    
    result = c.fetchone()
    conn.close()
    
    if result and result[0] > 0:
        observations, avg_usd, max_tx_count, smart_money_count = result
        velocity_score = min(observations * 2 + smart_money_count, 10)  # Cap at 10
        return {
            'observations': observations,
            'avg_usd_value': avg_usd or 0,
            'max_tx_count': max_tx_count or 0,
            'smart_money_interactions': smart_money_count,
            'velocity_score': velocity_score
        }
    return None

def should_fetch_detailed_stats(token_address, current_prelim_score):
    """Determine if we should make expensive API call for detailed stats"""
    # Always fetch for high preliminary scores
    if current_prelim_score >= 6:
        return True
    
    # Check velocity for medium scores
    if current_prelim_score >= 3:
        velocity = get_token_velocity(token_address, minutes_back=15)
        if velocity and velocity['velocity_score'] >= 5:
            return True
    
    return False
