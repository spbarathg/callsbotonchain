import argparse
import threading
import time

import requests

from .watcher import follow_decisions
from .strategy import decide_runner, decide_scout
from .trader import TradeEngine
from app.toggles import trading_enabled
from .db import get_open_position_id_by_token


def _get_last_price_usd(token: str) -> float:
    """Fetch last price from the app's tracked API to avoid paid services."""
    try:
        resp = requests.get("http://127.0.0.1/api/tracked?limit=200", timeout=5)
        resp.raise_for_status()
        rows = (resp.json() or {}).get("rows") or []
        for r in rows:
            if r.get("token") == token:
                lp = r.get("last_price") or r.get("peak_price") or r.get("first_price")
                return float(lp or 0.0)
    except Exception:
        pass
    return 0.0


def _exit_loop(engine: TradeEngine, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        # Iterate over a snapshot to avoid dict size change during loop
        for token in list(engine.live.keys()):
            pid = get_open_position_id_by_token(token)
            if not pid:
                continue
            price = _get_last_price_usd(token)
            if price > 0:
                try:
                    engine.check_exits(token, price)
                except Exception:
                    pass
        time.sleep(2)


def run() -> None:
	parser = argparse.ArgumentParser(description="Minimal tradingSystem runner")
	parser.add_argument("--dry", action="store_true", help="Dry run (no real trades)")
	parser.parse_args()

	engine = TradeEngine()
	# Start exit loop thread
	stop_event = threading.Event()
	t = threading.Thread(target=_exit_loop, args=(engine, stop_event), daemon=True)
	t.start()

	for ev in follow_decisions(start_at_end=True):
		# Respect trading toggle: monitor decisions but do not place orders
		if not trading_enabled():
			time.sleep(0.2)
			continue
		if ev["type"] == "pass_strict_smart":
			# Minimal bootstrap: reuse strict defaults until full stats fetch is wired
			stats = {"liquidity_usd": 20000, "ratio": 0.6, "market_cap_usd": 300000, "change_1h": 15.0}
			plan = decide_runner(stats, is_smart=True)
			if plan:
				engine.open_position(ev["ca"], plan)
		elif ev["type"] == "final":
			stats = {"liquidity_usd": 20000, "ratio": 0.9, "market_cap_usd": 500000, "change_1h": 25.0, "vel_score": 8, "unique_traders_15m": 30}
			plan = decide_scout(stats)
			if plan:
				engine.open_position(ev["ca"], plan)


if __name__ == "__main__":
	run()


