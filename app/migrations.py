"""
Database migration system for the signals database.

Provides a simple, reliable way to evolve the database schema
over time without manual intervention.
"""
import sqlite3
import time
from typing import List, Tuple, Callable


class Migration:
    """Represents a single database migration."""
    
    def __init__(self, version: int, name: str, up: Callable[[sqlite3.Connection], None]):
        """
        Args:
            version: Migration version number (monotonically increasing)
            name: Human-readable migration name
            up: Function to apply the migration (takes connection)
        """
        self.version = version
        self.name = name
        self.up = up
    
    def __repr__(self) -> str:
        return f"Migration({self.version}, {self.name!r})"


class MigrationRunner:
    """Runs database migrations."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._migrations: List[Migration] = []
    
    def register(self, version: int, name: str, up: Callable[[sqlite3.Connection], None]) -> None:
        """
        Register a new migration.
        
        Args:
            version: Migration version (must be unique and sequential)
            name: Migration name
            up: Function to apply the migration
        """
        self._migrations.append(Migration(version, name, up))
    
    def _ensure_migrations_table(self, conn: sqlite3.Connection) -> None:
        """Create migrations tracking table if it doesn't exist."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at REAL NOT NULL
            )
        """)
        conn.commit()
    
    def _get_current_version(self, conn: sqlite3.Connection) -> int:
        """Get the current schema version."""
        try:
            cursor = conn.execute("SELECT MAX(version) FROM schema_migrations")
            result = cursor.fetchone()
            return result[0] if result and result[0] is not None else 0
        except sqlite3.OperationalError:
            # Table doesn't exist yet
            return 0
    
    def _record_migration(self, conn: sqlite3.Connection, migration: Migration) -> None:
        """Record that a migration was applied."""
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (migration.version, migration.name, time.time())
        )
        conn.commit()
    
    def run(self) -> Tuple[int, int]:
        """
        Run all pending migrations.
        
        Returns:
            Tuple of (current_version, applied_count)
        """
        conn = sqlite3.connect(self.db_path, timeout=30)
        
        try:
            self._ensure_migrations_table(conn)
            current_version = self._get_current_version(conn)
            
            # Sort migrations by version
            pending = sorted(
                [m for m in self._migrations if m.version > current_version],
                key=lambda m: m.version
            )
            
            applied_count = 0
            for migration in pending:
                print(f"Applying migration {migration.version}: {migration.name}")
                
                try:
                    # Apply the migration
                    migration.up(conn)
                    
                    # Record it
                    self._record_migration(conn, migration)
                    
                    applied_count += 1
                    print(f"  [OK] Applied migration {migration.version}")
                    
                except Exception as e:
                    print(f"  [FAILED] Migration {migration.version}: {e}")
                    conn.rollback()
                    raise
            
            final_version = self._get_current_version(conn)
            
            return final_version, applied_count
            
        finally:
            conn.close()
    
    def get_status(self) -> dict:
        """
        Get migration status.
        
        Returns:
            Dict with current version, pending migrations, etc.
        """
        conn = sqlite3.connect(self.db_path, timeout=10)
        
        try:
            self._ensure_migrations_table(conn)
            current_version = self._get_current_version(conn)
            
            pending = [m for m in self._migrations if m.version > current_version]
            
            # Get migration history
            cursor = conn.execute(
                "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
            )
            history = [
                {"version": row[0], "name": row[1], "applied_at": row[2]}
                for row in cursor.fetchall()
            ]
            
            return {
                "current_version": current_version,
                "pending_count": len(pending),
                "pending": [{"version": m.version, "name": m.name} for m in pending],
                "history": history,
            }
            
        finally:
            conn.close()


# Define all migrations for the signals database
def get_signals_migrations() -> MigrationRunner:
    """Get migration runner for the signals database."""
    from app.database_config import DatabasePaths
    
    runner = MigrationRunner(DatabasePaths.SIGNALS_DB)
    
    # Migration 1: Add conviction_type column
    def migration_1_add_conviction_type(conn: sqlite3.Connection) -> None:
        """Add conviction_type column to alerted_tokens table."""
        cursor = conn.execute("PRAGMA table_info(alerted_tokens)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "conviction_type" not in columns:
            conn.execute("ALTER TABLE alerted_tokens ADD COLUMN conviction_type TEXT")
            conn.commit()
    
    runner.register(1, "add_conviction_type", migration_1_add_conviction_type)
    
    # Migration 2: Add velocity tracking columns
    def migration_2_add_velocity_columns(conn: sqlite3.Connection) -> None:
        """Add velocity tracking columns to alerted_token_stats table."""
        cursor = conn.execute("PRAGMA table_info(alerted_token_stats)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "velocity_score" not in columns:
            conn.execute("ALTER TABLE alerted_token_stats ADD COLUMN velocity_score REAL")
        
        if "unique_traders_15m" not in columns:
            conn.execute("ALTER TABLE alerted_token_stats ADD COLUMN unique_traders_15m INTEGER")
        
        conn.commit()
    
    runner.register(2, "add_velocity_columns", migration_2_add_velocity_columns)
    
    # Migration 3: Add ML scoring columns
    def migration_3_add_ml_columns(conn: sqlite3.Connection) -> None:
        """Add ML scoring columns to alerted_token_stats table."""
        cursor = conn.execute("PRAGMA table_info(alerted_token_stats)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "ml_enhanced" not in columns:
            conn.execute("ALTER TABLE alerted_token_stats ADD COLUMN ml_enhanced INTEGER DEFAULT 0")
        
        if "ml_predicted_gain" not in columns:
            conn.execute("ALTER TABLE alerted_token_stats ADD COLUMN ml_predicted_gain REAL")
        
        if "ml_winner_probability" not in columns:
            conn.execute("ALTER TABLE alerted_token_stats ADD COLUMN ml_winner_probability REAL")
        
        conn.commit()
    
    runner.register(3, "add_ml_columns", migration_3_add_ml_columns)
    
    # Migration 4: Add comprehensive transaction and wallet tracking
    def migration_4_add_tx_tracking(conn: sqlite3.Connection) -> None:
        """Add transaction snapshots and wallet first buys tracking."""
        # Transaction snapshots table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transaction_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_address TEXT NOT NULL,
                tx_signature TEXT NOT NULL,
                timestamp REAL NOT NULL,
                from_wallet TEXT,
                to_wallet TEXT,
                amount REAL,
                amount_usd REAL,
                tx_type TEXT,
                dex TEXT,
                is_smart_money BOOLEAN DEFAULT 0,
                FOREIGN KEY (token_address) REFERENCES alerted_tokens(token_address)
            )
        """)
        
        # Create indexes for fast queries
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tx_snapshots_token 
            ON transaction_snapshots(token_address)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tx_snapshots_timestamp 
            ON transaction_snapshots(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tx_snapshots_signature 
            ON transaction_snapshots(tx_signature)
        """)
        
        # Wallet first buys table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wallet_first_buys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_address TEXT NOT NULL,
                wallet_address TEXT NOT NULL,
                timestamp REAL NOT NULL,
                amount REAL,
                amount_usd REAL,
                price_usd REAL,
                is_smart_money BOOLEAN DEFAULT 0,
                wallet_pnl_history REAL,
                UNIQUE(token_address, wallet_address),
                FOREIGN KEY (token_address) REFERENCES alerted_tokens(token_address)
            )
        """)
        
        # Create indexes
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_wallet_buys_token 
            ON wallet_first_buys(token_address)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_wallet_buys_timestamp 
            ON wallet_first_buys(timestamp)
        """)
        
        # Add time-series indexes to price_snapshots for better querying
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_snapshots_token_time 
            ON price_snapshots(token_address, snapshot_at)
        """)
        
        conn.commit()
    
    runner.register(4, "add_transaction_wallet_tracking", migration_4_add_tx_tracking)
    
    return runner

