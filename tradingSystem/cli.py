import argparse
import json
import os
import threading
import time
from typing import Optional, Dict

import requests

from .watcher import follow_decisions
from .strategy import decide_runner, decide_scout, decide_strict, decide_nuanced
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


def _fetch_real_stats(token: str) -> Optional[Dict[str, float]]:
    """Fetch real-time stats for a token from tracking API and alerts.jsonl."""
    stats = {}
    
    # Try tracking API first (has latest price updates)
    try:
        resp = requests.get("http://127.0.0.1/api/tracked?limit=500", timeout=5)
        resp.raise_for_status()
        rows = (resp.json() or {}).get("rows") or []
        for r in rows:
            if r.get("token") == token:
                stats["market_cap_usd"] = float(r.get("last_mcap") or r.get("peak_mcap") or 0)
                stats["liquidity_usd"] = float(r.get("liquidity") or 0)
                stats["change_1h"] = float(r.get("change_1h") or 0) * 100  # Convert to percentage
                vol24 = float(r.get("vol24") or 0)
                mcap = stats.get("market_cap_usd") or 1
                stats["ratio"] = vol24 / max(mcap, 1) if mcap > 0 else 0
                stats["vol24_usd"] = vol24
                break
    except Exception:
        pass
    
    # Fallback to alerts.jsonl for initial alert data
    if not stats or stats.get("liquidity_usd", 0) == 0:
        try:
            alerts_path = os.path.join(os.path.dirname(__file__), "..", "data", "logs", "alerts.jsonl")
            if os.path.exists(alerts_path):
                # Read last 1000 lines for recent alerts
                with open(alerts_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for line in reversed(lines[-1000:]):
                        try:
                            alert = json.loads(line.strip())
                            if alert.get("token") == token:
                                stats["market_cap_usd"] = float(alert.get("market_cap") or 0)
                                stats["liquidity_usd"] = float(alert.get("liquidity") or 0)
                                stats["change_1h"] = float(alert.get("change_1h") or 0) * 100
                                vol24 = float(alert.get("volume_24h") or 0)
                                mcap = stats.get("market_cap_usd") or 1
                                stats["ratio"] = vol24 / max(mcap, 1) if mcap > 0 else 0
                                stats["vol24_usd"] = vol24
                                stats["vel_score"] = float(alert.get("velocity_score_15m") or 0)
                                stats["unique_traders_15m"] = float(alert.get("unique_traders_15m") or 0)
                                stats["final_score"] = int(alert.get("final_score") or 0)
                                stats["conviction_type"] = alert.get("conviction_type") or ""
                                break
                        except Exception:
                            continue
        except Exception:
            pass
    
    # Validation: reject if critical stats missing
    if not stats.get("market_cap_usd") or not stats.get("ratio"):
        return None
    
    return stats


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
	parser = argparse.ArgumentParser(description="Enhanced tradingSystem runner with real-time validation")
	parser.add_argument("--dry", action="store_true", help="Dry run (no real trades)")
	parser.parse_args()

	engine = TradeEngine()
	engine._log("trading_system_start", mode="dry_run" if engine.broker._dry else "live")
	
	# Start exit loop thread
	stop_event = threading.Event()
	t = threading.Thread(target=_exit_loop, args=(engine, stop_event), daemon=True)
	t.start()

	for ev in follow_decisions(start_at_end=True):
		token = ev.get("ca")
		event_type = ev.get("type")
		
		# Respect trading toggle
		if not trading_enabled():
			time.sleep(0.2)
			continue
		
		# Skip if already have position
		if engine.has_position(token):
			continue
		
		# Fetch real-time stats
		stats = _fetch_real_stats(token)
		if not stats:
			engine._log("stats_fetch_failed", token=token, event_type=event_type)
			continue
		
		# Route to appropriate strategy based on event type and conviction
		plan = None
		conviction = stats.get("conviction_type", "")
		
		if event_type == "pass_strict_smart":
			# High Confidence (Smart Money) - use runner strategy
			plan = decide_runner(stats, is_smart=True)
			
		elif event_type == "final":
			# Process based on conviction type in the alert
			if "Smart Money" in conviction:
				# High Confidence (Smart Money)
				plan = decide_runner(stats, is_smart=True)
			elif "Strict" in conviction:
				# High Confidence (Strict) - use new strict strategy
				plan = decide_strict(stats)
			elif "Nuanced" in conviction:
				# Nuanced Conviction - use nuanced strategy
				plan = decide_nuanced(stats)
			else:
				# Fallback: use scout for high velocity signals
				final_score = int(stats.get("final_score", 0))
				if final_score >= 6:
					plan = decide_scout(stats)
		
		# Execute trade if plan approved
		if plan:
			# Final validation: re-check if token hasn't already dumped
			current_price = _get_last_price_usd(token)
			alert_price = stats.get("price", 0)
			if current_price > 0 and alert_price > 0:
				price_change = (current_price - alert_price) / alert_price
				# Reject if already dumped >30% from alert
				if price_change < -0.30:
					engine._log("entry_rejected_dumped", token=token, price_change_pct=price_change * 100)
					continue
			
			engine.open_position(token, plan)


if __name__ == "__main__":
	run()


