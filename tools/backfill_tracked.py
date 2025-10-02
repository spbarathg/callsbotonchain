import os
import sqlite3
import time
from typing import Tuple


def _open(path: str) -> sqlite3.Connection:
	con = sqlite3.connect(path, timeout=10)
	con.execute("PRAGMA journal_mode=WAL")
	con.execute("PRAGMA busy_timeout=5000")
	return con


def _pick_db() -> str:
	candidates = [
		os.getenv("CALLSBOT_DB_FILE", "/app/var/alerted_tokens.db"),
		"/app/state/alerted_tokens.db",
		"/app/var/alerted_tokens.db",
		os.path.join("var", "alerted_tokens.db"),
	]
	best = candidates[0]
	best_mtime = -1.0
	for p in candidates:
		try:
			st = os.stat(p)
			mt = float(getattr(st, "st_mtime", 0.0) or 0.0)
			if mt > best_mtime:
				best = p; best_mtime = mt
		except Exception:
			continue
	return best


def _ensure_schema(cur: sqlite3.Cursor) -> None:
	cur.execute(
		"""
		CREATE TABLE IF NOT EXISTS alerted_token_stats (
			token_address TEXT PRIMARY KEY,
			first_alert_at TIMESTAMP,
			last_checked_at TIMESTAMP,
			first_price_usd REAL,
			first_market_cap_usd REAL,
			first_liquidity_usd REAL,
			last_price_usd REAL,
			last_market_cap_usd REAL,
			last_liquidity_usd REAL,
			last_volume_24h_usd REAL,
			peak_price_usd REAL,
			peak_market_cap_usd REAL,
			peak_price_at TIMESTAMP,
			peak_market_cap_at TIMESTAMP,
			peak_volume_24h_usd REAL,
			outcome TEXT,
			outcome_at TIMESTAMP,
			peak_drawdown_pct REAL
		)
		"""
	)


def backfill(limit: int = 500) -> Tuple[int, int]:
	db = _pick_db()
	con = _open(db)
	cur = con.cursor()
	_ensure_schema(cur)
	# Ensure stats rows exist for all alerts
	cur.execute(
		"""
		INSERT OR IGNORE INTO alerted_token_stats(token_address, first_alert_at)
		SELECT t.token_address, t.alerted_at
		FROM alerted_tokens t
		LEFT JOIN alerted_token_stats s ON s.token_address=t.token_address
		WHERE s.token_address IS NULL
		"""
	)
	con.commit()
	# Pull recent alerts needing update
	cur.execute(
		"""
		SELECT t.token_address
		FROM alerted_token_stats s
		JOIN alerted_tokens t ON t.token_address = s.token_address
		ORDER BY datetime(COALESCE(s.last_checked_at, s.first_alert_at)) DESC
		LIMIT ?
		""",
		(limit,),
	)
	rows = [r[0] for r in cur.fetchall() or []]
	updated = 0
	for tok in rows:
		cur.execute(
			"""
			UPDATE alerted_token_stats
			SET last_checked_at = CURRENT_TIMESTAMP,
				peak_price_usd = COALESCE(peak_price_usd, last_price_usd, first_price_usd),
				peak_market_cap_usd = COALESCE(peak_market_cap_usd, last_market_cap_usd, first_market_cap_usd),
				peak_price_at = COALESCE(peak_price_at, CURRENT_TIMESTAMP),
				peak_market_cap_at = COALESCE(peak_market_cap_at, CURRENT_TIMESTAMP)
			WHERE token_address = ?
			""",
			(tok,),
		)
		updated += 1
	con.commit(); con.close()
	return (len(rows), updated)


def main():
	start = time.time()
	n, upd = backfill()
	print({"selected": n, "updated": upd, "ms": int((time.time()-start)*1000)})


if __name__ == "__main__":
	main()


