# bot.py
import time
import atexit
import signal
import sys
import os
from datetime import datetime

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

try:
    from tools.relay import relay_contract_address_sync, relay_enabled
except Exception:
    def relay_enabled() -> bool:
        return False
    def relay_contract_address_sync(*_args, **_kwargs) -> bool:
        return False
from app.logger_utils import log_alert, log_tracking, log_process, log_heartbeat, mirror_stdout_line
import html
from app.toggles import signals_enabled
from app.logger_utils import log_process

# Optional Prometheus metrics (enable with CALLSBOT_METRICS_ENABLED=true)
METRICS_ENABLED = (os.getenv("CALLSBOT_METRICS_ENABLED", "false").strip().lower() == "true")
METRICS_PORT_ENV = os.getenv("CALLSBOT_METRICS_PORT")
_metrics = {"enabled": False}
if METRICS_ENABLED or METRICS_PORT_ENV:
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

def run_bot():
    global shutdown_flag
    # Emergency kill switch check
    if os.getenv("KILL_SWITCH", "false").strip().lower() == "true":
        _out("KILL_SWITCH active. Exiting bot run loop.")
        return
    # Lazy import all config-dependent modules to avoid requiring secrets in web-only mode
    from app.fetch_feed import fetch_solana_feed
    try:
        from app.fetch_feed import _fallback_feed_from_geckoterminal, _fallback_feed_from_dexscreener
    except Exception:
        _fallback_feed_from_geckoterminal = None
        _fallback_feed_from_dexscreener = None
    from app.analyze_token import (
        get_token_stats,
        score_token,
        calculate_preliminary_score,
        check_senior_strict,
        check_junior_strict,
        check_senior_nuanced,
        check_junior_nuanced,
    )
    from app.notify import send_telegram_alert
    from app.storage import (
        init_db,
        has_been_alerted,
        mark_as_alerted,
        record_token_activity,
        get_token_velocity,
        should_fetch_detailed_stats,
        ensure_indices,
        prune_old_activity,
        get_alerted_tokens_batch,
        update_token_tracking,
        get_tracking_snapshot,
    )
    from config import HIGH_CONFIDENCE_SCORE, FETCH_INTERVAL, DEBUG_PRELIM, TELEGRAM_ALERT_MIN_INTERVAL, TRACK_INTERVAL_MIN, TRACK_BATCH_SIZE, REQUIRE_SMART_MONEY_FOR_ALERT, REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT
    from config import (
        MIN_LIQUIDITY_USD,
        VOL_24H_MIN_FOR_ALERT,
        VOL_TO_MCAP_RATIO_MIN,
        MCAP_MICRO_MAX,
        MAX_MARKET_CAP_FOR_DEFAULT_ALERT,
        MOMENTUM_1H_STRONG,
        LARGE_CAP_MOMENTUM_GATE_1H,
        MAX_TOP10_CONCENTRATION,
        REQUIRE_MINT_REVOKED,
        REQUIRE_LP_LOCKED,
        ALLOW_UNKNOWN_SECURITY,
    )
    try:
        from config import CURRENT_GATES
    except Exception:
        CURRENT_GATES = None
    
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Enforce single-instance execution
    if not acquire_singleton_lock():
        _out("Another bot instance is already running. Exiting.")
        return

    try:
        init_db()  # ensure database is initialized
        ensure_indices()
        _out("Database initialized successfully")
    except Exception as e:
        _out(f"Failed to initialize database: {e}")
        return
    
    cursor_general = None
    cursor_smart = None
    processed_count = 0
    alert_count = 0
    last_alert_time = 0
    api_calls_saved = 0  # Track credit optimization
    session_alerted_tokens = set()
    last_track_time = 0
    
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
        f"<b>SMART MONEY Enhanced Memecoin Bot Started</b>\n\n"
        f"<b>Start Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"<b>Score Threshold:</b> {HIGH_CONFIDENCE_SCORE}/10\n"
        f"<b>Fetch Interval:</b> {FETCH_INTERVAL} seconds\n"
        f"<b>Features:</b> Smart Money Detection + Enhanced Analysis\n"
        f"<b>Status:</b> Monitoring Solana memecoin activity"
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
                if feed_error == "quota_exceeded" and retry_after_sec <= 0:
                    # Fall back to a conservative cooldown window when quota fully exhausted
                    retry_after_sec = max(300, FETCH_INTERVAL)  # at least 5 minutes
                elif retry_after_sec <= 0:
                    retry_after_sec = max(60, FETCH_INTERVAL)
                _out(f"Cielo {('quota' if feed_error=='quota_exceeded' else 'rate limit')} hit. Cooling down for {retry_after_sec}s")
                try:
                    log_process({
                        "type": "cooldown",
                        "pid": os.getpid(),
                        "reason": feed_error,
                        "retry_after_sec": retry_after_sec,
                    })
                except Exception:
                    pass
                for _ in range(retry_after_sec):
                    if shutdown_flag:
                        break
                    time.sleep(1)
                # Do not process this cycle; flip cycle to avoid hammering the same endpoint
                is_smart_cycle = not is_smart_cycle
                # Metrics: record cooldown
                if _metrics.get("enabled"):
                    try:
                        _metrics["cooldowns_total"].labels(reason=str(feed_error)).inc()
                    except Exception:
                        pass
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
                _out(f"No new transactions found")
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
            
            def _tx_has_smart_money(tx_obj: dict, smart_cycle: bool) -> bool:  
                """Looser detection to restore earlier behavior: smart IF cycle OR any strong hint."""
                try:
                    if smart_cycle:
                        return True
                    if any(bool(tx_obj.get(k)) for k in ("smart_money","is_smart","isTopWallet")):
                        return True
                    top_wallets = tx_obj.get("top_wallets")
                    if isinstance(top_wallets, (list, tuple)) and len(top_wallets) > 0:
                        return True
                    for key in ("wallet_pnl","min_wallet_pnl","trader_pnl","pnl_usd"):
                        val = tx_obj.get(key)
                        if isinstance(val, (int,float)) and val >= 1000:
                            return True
                    labels = tx_obj.get("labels") or tx_obj.get("wallet_labels")
                    if labels:
                        if isinstance(labels,(list,tuple)):
                            label_text = ",".join(str(x) for x in labels).lower()
                        else:
                            label_text = str(labels).lower()
                        if any(tag in label_text for tag in ("smart","top","alpha","elite")):
                            return True
                    return False
                except Exception:
                    return bool(smart_cycle)

            for tx in feed.get("transactions", []):
                if shutdown_flag:
                    break
                
                # Map Cielo feed fields → token + usd
                # Prefer the non-SOL leg as the token address; choose its USD amount
                sol_mint = "So11111111111111111111111111111111111111112"
                t0 = tx.get("token0_address")
                t1 = tx.get("token1_address")
                t0_usd = tx.get("token0_amount_usd", 0) or 0
                t1_usd = tx.get("token1_amount_usd", 0) or 0

                token_address = None
                usd_value = 0
                if t0 == sol_mint and t1:
                    token_address = t1
                    usd_value = t1_usd
                elif t1 == sol_mint and t0:
                    token_address = t0
                    usd_value = t0_usd
                else:
                    # Neither leg is SOL: pick the leg with higher USD
                    if t1_usd >= t0_usd:
                        token_address = t1
                        usd_value = t1_usd
                    else:
                        token_address = t0
                        usd_value = t0_usd
                
                # attach usd_value into tx for preliminary scoring
                tx["usd_value"] = usd_value
                smart_involved = _tx_has_smart_money(tx, is_smart_cycle)
                # Treat fallback-origin signals as smart-involved during smart cycle to keep parity
                if tx.get('tx_type', '').endswith('_fallback') and is_smart_cycle:
                    smart_involved = True

                if not token_address or usd_value == 0:
                    continue

                processed_count += 1
                if _metrics.get("enabled"):
                    try:
                        _metrics["processed_total"].inc()
                    except Exception:
                        pass

                if token_address in session_alerted_tokens or has_been_alerted(token_address):
                    continue  # skip previously alerted tokens

                try:
                    # STEP 1: Calculate preliminary score (NO API CALLS)
                    preliminary_score = calculate_preliminary_score(tx, smart_money_detected=smart_involved)
                    if DEBUG_PRELIM:
                        _out("    ⤷ prelim_debug: " + str({
                            'usd_value': round(tx.get('usd_value', 0) or 0, 2),
                            'token0_usd': round(tx.get('token0_amount_usd', 0) or 0, 2),
                            'token1_usd': round(tx.get('token1_amount_usd', 0) or 0, 2),
                            'tx_type': tx.get('tx_type'),
                            'dex': tx.get('dex')
                        }))
                    
                    # STEP 2: Record activity for velocity tracking
                    # Attempt to capture trader address for community velocity
                    trader = tx.get('from') or tx.get('wallet')
                    record_token_activity(
                        token_address, 
                        usd_value, 
                        1,  # Transaction count (individual tx)
                        smart_involved,
                        preliminary_score,
                        trader
                    )
                    
                    # STEP 3: CREDIT-EFFICIENT DECISION - Only fetch detailed stats if warranted
                    is_fallback_tx = tx.get('tx_type', '').endswith('_fallback')
                    if (not is_fallback_tx) and (not should_fetch_detailed_stats(token_address, preliminary_score)):
                        _out(f"Token {token_address} prelim: {preliminary_score}/10 (skipped detailed analysis)")
                        api_calls_saved += 1  # Track credits saved
                        if _metrics.get("enabled"):
                            try:
                                _metrics["api_calls_saved"].set(api_calls_saved)
                            except Exception:
                                pass
                        continue
                    
                    # STEP 4: EXPENSIVE API CALL - Only for high-potential tokens
                    _out(f"FETCHING DETAILED STATS for {token_address[:8]} (prelim: {preliminary_score}/10)")
                    stats = get_token_stats(token_address)
                    if not stats:
                        continue

                    # STEP 5: Enhanced scoring with velocity bonus
                    velocity_data = get_token_velocity(token_address, minutes_back=15)
                    velocity_bonus = velocity_data['velocity_score'] if velocity_data else 0
                    
                    score, scoring_details = score_token(stats, smart_money_detected=smart_involved, token_address=token_address)
                    
                    # Add velocity bonus
                    if velocity_bonus > 0:
                        score = min(score + (velocity_bonus // 2), 10)  # Half velocity score as bonus
                        scoring_details.append(f"Velocity: +{velocity_bonus//2} ({velocity_data['observations']} observations)")
                        # Community (unique traders) bonus
                        ut = velocity_data.get('unique_traders', 0)
                        if ut > 25:
                            score = min(score + 2, 10)
                            scoring_details.append(f"Community: +2 ({ut} unique traders in window)")
                        elif ut > 10:
                            score = min(score + 1, 10)
                            scoring_details.append(f"Community: +1 ({ut} unique traders in window)")
                    
                    _out(f"Token {token_address} FINAL: {score}/10 (prelim: {preliminary_score}, velocity: +{velocity_bonus//2})")
                    
                    # Optional post-score meta gates (smart-money/velocity)
                    if REQUIRE_SMART_MONEY_FOR_ALERT and not smart_involved:
                        continue
                    if REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT:
                        if (velocity_bonus // 2) < (REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT // 2):
                            continue

                    # --- PRIMARY EVALUATION (safety first)
                    if not check_senior_strict(stats, token_address):
                        _out(f"REJECTED (Senior Strict): {token_address}")
                        continue

                    jr_strict_ok = check_junior_strict(stats, score)

                    # --- DECISION: smart-money requires strict; others may fallback to nuanced junior
                    alert_token = False
                    conviction_type = None

                    if smart_involved:
                        if jr_strict_ok:
                            _out(f"PASSED (Strict + Smart Money): {token_address}")
                            alert_token = True
                            conviction_type = "High Confidence (Smart Money)"
                        else:
                            _out(f"REJECTED (Junior Strict): {token_address}")
                            continue
                    else:
                        if jr_strict_ok:
                            _out(f"PASSED (Strict Rules): {token_address}")
                            alert_token = True
                            conviction_type = "High Confidence (Strict)"
                        else:
                            # Fallback: keep strict safety, allow nuanced junior metrics
                            _out(f"ENTERING DEBATE (No Smart Money; Strict-Junior failed): {token_address}")
                            if check_junior_nuanced(stats, score):
                                _out(f"PASSED (Nuanced Junior): {token_address}")
                                alert_token = True
                                conviction_type = "Nuanced Conviction"
                            else:
                                _out(f"REJECTED (Nuanced Debate): {token_address}")
                                continue

                    if alert_token:
                        # Enhanced alert with conviction type
                        alert_type = "HIGH-CONFIDENCE" if smart_involved else "NUANCED"
                        price = stats.get('price_usd', 0)
                        change_1h = stats.get('change', {}).get('1h', 0)
                        change_24h = stats.get('change', {}).get('24h', 0)
                        # Metrics used in message and logging
                        volume_24h = stats.get('volume', {}).get('24h', {}).get('volume_usd', 0)
                        market_cap = stats.get('market_cap_usd', 0)
                        liquidity = (
                            stats.get('liquidity_usd')
                            or stats.get('liquidity', {}).get('usd')
                            or 0
                        )
                        name = html.escape(stats.get('name') or "Token")
                        symbol = html.escape(stats.get('symbol') or "?")
                        # Add cache-busting param so Telegram refreshes the preview image
                        chart_link = f"https://dexscreener.com/solana/{token_address}?t={int(time.time())}"
                        swap_link = (
                            f"https://raydium.io/swap/?inputMint=So11111111111111111111111111111111111111112&outputMint={token_address}"
                        )
                        # Safety/context badges based on stats
                        security = stats.get('security', {}) or {}
                        liq_obj = stats.get('liquidity', {}) or {}
                        holders_obj = stats.get('holders', {}) or {}
                        mint_revoked = security.get('is_mint_revoked')
                        lp_locked = (
                            liq_obj.get('is_lp_locked')
                            or liq_obj.get('lock_status') in ("locked", "burned")
                            or liq_obj.get('is_lp_burned')
                        )
                        top10 = holders_obj.get('top_10_concentration_percent') or holders_obj.get('top10_percent') or 0
                        try:
                            top10 = float(top10)
                        except Exception:
                            top10 = 0
                        badges = []
                        if mint_revoked is True:
                            badges.append("✅ Mint Revoked")
                        elif mint_revoked is False:
                            badges.append("⚠️ Mintable")
                        if lp_locked is True:
                            badges.append("✅ LP Locked/Burned")
                        elif lp_locked is False:
                            badges.append("⚠️ LP Unlocked")
                        if top10:
                            if top10 > 40:
                                badges.append(f"⚠️ Top10 {top10:.1f}%")
                            else:
                                badges.append(f"Top10 {top10:.1f}%")
                        badges_text = " | ".join(badges) if badges else ""

                        # Requested clean template with CA as plain text (non-link)
                        parts = []
                        parts.append(f"<b>{name} (${symbol})</b>\n\n")
                        parts.append("Fresh signal on Solana.\n\n")
                        parts.append(f"💰 <b>MCap:</b> ${market_cap:,.0f}\n")
                        parts.append(f"💧 <b>Liquidity:</b> ${liquidity:,.0f}\n")
                        if badges_text:
                            parts.append(f"{badges_text}\n")
                        parts.append(f"📈 <b>Chart:</b> <a href='{chart_link}'>DexScreener</a>\n")
                        parts.append(f"🔁 <b>Swap:</b> <a href='{swap_link}'>Raydium</a>\n\n")
                        parts.append(f"{html.escape(token_address)}\n")
                        parts.append("━━━━━━━━━━━━━━━\n")
                        parts.append(f"📊 <b>Score:</b> {score}/10\n")
                        parts.append(f"💸 <b>24h Vol:</b> ${volume_24h:,.0f}\n")
                        parts.append(f"💰 <b>Price:</b> ${price:.8f}\n")
                        parts.append(f"⏱ <b>1h Change:</b> {change_1h:+.1f}%\n")
                        parts.append(f"📆 <b>24h Change:</b> {change_24h:+.1f}%\n")
                        parts.append("━━━━━━━━━━━━━━━")
                        message = "".join(parts)
                        message += f"\n<b>Conviction:</b> {conviction_type}"
                        
                        # no extra smart money line in lean mode
                        
                        # Add detailed scoring breakdown
                        message += f"\n<b>Scoring Analysis:</b>\n"
                        for detail in scoring_details[:4]:  # Top 4 scoring factors
                            # Remove emojis from scoring details
                            clean_detail = detail.replace("✅ ", "").replace("⚡ ", "").replace("🟡 ", "").replace("❌ ", "")
                            message += f"  - {clean_detail}\n"
                        
                        message += f"\n<b>Alert Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        
                        # Throttle alerts if configured
                        if TELEGRAM_ALERT_MIN_INTERVAL and TELEGRAM_ALERT_MIN_INTERVAL > 0:
                            now = time.time()
                            delta = now - last_alert_time
                            if last_alert_time > 0 and delta < TELEGRAM_ALERT_MIN_INTERVAL:
                                wait_s = int(TELEGRAM_ALERT_MIN_INTERVAL - delta)
                                _out(f"Throttling alerts; waiting {wait_s}s before sending")
                                for _ in range(wait_s):
                                    if shutdown_flag:
                                        break
                                    time.sleep(1)
                            last_alert_time = time.time()

                        telegram_ok = False
                        try:
                            if os.getenv('DRY_RUN', 'false').strip().lower() != 'true':
                                telegram_ok = send_telegram_alert(message)
                        except Exception:
                            telegram_ok = False

                        # Baseline metrics for tracking (log alerts regardless of Telegram status)
                        baseline_price = float(price or 0)
                        baseline_mcap = float(market_cap or 0)
                        baseline_liq = float(liquidity or 0)
                        baseline_vol = float(volume_24h or 0)
                        mark_as_alerted(
                            token_address,
                            score,
                            smart_involved,
                            baseline_price,
                            baseline_mcap,
                            baseline_liq,
                            baseline_vol,
                            conviction_type=conviction_type,
                        )
                        try:
                            if relay_enabled():
                                relay_contract_address_sync(token_address)
                        except Exception:
                            pass
                        session_alerted_tokens.add(token_address)
                        alert_count += 1
                        if _metrics.get("enabled"):
                            try:
                                _metrics["alerts_total"].inc()
                            except Exception:
                                pass
                        _out(
                            f"Alert #{alert_count} for token {token_address} (Final: {score}/10, Prelim: {preliminary_score}/10, telegram_ok={telegram_ok})"
                        )
                        try:
                            log_process(
                                {
                                    "type": "alert_sent",
                                    "pid": os.getpid(),
                                    "token": token_address,
                                    "final_score": score,
                                    "prelim_score": preliminary_score,
                                    "conviction_type": conviction_type,
                                    "telegram_ok": bool(telegram_ok),
                                }
                            )
                        except Exception:
                            pass
                        try:
                            # Velocity snapshot at alert time
                            vel_snap = get_token_velocity(token_address, minutes_back=15) or {}
                            # Lightweight score components snapshot (derived from details where possible)
                            score_components = {
                                "smart_money": 3 if is_smart_cycle else 0,
                                "market_cap": None,
                                "volume": None,
                                "momentum": None,
                                "security_penalties": None,
                            }

                            # Enriched safety and gate logging
                            buyers_24 = (stats.get('volume', {}) or {}).get('24h', {}) or {}
                            unique_buyers_24h = buyers_24.get('unique_buyers') or 0
                            unique_sellers_24h = buyers_24.get('unique_sellers') or 0
                            vol_to_mcap_ratio = None
                            try:
                                vol_to_mcap_ratio = (volume_24h or 0) / (market_cap or 1)
                            except Exception:
                                vol_to_mcap_ratio = None

                            # Gate pass/fail snapshot at alert time
                            liq_gate = (baseline_liq or 0) >= (MIN_LIQUIDITY_USD or 0)
                            vol_gate = (baseline_vol or 0) >= (VOL_24H_MIN_FOR_ALERT or 0)
                            vtm_gate = (vol_to_mcap_ratio or 0) >= (VOL_TO_MCAP_RATIO_MIN or 0)
                            mcap_micro_gate = (baseline_mcap or 0) <= (MCAP_MICRO_MAX or float('inf'))
                            top10_gate = True
                            if isinstance(top10, (int, float)) and MAX_TOP10_CONCENTRATION:
                                top10_gate = float(top10) <= float(MAX_TOP10_CONCENTRATION)

                            log_alert(
                                {
                                    "token": token_address,
                                    "name": name,
                                    "symbol": symbol,
                                    "final_score": score,
                                    "prelim_score": preliminary_score,
                                    "velocity_bonus": int(velocity_bonus // 2),
                                    "velocity_score_15m": vel_snap.get('velocity_score'),
                                    "unique_traders_15m": vel_snap.get('unique_traders'),
                                    "volume_24h": volume_24h,
                                    "market_cap": market_cap,
                                    "price": float(price),
                                    "change_1h": change_1h,
                                    "change_24h": change_24h,
                                    "liquidity": liquidity,
                                    "conviction_type": conviction_type,
                                    "badges": badges,
                                    "score_components": score_components,
                                    "data_source": (stats.get("_source") or "unknown"),
                                    "smart_cycle": bool(is_smart_cycle),
                                    "smart_money_detected": bool(smart_involved),
                                    # Raw objects for post-hoc analysis
                                    "security": security,
                                    "liquidity_obj": liq_obj,
                                    "holders_obj": holders_obj,
                                    # Extracted safety fields
                                    "mint_revoked": mint_revoked,
                                    "is_honeypot": (security or {}).get('is_honeypot'),
                                    "lp_locked": bool(lp_locked) if lp_locked is not None else None,
                                    "lp_lock_status": (liq_obj or {}).get('lock_status'),
                                    "lp_burned": (liq_obj or {}).get('is_lp_burned'),
                                    "top10_concentration_percent": float(top10) if isinstance(top10, (int, float)) else None,
                                    # Ratios and engagement
                                    "vol_to_mcap_ratio": vol_to_mcap_ratio,
                                    "volume_24h_unique_buyers": unique_buyers_24h,
                                    "volume_24h_unique_sellers": unique_sellers_24h,
                                    # Gate snapshot
                                    "gates": {
                                        "MIN_LIQUIDITY_USD": MIN_LIQUIDITY_USD,
                                        "VOL_24H_MIN_FOR_ALERT": VOL_24H_MIN_FOR_ALERT,
                                        "VOL_TO_MCAP_RATIO_MIN": VOL_TO_MCAP_RATIO_MIN,
                                        "MCAP_MICRO_MAX": MCAP_MICRO_MAX,
                                        "MAX_MARKET_CAP_FOR_DEFAULT_ALERT": MAX_MARKET_CAP_FOR_DEFAULT_ALERT,
                                        "MOMENTUM_1H_STRONG": MOMENTUM_1H_STRONG,
                                        "LARGE_CAP_MOMENTUM_GATE_1H": LARGE_CAP_MOMENTUM_GATE_1H,
                                        "MAX_TOP10_CONCENTRATION": MAX_TOP10_CONCENTRATION,
                                        "REQUIRE_MINT_REVOKED": REQUIRE_MINT_REVOKED,
                                        "REQUIRE_LP_LOCKED": REQUIRE_LP_LOCKED,
                                        "ALLOW_UNKNOWN_SECURITY": ALLOW_UNKNOWN_SECURITY,
                                        "HIGH_CONFIDENCE_SCORE": HIGH_CONFIDENCE_SCORE,
                                        "GATE_MODE": (CURRENT_GATES.get('GATE_MODE') if CURRENT_GATES else None),
                                        # Pass/fail at alert time
                                        "passes": {
                                            "liquidity": liq_gate,
                                            "volume_24h": vol_gate,
                                            "vol_to_mcap": vtm_gate,
                                            "mcap_micro": mcap_micro_gate,
                                            "top10_concentration": top10_gate,
                                        },
                                    },
                                }
                            )
                        except Exception:
                            pass
                            
                except Exception as e:
                    _out(f"Error processing token {token_address}: {e}")
                    continue

            # Cursors are handled per cycle type above
            
            # Periodic maintenance
            try:
                deleted = prune_old_activity()
                if deleted:
                    _out(f"Pruned {deleted} old activity rows")
            except Exception:
                pass

            # Periodic tracking of alerted tokens for peak/last prices
            try:
                now = time.time()
                if now - last_track_time > TRACK_INTERVAL_MIN * 60:
                    to_check = get_alerted_tokens_batch(limit=TRACK_BATCH_SIZE, older_than_minutes=TRACK_INTERVAL_MIN)
                    if to_check:
                        _out(f"Tracking {len(to_check)} alerted tokens for price updates")
                    for ca in to_check:
                        try:
                            stats = get_token_stats(ca)
                            price = 0.0
                            mcap = None
                            liq = None
                            vol24 = None
                            if stats:
                                price = float(stats.get('price_usd') or 0.0)
                                mcap = stats.get('market_cap_usd')
                                liq = stats.get('liquidity_usd') or (stats.get('liquidity', {}) or {}).get('usd')
                                vol24 = (stats.get('volume', {}) or {}).get('24h', {}) or {}
                                vol24 = vol24.get('volume_usd')
                            update_token_tracking(ca, price, mcap, liq, vol24)
                            try:
                                snap = get_tracking_snapshot(ca) or {}
                                log_tracking({
                                    "token": ca,
                                    "price": price,
                                    "market_cap": mcap,
                                    "liquidity": liq,
                                    "vol24": vol24,
                                    "peak_price": snap.get('peak_price'),
                                    "peak_mcap": snap.get('peak_mcap'),
                                    "time_to_peak_price_s": snap.get('time_to_peak_price_s'),
                                    "time_to_peak_mcap_s": snap.get('time_to_peak_mcap_s'),
                                    "peak_x_price": snap.get('peak_x_price'),
                                    "peak_x_mcap": snap.get('peak_x_mcap'),
                                    "data_source": (stats.get("_source") if isinstance(stats, dict) else None) or "unknown",
                                })
                            except Exception:
                                pass
                        except Exception:
                            continue
                    last_track_time = now
            except Exception:
                pass

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
        f"<b>Solana Memecoin Bot Stopped</b>\n\n"
        f"<b>Stop Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"<b>Total Processed:</b> {processed_count} tokens\n"
        f"<b>Total Alerts Sent:</b> {alert_count}\n"
        f"<b>Status:</b> Bot shutdown complete"
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
            from tradingSystem.cli import run as trade_run
            trade_run()
        else:
            run_bot()
    except Exception as e:
        _out(f"Fatal error: {e}")
        sys.exit(1)
