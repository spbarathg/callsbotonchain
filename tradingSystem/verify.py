import json
import os
import re
import sqlite3
from typing import Dict, Any

from .config import (
	BOT_STDOUT_LOG,
	DB_PATH,
	DRY_RUN,
	MIN_LP_USD,
	RATIO_MIN,
	MCAP_MAX,
	MOMENTUM_1H_GATE,
	CORE_STOP_PCT,
	SCOUT_STOP_PCT,
	TRAIL_DEFAULT_PCT,
	TRAIL_TIGHT_PCT,
	TRAIL_WIDE_PCT,
)
from .db import init as db_init
from .strategy import decide_runner, decide_scout


def _exists(path: str) -> bool:
	try:
		return os.path.exists(path)
	except Exception:
		return False


def check_config() -> Dict[str, Any]:
	return {
		"BOT_STDOUT_LOG": BOT_STDOUT_LOG,
		"DB_PATH": DB_PATH,
		"DRY_RUN": DRY_RUN,
		"GATES": {
			"MIN_LP_USD": MIN_LP_USD,
			"RATIO_MIN": RATIO_MIN,
			"MCAP_MAX": MCAP_MAX,
			"MOMENTUM_1H_GATE": MOMENTUM_1H_GATE,
		},
		"STOPS_TRAILS": {
			"CORE_STOP_PCT": CORE_STOP_PCT,
			"SCOUT_STOP_PCT": SCOUT_STOP_PCT,
			"TRAIL_DEFAULT_PCT": TRAIL_DEFAULT_PCT,
			"TRAIL_TIGHT_PCT": TRAIL_TIGHT_PCT,
			"TRAIL_WIDE_PCT": TRAIL_WIDE_PCT,
		},
	}


def check_db() -> Dict[str, Any]:
	db_init()
	conn = sqlite3.connect(DB_PATH)
	try:
		integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
		pos_cols = [r[1] for r in conn.execute("PRAGMA table_info(positions)").fetchall()]
		fills_cols = [r[1] for r in conn.execute("PRAGMA table_info(fills)").fetchall()]
		return {
			"integrity": integrity,
			"positions_cols": pos_cols,
			"fills_cols": fills_cols,
		}
	finally:
		conn.close()


def check_watcher() -> Dict[str, Any]:
	path = BOT_STDOUT_LOG
	if not _exists(path):
		return {"exists": False, "finals": 0, "passes": 0, "rejects": 0}
	final_re = re.compile(r"Token\s+([A-Za-z0-9]{20,})\s+FINAL:")
	pass_re = re.compile(r"PASSED \(Strict \+ Smart Money\):")
	rej_re = re.compile(r"REJECTED \(Junior Strict\):")
	finals = passes = rejects = 0
	with open(path, "r", errors="ignore") as f:
		lines = f.readlines()[-2000:]
		for ln in lines:
			if final_re.search(ln):
				finals += 1
			if pass_re.search(ln):
				passes += 1
			if rej_re.search(ln):
				rejects += 1
	return {"exists": True, "finals": finals, "passes": passes, "rejects": rejects}


def check_strategy() -> Dict[str, Any]:
	# Minimal synthetic stats to validate decision branches
	runner_stats = {"liquidity_usd": 20000, "ratio": 0.6, "market_cap_usd": 300000, "change_1h": 25.0}
	scout_stats = {"liquidity_usd": 20000, "ratio": 0.9, "market_cap_usd": 500000, "change_1h": 28.0, "vel_score": 8, "unique_traders_15m": 30}
	plan_runner = decide_runner(runner_stats, is_smart=True)
	plan_scout = decide_scout(scout_stats)
	return {
		"runner_plan": plan_runner,
		"scout_plan": plan_scout,
	}


def main() -> None:
	result = {
		"config": check_config(),
		"db": check_db(),
		"watcher": check_watcher(),
		"strategy": check_strategy(),
	}
	print(json.dumps(result, indent=2))


if __name__ == "__main__":
    print("Not a standalone entrypoint. Use: python scripts/bot.py run|web|trade")


