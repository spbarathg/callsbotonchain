import json
import os
from datetime import datetime
from typing import Dict, Optional
from .db import init as db_init, create_position, add_fill, update_peak_and_trail, close_position, get_open_qty
from .config import CORE_STOP_PCT, SCOUT_STOP_PCT, STRICT_STOP_PCT, NUANCED_STOP_PCT, LOG_JSON_PATH, LOG_TEXT_PATH, MAX_CONCURRENT
from .config import DB_PATH
from .broker import Broker


class TradeEngine:
	def __init__(self) -> None:
		db_init()
		self.broker = Broker()
		# token_address -> {pid, strategy}
		self.live: Dict[str, Dict[str, object]] = {}
		os.makedirs(os.path.dirname(LOG_JSON_PATH), exist_ok=True)
		os.makedirs(os.path.dirname(LOG_TEXT_PATH), exist_ok=True)
		# Load open positions from DB for restart recovery
		try:
			import sqlite3
			con = sqlite3.connect(DB_PATH)
			cur = con.execute("SELECT id, token_address, strategy FROM positions WHERE status='open'")
			for pid, ca, strategy in cur.fetchall():
				self.live[str(ca)] = {"pid": int(pid), "strategy": str(strategy)}
			con.close()
			if self.live:
				self._log("recovery_loaded", open_positions=len(self.live))
		except Exception:
			pass

	def _log(self, event: str, **fields) -> None:
		payload = {"ts": datetime.utcnow().isoformat(timespec="seconds") + "Z", "event": event}
		payload.update(fields)
		try:
			with open(LOG_JSON_PATH, "a", encoding="utf-8") as f:
				f.write(json.dumps(payload, ensure_ascii=False) + "\n")
		except Exception:
			pass
		try:
			line = f"[{payload['ts']}] {event} " + " ".join(f"{k}={v}" for k, v in fields.items())
			with open(LOG_TEXT_PATH, "a", encoding="utf-8") as f:
				f.write(line + "\n")
		except Exception:
			pass

	def open_position(self, token: str, plan: Dict) -> Optional[int]:
		# Concurrency limit
		if len(self.live) >= int(MAX_CONCURRENT):
			self._log("open_skipped_max_concurrent", token=token, max_concurrent=int(MAX_CONCURRENT))
			return None
		usd = float(plan["usd_size"])
		trail_pct = float(plan["trail_pct"])
		fill = self.broker.market_buy(token, usd)
		pid = create_position(token, plan["strategy"], fill.price, fill.qty, usd, trail_pct)
		add_fill(pid, "buy", fill.price, fill.qty, fill.usd)
		self.live[token] = {"pid": pid, "strategy": plan.get("strategy")}
		self._log("open_position", token=token, strategy=plan.get("strategy"), pid=pid, price=fill.price, qty=fill.qty, usd=usd, trail_pct=trail_pct)
		return pid

	def has_position(self, token: str) -> bool:
		return token in self.live

	def position_strategy(self, token: str) -> Optional[str]:
		data = self.live.get(token)
		if not data:
			return None
		return str(data.get("strategy"))

	def check_exits(self, token: str, price: float) -> bool:
		data = self.live.get(token)
		pid = data.get("pid") if data else None
		if not pid:
			return False
		peak, trail = update_peak_and_trail(pid, price)
		strategy = str(data.get("strategy")) if data else "runner"
		
		# Strategy-specific stop loss percentages
		stop_pct_map = {
			"runner": CORE_STOP_PCT,
			"scout": SCOUT_STOP_PCT,
			"strict": STRICT_STOP_PCT,
			"nuanced": NUANCED_STOP_PCT,
		}
		stop_pct = stop_pct_map.get(strategy, CORE_STOP_PCT)
		
		# Hard stop
		if price <= (1.0 - stop_pct / 100.0) * max(1e-9, peak):
			qty_open = get_open_qty(int(pid))
			fill = self.broker.market_sell(token, float(qty_open))
			close_position(pid)
			self.live.pop(token, None)
			add_fill(int(pid), "sell", float(fill.price), float(fill.qty), float(fill.usd))
			self._log("exit_stop", token=token, pid=pid, price=price, peak=peak, stop_pct=stop_pct, strategy=strategy)
			return True
		# Trail
		if peak and price <= (1.0 - trail / 100.0) * peak:
			qty_open = get_open_qty(int(pid))
			fill = self.broker.market_sell(token, float(qty_open))
			close_position(pid)
			self.live.pop(token, None)
			add_fill(int(pid), "sell", float(fill.price), float(fill.qty), float(fill.usd))
			self._log("exit_trail", token=token, pid=pid, price=price, peak=peak, trail_pct=trail, strategy=strategy)
			return True
		return False


