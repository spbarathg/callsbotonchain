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
from config import HIGH_CONFIDENCE_SCORE, FETCH_INTERVAL

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
    smart_cursor = None
    processed_count = 0
    alert_count = 0
    cycle_count = 0
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
            cycle_count += 1
            is_smart_money_cycle = (cycle_count % 2 == 1)  # Alternate between smart money and general
            
            if is_smart_money_cycle:
                print(f"🧠 SMART MONEY CYCLE {cycle_count} (processed: {processed_count}, alerts: {alert_count}, API calls saved: {api_calls_saved})")
                feed = fetch_solana_feed(smart_cursor, smart_money_only=True)
                smart_cursor = feed.get("next_cursor")
            else:
                print(f"📡 GENERAL CYCLE {cycle_count} (processed: {processed_count}, alerts: {alert_count}, API calls saved: {api_calls_saved})")
                feed = fetch_solana_feed(cursor, smart_money_only=False)
                cursor = feed.get("next_cursor")

            # Log the number of items returned this cycle for visibility
            items_count = len(feed.get("transactions", []))
            cycle_name = "SMART MONEY" if is_smart_money_cycle else "GENERAL"
            print(f"🔎 {cycle_name} FEED ITEMS: {items_count}")
            
            if not feed.get("transactions"):
                cycle_type = "smart money" if is_smart_money_cycle else "general"
                print(f"📭 No new {cycle_type} transactions found")
            
            for tx in feed.get("transactions", []):
                if shutdown_flag:
                    break
                    
                token_address = tx.get("token_address")
                usd_value = tx.get("usd_value", 0)
                
                if not token_address or usd_value == 0:
                    continue

                processed_count += 1

                if has_been_alerted(token_address):
                    continue  # skip previously alerted tokens

                try:
                    # STEP 1: Calculate preliminary score (NO API CALLS)
                    preliminary_score = calculate_preliminary_score(tx, smart_money_detected=is_smart_money_cycle)
                    
                    # STEP 2: Record activity for velocity tracking
                    record_token_activity(
                        token_address, 
                        usd_value, 
                        1,  # Transaction count (individual tx)
                        is_smart_money_cycle,
                        preliminary_score
                    )
                    
                    # STEP 3: CREDIT-EFFICIENT DECISION - Only fetch detailed stats if warranted
                    if not should_fetch_detailed_stats(token_address, preliminary_score):
                        smart_indicator = "⚡" if is_smart_money_cycle else "📊"
                        print(f"{smart_indicator} Token {token_address[:8]}... prelim: {preliminary_score}/10 (skipped detailed analysis)")
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
                    
                    score, scoring_details = score_token(stats, smart_money_detected=is_smart_money_cycle)
                    
                    # Add velocity bonus
                    if velocity_bonus > 0:
                        score = min(score + (velocity_bonus // 2), 10)  # Half velocity score as bonus
                        scoring_details.append(f"Velocity: +{velocity_bonus//2} ({velocity_data['observations']} observations)")
                    
                    smart_indicator = "🧠" if is_smart_money_cycle else "📊"
                    print(f"{smart_indicator} Token {token_address[:8]}... FINAL: {score}/10 (prelim: {preliminary_score}, velocity: +{velocity_bonus//2})")
                    
                    if score >= HIGH_CONFIDENCE_SCORE:
                        # Enhanced alert with smart money indicators
                        alert_type = "🧠 SMART MONEY" if is_smart_money_cycle else "🔥 HIGH-CONFIDENCE"
                        
                        volume_24h = stats.get('volume', {}).get('24h', {}).get('volume_usd', 0)
                        market_cap = stats.get('market_cap_usd', 0)
                        price = stats.get('price_usd', 0)
                        change_1h = stats.get('change', {}).get('1h', 0)
                        change_24h = stats.get('change', {}).get('24h', 0)
                        
                        message = (
                            f"<b>{alert_type} MEMECOIN ALERT</b>\n\n"
                            f"<b>Contract Address:</b>\n<code>{token_address}</code>\n\n"
                            f"<b>Score:</b> {score}/10\n"
                            f"<b>Market Cap:</b> ${market_cap:,.0f}\n"
                            f"<b>24h Volume:</b> ${volume_24h:,.0f}\n"
                            f"<b>Price:</b> ${price:.8f}\n"
                            f"<b>Price Change:</b> 1h: {change_1h:+.1f}% | 24h: {change_24h:+.1f}%\n"
                        )
                        
                        if is_smart_money_cycle:
                            message += f"\n<b>SMART MONEY DETECTED</b>\nTop performing wallets are actively trading this token\n"
                        
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
