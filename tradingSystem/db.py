import os
import sqlite3
from typing import Optional, Tuple
from .config import DB_PATH


def _conn() -> sqlite3.Connection:
	os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
	conn = sqlite3.connect(DB_PATH, timeout=5)
	conn.execute("PRAGMA journal_mode=WAL")
	conn.execute("PRAGMA busy_timeout=3000")
	return conn


def init() -> None:
	conn = _conn()
	c = conn.cursor()
	c.execute(
		"""
		CREATE TABLE IF NOT EXISTS positions (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			token_address TEXT,
			strategy TEXT,
			entry_price REAL,
			qty REAL,
			usd_size REAL,
			open_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
			peak_price REAL,
			trail_pct REAL,
			status TEXT
		)
		"""
	)
	c.execute(
		"""
		CREATE TABLE IF NOT EXISTS fills (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			position_id INTEGER,
			side TEXT,
			price REAL,
			qty REAL,
			usd REAL,
			at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)
		"""
	)
	conn.commit()
	conn.close()


def create_position(token: str, strategy: str, entry_price: float, qty: float, usd_size: float, trail_pct: float) -> int:
	conn = _conn()
	c = conn.cursor()
	c.execute(
		"INSERT INTO positions(token_address,strategy,entry_price,qty,usd_size,peak_price,trail_pct,status) VALUES (?,?,?,?,?,?,?,?)",
		(token, strategy, entry_price, qty, usd_size, entry_price, trail_pct, "open"),
	)
	pid = c.lastrowid
	conn.commit()
	conn.close()
	return pid


def add_fill(position_id: int, side: str, price: float, qty: float, usd: float) -> None:
	conn = _conn()
	c = conn.cursor()
	c.execute(
		"INSERT INTO fills(position_id,side,price,qty,usd) VALUES (?,?,?,?,?)",
		(position_id, side, price, qty, usd),
	)
	conn.commit()
	conn.close()


def update_peak_and_trail(position_id: int, price: float) -> Tuple[float, float]:
	conn = _conn()
	c = conn.cursor()
	c.execute("SELECT peak_price, trail_pct FROM positions WHERE id=?", (position_id,))
	row = c.fetchone()
	peak, trail = row if row else (0.0, 0.0)
	if price > (peak or 0):
		c.execute("UPDATE positions SET peak_price=? WHERE id=?", (price, position_id))
		conn.commit()
		peak = price
	conn.close()
	return peak or 0.0, trail or 0.0


def close_position(position_id: int) -> None:
	conn = _conn()
	c = conn.cursor()
	c.execute("UPDATE positions SET status='closed' WHERE id=?", (position_id,))
	conn.commit()
	conn.close()


