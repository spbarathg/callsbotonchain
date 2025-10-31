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


def update_peak_and_trail(position_id: int, price: float, entry_price: float = 0.0) -> Tuple[float, float]:
	"""
	Update peak price and calculate PROFIT-BASED trailing stop.
	
	ULTRA AGGRESSIVE MOONSHOT MODE: Allow 35-50% drawdowns for dip-and-rip!
	OCT 25 2025 V3: Memecoins dip 20-30% then rebound to 10x - don't exit on pullbacks!
	Example: +80% → dips to +50% (-37% from peak) → rips to +500%
	- 0-50% profit: 35% trail (survive shakeouts!)
	- 50-100% profit: 38% trail (let dips play out)
	- 100-200% profit: 42% trail (dip-then-rip pattern)
	- 200-500% profit: 45% trail (massive consolidation room)
	- 500-1000% profit: 48% trail (moonshot volatility)
	- 1000%+ profit: 50% trail (10x moves need HUGE room!)
	"""
	conn = _conn()
	c = conn.cursor()
	c.execute("SELECT peak_price, trail_pct, entry_price FROM positions WHERE id=?", (position_id,))
	row = c.fetchone()
	if not row:
		conn.close()
		return 0.0, 0.0
	
	peak, trail_static, db_entry = row
	
	# Use provided entry_price or fall back to DB
	entry = entry_price if entry_price > 0 else (db_entry or 0.0)
	
	# Update peak if price is higher
	if price > (peak or 0):
		c.execute("UPDATE positions SET peak_price=? WHERE id=?", (price, position_id))
		conn.commit()
		peak = price
	conn.close()
	
	# Calculate profit-based trail (MOONSHOT MODE - AUDIT OPTIMIZED!)
	from tradingSystem.config_optimized import (
		ADAPTIVE_TRAILING_ENABLED,
		PROFIT_TIER_1, PROFIT_TIER_2, PROFIT_TIER_3, PROFIT_TIER_4, PROFIT_TIER_5,
		TRAIL_TIER_0, TRAIL_TIER_1, TRAIL_TIER_2, TRAIL_TIER_3, TRAIL_TIER_4, TRAIL_TIER_5,
		TRAIL_TIER_6, TRAIL_TIER_7, TRAIL_TIER_8
	)
	
	if ADAPTIVE_TRAILING_ENABLED and entry > 0 and peak > 0:
		# Calculate current profit %
		profit_pct = ((peak - entry) / entry) * 100
		
		# Select trail based on profit tier (EXTENDED FOR 800-1000x MEGA MOVERS!)
		# OCT 27 2025: MEGA MOONSHOT MODE (60-80% trails) - capture 800-1000x gains
		# User requirement: "Don't leave 800-1000x gains on the table"
		# Strategy: Ultra-wide trails for 100x+ to survive massive volatility
		# 
		# Example: Token at 100x (+9900%) dips to 60x (-40% from peak = within 60% trail)
		# → DON'T exit! It can rebound to 800x. Only exit if drops below 40x (-60% from 100x peak)
		if profit_pct < PROFIT_TIER_1:  # 0-50% profit
			trail = TRAIL_TIER_0  # 35% trail (survive shakeouts!)
		elif profit_pct < PROFIT_TIER_2:  # 50-100% profit
			trail = TRAIL_TIER_1  # 38% trail (let dips play out)
		elif profit_pct < PROFIT_TIER_3:  # 100-200% profit
			trail = TRAIL_TIER_2  # 42% trail (dip-then-rip pattern)
		elif profit_pct < PROFIT_TIER_4:  # 200-500% profit
			trail = TRAIL_TIER_3  # 45% trail (massive consolidation room)
		elif profit_pct < PROFIT_TIER_5:  # 500-1000% profit
			trail = TRAIL_TIER_4  # 48% trail (moonshot volatility)
		elif profit_pct < 5000:  # 1000-5000% profit (10x-50x)
			trail = TRAIL_TIER_5  # 50% trail (10x-50x needs HUGE room!)
		elif profit_pct < 10000:  # 5000-10000% profit (50x-100x)
			trail = TRAIL_TIER_6  # 60% trail (50x-100x ULTRA volatility)
		elif profit_pct < 80000:  # 10000-80000% profit (100x-800x)
			trail = TRAIL_TIER_7  # 70% trail (100x-800x LEGENDARY moves)
		else:  # 80000%+ profit (800x+ MEGA MOONSHOT!)
			trail = TRAIL_TIER_8  # 80% trail (800x+ ride FOREVER, NEVER SELL!)
	else:
		# Fall back to static trail from position creation
		trail = trail_static or 10.0
	
	return peak or 0.0, trail or 10.0


def update_position_qty(position_id: int, new_qty: float, avg_entry_price: float = None) -> None:
	"""Update position quantity after partial sell or pyramiding"""
	max_retries = 3
	for attempt in range(max_retries):
		try:
			conn = _conn()
			c = conn.cursor()
			if avg_entry_price is not None:
				# Update both qty and entry price (for pyramiding)
				c.execute("UPDATE positions SET qty=?, entry_price=? WHERE id=?", 
						 (new_qty, avg_entry_price, position_id))
				print(f"[DB] ✅ Updated position #{position_id} qty to {new_qty:.4f}, avg entry to {avg_entry_price:.8f}", flush=True)
			else:
				# Only update qty (for partial sells)
				c.execute("UPDATE positions SET qty=? WHERE id=?", (new_qty, position_id))
				print(f"[DB] ✅ Updated position #{position_id} qty to {new_qty:.4f}", flush=True)
			conn.commit()
			conn.close()
			return
		except Exception as e:
			print(f"[DB] ⚠️ Attempt {attempt+1}/{max_retries} failed to update qty: {e}", flush=True)
			if attempt == max_retries - 1:
				print(f"[DB] 🚨 CRITICAL: Failed to update qty after {max_retries} attempts!", flush=True)
				raise
			import time
			time.sleep(0.5)


def close_position(position_id: int) -> None:
	print(f"[DB] 🔒 Closing position #{position_id}", flush=True)
	conn = _conn()
	c = conn.cursor()
	c.execute("UPDATE positions SET status='closed' WHERE id=?", (position_id,))
	rows_affected = c.rowcount
	conn.commit()
	conn.close()
	print(f"[DB] ✅ Position #{position_id} closed ({rows_affected} rows affected)", flush=True)


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


def get_open_qty_by_token(token_address: str) -> Optional[float]:
	"""
	Get quantity for an open position by token address
	Used by Jupiter price oracle to get real sellable prices
	Returns None if position not found
	"""
	try:
		position_id = get_open_position_id_by_token(token_address)
		if position_id is None:
			return None
		return get_open_qty(position_id)
	except Exception:
		return None

