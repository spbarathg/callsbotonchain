"""
Repository Pattern Implementation

Splits storage.py into focused, single-responsibility repositories.
Each repository handles a specific domain concern.
"""
import sqlite3
import os
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from contextlib import contextmanager


# ============================================================================
# DATABASE CONNECTION MANAGEMENT
# ============================================================================

class DatabaseConnection:
    """Manages SQLite database connections with proper configuration"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    
    @contextmanager
    def get_connection(self):
        """Get a configured SQLite connection"""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        
        # Performance optimizations
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        conn.execute("PRAGMA busy_timeout=10000")
        
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# ============================================================================
# ALERT REPOSITORY
# ============================================================================

class AlertRepository:
    """Manages alerted tokens and their metadata"""
    
    def __init__(self, db_conn: DatabaseConnection):
        self.db = db_conn
        self._alerted_cache = set()
        self._cache_initialized = False
    
    def has_been_alerted(self, token_address: str) -> bool:
        """
        Check if a token has been alerted before.
        Uses in-memory cache for performance.
        """
        if not self._cache_initialized:
            self._load_cache()
        
        if token_address in self._alerted_cache:
            return True
        
        # Double-check database
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM alerted_tokens WHERE token_address = ? LIMIT 1",
                (token_address,)
            )
            row = cursor.fetchone()
            if row:
                self._alerted_cache.add(token_address)
                return True
        
        return False
    
    def mark_alerted(
        self,
        token_address: str,
        score: int,
        smart_money_detected: bool,
        conviction_type: str
    ) -> None:
        """Mark a token as alerted"""
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO alerted_tokens 
                (token_address, alerted_at, score, smart_money_detected, conviction_type)
                VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?)
                """,
                (token_address, score, smart_money_detected, conviction_type)
            )
        
        self._alerted_cache.add(token_address)
    
    def record_alert_with_metadata(
        self,
        token_address: str,
        preliminary_score: int,
        final_score: int,
        conviction_type: str,
        stats: Dict[str, Any],
        alert_metadata: Dict[str, Any]
    ) -> None:
        """Record comprehensive alert metadata for analysis"""
        with self.db.get_connection() as conn:
            # Extract stats
            price = self._safe_float(stats.get("price_usd"))
            market_cap = self._safe_float(stats.get("market_cap_usd"))
            liquidity = self._safe_float(stats.get("liquidity_usd"))
            volume_24h = self._safe_float(stats.get("volume_24h_usd"))
            change_1h = self._safe_float(stats.get("change_1h"))
            change_24h = self._safe_float(stats.get("change_24h"))
            
            security = stats.get("security", {}) or {}
            holders = stats.get("holders", {}) or {}
            
            # Insert into alerted_tokens table
            smart_money = alert_metadata.get("smart_money_involved", 0)
            conn.execute(
                """
                INSERT OR IGNORE INTO alerted_tokens 
                (token_address, alerted_at, score, smart_money_detected, conviction_type)
                VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?)
                """,
                (token_address, final_score, smart_money, conviction_type)
            )
            
            # Also update cache
            self._alerted_cache.add(token_address)
            
            # Insert into alerted_token_stats
            conn.execute(
                """
                INSERT OR REPLACE INTO alerted_token_stats (
                    token_address,
                    name,
                    symbol,
                    preliminary_score,
                    final_score,
                    conviction_type,
                    price_at_alert,
                    market_cap_at_alert,
                    liquidity_at_alert,
                    volume_24h_at_alert,
                    change_1h_at_alert,
                    change_24h_at_alert,
                    is_mint_revoked,
                    is_lp_locked,
                    top_10_concentration,
                    holder_count,
                    token_age_minutes,
                    unique_traders_15m,
                    smart_money_involved,
                    smart_wallet_address,
                    smart_wallet_pnl,
                    velocity_score_15m,
                    velocity_bonus,
                    passed_junior_strict,
                    passed_senior_strict,
                    passed_debate,
                    sol_price_usd,
                    feed_source,
                    dex_name,
                    alerted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    token_address,
                    stats.get("name"),
                    stats.get("symbol"),
                    preliminary_score,
                    final_score,
                    conviction_type,
                    price,
                    market_cap,
                    liquidity,
                    volume_24h,
                    change_1h,
                    change_24h,
                    security.get("is_mint_revoked"),
                    security.get("is_lp_locked"),
                    self._safe_float(holders.get("top_10_concentration_percent")),
                    holders.get("holder_count"),
                    alert_metadata.get("token_age_minutes"),
                    alert_metadata.get("unique_traders_15m"),
                    alert_metadata.get("smart_money_involved"),
                    alert_metadata.get("smart_wallet_address"),
                    self._safe_float(alert_metadata.get("smart_wallet_pnl")),
                    self._safe_float(alert_metadata.get("velocity_score_15m")),
                    alert_metadata.get("velocity_bonus", 0),
                    alert_metadata.get("passed_junior_strict"),
                    alert_metadata.get("passed_senior_strict"),
                    alert_metadata.get("passed_debate"),
                    self._safe_float(alert_metadata.get("sol_price_usd")),
                    alert_metadata.get("feed_source"),
                    alert_metadata.get("dex_name"),
                )
            )
    
    def get_alerted_tokens_for_tracking(
        self,
        limit: int = 100,
        hours_back: int = 168
    ) -> List[Tuple[str, str]]:
        """Get recently alerted tokens that need tracking"""
        cutoff = datetime.now() - timedelta(hours=hours_back)
        
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT token_address, alerted_at
                FROM alerted_tokens
                WHERE alerted_at >= ?
                ORDER BY alerted_at DESC
                LIMIT ?
                """,
                (cutoff.isoformat(), limit)
            )
            return [(row[0], row[1]) for row in cursor.fetchall()]
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get aggregate performance statistics"""
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    AVG(max_gain_pct) as avg_max_gain,
                    AVG(current_pnl_pct) as avg_current_pnl,
                    SUM(CASE WHEN max_gain_pct >= 50 THEN 1 ELSE 0 END) as pumped_50_pct,
                    SUM(CASE WHEN max_gain_pct >= 100 THEN 1 ELSE 0 END) as pumped_100_pct,
                    SUM(CASE WHEN is_rug = 1 THEN 1 ELSE 0 END) as rugs
                FROM alerted_token_stats
                WHERE alerted_at >= datetime('now', '-7 days')
                """
            )
            row = cursor.fetchone()
            if not row:
                return {}
            
            return {
                "total_alerts": row[0] or 0,
                "avg_max_gain_pct": row[1] or 0,
                "avg_current_pnl_pct": row[2] or 0,
                "pumped_50_pct_count": row[3] or 0,
                "pumped_100_pct_count": row[4] or 0,
                "rug_count": row[5] or 0,
            }
    
    def _load_cache(self):
        """Load alerted tokens into memory cache"""
        with self.db.get_connection() as conn:
            cursor = conn.execute("SELECT token_address FROM alerted_tokens")
            self._alerted_cache = {row[0] for row in cursor.fetchall()}
        self._cache_initialized = True
    
    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        """Safely convert to float, filtering NaN/Infinity"""
        import math
        try:
            f = float(value)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        except (ValueError, TypeError):
            return None


# ============================================================================
# PERFORMANCE REPOSITORY
# ============================================================================

class PerformanceRepository:
    """Manages token performance tracking and price snapshots"""
    
    def __init__(self, db_conn: DatabaseConnection):
        self.db = db_conn
    
    def record_price_snapshot(
        self,
        token_address: str,
        price: float,
        market_cap: Optional[float] = None,
        liquidity: Optional[float] = None,
        volume_24h: Optional[float] = None
    ) -> None:
        """Record a price snapshot for a token"""
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO price_snapshots 
                (token_address, snapshot_at, price, market_cap, liquidity, volume_24h)
                VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
                """,
                (token_address, price, market_cap, liquidity, volume_24h)
            )
    
    def update_token_performance(
        self,
        token_address: str,
        current_price: float,
        market_cap: Optional[float] = None,
        liquidity: Optional[float] = None
    ) -> None:
        """Update performance metrics for a token"""
        with self.db.get_connection() as conn:
            # Get entry price
            cursor = conn.execute(
                "SELECT price_at_alert FROM alerted_token_stats WHERE token_address = ?",
                (token_address,)
            )
            row = cursor.fetchone()
            if not row or not row[0]:
                return
            
            entry_price = float(row[0])
            if entry_price <= 0:
                return
            
            # Calculate metrics
            current_pnl_pct = ((current_price - entry_price) / entry_price) * 100
            
            # Get historical peak
            cursor = conn.execute(
                "SELECT max_gain_pct FROM alerted_token_stats WHERE token_address = ?",
                (token_address,)
            )
            row = cursor.fetchone()
            max_gain_pct = row[0] if row else 0.0
            max_gain_pct = max(max_gain_pct or 0, current_pnl_pct)
            
            # Calculate drawdown
            max_drawdown_pct = 0.0
            if max_gain_pct > 0:
                max_drawdown_pct = max_gain_pct - current_pnl_pct
            
            # Rug detection
            is_rug = False
            if liquidity and liquidity < 1000:  # Liquidity pulled
                is_rug = True
            if current_pnl_pct < -80:  # Price collapsed
                is_rug = True
            
            # Update stats
            conn.execute(
                """
                UPDATE alerted_token_stats
                SET 
                    current_price = ?,
                    current_pnl_pct = ?,
                    max_gain_pct = ?,
                    max_drawdown_pct = ?,
                    current_market_cap = ?,
                    current_liquidity = ?,
                    is_rug = ?,
                    last_updated_at = CURRENT_TIMESTAMP
                WHERE token_address = ?
                """,
                (
                    current_price,
                    current_pnl_pct,
                    max_gain_pct,
                    max_drawdown_pct,
                    market_cap,
                    liquidity,
                    is_rug,
                    token_address
                )
            )
    
    def get_tracking_snapshot(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Get the current tracking snapshot for a token"""
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT 
                    token_address,
                    name,
                    symbol,
                    price_at_alert,
                    current_price,
                    current_pnl_pct,
                    max_gain_pct,
                    max_drawdown_pct,
                    is_rug,
                    alerted_at,
                    last_updated_at
                FROM alerted_token_stats
                WHERE token_address = ?
                """,
                (token_address,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            
            return {
                "token_address": row[0],
                "name": row[1],
                "symbol": row[2],
                "entry_price": row[3],
                "current_price": row[4],
                "current_pnl_pct": row[5],
                "max_gain_pct": row[6],
                "max_drawdown_pct": row[7],
                "is_rug": bool(row[8]),
                "alerted_at": row[9],
                "last_updated": row[10],
            }


# ============================================================================
# ACTIVITY REPOSITORY
# ============================================================================

class ActivityRepository:
    """Manages token activity for velocity detection"""
    
    def __init__(self, db_conn: DatabaseConnection):
        self.db = db_conn
    
    def record_token_activity(
        self,
        token_address: str,
        usd_value: float,
        tx_count: int,
        smart_money: bool,
        preliminary_score: int,
        trader: Optional[str] = None
    ) -> None:
        """Record token activity for velocity tracking"""
        from datetime import datetime
        
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO token_activity 
                (token_address, observed_at, usd_value, tx_count, smart_money, preliminary_score, trader)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (token_address, datetime.utcnow().isoformat(), usd_value, tx_count, smart_money, preliminary_score, trader)
            )
    
    def get_recent_token_signals(
        self,
        token_address: str,
        window_seconds: int
    ) -> List[str]:
        """Get recent activity timestamps for a token"""
        cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
        
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT observed_at
                FROM token_activity
                WHERE token_address = ? AND observed_at >= ?
                ORDER BY observed_at DESC
                """,
                (token_address, cutoff.isoformat())
            )
            return [row[0] for row in cursor.fetchall()]
    
    def cleanup_old_activity(self, days_back: int = 7) -> None:
        """Remove old activity records"""
        cutoff = datetime.utcnow() - timedelta(days=days_back)
        
        with self.db.get_connection() as conn:
            conn.execute(
                "DELETE FROM token_activity WHERE observed_at < ?",
                (cutoff.isoformat(),)
            )


# ============================================================================
# SCHEMA INITIALIZATION
# ============================================================================

def initialize_schema(db_conn: DatabaseConnection) -> None:
    """Initialize database schema"""
    with db_conn.get_connection() as conn:
        # Alerted tokens table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alerted_tokens (
                token_address TEXT PRIMARY KEY,
                alerted_at TEXT NOT NULL,
                score INTEGER NOT NULL,
                smart_money_detected INTEGER DEFAULT 0,
                conviction_type TEXT
            )
            """
        )
        
        # Comprehensive alert stats
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alerted_token_stats (
                token_address TEXT PRIMARY KEY,
                name TEXT,
                symbol TEXT,
                preliminary_score INTEGER,
                final_score INTEGER,
                conviction_type TEXT,
                price_at_alert REAL,
                market_cap_at_alert REAL,
                liquidity_at_alert REAL,
                volume_24h_at_alert REAL,
                change_1h_at_alert REAL,
                change_24h_at_alert REAL,
                is_mint_revoked INTEGER,
                is_lp_locked INTEGER,
                top_10_concentration REAL,
                holder_count INTEGER,
                token_age_minutes REAL,
                unique_traders_15m INTEGER,
                smart_money_involved INTEGER,
                smart_wallet_address TEXT,
                smart_wallet_pnl REAL,
                velocity_score_15m REAL,
                velocity_bonus INTEGER,
                passed_junior_strict INTEGER,
                passed_senior_strict INTEGER,
                passed_debate INTEGER,
                sol_price_usd REAL,
                feed_source TEXT,
                dex_name TEXT,
                alerted_at TEXT NOT NULL,
                current_price REAL,
                current_pnl_pct REAL,
                max_gain_pct REAL DEFAULT 0,
                max_drawdown_pct REAL DEFAULT 0,
                current_market_cap REAL,
                current_liquidity REAL,
                is_rug INTEGER DEFAULT 0,
                last_updated_at TEXT
            )
            """
        )
        
        # Activity table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS token_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_address TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                usd_value REAL,
                tx_count INTEGER DEFAULT 1,
                smart_money INTEGER DEFAULT 0,
                preliminary_score INTEGER,
                trader TEXT
            )
            """
        )
        
        # Price snapshots
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_address TEXT NOT NULL,
                snapshot_at TEXT NOT NULL,
                price REAL NOT NULL,
                market_cap REAL,
                liquidity REAL,
                volume_24h REAL
            )
            """
        )
        
        # Indices
        conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_token_time ON token_activity(token_address, observed_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_token ON price_snapshots(token_address, snapshot_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stats_alerted_at ON alerted_token_stats(alerted_at)")


# ============================================================================
# REPOSITORY FACTORY
# ============================================================================

class RepositoryFactory:
    """Factory for creating repository instances"""
    
    def __init__(self, db_path: str = "var/admin.db"):
        self.db_conn = DatabaseConnection(db_path)
        initialize_schema(self.db_conn)
    
    def create_alert_repository(self) -> AlertRepository:
        return AlertRepository(self.db_conn)
    
    def create_performance_repository(self) -> PerformanceRepository:
        return PerformanceRepository(self.db_conn)
    
    def create_activity_repository(self) -> ActivityRepository:
        return ActivityRepository(self.db_conn)


# Singleton factory
_factory: Optional[RepositoryFactory] = None


def get_repository_factory(db_path: Optional[str] = None) -> RepositoryFactory:
    """Get the singleton repository factory"""
    global _factory
    if _factory is None:
        from app.config_unified import STORAGE_DB_FILE
        _factory = RepositoryFactory(db_path or STORAGE_DB_FILE)
    return _factory

