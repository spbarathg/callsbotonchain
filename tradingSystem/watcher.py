import re
import time
import json
import os
from typing import Iterator, Dict

# Legacy stdout log path (deprecated - use Redis instead)
BOT_STDOUT_LOG = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "logs", "stdout.log")


_FINAL_RE = re.compile(r"Token\s+([A-Za-z0-9]{20,64})\s+FINAL:\s+(\d+)/(\d+)\s+\(prelim:\s*(\d+),\s*velocity:\s*\+(\d+)\)")
_PASS_RE = re.compile(r"PASSED \(Strict \+ Smart Money\):\s+([A-Za-z0-9]{20,64})")
_REJECT_RE = re.compile(r"REJECTED \(Junior Strict\):\s+([A-Za-z0-9]{20,64})")

_BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{20,64}$")


# Redis client for real-time signal consumption
_REDIS_URL = os.getenv("REDIS_URL") or os.getenv("CALLSBOT_REDIS_URL") or ""
_redis_client = None
if _REDIS_URL:
	try:
		import redis  # type: ignore
		_redis_client = redis.from_url(_REDIS_URL, decode_responses=True)
		_redis_client.ping()
		print(f"✅ Redis watcher connected: {_REDIS_URL}")
	except Exception as e:
		print(f"⚠️ Redis watcher not available: {e}")
		_redis_client = None


def _valid_ca(ca: str) -> bool:
	# Basic base58/length filter (Solana typically 32-44, but allow 20-64 for safety)
	return bool(_BASE58_RE.match(ca))


def follow_signals_redis(block_timeout: int = 5) -> Iterator[Dict]:
	"""Yield trading signals from Redis in real-time (BLOCKING).
	
	This is the preferred method for paper/live trading as it receives
	signals immediately when the worker bot finds them.
	
	Args:
		block_timeout: Seconds to wait for new signals (default: 5s)
	
	Yields:
		Dict with keys: token, score, conviction_type, price, liquidity, etc.
	"""
	if _redis_client is None:
		raise RuntimeError("Redis not available. Cannot follow signals.")
	
	print(f"📡 Watching Redis for trading signals (blocking mode, timeout={block_timeout}s)...")
	
	# Track last processed timestamp to avoid duplicates on reconnect
	last_timestamp = time.time()
	
	while True:
		try:
			# BRPOP: Blocking right pop - waits for new signals
			# Returns: [list_name, json_payload] or None on timeout
			result = _redis_client.brpop("trading_signals", timeout=block_timeout)
			
			if result is None:
				# Timeout - no new signals, continue waiting
				continue
			
			_, payload = result
			signal = json.loads(payload)
			
			# Skip if this signal was already processed (e.g., after reconnect)
			signal_time = signal.get("timestamp", 0)
			if signal_time <= last_timestamp:
				continue
			
			last_timestamp = signal_time
			
			# Normalize to format expected by paper trader
			normalized = {
				"type": "signal",
				"ca": signal.get("token"),
				"score": signal.get("score"),
				"conviction_type": signal.get("conviction_type"),
				"price": signal.get("price"),
				"market_cap": signal.get("market_cap"),
				"liquidity": signal.get("liquidity"),
				"volume_24h": signal.get("volume_24h"),
				"change_1h": signal.get("change_1h"),
				"smart_money_detected": signal.get("smart_money_detected"),
				"timestamp": signal_time,
			}
			
			yield normalized
			
		except json.JSONDecodeError as e:
			print(f"⚠️ Invalid JSON signal in Redis: {e}")
			continue
		except Exception as e:
			print(f"⚠️ Redis read error: {e}")
			time.sleep(2)
			continue


def follow_decisions(start_at_end: bool = True) -> Iterator[Dict[str, str]]:
	"""Yield normalized events from stdout.log in near-real-time (LEGACY).
	
	⚠️ DEPRECATED: Use follow_signals_redis() for real-time signal consumption.
	This method polls a log file and may have stale data.

	Events:
	- {type: 'final', ca, final:int, prelim:int, vel:int}
	- {type: 'pass_strict_smart', ca}
	- {type: 'reject_junior', ca}
	"""
	path = BOT_STDOUT_LOG
	with open(path, "r", errors="ignore") as f:
		if start_at_end:
			f.seek(0, 2)
		while True:
			line = f.readline()
			if not line:
				time.sleep(0.2)
				continue
			m = _FINAL_RE.search(line)
			if m:
				ca = m.group(1)
				if not _valid_ca(ca):
					continue
				yield {
					"type": "final",
					"ca": ca,
					"final": m.group(2),
					"prelim": m.group(4),
					"vel": m.group(5),
				}
				continue
			m = _PASS_RE.search(line)
			if m:
				ca = m.group(1)
				if not _valid_ca(ca):
					continue
				yield {"type": "pass_strict_smart", "ca": ca}
				continue
			m = _REJECT_RE.search(line)
			if m:
				ca = m.group(1)
				if not _valid_ca(ca):
					continue
				yield {"type": "reject_junior", "ca": ca}


