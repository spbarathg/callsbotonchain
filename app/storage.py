# storage.py
import sqlite3
import math
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from app.config_unified import DB_FILE, DB_RETENTION_HOURS
from app.alert_cache import get_alert_cache


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


def _is_valid_number(value: Any) -> bool:
    """Return True if value can be coerced to a finite float."""
    try:
        f = float(value)
        return not (math.isnan(f) or math.isinf(f))
    except Exception:
        return False


def _select_valid_number(primary: Any, fallback: Any) -> float:
    """Select first valid numeric from primary or fallback, else 0.0."""
    if _is_valid_number(primary):
        return float(primary)
    if _is_valid_number(fallback):
        return float(fallback)
    return 0.0


def init_db():
    """
    Initialize database schema and run migrations.

    Creates base tables if they don't exist, then runs any pending migrations
    to bring the schema up to the latest version.
    """
    # FIRST: Create base tables (migrations depend on these existing)
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
        # Realistic returns tracking (with trailing stops)
        ("realistic_exit_price", "REAL"),
        ("realistic_gain_percent", "REAL"),
        ("trailing_stop_pct", "REAL DEFAULT 15.0"),
        ("would_have_exited_at", "REAL"),
    ]
    
    # Hardened: validate column names against allowlist before ALTER TABLE
    allowed_columns = {name for name, _ in new_columns}
    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            if col_name not in allowed_columns:
                raise ValueError(f"Invalid column name in migration: {col_name}")
            try:
                c.execute(f"ALTER TABLE alerted_token_stats ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                # Column already exists or other benign race condition
                pass

    conn.commit()
    # Idempotent schema version table and basic migrations (example)
    try:
        c.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.commit()
    except Exception:
        pass
    # Example migration sequence (extend as needed)
    def _get_schema_version() -> int:
        try:
            row = c.execute("SELECT MAX(version) FROM schema_version").fetchone()
            return int(row[0] or 0)
        except Exception:
            return 0
    current_version = _get_schema_version()
    migrations: List[tuple[int, str]] = []  # no-op placeholder; add future migrations here
    for version, sql in migrations:
        if version <= current_version:
            continue
        try:
            c.execute(sql)
            c.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    conn.close()

    # SECOND: Run migrations (now that base tables exist)
    try:
        from app.migrations import get_signals_migrations
        runner = get_signals_migrations()
        current_version, applied = runner.run()
        if applied > 0:
            print(f"Applied {applied} database migration(s). Current version: {current_version}")
    except Exception as e:
        print(f"Warning: Migration system error: {e}")
        import traceback
        traceback.print_exc()


def has_been_alerted(token_address: str) -> bool:
    """
    Check if a token has been alerted before.
    
    Uses in-memory cache to avoid repeated database queries.
    
    Args:
        token_address: Token address to check
        
    Returns:
        True if token has been alerted, False otherwise
    """
    # Check cache first (fast path)
    cache = get_alert_cache()
    if cache.contains(token_address):
        return True
    
    # Cache miss - check database
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM alerted_tokens WHERE token_address = ? LIMIT 1", (token_address,))
    row = c.fetchone()
    conn.close()
    
    # If found in DB, add to cache for next time
    if row is not None:
        cache.add(token_address)
        return True
    
    return False


def mark_alerted(token_address: str, final_score: int, smart_money_detected: bool, conviction_type: str) -> None:
    """
    Mark a token as alerted.
    
    Also updates the cache for subsequent lookups.
    """
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO alerted_tokens (token_address, final_score, smart_money_detected, conviction_type)
        VALUES (?, ?, ?, ?)
    """, (token_address, final_score, smart_money_detected, conviction_type))
    conn.commit()
    conn.close()
    
    # Update cache
    get_alert_cache().add(token_address)


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
    
    # Extract all relevant data with fallback to root level
    # Some APIs return nested structure (stats['price']['price_usd'])
    # Others return flat structure (stats['price_usd'])
    price_data = stats.get('price', stats)  # Fallback to root stats if no 'price' key
    market_data = stats.get('market', stats)  # Fallback to root stats
    security_data = stats.get('security', {})
    liquidity_data = stats.get('liquidity', stats)  # Fallback to root stats
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
    
    # Extract initial holder count for growth tracking
    initial_holder_count = holders_data.get('holder_count') or holders_data.get('holders')
    
    c.execute("""
        INSERT OR REPLACE INTO alerted_token_stats (
            token_address, first_alert_at, last_checked_at,
            preliminary_score, final_score, conviction_type,
            first_price_usd, first_market_cap_usd, first_liquidity_usd,
            last_price_usd, last_market_cap_usd, last_liquidity_usd,
            last_volume_24h_usd,
            token_name, token_symbol, token_age_minutes,
            holder_count, initial_holder_count, unique_traders_15m,
            smart_money_involved, smart_wallet_address, smart_wallet_pnl,
            velocity_score_15m, velocity_bonus,
            passed_junior_strict, passed_senior_strict, passed_debate,
            lp_locked, mint_revoked,
            top10_concentration, bundlers_percent, insiders_percent,
            sol_price_usd, feed_source, dex_name,
            price_change_1h, price_change_24h
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        token_address,
        now,
        now,
        preliminary_score,
        final_score,
        conviction_type,
        price_data.get('price_usd'),
        _select_valid_number(market_data.get('market_cap_usd'), stats.get('market_cap_usd')),
        _select_valid_number(liquidity_data.get('liquidity_usd'), stats.get('liquidity_usd')),
        price_data.get('price_usd'),
        _select_valid_number(market_data.get('market_cap_usd'), stats.get('market_cap_usd')),
        _select_valid_number(liquidity_data.get('liquidity_usd'), stats.get('liquidity_usd')),
        (market_data.get('volume', {}) or {}).get('24h_usd') or market_data.get('volume_24h_usd') or stats.get('volume', {}).get('24h', {}).get('volume_usd'),
        metadata.get('name') or stats.get('name'),
        metadata.get('symbol') or stats.get('symbol'),
        alert_metadata.get('token_age_minutes'),
        initial_holder_count,
        initial_holder_count,  # Store as initial_holder_count for growth tracking
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
    # Fallback to root stats if nested structure doesn't exist
    price_data = stats.get('price', stats)
    market_data = stats.get('market', stats)
    liquidity_data = stats.get('liquidity', stats)
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
        _select_valid_number(market_data.get('market_cap_usd'), None),
        _select_valid_number(liquidity_data.get('liquidity_usd'), None),
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
    # Fallback to root stats if nested structure doesn't exist
    price_data = stats.get('price', stats)
    market_data = stats.get('market', stats)
    liquidity_data = stats.get('liquidity', stats)
    
    # Get first price to calculate gains/losses
    c.execute("SELECT first_price_usd, peak_price_usd FROM alerted_token_stats WHERE token_address = ?", (token_address,))
    row = c.fetchone()
    
    if row:
        first_price = row[0] or 0
        current_peak = row[1] or 0
        current_price = price_data.get('price_usd', 0)
        
        # FIX: If first_price is missing, set it now (critical for ML training)
        if first_price == 0 and current_price > 0:
            first_price = current_price
            # Also set first_market_cap and first_liquidity
            c.execute("""
                UPDATE alerted_token_stats SET
                    first_price_usd = ?,
                    first_market_cap_usd = ?,
                    first_liquidity_usd = ?
                WHERE token_address = ? AND first_price_usd IS NULL
            """, (
                current_price,
                _select_valid_number(market_data.get('market_cap_usd'), None),
                _select_valid_number(liquidity_data.get('liquidity_usd'), None),
                token_address
            ))
        
        # Calculate performance metrics
        if first_price > 0:
            gain_percent = ((current_price - first_price) / first_price) * 100
            max_gain = max(gain_percent, ((current_peak - first_price) / first_price) * 100) if current_peak else gain_percent
            max_drawdown = min(0, gain_percent)  # Track worst drop from entry
        else:
            # FIX: Even if first_price is 0, we should still set max_gain to 0 (not NULL)
            # This ensures tokens have outcome data for ML training
            gain_percent = 0.0
            max_gain = 0.0
            max_drawdown = 0.0
        
        # Update peak if current price is higher
        new_peak_price = max(current_peak, current_price) if current_peak else current_price
        peak_price_at = now if new_peak_price > (current_peak or 0) else None
        
        # REALISTIC RETURNS: Calculate trailing stop exit
        # Get current trailing stop settings
        c.execute("SELECT realistic_exit_price, trailing_stop_pct, would_have_exited_at FROM alerted_token_stats WHERE token_address = ?", (token_address,))
        trailing_data = c.fetchone()
        
        realistic_exit_price = trailing_data[0] if trailing_data else None
        trailing_stop_pct = trailing_data[1] if trailing_data else 15.0  # Default 15% trailing stop
        already_exited_at = trailing_data[2] if trailing_data else None
        
        # If we haven't exited yet, check if trailing stop hit
        if not already_exited_at and new_peak_price and first_price > 0:
            # Calculate trailing stop level (e.g., 15% below peak)
            trailing_stop_price = new_peak_price * (1 - trailing_stop_pct / 100.0)
            
            # Check if current price dropped below trailing stop
            if current_peak and current_price < trailing_stop_price and new_peak_price > first_price * 1.10:
                # We would have exited here! Lock in the realistic exit
                realistic_exit_price = trailing_stop_price
                already_exited_at = now
        
        # Calculate realistic gain (what you'd actually get with trailing stop)
        realistic_gain_percent = None
        if first_price > 0:
            if already_exited_at and realistic_exit_price:
                # Already exited with trailing stop
                realistic_gain_percent = ((realistic_exit_price - first_price) / first_price) * 100
            elif new_peak_price > first_price * 1.10:  # Only track if >10% gain (to avoid false positives)
                # Still holding, show what we'd get if we exit at trailing stop now
                current_trailing_stop = new_peak_price * (1 - trailing_stop_pct / 100.0)
                realistic_gain_percent = ((current_trailing_stop - first_price) / first_price) * 100
        
        # DISABLED: Rug detection was marking 1462x winners as rugs
        # The logic had 80% false positive rate on moonshots (373/711 signals marked as rugs)
        # High volatility (80% drops) is NORMAL for 1000x+ tokens during consolidation
        # Real rugs have different patterns (dev dumps, instant liquidity removal)
        # Rug detection disabled; always return False/None
        # Commented out broken logic:
        # if current_peak and current_price < current_peak * 0.2:  # >80% drop from peak
        #     is_rug = True
        #     rug_at = now
        # elif liquidity_data.get('liquidity_usd', float('inf')) < 100:  # Liquidity removed
        #     is_rug = True
        #     rug_at = now
        
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
                price_change_24h = ?,
                realistic_gain_percent = ?,
                trailing_stop_pct = ?
        """
        
        params = [
            now,
            current_price,
            _select_valid_number(market_data.get('market_cap_usd'), None),
            _select_valid_number(liquidity_data.get('liquidity_usd'), None),
            market_data.get('volume_24h_usd'),
            new_peak_price,
            max_gain,
            max_drawdown,
            change_1h,
            change_6h,
            change_24h,
            realistic_gain_percent,
            trailing_stop_pct,
        ]
        
        if peak_price_at:
            update_sql += ", peak_price_at = ?"
            params.append(peak_price_at)
        
        # Update realistic exit data if trailing stop was hit
        if already_exited_at and realistic_exit_price and not trailing_data[2]:
            update_sql += ", realistic_exit_price = ?, would_have_exited_at = ?"
            params.extend([realistic_exit_price, already_exited_at])
        
        # DISABLED: Rug flag updates (rug detection disabled)
        # This was marking winners as rugs and preventing tracking
        # if is_rug:
        #     update_sql += ", is_rug = CASE WHEN (is_rug IS NULL OR is_rug = 0) THEN 1 ELSE is_rug END"
        #     if rug_at:
        #         update_sql += ", rug_detected_at = COALESCE(rug_detected_at, ?)"
        #         params.extend([rug_at])
        
        update_sql += " WHERE token_address = ?"
        params.append(token_address)
        
        c.execute(update_sql, params)
    
    conn.commit()
    conn.close()


def get_alerted_tokens_for_tracking() -> List[str]:
    """Get list of tokens that need performance tracking"""
    conn = _get_conn()
    c = conn.cursor()
    
    # Get tokens alerted in last 24 hours (reduced from 48h to save API credits)
    one_day_ago = (datetime.now() - timedelta(hours=24)).timestamp()

    # Query from alerted_tokens (primary table) and LEFT JOIN with stats
    # This ensures we track ALL alerted tokens, even those without stats records yet
    # FIX: Use timestamp comparison, not datetime() function (alerted_at is Unix timestamp)
    # REMOVED RUG FILTER: Was excluding 373 signals including top winners (1462x, 298x, 43x)
    c.execute("""
        SELECT a.token_address, a.alerted_at, a.final_score, a.conviction_type
        FROM alerted_tokens a
        LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
        WHERE a.alerted_at >= ?
        ORDER BY a.alerted_at DESC
    """, (one_day_ago,))
    
    rows = c.fetchall()
    
    # Create stats records for tokens that don't have them yet
    for token_address, alerted_at, final_score, conviction_type in rows:
        c.execute("SELECT token_address FROM alerted_token_stats WHERE token_address = ?", (token_address,))
        if not c.fetchone():
            # Create initial stats record for orphaned token
            alerted_timestamp = datetime.fromisoformat(alerted_at.replace(' ', 'T')).timestamp() if isinstance(alerted_at, str) else float(alerted_at)
            c.execute("""
                INSERT INTO alerted_token_stats (
                    token_address, first_alert_at, last_checked_at, final_score, conviction_type
                ) VALUES (?, ?, ?, ?, ?)
            """, (token_address, alerted_timestamp, alerted_timestamp, final_score, conviction_type))
    
    conn.commit()
    
    tokens = [row[0] for row in rows]
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


def record_transaction_snapshot(
    token_address: str,
    tx_signature: str,
    timestamp: float,
    from_wallet: Optional[str] = None,
    to_wallet: Optional[str] = None,
    amount: Optional[float] = None,
    amount_usd: Optional[float] = None,
    tx_type: Optional[str] = None,
    dex: Optional[str] = None,
    is_smart_money: bool = False
) -> None:
    """
    Record a transaction snapshot for tracking token activity.
    
    Args:
        token_address: Token contract address
        tx_signature: Solana transaction signature
        timestamp: Unix timestamp of transaction
        from_wallet: Sender wallet address
        to_wallet: Receiver wallet address
        amount: Token amount transacted
        amount_usd: USD value of transaction
        tx_type: Type of transaction (buy, sell, swap, etc.)
        dex: DEX name where transaction occurred
        is_smart_money: Whether wallet is identified as smart money
    """
    conn = _get_conn()
    c = conn.cursor()
    
    try:
        c.execute("""
            INSERT OR IGNORE INTO transaction_snapshots (
                token_address, tx_signature, timestamp, from_wallet, to_wallet,
                amount, amount_usd, tx_type, dex, is_smart_money
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            token_address, tx_signature, timestamp, from_wallet, to_wallet,
            amount, amount_usd, tx_type, dex, is_smart_money
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        # Log but don't crash
        try:
            from app.logger_utils import log_process
            log_process({"type": "tx_snapshot_error", "error": str(e), "token": token_address})
        except Exception:
            pass
    finally:
        conn.close()


def record_wallet_first_buy(
    token_address: str,
    wallet_address: str,
    timestamp: float,
    amount: Optional[float] = None,
    amount_usd: Optional[float] = None,
    price_usd: Optional[float] = None,
    is_smart_money: bool = False,
    wallet_pnl_history: Optional[float] = None
) -> None:
    """
    Record first buy from a wallet for a token.
    
    Args:
        token_address: Token contract address
        wallet_address: Buyer wallet address
        timestamp: Unix timestamp of first buy
        amount: Token amount purchased
        amount_usd: USD value of purchase
        price_usd: Price per token in USD
        is_smart_money: Whether wallet is identified as smart money
        wallet_pnl_history: Historical PnL of wallet (if known)
    """
    conn = _get_conn()
    c = conn.cursor()
    
    try:
        c.execute("""
            INSERT OR IGNORE INTO wallet_first_buys (
                token_address, wallet_address, timestamp, amount, amount_usd,
                price_usd, is_smart_money, wallet_pnl_history
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            token_address, wallet_address, timestamp, amount, amount_usd,
            price_usd, is_smart_money, wallet_pnl_history
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        # Log but don't crash
        try:
            from app.logger_utils import log_process
            log_process({"type": "wallet_buy_error", "error": str(e), "token": token_address})
        except Exception:
            pass
    finally:
        conn.close()


def get_token_comprehensive_data(token_address: str) -> Dict[str, Any]:
    """
    Get all comprehensive tracking data for a token.
    
    Returns:
        Dictionary with all tracking data including:
        - ca: Contract address
        - first_seen_ts: First seen timestamp
        - liquidity_snapshots: Time series of liquidity
        - tx_snapshots: Transaction history
        - wallet_first_buys: First N wallet buyers
        - price_time_series: Price at key intervals
        - holders_count_ts: Holder counts over time
        - token_meta: Token metadata
        - outcome_label: Final outcome classification
    """
    conn = _get_conn()
    c = conn.cursor()
    
    # Get basic token info
    c.execute("""
        SELECT 
            a.token_address, a.alerted_at, a.final_score, a.smart_money_detected, a.conviction_type,
            s.token_name, s.token_symbol, s.first_price_usd, s.peak_price_usd, s.last_price_usd,
            s.first_market_cap_usd, s.peak_market_cap_usd, s.last_market_cap_usd,
            s.first_liquidity_usd, s.last_liquidity_usd, s.last_volume_24h_usd,
            s.max_gain_percent, s.is_rug, s.holder_count, s.peak_price_at
        FROM alerted_tokens a
        LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
        WHERE a.token_address = ?
    """, (token_address,))
    
    row = c.fetchone()
    if not row:
        conn.close()
        return {}
    
    # Parse basic data
    data = {
        "ca": row[0],
        "first_seen_ts": row[1],
        "final_score": row[2],
        "smart_money_detected": bool(row[3]),
        "conviction_type": row[4],
        "token_meta": {
            "name": row[5],
            "symbol": row[6],
            "decimals": None,  # Not tracked yet
            "total_supply": None  # Not tracked yet
        }
    }
    
    # Get price time series (at specific intervals)
    c.execute("""
        SELECT snapshot_at, price_usd
        FROM price_snapshots
        WHERE token_address = ?
        ORDER BY snapshot_at
    """, (token_address,))
    
    snapshots = c.fetchall()
    first_ts = row[1]  # alerted_at
    
    # Create time series at key intervals: t0, +1m, +5m, +15m, +1h, +24h
    price_time_series = {
        "t0": row[7],  # first_price_usd
        "t_1m": None,
        "t_5m": None,
        "t_15m": None,
        "t_1h": None,
        "t_24h": None,
        "t_peak": row[8],  # peak_price_usd
        "t_latest": row[9],  # last_price_usd
    }
    
    if first_ts and snapshots:
        try:
            first_timestamp = float(first_ts) if isinstance(first_ts, (int, float)) else datetime.fromisoformat(first_ts).timestamp()
            
            for snap_ts, price in snapshots:
                elapsed = snap_ts - first_timestamp
                if elapsed >= 60 and price_time_series["t_1m"] is None:
                    price_time_series["t_1m"] = price
                if elapsed >= 300 and price_time_series["t_5m"] is None:
                    price_time_series["t_5m"] = price
                if elapsed >= 900 and price_time_series["t_15m"] is None:
                    price_time_series["t_15m"] = price
                if elapsed >= 3600 and price_time_series["t_1h"] is None:
                    price_time_series["t_1h"] = price
                if elapsed >= 86400 and price_time_series["t_24h"] is None:
                    price_time_series["t_24h"] = price
        except Exception:
            pass
    
    data["price_time_series"] = price_time_series
    
    # Get liquidity snapshots
    c.execute("""
        SELECT snapshot_at, liquidity_usd
        FROM price_snapshots
        WHERE token_address = ? AND liquidity_usd IS NOT NULL
        ORDER BY snapshot_at
    """, (token_address,))
    
    data["liquidity_snapshots"] = [
        {"ts": snap[0], "liquidity_sol": snap[1] / 150.0 if snap[1] else None}  # Rough conversion
        for snap in c.fetchall()
    ]
    
    # Get holder count time series
    c.execute("""
        SELECT snapshot_at, holder_count
        FROM price_snapshots
        WHERE token_address = ? AND holder_count IS NOT NULL
        ORDER BY snapshot_at
    """, (token_address,))
    
    data["holders_count_ts"] = [
        {"ts": snap[0], "holders": snap[1]}
        for snap in c.fetchall()
    ]
    
    # Get transaction snapshots
    c.execute("""
        SELECT 
            tx_signature, timestamp, from_wallet, to_wallet, amount, 
            amount_usd, tx_type, dex, is_smart_money
        FROM transaction_snapshots
        WHERE token_address = ?
        ORDER BY timestamp
        LIMIT 500
    """, (token_address,))
    
    data["tx_snapshots"] = [
        {
            "signature": tx[0],
            "ts": tx[1],
            "from_wallet": tx[2],
            "to_wallet": tx[3],
            "amount": tx[4],
            "amount_usd": tx[5],
            "tx_type": tx[6],
            "dex": tx[7],
            "is_smart_money": bool(tx[8])
        }
        for tx in c.fetchall()
    ]
    
    # Get wallet first buys (top N by amount)
    c.execute("""
        SELECT 
            wallet_address, timestamp, amount, amount_usd, price_usd,
            is_smart_money, wallet_pnl_history
        FROM wallet_first_buys
        WHERE token_address = ?
        ORDER BY amount_usd DESC NULLS LAST, timestamp ASC
        LIMIT 50
    """, (token_address,))
    
    data["wallet_first_buys"] = [
        {
            "wallet": buy[0],
            "ts": buy[1],
            "amount": buy[2],
            "amount_usd": buy[3],
            "price_usd": buy[4],
            "is_smart_money": bool(buy[5]),
            "wallet_pnl_history": buy[6]
        }
        for buy in c.fetchall()
    ]
    
    # Compute outcome label
    max_gain = row[16]  # max_gain_percent
    is_rug = row[17]
    
    if is_rug:
        outcome = "rug"
    elif max_gain is None:
        outcome = "pending"
    elif max_gain >= 900:
        outcome = "moonshot_10x+"
    elif max_gain >= 400:
        outcome = "strong_5x+"
    elif max_gain >= 100:
        outcome = "good_2x+"
    elif max_gain >= 50:
        outcome = "moderate_1.5x+"
    elif max_gain >= 0:
        outcome = "breakeven"
    else:
        outcome = "loss"
    
    data["outcome_label"] = outcome
    data["max_gain_percent"] = max_gain
    
    conn.close()
    return data


def get_all_tracked_tokens_summary(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get summary of all tracked tokens for display on website.
    
    Returns list of dictionaries with key metrics for each token.
    """
    conn = _get_conn()
    c = conn.cursor()
    
    c.execute("""
        SELECT 
            a.token_address, a.alerted_at, a.final_score, a.conviction_type,
            s.token_name, s.token_symbol, s.first_price_usd, s.peak_price_usd, 
            s.last_price_usd, s.max_gain_percent, s.is_rug,
            s.first_liquidity_usd, s.last_liquidity_usd, s.last_volume_24h_usd,
            (SELECT COUNT(*) FROM transaction_snapshots WHERE token_address = a.token_address) as tx_count,
            (SELECT COUNT(*) FROM wallet_first_buys WHERE token_address = a.token_address) as buyer_count
        FROM alerted_tokens a
        LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
        ORDER BY a.alerted_at DESC
        LIMIT ?
    """, (limit,))
    
    tokens = []
    for row in c.fetchall():
        max_gain = row[9]
        is_rug = row[10]
        
        if is_rug:
            outcome = "rug"
        elif max_gain is None:
            outcome = "tracking"
        elif max_gain >= 100:
            outcome = "2x+"
        elif max_gain >= 0:
            outcome = "positive"
        else:
            outcome = "negative"
        
        tokens.append({
            "ca": row[0],
            "alerted_at": row[1],
            "score": row[2],
            "conviction": row[3],
            "name": row[4],
            "symbol": row[5],
            "entry_price": row[6],
            "peak_price": row[7],
            "current_price": row[8],
            "max_gain_pct": max_gain,
            "outcome": outcome,
            "liquidity": row[12],
            "volume_24h": row[13],
            "tx_count": row[14],
            "buyer_count": row[15]
        })
    
    conn.close()
    return tokens