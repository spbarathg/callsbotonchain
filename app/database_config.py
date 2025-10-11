"""
Centralized database path configuration.

Provides a single source of truth for all database paths,
ensuring consistency across the application.
"""
import os
from typing import Optional


# Base directory for all database files
VAR_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "var")


class DatabasePaths:
    """Central registry for all database paths."""
    
    # Signals/alerts database
    SIGNALS_DB = os.getenv(
        "CALLSBOT_DB_FILE",
        os.path.join(VAR_DIR, "alerted_tokens.db")
    )
    
    # Trading database
    TRADING_DB = os.getenv(
        "CALLSBOT_TRADING_DB",
        os.path.join(VAR_DIR, "trading.db")
    )
    
    # Admin/audit database
    ADMIN_DB = os.getenv(
        "CALLSBOT_ADMIN_DB",
        os.path.join(VAR_DIR, "admin.db")
    )
    
    # Treasury state database
    TREASURY_DB = os.getenv(
        "CALLSBOT_TREASURY_DB",
        os.path.join(VAR_DIR, "treasury.json")
    )
    
    @classmethod
    def get_signals_db(cls) -> str:
        """Get path to signals/alerts database."""
        return cls.SIGNALS_DB
    
    @classmethod
    def get_trading_db(cls) -> str:
        """Get path to trading database."""
        return cls.TRADING_DB
    
    @classmethod
    def get_admin_db(cls) -> str:
        """Get path to admin/audit database."""
        return cls.ADMIN_DB
    
    @classmethod
    def get_treasury_db(cls) -> str:
        """Get path to treasury state file."""
        return cls.TREASURY_DB
    
    @classmethod
    def ensure_var_dir(cls) -> None:
        """Ensure var directory exists."""
        os.makedirs(VAR_DIR, exist_ok=True)
    
    @classmethod
    def get_var_dir(cls) -> str:
        """Get the var directory path."""
        return VAR_DIR


# Backward compatibility aliases
DB_FILE = DatabasePaths.SIGNALS_DB
TRADING_DB_PATH = DatabasePaths.TRADING_DB
ADMIN_DB_PATH = DatabasePaths.ADMIN_DB


# Helper function for database connection URIs
def get_db_uri(db_path: str, read_only: bool = False) -> str:
    """
    Get a SQLite connection URI.
    
    Args:
        db_path: Path to the database file
        read_only: Whether to open in read-only mode
        
    Returns:
        SQLite URI string
    """
    if read_only:
        return f"file:{db_path}?mode=ro"
    return db_path


# Export all
__all__ = [
    "DatabasePaths",
    "DB_FILE",
    "TRADING_DB_PATH",
    "ADMIN_DB_PATH",
    "get_db_uri",
]

