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

from app.fetch_feed import fetch_solana_feed
from app.analyze_token import get_token_stats, score_token, calculate_preliminary_score
from app.notify import send_telegram_alert
from app.storage import (init_db, has_been_alerted, mark_as_alerted, 
                    record_token_activity, get_token_velocity, should_fetch_detailed_stats,
                    ensure_indices, prune_old_activity, get_alerted_tokens_batch, update_token_tracking,
                    get_tracking_snapshot)
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
    # Gate mode snapshot for logging
    from config import CURRENT_GATES
except Exception:
    CURRENT_GATES = None
try:
    from tools.relay import relay_contract_address_sync, relay_enabled
except Exception:
    def relay_enabled() -> bool:
        return False
    def relay_contract_address_sync(*_args, **_kwargs) -> bool:
        return False
from app.logger_utils import log_alert, log_tracking
import html

# Global flag for graceful shutdown
shutdown_flag = False

# Global lock handle to keep singleton lock alive for process lifetime
_singleton_lock_file = None

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
                f.close()
                return False
        except ImportError:
            # Windows: use msvcrt locking on the first byte
            import msvcrt  # type: ignore
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                f.close()
                return False
        # Write PID for debugging purposes
        try:
            f.seek(0)
            pid_bytes = str(os.getpid()).encode("utf-8")
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
    print("\n🛑 Shutdown signal received. Gracefully stopping bot...")
    shutdown_flag = True

def run_bot():
    global shutdown_flag
    
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Enforce single-instance execution
    if not acquire_singleton_lock():
        print("🚫 Another bot instance is already running. Exiting.")
        return

    try:
        init_db()  # ensure database is initialized
        ensure_indices()
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        return
    
    cursor_general = None
    cursor_smart = None
    processed_count = 0
    alert_count = 0
    last_alert_time = 0
    api_calls_saved = 0  # Track credit optimization
    session_alerted_tokens = set()
    last_track_time = 0
    
    print("🧠 SMART MONEY ENHANCED SOLANA MEMECOIN BOT STARTED!")
    print(f"📊 Configuration: Score threshold = {HIGH_CONFIDENCE_SCORE}, Fetch interval = {FETCH_INTERVAL}s")
    if CURRENT_GATES:
        gm = CURRENT_GATES.get('GATE_MODE')
        print(f"🎚️ Gate Mode: {gm} | Gates: score>={CURRENT_GATES.get('HIGH_CONFIDENCE_SCORE')}, liq>={CURRENT_GATES.get('MIN_LIQUIDITY_USD')}, vol24>={CURRENT_GATES.get('VOL_24H_MIN_FOR_ALERT')}, mcap<={CURRENT_GATES.get('MAX_MARKET_CAP_FOR_DEFAULT_ALERT')}, vol/mcap>={CURRENT_GATES.get('VOL_TO_MCAP_RATIO_MIN')}")
    print("🎯 Features: Smart Money Detection + Enhanced Scoring + Detailed Analysis")
    print("✅ Smart-money cycle enabled (top_wallets=true, min_wallet_pnl=1000)")
    print("🛡️ Adaptive cooldown on Cielo rate limits is enabled")
    
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
    
    is_smart_cycle = False
    while not shutdown_flag:
        try:
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
                print(f"⏳ Cielo {('quota' if feed_error=='quota_exceeded' else 'rate limit')} hit. Cooling down for {retry_after_sec}s…")
                for _ in range(retry_after_sec):
                    if shutdown_flag:
                        break
                    time.sleep(1)
                # Do not process this cycle; flip cycle to avoid hammering the same endpoint
                is_smart_cycle = not is_smart_cycle
                continue

            # Log the number of items returned this cycle for visibility
            items_count = len(feed.get("transactions", []))
            print(f"🔎 FEED ITEMS: {items_count}")
            
            if not feed.get("transactions"):
                print(f"📭 No new transactions found")
            
            def _tx_has_smart_money(tx_obj: dict, smart_cycle: bool) -> bool:
                """Best-effort detection of smart-money involvement from feed item.
                Falls back to cycle type only if explicit hints are missing.
                """
                try:
                    if smart_cycle:
                        return True
                    # Common hints in feed payloads
                    hints = [
                        tx_obj.get("smart_money"),
                        tx_obj.get("top_wallets"),
                        tx_obj.get("is_smart"),
                        tx_obj.get("isTopWallet"),
                    ]
                    # Wallet/trader pnl signals
                    for key in ("wallet_pnl", "min_wallet_pnl", "trader_pnl", "pnl_usd"):
                        val = tx_obj.get(key)
                        if isinstance(val, (int, float)) and val >= 1000:
                            hints.append(True)
                    # Label-based signal
                    labels = tx_obj.get("labels") or tx_obj.get("wallet_labels")
                    if labels:
                        if isinstance(labels, (list, tuple)):
                            label_text = ",".join(str(x) for x in labels).lower()
                        else:
                            label_text = str(labels).lower()
                        if any(tag in label_text for tag in ("smart", "top", "alpha", "elite")):
                            hints.append(True)
                    return any(bool(h) for h in hints)
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

                if not token_address or usd_value == 0:
                    continue

                processed_count += 1

                if token_address in session_alerted_tokens or has_been_alerted(token_address):
                    continue  # skip previously alerted tokens

                try:
                    # STEP 1: Calculate preliminary score (NO API CALLS)
                    preliminary_score = calculate_preliminary_score(tx, smart_money_detected=smart_involved)
                    if DEBUG_PRELIM:
                        print("    ⤷ prelim_debug:", {
                            'usd_value': round(tx.get('usd_value', 0) or 0, 2),
                            'token0_usd': round(tx.get('token0_amount_usd', 0) or 0, 2),
                            'token1_usd': round(tx.get('token1_amount_usd', 0) or 0, 2),
                            'tx_type': tx.get('tx_type'),
                            'dex': tx.get('dex')
                        })
                    
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
                    if not should_fetch_detailed_stats(token_address, preliminary_score):
                        print(f"📊 Token {token_address} prelim: {preliminary_score}/10 (skipped detailed analysis)")
                        api_calls_saved += 1  # Track credits saved
                        continue
                    
                    # STEP 4: EXPENSIVE API CALL - Only for high-potential tokens
                    print(f"💰 FETCHING DETAILED STATS for {token_address[:8]}... (prelim: {preliminary_score}/10)")
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
                    
                    print(f"📈 Token {token_address} FINAL: {score}/10 (prelim: {preliminary_score}, velocity: +{velocity_bonus//2})")
                    
                    # Optional post-score meta gates (smart-money/velocity)
                    if REQUIRE_SMART_MONEY_FOR_ALERT and not smart_involved:
                        continue
                    if REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT:
                        if (velocity_bonus // 2) < (REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT // 2):
                            continue

                    # Gate checks (explicit)
                    volume_24h = stats.get('volume', {}).get('24h', {}).get('volume_usd', 0)
                    market_cap = stats.get('market_cap_usd', 0)
                    liquidity = (
                        stats.get('liquidity_usd')
                        or stats.get('liquidity', {}).get('usd')
                        or 0
                    )
                    vol_to_mcap_ok = False
                    try:
                        vol_to_mcap_ok = (float(volume_24h or 0) / float(market_cap or 1)) >= (VOL_TO_MCAP_RATIO_MIN or 0)
                    except Exception:
                        vol_to_mcap_ok = False

                    liq_ok = (liquidity or 0) >= (MIN_LIQUIDITY_USD or 0)
                    vol_ok = (volume_24h or 0) >= (VOL_24H_MIN_FOR_ALERT or 0)
                    mcap_ok = (market_cap or 0) <= (MAX_MARKET_CAP_FOR_DEFAULT_ALERT or float('inf'))

                    print(f"🧪 Gate check: score>={HIGH_CONFIDENCE_SCORE}? {score>=HIGH_CONFIDENCE_SCORE} | liq_ok={liq_ok} (${liquidity:,.0f}) | vol_ok={vol_ok} (${volume_24h:,.0f}) | mcap_ok={mcap_ok} (${market_cap:,.0f}) | vtm_ok={vol_to_mcap_ok}")

                    if score >= HIGH_CONFIDENCE_SCORE and liq_ok and vol_ok and mcap_ok and (VOL_TO_MCAP_RATIO_MIN == 0 or vol_to_mcap_ok):
                        # Enhanced alert with smart money indicators
                        alert_type = "HIGH-CONFIDENCE"
                        price = stats.get('price_usd', 0)
                        change_1h = stats.get('change', {}).get('1h', 0)
                        change_24h = stats.get('change', {}).get('24h', 0)
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
                                print(f"⏳ Throttling alerts; waiting {wait_s}s before sending…")
                                for _ in range(wait_s):
                                    if shutdown_flag:
                                        break
                                    time.sleep(1)
                            last_alert_time = time.time()

                        if send_telegram_alert(message):
                            # Baseline metrics for tracking
                            baseline_price = float(price or 0)
                            baseline_mcap = float(market_cap or 0)
                            baseline_liq = float(liquidity or 0)
                            baseline_vol = float(volume_24h or 0)
                            mark_as_alerted(token_address, score, smart_involved,
                                            baseline_price, baseline_mcap, baseline_liq, baseline_vol)
                            try:
                                if relay_enabled():
                                    relay_contract_address_sync(token_address)
                            except Exception:
                                pass
                            session_alerted_tokens.add(token_address)
                            alert_count += 1
                            print(f"✅ Alert #{alert_count} sent for token {token_address} (Final: {score}/10, Prelim: {preliminary_score}/10)")
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

                                log_alert({
                                    "token": token_address,
                                    "name": name,
                                    "symbol": symbol,
                                    "final_score": score,
                                    "prelim_score": preliminary_score,
                                    "velocity_bonus": int(velocity_bonus//2),
                                    "velocity_score_15m": vel_snap.get('velocity_score'),
                                    "unique_traders_15m": vel_snap.get('unique_traders'),
                                    "volume_24h": volume_24h,
                                    "market_cap": market_cap,
                                    "price": float(price),
                                    "change_1h": change_1h,
                                    "change_24h": change_24h,
                                    "liquidity": liquidity,
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
                                })
                            except Exception:
                                pass
                        else:
                            print(f"❌ Failed to send alert for token {token_address}")
                            
                except Exception as e:
                    print(f"⚠️ Error processing token {token_address}: {e}")
                    continue

            # Cursors are handled per cycle type above
            
            # Periodic maintenance
            try:
                deleted = prune_old_activity()
                if deleted:
                    print(f"🧹 Pruned {deleted} old activity rows")
            except Exception:
                pass

            # Periodic tracking of alerted tokens for peak/last prices
            try:
                now = time.time()
                if now - last_track_time > TRACK_INTERVAL_MIN * 60:
                    to_check = get_alerted_tokens_batch(limit=TRACK_BATCH_SIZE, older_than_minutes=TRACK_INTERVAL_MIN)
                    if to_check:
                        print(f"🛰 Tracking {len(to_check)} alerted tokens for price updates…")
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
                print(f"😴 Sleeping for {FETCH_INTERVAL} seconds...")
                for _ in range(FETCH_INTERVAL):
                    if shutdown_flag:
                        break
                    time.sleep(1)
            # flip cycle after sleep
            is_smart_cycle = not is_smart_cycle
                
        except KeyboardInterrupt:
            print("\n🛑 Keyboard interrupt received")
            break
        except Exception as e:
            print(f"❌ Unexpected error in main loop: {e}")
            print("🔄 Continuing after error...")
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
    print(f"👋 Bot stopped gracefully. Processed {processed_count} tokens, sent {alert_count} alerts.")

if __name__ == "__main__":
    try:
        run_bot()
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        sys.exit(1)
