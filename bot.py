# bot.py
import time
import signal
import sys
from datetime import datetime
from fetch_feed import fetch_solana_feed
from analyze_token import get_token_stats, score_token, calculate_preliminary_score
from notify import send_telegram_alert
from storage import (init_db, has_been_alerted, mark_as_alerted, 
                    record_token_activity, get_token_velocity, should_fetch_detailed_stats)
from config import HIGH_CONFIDENCE_SCORE, FETCH_INTERVAL, DEBUG_PRELIM

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
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        return
    
    cursor = None
    processed_count = 0
    alert_count = 0
    api_calls_saved = 0  # Track credit optimization
    
    print("🧠 SMART MONEY ENHANCED SOLANA MEMECOIN BOT STARTED!")
    print(f"📊 Configuration: Score threshold = {HIGH_CONFIDENCE_SCORE}, Fetch interval = {FETCH_INTERVAL}s")
    print("🎯 Features: Smart Money Detection + Enhanced Scoring + Detailed Analysis")
    print("✅ Smart-money filters enabled (top_wallets=true, min_wallet_pnl=1000)")
    
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
    
    while not shutdown_flag:
        try:
            feed = fetch_solana_feed(cursor)
            cursor = feed.get("next_cursor")

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

                if has_been_alerted(token_address):
                    continue  # skip previously alerted tokens

                try:
                    # STEP 1: Calculate preliminary score (NO API CALLS)
                    preliminary_score = calculate_preliminary_score(tx, smart_money_detected=False)
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
                        False,
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
                    
                    score, scoring_details = score_token(stats, smart_money_detected=False)
                    
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
                        name = stats.get('name') or "Token"
                        symbol = stats.get('symbol') or "?"
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
                        message = (
                            f"<b>{name} (${symbol})</b>\n\n"
                            f"Fresh signal on Solana.\n\n"
                            f"💰 <b>MCap:</b> ${market_cap:,.0f}\n"
                            f"💧 <b>Liquidity:</b> ${liquidity:,.0f}\n"
                            f"{badges_text}\n" if badges_text else ""
                            f"📈 <b>Chart:</b> <a href='{chart_link}'>DexScreener</a>\n"
                            f"🔁 <b>Swap:</b> <a href='{swap_link}'>Raydium</a>\n\n"
                            f"<code>{token_address}</code>\n"
                            f"\n—\n"
                            f"Score: {score}/10 | 24h Vol: ${volume_24h:,.0f} | Price: ${price:.8f} | 1h {change_1h:+.1f}% | 24h {change_24h:+.1f}%"
                        )
                        
                        # no extra smart money line in lean mode
                        
                        # Add detailed scoring breakdown
                        message += f"\n<b>Scoring Analysis:</b>\n"
                        for detail in scoring_details[:4]:  # Top 4 scoring factors
                            # Remove emojis from scoring details
                            clean_detail = detail.replace("✅ ", "").replace("⚡ ", "").replace("🟡 ", "").replace("❌ ", "")
                            message += f"  - {clean_detail}\n"
                        
                        message += f"\n<b>Alert Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        
                        if send_telegram_alert(message):
                            mark_as_alerted(token_address, score, is_smart_money_cycle)
                            alert_count += 1
                            print(f"✅ Alert #{alert_count} sent for token {token_address} (Final: {score}/10, Prelim: {preliminary_score}/10)")
                        else:
                            print(f"❌ Failed to send alert for token {token_address}")
                            
                except Exception as e:
                    print(f"⚠️ Error processing token {token_address}: {e}")
                    continue

            # Cursors are handled per cycle type above
            
            if not shutdown_flag:
                print(f"😴 Sleeping for {FETCH_INTERVAL} seconds...")
                for _ in range(FETCH_INTERVAL):
                    if shutdown_flag:
                        break
                    time.sleep(1)
                
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
