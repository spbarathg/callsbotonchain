# storage.py
import sqlite3
import math
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from config.config import DB_FILE, DB_RETENTION_HOURS


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

    # Enhanced price tracking for alerted tokens with comprehensive metadata
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerted_token_stats (
            token_address TEXT PRIMARY KEY,
            first_alert_at REAL,
            last_checked_at REAL,
            preliminary_score INTEGER,
            final_score INTEGER,
            conviction_type TEXT,
            
            -- Price tracking
            first_price_usd REAL,
            first_market_cap_usd REAL,
            first_liquidity_usd REAL,
            last_price_usd REAL,
            last_market_cap_usd REAL,
            last_liquidity_usd REAL,
            last_volume_24h_usd REAL,
            peak_price_usd REAL,
            peak_market_cap_usd REAL,
            peak_price_at REAL,
            peak_market_cap_at REAL,
            peak_volume_24h_usd REAL,
            
            -- Performance metrics
            price_change_1h REAL,
            price_change_6h REAL,
            price_change_24h REAL,
            max_gain_percent REAL,
            max_drawdown_percent REAL,
            is_rug BOOLEAN DEFAULT 0,
            rug_detected_at REAL,
            
            -- Token metadata at alert time
            token_name TEXT,
            token_symbol TEXT,
            token_age_minutes REAL,
            holder_count INTEGER,
            unique_traders_15m INTEGER,
            
            -- Alert reasoning - WHY it passed
            smart_money_involved BOOLEAN,
            smart_wallet_address TEXT,
            smart_wallet_pnl REAL,
            velocity_score_15m INTEGER,
            velocity_bonus INTEGER,
            passed_junior_strict BOOLEAN,
            passed_senior_strict BOOLEAN,
            passed_debate BOOLEAN,
            
            -- Security features at alert
            lp_locked BOOLEAN,
            mint_revoked BOOLEAN,
            top10_concentration REAL,
            bundlers_percent REAL,
            insiders_percent REAL,
            
            -- Market conditions at alert
            sol_price_usd REAL,
            feed_source TEXT,
            dex_name TEXT
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

    # New table: Price snapshots over time for alerted tokens
    c.execute("""
        CREATE TABLE IF NOT EXISTS price_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT,
            snapshot_at REAL,
            price_usd REAL,
            market_cap_usd REAL,
            liquidity_usd REAL,
            volume_24h_usd REAL,
            holder_count INTEGER,
            price_change_1h REAL,
            price_change_24h REAL,
            FOREIGN KEY (token_address) REFERENCES alerted_token_stats(token_address)
        )
    """)
    
    # Create index for faster lookups
    c.execute("CREATE INDEX IF NOT EXISTS idx_price_snapshots_token ON price_snapshots(token_address)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_price_snapshots_time ON price_snapshots(snapshot_at)")

    # Migration: Add new columns to existing tables if they don't exist
    existing_columns = [row[1] for row in c.execute("PRAGMA table_info(alerted_token_stats)").fetchall()]
    
    new_columns = [
        ("preliminary_score", "INTEGER"),
        ("token_name", "TEXT"),
        ("token_symbol", "TEXT"),
        ("token_age_minutes", "REAL"),
        ("holder_count", "INTEGER"),
        ("unique_traders_15m", "INTEGER"),
        ("smart_money_involved", "BOOLEAN"),
        ("smart_wallet_address", "TEXT"),
        ("smart_wallet_pnl", "REAL"),
        ("velocity_score_15m", "INTEGER"),
        ("velocity_bonus", "INTEGER"),
        ("passed_junior_strict", "BOOLEAN"),
        ("passed_senior_strict", "BOOLEAN"),
        ("passed_debate", "BOOLEAN"),
        ("lp_locked", "BOOLEAN"),
        ("mint_revoked", "BOOLEAN"),
        ("top10_concentration", "REAL"),
        ("bundlers_percent", "REAL"),
        ("insiders_percent", "REAL"),
        ("sol_price_usd", "REAL"),
        ("feed_source", "TEXT"),
        ("dex_name", "TEXT"),
        ("price_change_1h", "REAL"),
        ("price_change_6h", "REAL"),
        ("price_change_24h", "REAL"),
        ("max_gain_percent", "REAL"),
        ("max_drawdown_percent", "REAL"),
        ("is_rug", "BOOLEAN DEFAULT 0"),
        ("rug_detected_at", "REAL"),
    ]
    
    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            try:
                c.execute(f"ALTER TABLE alerted_token_stats ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass  # Column already exists

    conn.commit()
    conn.close()


def has_been_alerted(token_address: str) -> bool:
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM alerted_tokens WHERE token_address = ? LIMIT 1", (token_address,))
    row = c.fetchone()
    conn.close()
    return row is not None


def mark_alerted(token_address: str, final_score: int, smart_money_detected: bool, conviction_type: str) -> None:
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO alerted_tokens (token_address, final_score, smart_money_detected, conviction_type)
        VALUES (?, ?, ?, ?)
    """, (token_address, final_score, smart_money_detected, conviction_type))
    conn.commit()
    conn.close()


def record_alert_with_metadata(
    token_address: str,
    preliminary_score: int,
    final_score: int,
    conviction_type: str,
    stats: Dict[str, Any],
    alert_metadata: Dict[str, Any]
) -> None:
    """
    Record comprehensive alert data including WHY the token passed gates.
    This allows us to analyze which features correlate with success/failure.
    """
    conn = _get_conn()
    c = conn.cursor()
    
    now = datetime.now().timestamp()
    
    # Extract all relevant data
    price_data = stats.get('price', {})
    market_data = stats.get('market', {})
    security_data = stats.get('security', {})
    liquidity_data = stats.get('liquidity', {})
    holders_data = stats.get('holders', {})
    metadata = stats.get('metadata', {})
    
    # Extract security/liquidity/holders data with proper handling for missing data
    lp_locked = liquidity_data.get('is_lp_locked')
    if lp_locked is None:
        lp_locked = liquidity_data.get('is_lp_burned')
    if lp_locked is None and liquidity_data.get('lock_status') in ("locked", "burned"):
        lp_locked = True
    
    mint_revoked = security_data.get('is_mint_revoked')
    
    top10 = holders_data.get('top_10_holders_percent')
    if top10 is None:
        top10 = holders_data.get('top_10_concentration')
    if top10 is None:
        top10 = holders_data.get('top10_concentration')
    
    c.execute("""
        INSERT OR REPLACE INTO alerted_token_stats (
            token_address, first_alert_at, last_checked_at,
            preliminary_score, final_score, conviction_type,
            first_price_usd, first_market_cap_usd, first_liquidity_usd,
            last_price_usd, last_market_cap_usd, last_liquidity_usd,
            last_volume_24h_usd,
            token_name, token_symbol, token_age_minutes,
            holder_count, unique_traders_15m,
            smart_money_involved, smart_wallet_address, smart_wallet_pnl,
            velocity_score_15m, velocity_bonus,
            passed_junior_strict, passed_senior_strict, passed_debate,
            lp_locked, mint_revoked,
            top10_concentration, bundlers_percent, insiders_percent,
            sol_price_usd, feed_source, dex_name,
            price_change_1h, price_change_24h
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        token_address,
        now,
        now,
        preliminary_score,
        final_score,
        conviction_type,
        price_data.get('price_usd'),
        market_data.get('market_cap_usd') if not isinstance(market_data.get('market_cap_usd'), float) or not math.isnan(market_data.get('market_cap_usd')) else stats.get('market_cap_usd'),
        liquidity_data.get('liquidity_usd') if not isinstance(liquidity_data.get('liquidity_usd'), float) or not math.isnan(liquidity_data.get('liquidity_usd')) else stats.get('liquidity_usd'),
        price_data.get('price_usd'),
        market_data.get('market_cap_usd') if not isinstance(market_data.get('market_cap_usd'), float) or not math.isnan(market_data.get('market_cap_usd')) else stats.get('market_cap_usd'),
        liquidity_data.get('liquidity_usd') if not isinstance(liquidity_data.get('liquidity_usd'), float) or not math.isnan(liquidity_data.get('liquidity_usd')) else stats.get('liquidity_usd'),
        (market_data.get('volume', {}) or {}).get('24h_usd') or market_data.get('volume_24h_usd') or stats.get('volume', {}).get('24h', {}).get('volume_usd'),
        metadata.get('name') or stats.get('name'),
        metadata.get('symbol') or stats.get('symbol'),
        alert_metadata.get('token_age_minutes'),
        holders_data.get('holder_count') or holders_data.get('holders'),
        alert_metadata.get('unique_traders_15m'),
        alert_metadata.get('smart_money_involved', False),
        alert_metadata.get('smart_wallet_address'),
        alert_metadata.get('smart_wallet_pnl'),
        alert_metadata.get('velocity_score_15m'),
        alert_metadata.get('velocity_bonus'),
        alert_metadata.get('passed_junior_strict', False),
        alert_metadata.get('passed_senior_strict', False),
        alert_metadata.get('passed_debate', False),
        lp_locked,
        mint_revoked,
        top10,
        holders_data.get('bundlers_percent') or holders_data.get('bundlers'),
        holders_data.get('insiders_percent') or holders_data.get('insiders'),
        alert_metadata.get('sol_price_usd'),
        alert_metadata.get('feed_source'),
        alert_metadata.get('dex_name'),
        (price_data.get('change', {}) or {}).get('1h') or price_data.get('price_change_1h') or stats.get('change', {}).get('1h'),
        (price_data.get('change', {}) or {}).get('24h') or price_data.get('price_change_24h') or stats.get('change', {}).get('24h'),
    ))
    
    conn.commit()
    conn.close()


def record_price_snapshot(token_address: str, stats: Dict[str, Any]) -> None:
    """Record a price snapshot for tracking performance over time"""
    conn = _get_conn()
    c = conn.cursor()
    
    now = datetime.now().timestamp()
    price_data = stats.get('price', {})
    market_data = stats.get('market', {})
    liquidity_data = stats.get('liquidity', {})
    holders_data = stats.get('holders', {})
    
    c.execute("""
        INSERT INTO price_snapshots (
            token_address, snapshot_at, price_usd, market_cap_usd,
            liquidity_usd, volume_24h_usd, holder_count,
            price_change_1h, price_change_24h
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        token_address,
        now,
        price_data.get('price_usd'),
        market_data.get('market_cap_usd'),
        liquidity_data.get('liquidity_usd'),
        market_data.get('volume_24h_usd'),
        holders_data.get('holder_count'),
        price_data.get('price_change_1h'),
        price_data.get('price_change_24h'),
    ))
    
    conn.commit()
    conn.close()


def update_token_performance(token_address: str, stats: Dict[str, Any]) -> None:
    """Update performance metrics for an alerted token"""
    conn = _get_conn()
    c = conn.cursor()
    
    now = datetime.now().timestamp()
    price_data = stats.get('price', {})
    market_data = stats.get('market', {})
    liquidity_data = stats.get('liquidity', {})
    
    # Get first price to calculate gains/losses
    c.execute("SELECT first_price_usd, peak_price_usd FROM alerted_token_stats WHERE token_address = ?", (token_address,))
    row = c.fetchone()
    
    if row:
        first_price = row[0] or 0
        current_peak = row[1] or 0
        current_price = price_data.get('price_usd', 0)
        
        # Calculate performance metrics
        if first_price > 0:
            gain_percent = ((current_price - first_price) / first_price) * 100
            max_gain = max(gain_percent, ((current_peak - first_price) / first_price) * 100) if current_peak else gain_percent
            max_drawdown = min(0, gain_percent)  # Track worst drop from entry
        else:
            gain_percent = max_gain = max_drawdown = 0
        
        # Update peak if current price is higher
        new_peak_price = max(current_peak, current_price) if current_peak else current_price
        peak_price_at = now if new_peak_price > (current_peak or 0) else None
        
        # Detect rug pull: >80% drop from peak or liquidity removed
        is_rug = False
        rug_at = None
        if current_peak and current_price < current_peak * 0.2:  # >80% drop from peak
            is_rug = True
            rug_at = now
        elif liquidity_data.get('liquidity_usd', float('inf')) < 100:  # Liquidity removed
            is_rug = True
            rug_at = now
        
        # Calculate time-based returns
        c.execute("SELECT snapshot_at, price_usd FROM price_snapshots WHERE token_address = ? ORDER BY snapshot_at", (token_address,))
        snapshots = c.fetchall()
        
        price_1h = price_6h = None
        for snap_time, snap_price in snapshots:
            if now - snap_time <= 3600 and price_1h is None:  # 1 hour
                price_1h = snap_price
            if now - snap_time <= 21600 and price_6h is None:  # 6 hours
                price_6h = snap_price
        
        change_1h = ((current_price - price_1h) / price_1h * 100) if price_1h and price_1h > 0 else None
        change_6h = ((current_price - price_6h) / price_6h * 100) if price_6h and price_6h > 0 else None
        change_24h = price_data.get('price_change_24h')
        
        update_sql = """
            UPDATE alerted_token_stats SET
                last_checked_at = ?,
                last_price_usd = ?,
                last_market_cap_usd = ?,
                last_liquidity_usd = ?,
                last_volume_24h_usd = ?,
                peak_price_usd = ?,
                max_gain_percent = ?,
                max_drawdown_percent = ?,
                price_change_1h = ?,
                price_change_6h = ?,
                price_change_24h = ?
        """
        
        params = [
            now,
            current_price,
            market_data.get('market_cap_usd'),
            liquidity_data.get('liquidity_usd'),
            market_data.get('volume_24h_usd'),
            new_peak_price,
            max_gain,
            max_drawdown,
            change_1h,
            change_6h,
            change_24h,
        ]
        
        if peak_price_at:
            update_sql += ", peak_price_at = ?"
            params.append(peak_price_at)
        
        if is_rug and not row:  # Only set rug flag once
            update_sql += ", is_rug = 1, rug_detected_at = ?"
            params.extend([rug_at])
        
        update_sql += " WHERE token_address = ?"
        params.append(token_address)
        
        c.execute(update_sql, params)
    
    conn.commit()
    conn.close()


def get_alerted_tokens_for_tracking() -> List[str]:
    """Get list of tokens that need performance tracking"""
    conn = _get_conn()
    c = conn.cursor()
    
    # Get tokens alerted in last 24 hours that aren't rugged (reduced from 48h to save API credits)
    one_day_ago = (datetime.now() - timedelta(hours=24)).timestamp()
    c.execute("""
        SELECT token_address FROM alerted_token_stats
        WHERE first_alert_at >= ? AND (is_rug IS NULL OR is_rug = 0)
        ORDER BY first_alert_at DESC
    """, (one_day_ago,))
    
    tokens = [row[0] for row in c.fetchall()]
    conn.close()
    return tokens


def get_performance_summary() -> Dict[str, Any]:
    """Get aggregate performance statistics"""
    conn = _get_conn()
    c = conn.cursor()
    
    summary = {}
    
    # Overall stats
    c.execute("""
        SELECT 
            COUNT(*) as total_alerts,
            AVG(max_gain_percent) as avg_max_gain,
            AVG(price_change_1h) as avg_1h,
            AVG(price_change_6h) as avg_6h,
            AVG(price_change_24h) as avg_24h,
            COUNT(CASE WHEN max_gain_percent > 50 THEN 1 END) as pumps_50plus,
            COUNT(CASE WHEN max_gain_percent > 100 THEN 1 END) as pumps_100plus,
            COUNT(CASE WHEN is_rug = 1 THEN 1 END) as rugs,
            COUNT(CASE WHEN max_gain_percent < -20 THEN 1 END) as dumps_20plus
        FROM alerted_token_stats
        WHERE last_checked_at IS NOT NULL
    """)
    
    row = c.fetchone()
    if row:
        summary['total_alerts'] = row[0]
        summary['avg_max_gain'] = row[1]
        summary['avg_1h'] = row[2]
        summary['avg_6h'] = row[3]
        summary['avg_24h'] = row[4]
        summary['pumps_50plus'] = row[5]
        summary['pumps_100plus'] = row[6]
        summary['rugs'] = row[7]
        summary['dumps_20plus'] = row[8]
    
    # Performance by conviction type
    c.execute("""
        SELECT 
            conviction_type,
            COUNT(*) as count,
            AVG(max_gain_percent) as avg_gain,
            COUNT(CASE WHEN is_rug = 1 THEN 1 END) as rug_count
        FROM alerted_token_stats
        WHERE last_checked_at IS NOT NULL
        GROUP BY conviction_type
    """)
    
    summary['by_conviction'] = {}
    for row in c.fetchall():
        summary['by_conviction'][row[0]] = {
            'count': row[1],
            'avg_gain': row[2],
            'rug_count': row[3]
        }
    
    # Performance by feature
    for feature in ['smart_money_involved', 'lp_locked', 'mint_revoked', 'passed_senior_strict']:
        c.execute(f"""
            SELECT 
                AVG(max_gain_percent) as avg_gain,
                COUNT(CASE WHEN is_rug = 1 THEN 1 END) as rug_count,
                COUNT(*) as total
            FROM alerted_token_stats
            WHERE last_checked_at IS NOT NULL AND {feature} = 1
        """)
        row = c.fetchone()
        if row:
            summary[f'{feature}_performance'] = {
                'avg_gain': row[0],
                'rug_count': row[1],
                'total': row[2]
            }
    
    conn.close()
    return summary


def record_token_activity(token_address: str, usd_value: float, tx_count: int, smart_money_involved: bool, prelim_score: int, trader_address: Optional[str] = None) -> None:
    """Record token activity for velocity tracking"""
    conn = _get_conn()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO token_activity
            (token_address, observed_at, usd_value, transaction_count, smart_money_involved, preliminary_score, trader_address)
            VALUES (?, datetime('now'), ?, ?, ?, ?, ?)
        """, (token_address, usd_value, tx_count, smart_money_involved, prelim_score, trader_address))
        conn.commit()
    except sqlite3.IntegrityError:
        # Ignore duplicate-in-same-second inserts on legacy schemas
        pass
    conn.close()


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


def cleanup_old_activity():
    """Remove old token activity records beyond retention window"""
    conn = _get_conn()
    c = conn.cursor()
    cutoff = datetime.now() - timedelta(hours=DB_RETENTION_HOURS)
    c.execute("DELETE FROM token_activity WHERE observed_at < ?", (cutoff,))
    conn.commit()
    conn.close()