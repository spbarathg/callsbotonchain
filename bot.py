# bot.py
import time
import signal
import sys
from datetime import datetime
from fetch_feed import fetch_solana_feed
from analyze_token import get_token_stats, score_token, calculate_preliminary_score
from notify import send_telegram_alert
from storage import (init_db, has_been_alerted, mark_as_alerted, 
                    record_token_activity, get_token_velocity, should_fetch_detailed_stats,
                    ensure_indices, prune_old_activity, get_alerted_tokens_batch, update_token_tracking)
from config import HIGH_CONFIDENCE_SCORE, FETCH_INTERVAL, DEBUG_PRELIM, TELEGRAM_ALERT_MIN_INTERVAL, TRACK_INTERVAL_MIN, TRACK_BATCH_SIZE
from relay import relay_contract_address_sync, relay_enabled
from logger_utils import log_alert, log_tracking
import html

# Global flag for graceful shutdown
shutdown_flag = False

def signal_handler(sig, frame):
    global shutdown_flag
    print("\n🛑 Shutdown signal received. Gracefully stopping bot...")
    shutdown_flag = True

def run_bot():
    global shutdown_flag
    
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
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
    print("🎯 Features: Smart Money Detection + Enhanced Scoring + Detailed Analysis")
    print("✅ Smart-money cycle enabled (top_wallets=true, min_wallet_pnl=1000)")
    
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

            # Log the number of items returned this cycle for visibility
            items_count = len(feed.get("transactions", []))
            print(f"🔎 FEED ITEMS: {items_count}")
            
            if not feed.get("transactions"):
                print(f"📭 No new transactions found")
            
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

                if not token_address or usd_value == 0:
                    continue

                processed_count += 1

                if token_address in session_alerted_tokens or has_been_alerted(token_address):
                    continue  # skip previously alerted tokens

                try:
                    # STEP 1: Calculate preliminary score (NO API CALLS)
                    preliminary_score = calculate_preliminary_score(tx, smart_money_detected=is_smart_cycle)
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
                        is_smart_cycle,
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
                    
                    score, scoring_details = score_token(stats, smart_money_detected=is_smart_cycle)
                    
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
                    
                    if score >= HIGH_CONFIDENCE_SCORE:
                        # Enhanced alert with smart money indicators
                        alert_type = "HIGH-CONFIDENCE"

                        volume_24h = stats.get('volume', {}).get('24h', {}).get('volume_usd', 0)
                        market_cap = stats.get('market_cap_usd', 0)
                        price = stats.get('price_usd', 0)
                        change_1h = stats.get('change', {}).get('1h', 0)
                        change_24h = stats.get('change', {}).get('24h', 0)
                        name = html.escape(stats.get('name') or "Token")
                        symbol = html.escape(stats.get('symbol') or "?")
                        liquidity = (
                            stats.get('liquidity_usd')
                            or stats.get('liquidity', {}).get('usd')
                            or 0
                        )
                        chart_link = f"https://dexscreener.com/solana/{token_address}"
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
                            mark_as_alerted(token_address, score, is_smart_cycle,
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
                                log_alert({
                                    "token": token_address,
                                    "name": name,
                                    "symbol": symbol,
                                    "final_score": score,
                                    "prelim_score": preliminary_score,
                                    "velocity_bonus": int(velocity_bonus//2),
                                    "volume_24h": volume_24h,
                                    "market_cap": market_cap,
                                    "price": float(price),
                                    "change_1h": change_1h,
                                    "change_24h": change_24h,
                                    "liquidity": liquidity,
                                    "badges": badges,
                                    "data_source": (stats.get("_source") or "unknown"),
                                    "smart_cycle": bool(is_smart_cycle),
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
                                log_tracking({
                                    "token": ca,
                                    "price": price,
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
