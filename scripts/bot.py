# bot.py
import time
import atexit
import signal
import sys
import os
from datetime import datetime
from typing import Optional
from app.logger_utils import log_process, log_heartbeat, mirror_stdout_line
from app.toggles import signals_enabled
from app.storage import init_db
from app.notify import send_telegram_alert
from app.signal_processor import SignalProcessor

# Ensure project root is importable when running this script directly
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Ensure stdout/stderr can print emojis on Windows terminals
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# REMOVED: Redundant functions - relay functionality and tx_has_smart_money now in SignalProcessor
# These stub functions kept for backward compatibility only if referenced elsewhere
def relay_enabled() -> bool:
    return False

def relay_contract_address_sync(*_args, **_kwargs) -> bool:
    return False

# OPTIMIZED: Use SignalProcessor for all feed processing (removed 870 lines of duplicate logic)

# Optional Prometheus metrics (enable with CALLSBOT_METRICS_ENABLED=true)
METRICS_ENABLED = (os.getenv("CALLSBOT_METRICS_ENABLED", "false").strip().lower() == "true")
METRICS_PORT_ENV = os.getenv("CALLSBOT_METRICS_PORT")
_metrics = {"enabled": False}
_metrics_server_started = False

# Don't start metrics server during tests (pytest sets PYTEST_CURRENT_TEST)
IS_TESTING = "PYTEST_CURRENT_TEST" in os.environ

if (METRICS_ENABLED or METRICS_PORT_ENV) and not IS_TESTING:
    try:
        from prometheus_client import Counter, Gauge, start_http_server
        _port = 9108
        try:
            if METRICS_PORT_ENV:
                _port = int(METRICS_PORT_ENV)
        except Exception:
            _port = 9108
        _addr = os.getenv("CALLSBOT_METRICS_ADDR", "127.0.0.1")
        start_http_server(port=_port, addr=_addr)
        _metrics_server_started = True
        _metrics["processed_total"] = Counter("callsbot_processed_total", "Total processed transactions")
        _metrics["alerts_total"] = Counter("callsbot_alerts_total", "Total alerts sent")
        _metrics["feed_items"] = Gauge("callsbot_feed_items", "Items received in last feed cycle")
        _metrics["api_calls_saved"] = Gauge("callsbot_api_calls_saved", "API calls saved due to prelim gating")
        _metrics["cooldowns_total"] = Counter("callsbot_cooldowns_total", "Cooldowns due to rate limit/quota", ["reason"])
        _metrics["last_cycle_type"] = Gauge("callsbot_last_cycle_type", "Last cycle type: 1=smart, 0=general")
        _metrics["enabled"] = True
    except Exception:
        _metrics["enabled"] = False

# Global flag for graceful shutdown
shutdown_flag = False

# Global lock handle to keep singleton lock alive for process lifetime
_singleton_lock_file = None


def _out(msg: str) -> None:
	try:
		print(msg)
		mirror_stdout_line(str(msg))
	except Exception:
		pass


# OPTIMIZED: Removed tx_has_smart_money - moved to SignalProcessor


def _release_singleton_lock(lock_path: str) -> None:
    global _singleton_lock_file
    try:
        if _singleton_lock_file is not None:
            try:
                # On Windows, unlocking is implicit on close; on Unix, flock releases on close
                _singleton_lock_file.close()
            except Exception:
                pass
            _singleton_lock_file = None
        # Best-effort cleanup of the lock file itself
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except Exception:
            pass
    except Exception:
        pass


def acquire_singleton_lock() -> bool:
    """
    Enforce a single running instance via a cross-platform advisory file lock.
    Returns True if lock acquired; False if another instance holds the lock.
    """
    global _singleton_lock_file
    # If already acquired in this process, treat as success
    try:
        if _singleton_lock_file is not None:
            return True
    except Exception:
        pass
    lock_path = os.path.join(PROJECT_ROOT, "var", "bot.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)

    # Clean up stale lock if process is dead
    try:
        if os.path.exists(lock_path):
            with open(lock_path, "r", encoding="utf-8", errors="ignore") as f_old:
                content = f_old.read().strip()
                if "@" in content:
                    pid_str = content.split("@")[0].strip()
                    try:
                        old_pid = int(pid_str)
                        # Check if process alive
                        try:
                            import psutil  # type: ignore
                            alive = psutil.Process(old_pid).is_running()
                        except Exception:
                            alive = True  # best effort; if psutil missing, skip removal
                        if not alive:
                            try:
                                os.remove(lock_path)
                            except Exception:
                                pass
                    except Exception:
                        pass
    except Exception:
        pass

    # Open or create the lock file in binary mode
    f = open(lock_path, "a+b")

    # Ensure at least 1 byte exists for Windows region locking
    try:
        f.seek(0, os.SEEK_END)
        if f.tell() == 0:
            f.write(b"\0")
            f.flush()
    except Exception:
        pass

    try:
        try:
            # Prefer POSIX flock when available
            import fcntl  # type: ignore
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                try:
                    # Read owner PID for diagnostics
                    f.seek(0)
                    owner = f.read(64).decode("utf-8", errors="ignore").strip()
                    mirror_stdout_line(f"Lock held by PID: {owner}")
                except Exception:
                    pass
                f.close()
                return False
        except ImportError:
            # Windows: use msvcrt locking on the first byte
            import msvcrt  # type: ignore
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                try:
                    f.seek(0)
                    owner = f.read(64).decode("utf-8", errors="ignore").strip()
                    mirror_stdout_line(f"Lock held by PID: {owner}")
                except Exception:
                    pass
                f.close()
                return False
        # Write PID and hostname for debugging purposes (fixed-length header)
        try:
            f.seek(0)
            ident = f"{os.getpid()}@{os.uname().nodename if hasattr(os, 'uname') else 'host'}"
            pid_bytes = ident.encode("utf-8")
            f.write(pid_bytes[:64].ljust(64, b" "))
            f.flush()
        except Exception:
            pass
        _singleton_lock_file = f
        # Register cleanup
        atexit.register(_release_singleton_lock, lock_path)
        return True
    except Exception:
        try:
            f.close()
        except Exception:
            pass
        return False


def signal_handler(sig, frame):
    global shutdown_flag
    _out("\nShutdown signal received. Gracefully stopping bot...")
    shutdown_flag = True


def initialize_bot() -> bool:
	"""Setup signals, enforce singleton, init DB, and emit startup notification."""
	from app.config_unified import HIGH_CONFIDENCE_SCORE, FETCH_INTERVAL
	try:
		signal.signal(signal.SIGINT, signal_handler)
		signal.signal(signal.SIGTERM, signal_handler)
	except Exception:
		pass
	if not acquire_singleton_lock():
		_out("Another bot instance is already running. Exiting.")
		return False
	try:
		init_db()
		# ensure_indices() # Disabled - function not available yet
		_out("Database initialized successfully")
	except Exception as e:
		_out(f"Failed to initialize database: {e}")
		return False
	
	# Start Telegram signal aggregator monitoring
	# TEMPORARILY DISABLED: Conflicts with Telethon notifier (session lock)
	# TODO: Fix session sharing issue
	# try:
	# 	import asyncio
	# 	from app.signal_aggregator import start_monitoring
	# 	loop = asyncio.new_event_loop()
	# 	asyncio.set_event_loop(loop)
	# 	# Start monitoring in background thread
	# 	import threading
	# 	def run_aggregator():
	# 		loop.run_until_complete(start_monitoring())
	# 	aggregator_thread = threading.Thread(target=run_aggregator, daemon=True)
	# 	aggregator_thread.start()
	# 	_out("✅ Telegram signal aggregator started - monitoring 13 groups")
	# except Exception as e:
	# 	_out(f"⚠️ Failed to start signal aggregator: {e}")
	# 	# Don't fail bot startup if aggregator fails
	_out("ℹ️  Signal aggregator disabled (session conflict - will be fixed)")
	# Startup message
	startup_message = (
		"<b>SMART MONEY Enhanced Memecoin Bot Started</b>\n\n"
		f"<b>Start Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
		f"<b>Score Threshold:</b> {HIGH_CONFIDENCE_SCORE}/10\n"
		f"<b>Fetch Interval:</b> {FETCH_INTERVAL} seconds\n"
		"<b>Features:</b> Smart Money Detection + Enhanced Analysis\n"
		"<b>Status:</b> Monitoring Solana memecoin activity"
	)
	try:
		send_telegram_alert(startup_message)
	except Exception:
		pass
	try:
		log_process({
			"type": "startup",
			"pid": os.getpid(),
			"fetch_interval": FETCH_INTERVAL,
			"dry_run": bool(os.getenv('DRY_RUN', 'false').strip().lower() == 'true'),
			"kill_switch": bool(os.getenv('KILL_SWITCH', 'false').strip().lower() == 'true'),
		})
	except Exception:
		pass
	return True


def handle_cooldown(feed_error: Optional[str], retry_after_sec: int) -> None:
	"""Sleep with logging and metrics when upstream signals a cooldown event."""
	from app.config_unified import FETCH_INTERVAL
	if feed_error == "quota_exceeded" and retry_after_sec <= 0:
		retry_after_sec = max(300, FETCH_INTERVAL)
	elif retry_after_sec <= 0:
		retry_after_sec = max(60, FETCH_INTERVAL)
	_out(f"Cielo {'quota' if feed_error == 'quota_exceeded' else 'rate limit'} hit. Cooling down for {retry_after_sec}s")
	try:
		log_process({
			"type": "cooldown",
			"pid": os.getpid(),
			"reason": feed_error,
			"retry_after_sec": retry_after_sec,
		})
	except Exception:
		pass
	if _metrics.get("enabled"):
		try:
			_metrics["cooldowns_total"].labels(reason=str(feed_error)).inc()
		except Exception:
			pass
	for _ in range(retry_after_sec):
		if shutdown_flag:
			break
		time.sleep(1)
                

# OPTIMIZED: Removed _select_token_and_usd - logic moved to FeedTransaction model

# OPTIMIZED: Removed 870-line process_feed_item_legacy function - replaced with SignalProcessor
# All signal detection logic is now in app/signal_processor.py (single source of truth)

def run_periodic_tasks(last_track_time: float) -> float:
	"""
	Run periodic maintenance tasks.
	
	Currently minimal - tracking functions are handled separately via dedicated scripts.
	Returns updated last_track_time for future use.
	"""
	# NOTE: Token performance tracking is handled by scripts/track_performance.py
	# This function is kept for future periodic maintenance tasks
	return last_track_time


def run_bot():
    # Emergency kill switch check
    if os.getenv("KILL_SWITCH", "false").strip().lower() == "true":
        _out("KILL_SWITCH active. Exiting bot run loop.")
        return

    # Helper imports kept local to reduce import-time requirements
    from app.fetch_feed import fetch_solana_feed
    try:
        from app.fetch_feed import _fallback_feed_from_geckoterminal, _fallback_feed_from_dexscreener
    except Exception:
        _fallback_feed_from_geckoterminal = None  # type: ignore
        _fallback_feed_from_dexscreener = None  # type: ignore
    try:
        from app.config_unified import CURRENT_GATES
    except Exception:
        CURRENT_GATES = None

    # Initialize bot (signals, lock, DB, startup message)
    if not initialize_bot():
        return
    
    cursor_general = None
    cursor_smart = None
    processed_count = 0
    alert_count = 0
    # last_alert_time was unused; keep for future rate-limit logic only if needed
    api_calls_saved = 0  # Track credit optimization
    session_alerted_tokens = set()
    last_track_time = 0

    from app.config_unified import HIGH_CONFIDENCE_SCORE, FETCH_INTERVAL
    _out("SMART MONEY ENHANCED SOLANA MEMECOIN BOT STARTED")
    _out(f"Configuration: Score threshold = {HIGH_CONFIDENCE_SCORE}, Fetch interval = {FETCH_INTERVAL}s")
    if 'CURRENT_GATES' in globals() and CURRENT_GATES:
        gm = CURRENT_GATES.get('GATE_MODE')
        _out(f"Gate Mode: {gm} | Gates: score>={CURRENT_GATES.get('HIGH_CONFIDENCE_SCORE')}, liq>={CURRENT_GATES.get('MIN_LIQUIDITY_USD')}, vol24>={CURRENT_GATES.get('VOL_24H_MIN_FOR_ALERT')}, mcap<={CURRENT_GATES.get('MAX_MARKET_CAP_FOR_DEFAULT_ALERT')}, vol/mcap>={CURRENT_GATES.get('VOL_TO_MCAP_RATIO_MIN')}")
    _out("Features: Smart Money Detection + Enhanced Scoring + Detailed Analysis")
    _out("Smart-money cycle enabled (top_wallets=true, min_wallet_pnl=1000)")
    _out("Adaptive cooldown on Cielo rate limits is enabled")
    
    # Send startup notification
    startup_message = (
        "<b>SMART MONEY Enhanced Memecoin Bot Started</b>\n\n"
        f"<b>Start Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"<b>Score Threshold:</b> {HIGH_CONFIDENCE_SCORE}/10\n"
        f"<b>Fetch Interval:</b> {FETCH_INTERVAL} seconds\n"
        "<b>Features:</b> Smart Money Detection + Enhanced Analysis\n"
        "<b>Status:</b> Monitoring Solana memecoin activity"
    )
    send_telegram_alert(startup_message)
    try:
        log_process({
            "type": "startup",
            "pid": os.getpid(),
            "fetch_interval": FETCH_INTERVAL,
            "gates": CURRENT_GATES or {},
            "dry_run": bool(os.getenv('DRY_RUN', 'false').strip().lower() == 'true'),
            "kill_switch": bool(os.getenv('KILL_SWITCH', 'false').strip().lower() == 'true'),
        })
    except Exception:
        pass
    
    # OPTIMIZED: Initialize SignalProcessor (replaces duplicate logic)
    processor = SignalProcessor({})
    
    is_smart_cycle = False
    while not shutdown_flag:
        try:
            # Respect signals toggle: if disabled, idle-loop while keeping heartbeats
            if os.getenv("KILL_SWITCH", "false").strip().lower() == "true":
                _out("KILL_SWITCH active. Sleeping...")
                for _ in range(max(5, FETCH_INTERVAL // 2)):
                    if shutdown_flag:
                        break
                    time.sleep(1)
                continue
            if not signals_enabled():
                _out("Signals disabled via toggle. Sleeping...")
                for _ in range(max(5, FETCH_INTERVAL // 2)):
                    if shutdown_flag:
                        break
                    time.sleep(1)
                continue

            # Alternate between general feed and smart-money-only feed
            if is_smart_cycle:
                feed = fetch_solana_feed(cursor_smart, smart_money_only=True)
                cursor_smart = feed.get("next_cursor")
            else:
                feed = fetch_solana_feed(cursor_general, smart_money_only=False)
                cursor_general = feed.get("next_cursor")

            # Handle adaptive cooldown on rate limit / quota exhaust
            feed_error = feed.get("error")
            if feed_error in ("rate_limited", "quota_exceeded"):
                retry_after_sec = int(feed.get("retry_after_sec") or 0)
                handle_cooldown(feed_error, retry_after_sec)
                is_smart_cycle = not is_smart_cycle
                continue

            # Log the number of items returned this cycle for visibility
            items_count = len(feed.get("transactions", []))
            _out(f"FEED ITEMS: {items_count}")
            try:
                from app.metrics import set_queue_len
                set_queue_len(items_count)
            except Exception:
                pass
            try:
                log_heartbeat(os.getpid(), extra={
                    "cycle": ("smart" if is_smart_cycle else "general"),
                    "feed_items": items_count,
                    "processed_count": processed_count,
                    "api_calls_saved": api_calls_saved,
                    "alerts_sent": alert_count,
                })
            except Exception:
                pass
            # Metrics: update gauges for cycle and feed size
            if _metrics.get("enabled"):
                try:
                    _metrics["feed_items"].set(items_count)
                    _metrics["last_cycle_type"].set(1 if is_smart_cycle else 0)
                except Exception:
                    pass
            
            # If upstream feed is empty, attempt local fallbacks to keep signals flowing
            if not feed.get("transactions"):
                _out("No new transactions found")
                fallback_items = []
                try:
                    if _fallback_feed_from_geckoterminal:
                        fallback_items = _fallback_feed_from_geckoterminal(limit=40)
                except Exception:
                    fallback_items = []
                if not fallback_items:
                    try:
                        if _fallback_feed_from_dexscreener:
                            fallback_items = _fallback_feed_from_dexscreener(limit=40, smart_money_only=is_smart_cycle)
                    except Exception:
                        fallback_items = []
                try:
                    _out(f"Fallback items count: {len(fallback_items) if fallback_items else 0}")
                except Exception:
                    pass
                if fallback_items:
                    feed["transactions"] = fallback_items
                    items_count = len(fallback_items)
                    _out(f"Using fallback feed items: {items_count}")
                    try:
                        log_process({
                            "type": "feed_fallback_injected",
                            "count": items_count,
                            "smart_cycle": bool(is_smart_cycle),
                        })
                    except Exception:
                        pass
            
            # OPTIMIZED: Use SignalProcessor for all feed items
            for tx in feed.get("transactions", []):
                try:
                    if shutdown_flag:
                        break
                    
                    # Process feed item using optimized SignalProcessor
                    result = processor.process_feed_item(tx, is_smart_cycle)
                    
                    processed_count += 1
                    
                    # Track API calls saved
                    if result.api_calls_saved:
                        api_calls_saved += result.api_calls_saved
                    
                    # Handle alerts
                    if result.is_alert and result.token_address:
                        session_alerted_tokens.add(result.token_address)
                        alert_count += 1
                    
                except Exception as e:
                    # Don't let one bad transaction crash the entire loop
                    _out(f"Error processing transaction: {e}")
                    try:
                        log_process({
                            "type": "transaction_error",
                            "error": str(e),
                            "token": tx.get("token1_address") or tx.get("token0_address") or "unknown",
                        })
                    except Exception:
                        pass
                    continue

            # Periodic maintenance and tracking
            last_track_time = run_periodic_tasks(last_track_time)

            if not shutdown_flag:
                _out(f"Sleeping for {FETCH_INTERVAL} seconds...")
                for _ in range(FETCH_INTERVAL):
                    if shutdown_flag:
                        break
                    time.sleep(1)
            # flip cycle after sleep
            is_smart_cycle = not is_smart_cycle
                
        except KeyboardInterrupt:
            _out("\nKeyboard interrupt received")
            break
        except Exception as e:
            _out(f"Unexpected error in main loop: {e}")
            _out("Continuing after error...")
            time.sleep(30)  # Wait before retrying
    
    # Send shutdown notification
    shutdown_message = (
        "<b>Solana Memecoin Bot Stopped</b>\n\n"
        f"<b>Stop Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"<b>Total Processed:</b> {processed_count} tokens\n"
        f"<b>Total Alerts Sent:</b> {alert_count}\n"
        "<b>Status:</b> Bot shutdown complete"
    )
    send_telegram_alert(shutdown_message)
    _out(f"Bot stopped gracefully. Processed {processed_count} tokens, sent {alert_count} alerts.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CALLSBOTONCHAIN controller")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("run", help="Run the signals bot (default)")
    webp = sub.add_parser("web", help="Run the dashboard web server")
    webp.add_argument("--host", default=os.getenv("DASH_HOST", "0.0.0.0"))
    webp.add_argument("--port", type=int, default=int(os.getenv("DASH_PORT", "8080")))
    trad = sub.add_parser("trade", help="Run tradingSystem CLI loop (respects web toggle)")
    args = parser.parse_args()
    cmd = args.cmd or "run"
    try:
        if cmd == "web":
            from src.server import create_app
            app = create_app()
            app.run(host=args.host, port=args.port, debug=False)
        elif cmd == "trade":
            from tradingSystem.cli_optimized import run as trade_run
            trade_run()
        else:
            run_bot()
    except Exception as e:
        _out(f"Fatal error: {e}")
        sys.exit(1)
