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
	
	# Track processed signals to avoid true duplicates
	# Use OrderedDict for FIFO eviction (set.pop() removes random element!)
	from collections import OrderedDict
	processed_tokens: OrderedDict = OrderedDict()
	
	while True:
		try:
			# BRPOP: Blocking right pop - waits for new signals
			# Returns: [list_name, json_payload] or None on timeout
			# Try both queue names - callsbot:signal_queue (ATM) and trading_signals (legacy)
			# KNOWN LIMITATION (2026-05-17): signal_queue.py uses lpush (stack order)
			# while we consume with brpop (right-pop = FIFO order). The in-memory
			# heap's score-based priority ordering is only maintained within the
			# running process. After a restart, signals replay in FIFO order from
			# Redis, not score order. Accepted trade-off at current scale. To fix,
			# migrate Redis persistence to a Sorted Set (ZADD/ZPOPMAX).
			result = _redis_client.brpop(["callsbot:signal_queue", "trading_signals"], timeout=block_timeout)
			
			if result is None:
				# Timeout - no new signals, continue waiting
				continue
			
			queue_name, payload = result
			signal = json.loads(payload)
			
			# Get token and timestamp - handle both ATM format and legacy format
			token = signal.get("token_address") or signal.get("token", "unknown")
			# Try both 'timestamp' and 'ts' fields, parse ISO format if needed
			signal_time = signal.get("timestamp") or signal.get("ts")
			if signal_time and isinstance(signal_time, str):
				try:
					from datetime import datetime
					dt = datetime.fromisoformat(signal_time.replace('Z', '+00:00'))
					signal_time = dt.timestamp()
				except:
					signal_time = time.time()  # Assume fresh if parse fails
			elif not signal_time:
				signal_time = time.time()  # Assume fresh if no timestamp
			age_seconds = time.time() - signal_time
			
			# Skip if this signal is too old (>10 minutes) to prevent stale trades
			if age_seconds > 600:  # 10 minutes
				print(f"[DEBUG] Skipping stale signal: {token[:8]}... (age: {age_seconds/60:.1f} minutes)", flush=True)
				continue
			
			# Skip true duplicates (same token seen recently)
			if token in processed_tokens:
				print(f"[DEBUG] Skipping duplicate signal: {token[:8]}...", flush=True)
				continue
			
			# Add to processed tracker (keep last 1000 to prevent memory bloat)
			# OrderedDict preserves insertion order so eviction removes the TRUE oldest
			processed_tokens[token] = True
			if len(processed_tokens) > 1000:
				processed_tokens.popitem(last=False)  # Remove oldest (FIFO)
			
			print(f"[DEBUG] Processing fresh signal: {token[:8]}... (age: {age_seconds:.0f}s)", flush=True)
			
			# Normalize to format expected by paper trader
			# Handle both ATM format (token_address, raw_score, atm_meta) and legacy format
			atm_meta = signal.get("atm_meta") or {}
			score = signal.get("raw_score") or signal.get("final_score") or 0
			
			normalized = {
				"type": "signal",
				"ca": token,
				"score": score,
				"final_score": score,
				"conviction_type": signal.get("conviction_type"),
				"price": atm_meta.get("price_usd") or signal.get("price"),
				"market_cap": atm_meta.get("market_cap_usd") or signal.get("market_cap"),
				"liquidity": signal.get("liquidity"),
				"volume_24h": signal.get("volume_24h"),
				"change_1h": atm_meta.get("price_change", {}).get("1h") or signal.get("change_1h"),
				"smart_money_detected": signal.get("smart_money_detected"),
				"timestamp": signal_time,
				"atm_meta": atm_meta,  # Pass through for trader use
				"source": signal.get("source"),
			}
			
			yield normalized
			
		except json.JSONDecodeError as e:
			print(f"⚠️ Invalid JSON signal in Redis: {e}")
			continue
		except Exception as e:
			print(f"⚠️ Redis read error: {e}")
			time.sleep(2)
			continue




# Legacy follow_decisions() removed (2026-05-17 refactor).
# It was a deprecated stdout.log file-tailer that has been fully replaced
# by follow_signals_redis() for real-time Redis-based signal consumption.
