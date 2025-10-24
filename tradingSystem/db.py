import os
import sqlite3
from typing import Optional, Tuple
from .config_optimized import DB_PATH


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
	"""Create position with retry logic to prevent orphaned positions"""
	max_retries = 3
	for attempt in range(max_retries):
		try:
			conn = _conn()
			c = conn.cursor()
			c.execute(
				"INSERT INTO positions(token_address,strategy,entry_price,qty,usd_size,peak_price,trail_pct,status) VALUES (?,?,?,?,?,?,?,?)",
				(token, strategy, entry_price, qty, usd_size, entry_price, trail_pct, "open"),
			)
			pid = c.lastrowid
			conn.commit()
			conn.close()
			print(f"[DB] ✅ Position #{pid} created for {token[:8]}...", flush=True)
			return pid
		except Exception as e:
			print(f"[DB] ⚠️ Attempt {attempt+1}/{max_retries} failed to create position: {e}", flush=True)
			if attempt == max_retries - 1:
				# Last attempt failed - this is critical!
				print(f"[DB] 🚨 CRITICAL: Failed to create position after {max_retries} attempts!", flush=True)
				raise  # Re-raise to ensure caller knows it failed
			import time
			time.sleep(0.5)  # Wait before retry


def add_fill(position_id: int, side: str, price: float, qty: float, usd: float) -> None:
	"""Add fill with retry logic"""
	max_retries = 3
	for attempt in range(max_retries):
		try:
			conn = _conn()
			c = conn.cursor()
			c.execute(
				"INSERT INTO fills(position_id,side,price,qty,usd) VALUES (?,?,?,?,?)",
				(position_id, side, price, qty, usd),
			)
			conn.commit()
			conn.close()
			return
		except Exception as e:
			print(f"[DB] ⚠️ Attempt {attempt+1}/{max_retries} failed to add fill: {e}", flush=True)
			if attempt == max_retries - 1:
				print(f"[DB] 🚨 CRITICAL: Failed to add fill after {max_retries} attempts!", flush=True)
				raise
			import time
			time.sleep(0.5)


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


def get_open_qty(position_id: int) -> float:
	"""Return current open quantity for a position as sum(buys) - sum(sells)."""
	conn = _conn()
	c = conn.cursor()
	c.execute(
		"""
		WITH sums AS (
			SELECT
				SUM(CASE WHEN side='buy' THEN COALESCE(qty,0) ELSE 0 END) AS buy_qty,
				SUM(CASE WHEN side='sell' THEN COALESCE(qty,0) ELSE 0 END) AS sell_qty
			FROM fills WHERE position_id=?
		)
		SELECT COALESCE(buy_qty,0) - COALESCE(sell_qty,0) FROM sums
		""",
		(position_id,),
	)
	row = c.fetchone()
	conn.close()
	return float(row[0] or 0.0) if row else 0.0


def get_open_position_id_by_token(token: str) -> Optional[int]:
	"""Return open position id for a token address if any."""
	conn = _conn()
	c = conn.cursor()
	c.execute("SELECT id FROM positions WHERE token_address=? AND status='open' ORDER BY id DESC LIMIT 1", (token,))
	row = c.fetchone()
	conn.close()
	return int(row[0]) if row and row[0] is not None else None

