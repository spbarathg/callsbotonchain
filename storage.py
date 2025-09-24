# storage.py
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from config import DB_FILE, DB_RETENTION_HOURS

DB_FILE = DB_FILE

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

    # Price tracking for alerted tokens
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerted_token_stats (
            token_address TEXT PRIMARY KEY,
            first_alert_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_checked_at TIMESTAMP,
            first_price_usd REAL,
            first_market_cap_usd REAL,
            first_liquidity_usd REAL,
            last_price_usd REAL,
            last_market_cap_usd REAL,
            last_liquidity_usd REAL,
            last_volume_24h_usd REAL,
            peak_price_usd REAL,
            peak_market_cap_usd REAL,
            peak_volume_24h_usd REAL
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
    
    # Migration: add missing columns to alerted_token_stats
    try:
        cols = c.execute("PRAGMA table_info(alerted_token_stats)").fetchall()
        col_names = {col[1] for col in cols}
        add_cols = []
        if 'first_price_usd' not in col_names:
            add_cols.append("ADD COLUMN first_price_usd REAL")
        if 'first_market_cap_usd' not in col_names:
            add_cols.append("ADD COLUMN first_market_cap_usd REAL")
        if 'first_liquidity_usd' not in col_names:
            add_cols.append("ADD COLUMN first_liquidity_usd REAL")
        if 'last_market_cap_usd' not in col_names:
            add_cols.append("ADD COLUMN last_market_cap_usd REAL")
        if 'last_liquidity_usd' not in col_names:
            add_cols.append("ADD COLUMN last_liquidity_usd REAL")
        if 'last_volume_24h_usd' not in col_names:
            add_cols.append("ADD COLUMN last_volume_24h_usd REAL")
        if 'peak_market_cap_usd' not in col_names:
            add_cols.append("ADD COLUMN peak_market_cap_usd REAL")
        if 'peak_volume_24h_usd' not in col_names:
            add_cols.append("ADD COLUMN peak_volume_24h_usd REAL")
        for stmt in add_cols:
            c.execute(f"ALTER TABLE alerted_token_stats {stmt}")
    except Exception:
        pass

    conn.commit()
    conn.close()

def has_been_alerted(token_address: str) -> bool:
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM alerted_tokens WHERE token_address = ?", (token_address,))
    result = c.fetchone()
    conn.close()
    return result is not None

def mark_as_alerted(token_address: str, score: int = 0, smart_money_detected: bool = False,
                    baseline_price_usd: float = None, baseline_market_cap_usd: float = None,
                    baseline_liquidity_usd: float = None, baseline_volume_24h_usd: float = None) -> None:
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO alerted_tokens 
        (token_address, final_score, smart_money_detected) 
        VALUES (?, ?, ?)
    """, (token_address, score, smart_money_detected))
    # initialize tracking row
    c.execute(
        """
        INSERT OR IGNORE INTO alerted_token_stats (
            token_address, last_checked_at, first_price_usd, first_market_cap_usd, first_liquidity_usd,
            last_price_usd, last_market_cap_usd, last_liquidity_usd, last_volume_24h_usd,
            peak_price_usd, peak_market_cap_usd, peak_volume_24h_usd
        ) VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            token_address,
            baseline_price_usd, baseline_market_cap_usd, baseline_liquidity_usd,
            baseline_price_usd, baseline_market_cap_usd, baseline_liquidity_usd, baseline_volume_24h_usd,
            baseline_price_usd, baseline_market_cap_usd, baseline_volume_24h_usd,
        ),
    )
    conn.commit()
    conn.close()

def record_token_activity(token_address: str, usd_value: float, tx_count: int, smart_money_involved: bool, prelim_score: int, trader_address: Optional[str] = None) -> None:
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

def get_token_velocity(token_address: str, minutes_back: int = 30) -> Optional[Dict[str, Any]]:
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

def should_fetch_detailed_stats(token_address: str, current_prelim_score: int) -> bool:
    """Determine if we should make expensive API call for detailed stats"""
    # Always fetch for high preliminary scores
    from config import PRELIM_DETAILED_MIN, PRELIM_VELOCITY_MIN_SCORE, VELOCITY_REQUIRED
    if current_prelim_score >= PRELIM_DETAILED_MIN:
        return True
    
    # Check velocity for medium scores
    if current_prelim_score >= PRELIM_VELOCITY_MIN_SCORE:
        velocity = get_token_velocity(token_address, minutes_back=15)
        if velocity and velocity['velocity_score'] >= VELOCITY_REQUIRED:
            return True
    
    return False


def get_alerted_tokens_batch(limit: int = 25, older_than_minutes: int = 55):
    """Return a batch of alerted tokens that haven't been checked recently."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT t.token_address
        FROM alerted_token_stats s
        JOIN alerted_tokens t ON t.token_address = s.token_address
        WHERE (strftime('%s','now') - strftime('%s', COALESCE(s.last_checked_at, '1970-01-01 00:00:00'))) > (? * 60)
        ORDER BY s.last_checked_at ASC NULLS FIRST
        LIMIT ?
        """,
        (older_than_minutes, limit),
    )
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    return rows


def update_token_tracking(token_address: str, price_usd: float, market_cap_usd: float = None,
                          liquidity_usd: float = None, volume_24h_usd: float = None) -> None:
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        """
        UPDATE alerted_token_stats
        SET last_checked_at = CURRENT_TIMESTAMP,
            last_price_usd = ?,
            last_market_cap_usd = COALESCE(?, last_market_cap_usd),
            last_liquidity_usd = COALESCE(?, last_liquidity_usd),
            last_volume_24h_usd = COALESCE(?, last_volume_24h_usd),
            peak_price_usd = CASE WHEN peak_price_usd IS NULL OR ? > peak_price_usd THEN ? ELSE peak_price_usd END,
            peak_market_cap_usd = CASE WHEN peak_market_cap_usd IS NULL OR COALESCE(?,0) > COALESCE(peak_market_cap_usd,0) THEN COALESCE(?, peak_market_cap_usd) ELSE peak_market_cap_usd END,
            peak_volume_24h_usd = CASE WHEN peak_volume_24h_usd IS NULL OR COALESCE(?,0) > COALESCE(peak_volume_24h_usd,0) THEN COALESCE(?, peak_volume_24h_usd) ELSE peak_volume_24h_usd END
        WHERE token_address = ?
        """,
        (
            price_usd,
            market_cap_usd,
            liquidity_usd,
            volume_24h_usd,
            price_usd, price_usd,
            market_cap_usd, market_cap_usd,
            volume_24h_usd, volume_24h_usd,
            token_address,
        ),
    )
    conn.commit()
    conn.close()


def prune_old_activity(hours: int = DB_RETENTION_HOURS) -> int:
    """Delete token_activity rows older than the retention window. Returns rows deleted."""
    conn = _get_conn()
    c = conn.cursor()
    cutoff_time = datetime.now() - timedelta(hours=hours)
    cutoff_iso = cutoff_time.strftime('%Y-%m-%d %H:%M:%S')
    c.execute("DELETE FROM token_activity WHERE observed_at < ?", (cutoff_iso,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted


def ensure_indices() -> None:
    """Create indices to speed up velocity queries if not present."""
    conn = _get_conn()
    c = conn.cursor()
    try:
        c.execute("CREATE INDEX IF NOT EXISTS idx_token_activity_token_time ON token_activity(token_address, observed_at)")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
