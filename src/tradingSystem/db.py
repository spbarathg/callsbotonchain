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
	c.execute(
		"""
		CREATE TABLE IF NOT EXISTS position_price_snapshots (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			position_id INTEGER,
			token_address TEXT,
			snapshot_at REAL,
			price_usd REAL,
			qty REAL,
			position_value_usd REAL,
			unrealized_pnl_pct REAL,
			source TEXT,
			FOREIGN KEY(position_id) REFERENCES positions(id)
		)
		"""
	)
	c.execute("CREATE INDEX IF NOT EXISTS idx_position_snapshots_position ON position_price_snapshots(position_id)")
	c.execute("CREATE INDEX IF NOT EXISTS idx_position_snapshots_time ON position_price_snapshots(snapshot_at)")
	
	# Migrations for new fields
	try:
		c.execute("ALTER TABLE positions ADD COLUMN signal_source TEXT DEFAULT 'unknown'")
	except sqlite3.OperationalError:
		pass
	try:
		c.execute("ALTER TABLE positions ADD COLUMN entry_score INTEGER DEFAULT 0")
	except sqlite3.OperationalError:
		pass
	try:
		c.execute("ALTER TABLE positions ADD COLUMN token_age_mins REAL DEFAULT 0.0")
	except sqlite3.OperationalError:
		pass
	try:
		c.execute("ALTER TABLE positions ADD COLUMN market_cap REAL DEFAULT 0.0")
	except sqlite3.OperationalError:
		pass
		
	# New attribution columns
	try:
		c.execute("ALTER TABLE positions ADD COLUMN signal_channel_id TEXT DEFAULT 'unknown'")
	except sqlite3.OperationalError:
		pass
	try:
		c.execute("ALTER TABLE positions ADD COLUMN signal_channel_name TEXT DEFAULT 'unknown'")
	except sqlite3.OperationalError:
		pass
	try:
		c.execute("ALTER TABLE positions ADD COLUMN first_seen_source TEXT DEFAULT 'unknown'")
	except sqlite3.OperationalError:
		pass
	try:
		c.execute("ALTER TABLE positions ADD COLUMN signal_confidence INTEGER DEFAULT 0")
	except sqlite3.OperationalError:
		pass
	try:
		c.execute("ALTER TABLE positions ADD COLUMN pnl_usd REAL DEFAULT NULL")
	except sqlite3.OperationalError:
		pass
	try:
		c.execute("ALTER TABLE positions ADD COLUMN pnl_pct REAL DEFAULT NULL")
	except sqlite3.OperationalError:
		pass
	try:
		c.execute("ALTER TABLE positions ADD COLUMN signal_liquidity REAL DEFAULT 0.0")
	except sqlite3.OperationalError:
		pass

	try:
		c.execute("ALTER TABLE positions ADD COLUMN entry_source TEXT DEFAULT 'unknown'")
	except sqlite3.OperationalError:
		pass
	try:
		c.execute("ALTER TABLE positions ADD COLUMN all_sources TEXT DEFAULT '[]'")
	except sqlite3.OperationalError:
		pass
	try:
		c.execute("ALTER TABLE positions ADD COLUMN signal_time_first REAL DEFAULT 0.0")
	except sqlite3.OperationalError:
		pass
	try:
		c.execute("ALTER TABLE positions ADD COLUMN signal_time_entry REAL DEFAULT 0.0")
	except sqlite3.OperationalError:
		pass
	try:
		c.execute("ALTER TABLE positions ADD COLUMN time_to_entry_mins REAL DEFAULT 0.0")
	except sqlite3.OperationalError:
		pass
	try:
		c.execute("ALTER TABLE positions ADD COLUMN initial_risk_usd REAL DEFAULT 0.0")
	except sqlite3.OperationalError:
		pass

	# Signals funnel table
	c.execute(
		"""
		CREATE TABLE IF NOT EXISTS signals (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			token_address TEXT,
			source_id TEXT,
			source_name TEXT,
			timestamp REAL,
			market_cap REAL,
			score INTEGER,
			entered_trade BOOLEAN DEFAULT 0,
			peak_return_24h REAL DEFAULT NULL,
			peak_return_7d REAL DEFAULT NULL,
			drawdown_24h REAL DEFAULT NULL,
			drawdown_7d REAL DEFAULT NULL,
			time_to_peak REAL DEFAULT NULL,
			sol_price REAL DEFAULT NULL,
			sol_trend TEXT DEFAULT NULL,
			btc_trend TEXT DEFAULT NULL,
			market_regime TEXT DEFAULT NULL
		)
		"""
	)
	c.execute("CREATE INDEX IF NOT EXISTS idx_signals_token ON signals(token_address)")
	
	# Signal price snapshots for opportunity cost tracking
	c.execute(
		"""
		CREATE TABLE IF NOT EXISTS signal_price_snapshots (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			signal_id INTEGER,
			timestamp REAL,
			price_usd REAL,
			market_cap_usd REAL,
			liquidity_usd REAL,
			FOREIGN KEY(signal_id) REFERENCES signals(id)
		)
		"""
	)
	c.execute("CREATE INDEX IF NOT EXISTS idx_signal_snapshots_signal ON signal_price_snapshots(signal_id)")

	conn.commit()
	conn.close()


def create_position(token: str, strategy: str, entry_price: float, qty: float, usd_size: float, trail_pct: float, 
                    signal_source: str = "unknown", entry_score: int = 0, token_age_mins: float = 0.0, market_cap: float = 0.0,
                    signal_channel_id: str = "unknown", signal_channel_name: str = "unknown", 
                    first_seen_source: str = "unknown", signal_confidence: int = 0, signal_liquidity: float = 0.0) -> int:
	"""Create position with retry logic to prevent orphaned positions"""
	
	# Extract advanced source attribution from signals table
	all_sources_json = '[]'
	signal_time_first = 0.0
	signal_time_entry = 0.0
	time_to_entry_mins = 0.0
	try:
		from datetime import datetime
		import json
		conn_tmp = _conn()
		c_tmp = conn_tmp.cursor()
		c_tmp.execute("SELECT source_name, timestamp FROM signals WHERE token_address=? ORDER BY timestamp ASC", (token,))
		rows = c_tmp.fetchall()
		if rows:
			sources_list = []
			for row in rows:
				if row[0] not in sources_list:
					sources_list.append(row[0])
			all_sources_json = json.dumps(sources_list)
			signal_time_first = rows[0][1]
			signal_time_entry = rows[-1][1]  # The latest signal before entry
			time_to_entry_mins = (datetime.now().timestamp() - signal_time_first) / 60.0
		conn_tmp.close()
	except Exception as e:
		print(f"[DB] Error extracting advanced attribution: {e}")
	
	initial_risk_usd = usd_size * (trail_pct / 100.0) if trail_pct else 0.0

	max_retries = 3
	for attempt in range(max_retries):
		try:
			conn = _conn()
			c = conn.cursor()
			c.execute(
				"""
				INSERT INTO positions(
					token_address, strategy, entry_price, qty, usd_size, peak_price, trail_pct, status,
					signal_source, entry_score, token_age_mins, market_cap,
					signal_channel_id, signal_channel_name, first_seen_source, signal_confidence, signal_liquidity,
					entry_source, all_sources, signal_time_first, signal_time_entry, time_to_entry_mins, initial_risk_usd
				) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
				""",
				(token, strategy, entry_price, qty, usd_size, entry_price, trail_pct, "open", 
				 signal_source, entry_score, token_age_mins, market_cap,
				 signal_channel_id, signal_channel_name, first_seen_source, signal_confidence, signal_liquidity,
				 signal_source, all_sources_json, signal_time_first, signal_time_entry, time_to_entry_mins, initial_risk_usd),
			)
			pid = c.lastrowid
			conn.commit()
			conn.close()
			print(f"[DB] Γ£à Position #{pid} created for {token[:8]}...", flush=True)
			return pid
		except Exception as e:
			print(f"[DB] ΓÜá∩╕Å Attempt {attempt+1}/{max_retries} failed to create position: {e}", flush=True)
			if attempt == max_retries - 1:
				# Last attempt failed - this is critical!
				print(f"[DB] ≡ƒÜ¿ CRITICAL: Failed to create position after {max_retries} attempts!", flush=True)
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
			print(f"[DB] ΓÜá∩╕Å Attempt {attempt+1}/{max_retries} failed to add fill: {e}", flush=True)
			if attempt == max_retries - 1:
				print(f"[DB] ≡ƒÜ¿ CRITICAL: Failed to add fill after {max_retries} attempts!", flush=True)
				raise
			import time
			time.sleep(0.5)


def update_peak_and_trail(position_id: int, price: float, entry_price: float = 0.0) -> Tuple[float, float]:
	"""
	Update peak price and calculate PROFIT-BASED trailing stop.
	
	ULTRA AGGRESSIVE MOONSHOT MODE: Allow 35-50% drawdowns for dip-and-rip!
	OCT 25 2025 V3: Memecoins dip 20-30% then rebound to 10x - don't exit on pullbacks!
	Example: +80% ΓåÆ dips to +50% (-37% from peak) ΓåÆ rips to +500%
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
		# ΓåÆ DON'T exit! It can rebound to 800x. Only exit if drops below 40x (-60% from 100x peak)
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
				print(f"[DB] Γ£à Updated position #{position_id} qty to {new_qty:.4f}, avg entry to {avg_entry_price:.8f}", flush=True)
			else:
				# Only update qty (for partial sells)
				c.execute("UPDATE positions SET qty=? WHERE id=?", (new_qty, position_id))
				print(f"[DB] Γ£à Updated position #{position_id} qty to {new_qty:.4f}", flush=True)
			conn.commit()
			conn.close()
			return
		except Exception as e:
			print(f"[DB] ΓÜá∩╕Å Attempt {attempt+1}/{max_retries} failed to update qty: {e}", flush=True)
			if attempt == max_retries - 1:
				print(f"[DB] ≡ƒÜ¿ CRITICAL: Failed to update qty after {max_retries} attempts!", flush=True)
				raise
			import time
			time.sleep(0.5)


def close_position(position_id: int, pnl_usd: float = None, pnl_pct: float = None) -> None:
	conn = _conn()
	c = conn.cursor()
	if pnl_usd is not None and pnl_pct is not None:
		c.execute("UPDATE positions SET status='closed', pnl_usd=?, pnl_pct=? WHERE id=?", (pnl_usd, pnl_pct, position_id))
	else:
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


def get_open_positions() -> list:
	"""
	Return a list of open positions for tracking.
	Each item: dict with id, token_address, entry_price, qty, usd_size, open_at, peak_price, trail_pct.
	"""
	conn = _conn()
	c = conn.cursor()
	c.execute(
		"""
		SELECT id, token_address, entry_price, qty, usd_size, open_at, peak_price, trail_pct
		FROM positions
		WHERE status='open'
		ORDER BY id DESC
		"""
	)
	rows = c.fetchall()
	conn.close()
	positions = []
	for row in rows:
		positions.append({
			"id": row[0],
			"token_address": row[1],
			"entry_price": row[2],
			"qty": row[3],
			"usd_size": row[4],
			"open_at": row[5],
			"peak_price": row[6],
			"trail_pct": row[7],
		})
	return positions


def record_position_price_snapshot(
	position_id: int,
	token_address: str,
	price_usd: float,
	qty: float,
	entry_price: float,
	source: str,
) -> None:
	"""Persist a position price snapshot for long-term tracking."""
	if price_usd <= 0 or qty <= 0:
		return
	position_value = price_usd * qty
	unrealized_pct = 0.0
	if entry_price and entry_price > 0:
		unrealized_pct = ((price_usd - entry_price) / entry_price) * 100.0
	conn = _conn()
	c = conn.cursor()
	try:
		c.execute(
			"""
			INSERT INTO position_price_snapshots (
				position_id, token_address, snapshot_at, price_usd, qty,
				position_value_usd, unrealized_pnl_pct, source
			) VALUES (?, ?, strftime('%s','now'), ?, ?, ?, ?, ?)
			""",
			(position_id, token_address, price_usd, qty, position_value, unrealized_pct, source),
		)
		conn.commit()
	finally:
		conn.close()


def log_signal(token: str, source_id: str, source_name: str, market_cap: float, score: int, 
               sol_price: float = None, sol_trend: str = None, btc_trend: str = None, market_regime: str = None) -> None:
	"""Log every processed signal to measure top-of-funnel conversion"""
	conn = _conn()
	c = conn.cursor()
	try:
		c.execute(
			"""
			INSERT INTO signals (token_address, source_id, source_name, timestamp, market_cap, score, sol_price, sol_trend, btc_trend, market_regime)
			VALUES (?, ?, ?, strftime('%s','now'), ?, ?, ?, ?, ?, ?)
			""",
			(token, source_id, source_name, market_cap, score, sol_price, sol_trend, btc_trend, market_regime)
		)
		conn.commit()
	except Exception as e:
		print(f"[DB] Error logging signal: {e}")
	finally:
		conn.close()


def get_first_seen_source(token: str) -> str:
	"""Get the first source that ever mentioned this token"""
	conn = _conn()
	c = conn.cursor()
	try:
		c.execute("SELECT source_name FROM signals WHERE token_address=? ORDER BY timestamp ASC LIMIT 1", (token,))
		row = c.fetchone()
		return row[0] if row else "unknown"
	except Exception:
		return "unknown"
	finally:
		conn.close()


def mark_signal_entered_trade(token: str) -> None:
	"""Mark that a signal resulted in a trade"""
	conn = _conn()
	c = conn.cursor()
	try:
		# Mark the most recent signal for this token as having entered a trade
		c.execute(
			"""
			UPDATE signals SET entered_trade=1 
			WHERE id = (SELECT id FROM signals WHERE token_address=? ORDER BY timestamp DESC LIMIT 1)
			""", 
			(token,)
		)
		conn.commit()
	except Exception:
		pass
	finally:
		conn.close()

