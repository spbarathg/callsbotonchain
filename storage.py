# storage.py
import sqlite3
from datetime import datetime, timedelta

DB_FILE = "alerted_tokens.db"

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
    except Exception:
        pass
    return conn

def init_db():
    conn = _get_conn()
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
            preliminary_score INTEGER,
            trader_address TEXT
        )
    """)

    # Migration: if an older schema used a composite PRIMARY KEY
    try:
        row = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='token_activity'").fetchone()
        if row and "PRIMARY KEY (token_address, observed_at)" in (row[0] or ""):
            # Migrate to autoincrement id table
            c.execute("""
                CREATE TABLE token_activity_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_address TEXT,
                    observed_at TIMESTAMP,
                    usd_value REAL,
                    transaction_count INTEGER,
                    smart_money_involved BOOLEAN,
                    preliminary_score INTEGER
                )
            """)
            c.execute("""
                INSERT INTO token_activity_new (token_address, observed_at, usd_value, transaction_count, smart_money_involved, preliminary_score)
                SELECT token_address, observed_at, usd_value, transaction_count, smart_money_involved, preliminary_score FROM token_activity
            """)
            c.execute("DROP TABLE token_activity")
            c.execute("ALTER TABLE token_activity_new RENAME TO token_activity")
    except Exception:
        pass

    # Migration: add trader_address column if missing
    try:
        cols = c.execute("PRAGMA table_info(token_activity)").fetchall()
        col_names = {col[1] for col in cols}
        if 'trader_address' not in col_names:
            c.execute("ALTER TABLE token_activity ADD COLUMN trader_address TEXT")
    except Exception:
        pass
    
    conn.commit()
    conn.close()

def has_been_alerted(token_address):
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM alerted_tokens WHERE token_address = ?", (token_address,))
    result = c.fetchone()
    conn.close()
    return result is not None

def mark_as_alerted(token_address, score=0, smart_money_detected=False):
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO alerted_tokens 
        (token_address, final_score, smart_money_detected) 
        VALUES (?, ?, ?)
    """, (token_address, score, smart_money_detected))
    conn.commit()
    conn.close()

def record_token_activity(token_address, usd_value, tx_count, smart_money_involved, prelim_score, trader_address=None):
    """Record token activity for velocity tracking"""
    conn = _get_conn()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO token_activity 
            (token_address, usd_value, transaction_count, smart_money_involved, preliminary_score, trader_address)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (token_address, usd_value, tx_count, smart_money_involved, prelim_score, trader_address))
        conn.commit()
    except sqlite3.IntegrityError:
        # Ignore duplicate-in-same-second inserts on legacy schemas
        pass
    conn.close()

def get_token_velocity(token_address, minutes_back=30):
    """Calculate token velocity - activity increase over time"""
    conn = _get_conn()
    c = conn.cursor()
    
    cutoff_time = datetime.now() - timedelta(minutes=minutes_back)
    # Format cutoff to ISO string for consistent SQLite comparison
    cutoff_iso = cutoff_time.strftime('%Y-%m-%d %H:%M:%S')
    c.execute("""
        SELECT COUNT(*), AVG(usd_value), MAX(transaction_count), 
               COUNT(CASE WHEN smart_money_involved = 1 THEN 1 END),
               COUNT(DISTINCT COALESCE(trader_address, ''))
        FROM token_activity 
        WHERE token_address = ? AND observed_at > ?
    """, (token_address, cutoff_iso))
    
    result = c.fetchone()
    conn.close()
    
    if result and result[0] > 0:
        observations, avg_usd, max_tx_count, smart_money_count, unique_traders = result
        velocity_score = min(observations * 2 + smart_money_count, 10)  # Cap at 10
        return {
            'observations': observations,
            'avg_usd_value': avg_usd or 0,
            'max_tx_count': max_tx_count or 0,
            'smart_money_interactions': smart_money_count,
            'velocity_score': velocity_score,
            'unique_traders': unique_traders or 0
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
