import argparse
import json
import threading
import time
from typing import Dict

from .watcher import follow_decisions
from .strategy import decide_runner, decide_scout
from .trader import TradeEngine
from app.toggles import trading_enabled


def run() -> None:
	parser = argparse.ArgumentParser(description="Minimal tradingSystem runner")
	parser.add_argument("--dry", action="store_true", help="Dry run (no real trades)")
	args = parser.parse_args()

	engine = TradeEngine()

	for ev in follow_decisions(start_at_end=True):
		# Respect trading toggle: monitor decisions but do not place orders
		if not trading_enabled():
			time.sleep(0.2)
			continue
		if ev["type"] == "pass_strict_smart":
			# In real system we'd fetch stats; here we emit a minimal placeholder
			stats = {"liquidity_usd": 20000, "ratio": 0.6, "market_cap_usd": 300000, "change_1h": 15.0}
			plan = decide_runner(stats, is_smart=True)
			if plan:
				engine.open_position(ev["ca"], plan)
		elif ev["type"] == "final":
			# Use FINAL to drive scout attempts with placeholder stats
			stats = {"liquidity_usd": 20000, "ratio": 0.9, "market_cap_usd": 500000, "change_1h": 25.0, "vel_score": 8, "unique_traders_15m": 30}
			plan = decide_scout(stats)
			if plan:
				engine.open_position(ev["ca"], plan)


if __name__ == "__main__":
	run()


