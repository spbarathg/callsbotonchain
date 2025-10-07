#!/usr/bin/env python3
"""
Database Cleanup Script
Removes old price snapshots to prevent database growth

Run this script periodically (e.g., daily via cron) to maintain database size
"""
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from app.logger_utils import _out


def cleanup_old_snapshots(db_path: str, retention_days: int = 30):
    """
    Remove price snapshots older than retention_days
    
    Args:
        db_path: Path to the database file
        retention_days: Number of days to keep (default: 30)
    """
    try:
        _out(f"🧹 Starting database cleanup...")
        _out(f"Database: {db_path}")
        _out(f"Retention: {retention_days} days")
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Count total snapshots before cleanup
        cursor.execute("SELECT COUNT(*) FROM price_snapshots")
        total_before = cursor.fetchone()[0]
        _out(f"Total snapshots before cleanup: {total_before:,}")
        
        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        cutoff_str = cutoff_date.strftime('%Y-%m-%d %H:%M:%S')
        
        # Count snapshots to be deleted
        cursor.execute(
            "SELECT COUNT(*) FROM price_snapshots WHERE snapshot_at < ?",
            (cutoff_str,)
        )
        to_delete = cursor.fetchone()[0]
        _out(f"Snapshots to delete (older than {cutoff_str}): {to_delete:,}")
        
        if to_delete == 0:
            _out("✅ No old snapshots to delete. Database is clean!")
            conn.close()
            return
        
        # Delete old snapshots
        cursor.execute(
            "DELETE FROM price_snapshots WHERE snapshot_at < ?",
            (cutoff_str,)
        )
        deleted = cursor.rowcount
        
        # Commit changes
        conn.commit()
        
        # Count remaining snapshots
        cursor.execute("SELECT COUNT(*) FROM price_snapshots")
        total_after = cursor.fetchone()[0]
        
        # Vacuum to reclaim space
        _out("🗜️  Running VACUUM to reclaim disk space...")
        cursor.execute("VACUUM")
        conn.commit()
        
        # Get database size
        cursor.execute("PRAGMA page_count")
        page_count = cursor.fetchone()[0]
        cursor.execute("PRAGMA page_size")
        page_size = cursor.fetchone()[0]
        db_size_mb = (page_count * page_size) / (1024 * 1024)
        
        conn.close()
        
        _out(f"✅ Cleanup complete!")
        _out(f"   Deleted: {deleted:,} snapshots")
        _out(f"   Remaining: {total_after:,} snapshots")
        _out(f"   Database size: {db_size_mb:.2f} MB")
        
    except Exception as e:
        _out(f"❌ Error during cleanup: {e}")
        raise


def cleanup_completed_tracking(db_path: str, retention_days: int = 7):
    """
    Archive or remove tracking data for tokens that have completed their lifecycle
    (rugged or reached final state) and are older than retention_days
    
    Args:
        db_path: Path to the database file
        retention_days: Number of days to keep completed tracking (default: 7)
    """
    try:
        _out(f"🧹 Cleaning up completed tracking records...")
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        cutoff_str = cutoff_date.strftime('%Y-%m-%d %H:%M:%S')
        
        # Count completed tracking records to archive
        cursor.execute(
            """
            SELECT COUNT(*) FROM alerted_token_stats 
            WHERE outcome IN ('rug', 'completed') 
            AND outcome_at < ?
            """,
            (cutoff_str,)
        )
        to_archive = cursor.fetchone()[0]
        
        if to_archive == 0:
            _out("✅ No old completed tracking records to archive.")
            conn.close()
            return
        
        _out(f"Found {to_archive} completed tracking records older than {retention_days} days")
        _out("ℹ️  Keeping records for historical analysis (not deleting)")
        
        # Note: We don't actually delete these, just report them
        # In production, you might want to archive to a separate table
        
        conn.close()
        
    except Exception as e:
        _out(f"⚠️  Error during tracking cleanup: {e}")


def main():
    """Main cleanup routine"""
    # Get database path from environment or use default
    db_path = os.getenv("CALLSBOT_DB_FILE", os.path.join("var", "alerted_tokens.db"))
    
    # Get retention settings from environment
    snapshot_retention = int(os.getenv("SNAPSHOT_RETENTION_DAYS", "30"))
    tracking_retention = int(os.getenv("TRACKING_RETENTION_DAYS", "7"))
    
    _out("="*60)
    _out("🧹 DATABASE CLEANUP SCRIPT")
    _out("="*60)
    
    # Check if database exists
    if not os.path.exists(db_path):
        _out(f"❌ Database not found: {db_path}")
        sys.exit(1)
    
    # Get initial database size
    initial_size = os.path.getsize(db_path) / (1024 * 1024)
    _out(f"Initial database size: {initial_size:.2f} MB")
    
    # Run cleanup tasks
    cleanup_old_snapshots(db_path, snapshot_retention)
    cleanup_completed_tracking(db_path, tracking_retention)
    
    # Get final database size
    final_size = os.path.getsize(db_path) / (1024 * 1024)
    saved = initial_size - final_size
    
    _out("="*60)
    _out(f"✅ CLEANUP COMPLETE")
    _out(f"   Initial size: {initial_size:.2f} MB")
    _out(f"   Final size: {final_size:.2f} MB")
    _out(f"   Space saved: {saved:.2f} MB ({saved/initial_size*100:.1f}%)")
    _out("="*60)


if __name__ == "__main__":
    main()