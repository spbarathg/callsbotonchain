# storage.py
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from config import DB_FILE, DB_RETENTION_HOURS


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, timeout=10)
    try:
        # Use rollback journal to avoid cross-container/WAL file issues on some hosts
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
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
            smart_money_detected BOOLEAN,
            conviction_type TEXT
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
            peak_price_at TIMESTAMP,
            peak_market_cap_at TIMESTAMP,
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
        if 'peak_price_at' not in col_names:
            add_cols.append("ADD COLUMN peak_price_at TIMESTAMP")
        if 'peak_market_cap_at' not in col_names:
            add_cols.append("ADD COLUMN peak_market_cap_at TIMESTAMP")
        if 'outcome' not in col_names:
            add_cols.append("ADD COLUMN outcome TEXT")
        if 'outcome_at' not in col_names:
            add_cols.append("ADD COLUMN outcome_at TIMESTAMP")
        if 'peak_drawdown_pct' not in col_names:
            add_cols.append("ADD COLUMN peak_drawdown_pct REAL")
        for stmt in add_cols:
            c.execute(f"ALTER TABLE alerted_token_stats {stmt}")
    except Exception:
        pass

    # Migration: add conviction_type to alerted_tokens if missing
    try:
        cols = c.execute("PRAGMA table_info(alerted_tokens)").fetchall()
        col_names = {col[1] for col in cols}
        if 'conviction_type' not in col_names:
            c.execute("ALTER TABLE alerted_tokens ADD COLUMN conviction_type TEXT")
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
                    baseline_liquidity_usd: float = None, baseline_volume_24h_usd: float = None,
                    conviction_type: Optional[str] = None) -> None:
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO alerted_tokens
        (token_address, final_score, smart_money_detected, conviction_type)
        VALUES (?, ?, ?, ?)
    """, (token_address, score, smart_money_detected, conviction_type))
    # initialize tracking row
    c.execute(
        """
        INSERT OR IGNORE INTO alerted_token_stats (
            token_address, last_checked_at, first_price_usd, first_market_cap_usd, first_liquidity_usd,
            last_price_usd, last_market_cap_usd, last_liquidity_usd, last_volume_24h_usd,
            peak_price_usd, peak_market_cap_usd, peak_volume_24h_usd,
            peak_price_at, peak_market_cap_at
        ) VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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


def get_recent_token_signals(token_address: str, window_seconds: int) -> List[str]:
    """Return timestamps (ISO) of recent observations for a token within window.
    Used for multi-signal confirmation prior to expensive stats calls.
    """
    conn = _get_conn()
    c = conn.cursor()
    try:
        c.execute(
            """
            SELECT observed_at FROM token_activity
            WHERE token_address = ? AND observed_at >= datetime('now', printf('-%d seconds', ?))
            ORDER BY observed_at DESC
            """,
            (token_address, int(window_seconds)),
        )
        rows = [r[0] for r in c.fetchall()]
    except Exception:
        # Fallback for environments without printf
        c.execute(
            """
            SELECT observed_at FROM token_activity
            WHERE token_address = ? AND (strftime('%s','now') - strftime('%s', observed_at)) <= ?
            ORDER BY observed_at DESC
            """,
            (token_address, int(window_seconds)),
        )
        rows = [r[0] for r in c.fetchall()]
    finally:
        conn.close()
    return rows


def should_fetch_detailed_stats(token_address: str, current_prelim_score: int, *, is_synthetic: bool = False) -> bool:
    """Determine if we should make expensive API call for detailed stats"""
    # Always fetch for high preliminary scores
    from config import PRELIM_DETAILED_MIN, PRELIM_VELOCITY_MIN_SCORE, VELOCITY_REQUIRED
    # Synthetic items require a higher barrier to spend credits
    threshold = int(PRELIM_DETAILED_MIN + (1 if is_synthetic else 0))
    if current_prelim_score >= threshold:
        return True

    # Check velocity for medium scores
    vel_gate = int(PRELIM_VELOCITY_MIN_SCORE + (1 if is_synthetic else 0))
    if current_prelim_score >= vel_gate:
        velocity = get_token_velocity(token_address, minutes_back=15)
        if velocity and velocity['velocity_score'] >= VELOCITY_REQUIRED:
            return True

    return False


def get_alerted_tokens_batch(limit: int = 25, older_than_minutes: int = 55):
    """Return a batch of alerted tokens that haven't been checked recently."""
    conn = _get_conn()
    c = conn.cursor()
    try:
        c.execute(
            """
            SELECT t.token_address
            FROM alerted_token_stats s
            JOIN alerted_tokens t ON t.token_address = s.token_address
            WHERE s.last_checked_at IS NULL OR s.last_checked_at < datetime('now', printf('-%d minutes', ?))
            ORDER BY (s.last_checked_at IS NOT NULL), s.last_checked_at ASC
            LIMIT ?
            """,
            (older_than_minutes, limit),
        )
    except Exception as e:
        from app.logger_utils import log_process
        try:
            log_process({"type": "error", "stage": "get_alerted_tokens_batch", "error": str(e)})
        except Exception:
            pass
        # Fallback to previous expression if printf not supported
        c.execute(
            """
            SELECT t.token_address
            FROM alerted_token_stats s
            JOIN alerted_tokens t ON t.token_address = s.token_address
            WHERE (strftime('%s','now') - strftime('%s', COALESCE(s.last_checked_at, '1970-01-01 00:00:00'))) > (? * 60)
            ORDER BY (s.last_checked_at IS NOT NULL), s.last_checked_at ASC
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
            peak_price_at  = CASE WHEN peak_price_usd IS NULL OR ? > peak_price_usd THEN CURRENT_TIMESTAMP ELSE peak_price_at END,
            peak_market_cap_usd = CASE WHEN peak_market_cap_usd IS NULL OR COALESCE(?,0) > COALESCE(peak_market_cap_usd,0) THEN COALESCE(?, peak_market_cap_usd) ELSE peak_market_cap_usd END,
            peak_market_cap_at  = CASE WHEN peak_market_cap_usd IS NULL OR COALESCE(?,0) > COALESCE(peak_market_cap_usd,0) THEN CURRENT_TIMESTAMP ELSE peak_market_cap_at END,
            peak_volume_24h_usd = CASE WHEN peak_volume_24h_usd IS NULL OR COALESCE(?,0) > COALESCE(peak_volume_24h_usd,0) THEN COALESCE(?, peak_volume_24h_usd) ELSE peak_volume_24h_usd END
        WHERE token_address = ?
        """,
        (
            price_usd,
            market_cap_usd,
            liquidity_usd,
            volume_24h_usd,
            price_usd, price_usd,
            price_usd,
            market_cap_usd, market_cap_usd,
            market_cap_usd,
            volume_24h_usd, volume_24h_usd,
            token_address,
        ),
    )
    # Backfill baseline if missing (improves export completeness)
    try:
        row = c.execute(
            """
            SELECT first_price_usd, first_market_cap_usd, first_liquidity_usd, first_alert_at
            FROM alerted_token_stats WHERE token_address = ?
            """,
            (token_address,),
        ).fetchone()
        if row:
            first_p, first_m, first_l, first_at = row
            if first_p is None or first_m is None or first_l is None:
                c.execute(
                    """
                    UPDATE alerted_token_stats
                    SET first_price_usd = COALESCE(first_price_usd, ?),
                        first_market_cap_usd = COALESCE(first_market_cap_usd, ?),
                        first_liquidity_usd = COALESCE(first_liquidity_usd, ?),
                        first_alert_at = COALESCE(first_alert_at, CURRENT_TIMESTAMP)
                    WHERE token_address = ?
                    """,
                    (price_usd, market_cap_usd, liquidity_usd, token_address),
                )
    except Exception:
        pass
    # Rug/outcome heuristic and drawdown update always
    try:
        row = c.execute(
            """
            SELECT first_price_usd, peak_price_usd, last_price_usd, last_liquidity_usd, outcome
            FROM alerted_token_stats WHERE token_address = ?
            """,
            (token_address,),
        ).fetchone()
        if row:
            first_p, peak_p, last_p, last_liq, outcome = row
            peak_p = peak_p or 0
            last_p = last_p or 0
            drawdown_pct = None
            if peak_p > 0 and last_p >= 0:
                drawdown_pct = (1 - (last_p / peak_p)) * 100
                c.execute(
                    """
                    UPDATE alerted_token_stats
                    SET peak_drawdown_pct = ?
                    WHERE token_address = ?
                    """,
                    (drawdown_pct, token_address),
                )
            from config import RUG_DRAWDOWN_PCT, RUG_MIN_LIQUIDITY_USD
            is_lp_gone = (last_liq or 0) <= RUG_MIN_LIQUIDITY_USD
            is_hard_drawdown = (drawdown_pct is not None) and (drawdown_pct >= RUG_DRAWDOWN_PCT)
            if outcome is None and (is_lp_gone or is_hard_drawdown):
                c.execute(
                    """
                    UPDATE alerted_token_stats
                    SET outcome = 'rug', outcome_at = CURRENT_TIMESTAMP, peak_drawdown_pct = ?
                    WHERE token_address = ?
                    """,
                    (drawdown_pct, token_address),
                )
            # Mark ongoing explicitly if no rug and we have at least one check
            if outcome is None and not is_lp_gone and not is_hard_drawdown:
                c.execute(
                    """
                    UPDATE alerted_token_stats
                    SET outcome = COALESCE(outcome, 'ongoing')
                    WHERE token_address = ?
                    """,
                    (token_address,),
                )
    except Exception:
        pass
    conn.commit()
    conn.close()


def get_tracking_snapshot(token_address: str) -> Optional[Dict[str, Any]]:
    """Return current tracking snapshot with computed peak multiples and time-to-peak seconds."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT token_address, first_alert_at, first_price_usd, first_market_cap_usd,
               last_price_usd, last_market_cap_usd,
               peak_price_usd, peak_market_cap_usd, peak_price_at, peak_market_cap_at,
               outcome, peak_drawdown_pct
        FROM alerted_token_stats WHERE token_address = ?
        """,
        (token_address,),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    (
        tok, first_alert_at, first_price, first_mcap,
        last_price, last_mcap,
        peak_price, peak_mcap, peak_price_at, peak_mcap_at,
        outcome, peak_drawdown_pct,
    ) = row

    def _parse(ts: Optional[str]) -> Optional[datetime]:
        if not ts:
            return None
        try:
            # SQLite CURRENT_TIMESTAMP is 'YYYY-MM-DD HH:MM:SS'
            return datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
        except Exception:
            try:
                return datetime.fromisoformat(ts)
            except Exception:
                return None

    t0 = _parse(first_alert_at)
    tp = _parse(peak_price_at)
    tm = _parse(peak_mcap_at)
    ttp_s = int((tp - t0).total_seconds()) if t0 and tp else None
    ttm_s = int((tm - t0).total_seconds()) if t0 and tm else None

    peak_x_price = (peak_price / first_price) if (first_price or 0) else None
    peak_x_mcap = (peak_mcap / first_mcap) if (first_mcap or 0) else None

    return {
        'token': tok,
        'first_alert_at': first_alert_at,
        'first_price': first_price or 0,
        'first_mcap': first_mcap or 0,
        'last_price': last_price or 0,
        'last_mcap': last_mcap or 0,
        'peak_price': peak_price or 0,
        'peak_mcap': peak_mcap or 0,
        'peak_price_at': peak_price_at,
        'peak_mcap_at': peak_mcap_at,
        'time_to_peak_price_s': ttp_s,
        'time_to_peak_mcap_s': ttm_s,
        'peak_x_price': peak_x_price,
        'peak_x_mcap': peak_x_mcap,
        'outcome': outcome,
        'peak_drawdown_pct': peak_drawdown_pct,
    }


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
        c.execute("CREATE INDEX IF NOT EXISTS idx_alerted_stats_last_checked ON alerted_token_stats(last_checked_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_alerted_tokens_alerted_at ON alerted_tokens(alerted_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_alerted_stats_outcome ON alerted_token_stats(outcome)")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def repair_first_prices_from_alerts() -> int:
    """Backfill first_price_usd from alerts.jsonl for tokens with 0 or NULL first_price."""
    import json
    import os
    
    conn = _get_conn()
    c = conn.cursor()
    
    # Read alerts.jsonl to extract baseline prices
    alerts_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'logs', 'alerts.jsonl')
    alerts = {}
    try:
        with open(alerts_file, 'r') as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    if 'token_address' in obj and 'price' in obj:
                        price = float(obj.get('price', 0) or 0)
                        if price > 0:
                            alerts[obj['token_address']] = price
                except:
                    pass
    except Exception:
        pass
    
    # Update first_price_usd for tokens with 0 or NULL
    updated = 0
    for token, price in alerts.items():
        c.execute(
            "UPDATE alerted_token_stats SET first_price_usd = ? WHERE token_address = ? AND (first_price_usd IS NULL OR first_price_usd = 0)",
            (price, token)
        )
        if c.rowcount > 0:
            updated += 1
    
    conn.commit()
    conn.close()
    return updated
