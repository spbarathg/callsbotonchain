"""
Minimal repository layer used by tests to validate DB ops without coupling
to production storage code.
"""
import sqlite3
from contextlib import contextmanager
from typing import Iterator


class DatabaseConnection:
    def __init__(self, path: str):
        self.path = path

    @contextmanager
    def get_connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        try:
            yield conn
        finally:
            conn.close()


def initialize_schema(db: DatabaseConnection) -> None:
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS alerted_tokens (
                token_address TEXT PRIMARY KEY
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS alerted_token_stats (
                token_address TEXT PRIMARY KEY,
                name TEXT,
                symbol TEXT,
                final_score INTEGER,
                conviction_type TEXT,
                price_usd REAL
            )
            """
        )
        conn.commit()


class AlertRepository:
    def __init__(self, db: DatabaseConnection):
        self.db = db

    def has_been_alerted(self, token: str) -> bool:
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT 1 FROM alerted_tokens WHERE token_address=?", (token,))
            return cur.fetchone() is not None

    def mark_alerted(self, token: str, *, score: int, smart_money_detected: bool, conviction_type: str) -> None:
        with self.db.get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO alerted_tokens(token_address) VALUES(?)", (token,))
            conn.commit()

    def record_alert_with_metadata(self, *, token_address: str, preliminary_score: int, final_score: int,
                                   conviction_type: str, stats: dict, alert_metadata: dict) -> None:
        with self.db.get_connection() as conn:
            # Also store basic entry price if provided to support performance tracking
            price_val = None
            try:
                price_val = float((stats or {}).get("price_usd"))
            except Exception:
                price_val = None
            conn.execute(
                "CREATE TABLE IF NOT EXISTS alerted_token_stats(token_address TEXT PRIMARY KEY, name TEXT, symbol TEXT, final_score INTEGER, conviction_type TEXT, price_usd REAL)"
            )
            conn.execute(
                "INSERT OR REPLACE INTO alerted_token_stats(token_address, name, symbol, final_score, conviction_type, price_usd) VALUES(?,?,?,?,?,?)",
                (
                    token_address,
                    (stats or {}).get("name"),
                    (stats or {}).get("symbol"),
                    int(final_score),
                    conviction_type,
                    price_val,
                ),
            )
            conn.execute("INSERT OR REPLACE INTO alerted_tokens(token_address) VALUES(?)", (token_address,))
            conn.commit()


class PerformanceRepository:
    def __init__(self, db: DatabaseConnection):
        self.db = db

    def record_price_snapshot(self, token_address: str, *, price: float, liquidity: float) -> None:
        with self.db.get_connection() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS price_snapshots(token_address TEXT, price REAL, liquidity REAL, ts INTEGER)"
            )
            conn.execute(
                "INSERT INTO price_snapshots(token_address, price, liquidity, ts) VALUES(?,?,?, strftime('%s','now'))",
                (token_address, float(price), float(liquidity)),
            )
            conn.commit()

    def update_token_performance(self, token_address: str, *, current_price: float, liquidity: float) -> None:
        # Get entry price from alerted_token_stats if available; fall back to earliest snapshot
        entry_price = None
        with self.db.get_connection() as conn:
            try:
                cur = conn.execute("SELECT price_usd FROM alerted_token_stats WHERE token_address=?", (token_address,))
                row = cur.fetchone()
                if row and row[0]:
                    entry_price = float(row[0])
            except Exception:
                entry_price = None
            if entry_price is None:
                cur = conn.execute(
                    "SELECT price FROM price_snapshots WHERE token_address=? ORDER BY ts ASC LIMIT 1",
                    (token_address,),
                )
                row = cur.fetchone()
                entry_price = float(row[0]) if row else float(current_price)
            # store tracking snapshot (current pnl and max gain)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS performance_tracking(token_address TEXT PRIMARY KEY, entry_price REAL, current_price REAL, max_gain_pct REAL, ts INTEGER)"
            )
            gain_pct = ((float(current_price) - float(entry_price)) / max(float(entry_price), 1e-12)) * 100.0
            # max_gain_pct is monotonic max
            cur = conn.execute("SELECT max_gain_pct FROM performance_tracking WHERE token_address=?", (token_address,))
            row = cur.fetchone()
            prev_max = float(row[0]) if row and row[0] is not None else gain_pct
            max_gain = max(prev_max, gain_pct)
            conn.execute(
                "INSERT OR REPLACE INTO performance_tracking(token_address, entry_price, current_price, max_gain_pct, ts) VALUES(?,?,?,?, strftime('%s','now'))",
                (token_address, float(entry_price), float(current_price), float(max_gain)),
            )
            conn.commit()

    def get_tracking_snapshot(self, token_address: str):
        with self.db.get_connection() as conn:
            cur = conn.execute(
                "SELECT entry_price, current_price, max_gain_pct FROM performance_tracking WHERE token_address=?",
                (token_address,),
            )
            row = cur.fetchone()
            if not row:
                return None
            entry_price, current_price, max_gain_pct = row
            # Also try to pull name from alerted_token_stats when present
            name = None
            cur2 = conn.execute("SELECT name FROM alerted_token_stats WHERE token_address=?", (token_address,))
            r2 = cur2.fetchone()
            if r2 and r2[0]:
                name = r2[0]
            return {
                "entry_price": float(entry_price),
                "current_price": float(current_price),
                "current_pnl_pct": ((float(current_price) - float(entry_price)) / max(float(entry_price), 1e-12)) * 100.0,
                "max_gain_pct": float(max_gain_pct),
                "name": name,
            }


class ActivityRepository:
    def __init__(self, db: DatabaseConnection):
        self.db = db

    def record_token_activity(self, *, token_address: str, usd_value: float, tx_count: int,
                               smart_money: bool, preliminary_score: int, trader: str) -> None:
        with self.db.get_connection() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS token_activity(token_address TEXT, usd_value REAL, tx_count INTEGER, smart_money INTEGER, preliminary_score INTEGER, trader TEXT, ts INTEGER)"
            )
            conn.execute(
                "INSERT INTO token_activity(token_address, usd_value, tx_count, smart_money, preliminary_score, trader, ts) VALUES(?,?,?,?,?,?, strftime('%s','now'))",
                (token_address, float(usd_value), int(tx_count), 1 if smart_money else 0, int(preliminary_score), str(trader)),
            )
            conn.commit()

    def get_recent_token_signals(self, token_address: str, *, window_seconds: int):
        with self.db.get_connection() as conn:
            cur = conn.execute(
                "SELECT token_address, usd_value, tx_count, smart_money, preliminary_score, trader, ts FROM token_activity WHERE token_address=? AND ts >= strftime('%s','now') - ?",
                (token_address, int(window_seconds)),
            )
            return [
                {
                    "token_address": r[0],
                    "usd_value": float(r[1]),
                    "tx_count": int(r[2]),
                    "smart_money": bool(r[3]),
                    "preliminary_score": int(r[4]),
                    "trader": r[5],
                    "ts": int(r[6]),
                }
                for r in cur.fetchall()
            ]

    def cleanup_old_activity(self, *, days_back: int):
        with self.db.get_connection() as conn:
            # When days_back==0, delete all
            if int(days_back) <= 0:
                conn.execute("DELETE FROM token_activity")
            else:
                conn.execute(
                    "DELETE FROM token_activity WHERE ts < strftime('%s','now') - ?",
                    (int(days_back * 86400),),
                )
            conn.commit()


