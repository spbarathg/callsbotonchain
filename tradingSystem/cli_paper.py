"""
PAPER TRADING CLI - Realistic Simulation Runner
Connects signal bot to paper trading engine
Emulates real trading with $500, fees, latency, and slippage
"""
import argparse
import json
import os
import threading
import time
from typing import Optional, Dict

import requests

from .watcher import follow_signals_redis
from .paper_trader import PaperTrader
from .strategy_optimized import decide_trade
from app.toggles import trading_enabled


def _get_last_price_usd(token: str) -> float:
    """Fetch last price from tracked API"""
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


def _fetch_real_stats(token: str) -> Optional[Dict]:
    """Fetch comprehensive stats for a token"""
    stats = {}
    
    # Try tracking API first
    try:
        resp = requests.get("http://127.0.0.1/api/tracked?limit=500", timeout=5)
        resp.raise_for_status()
        rows = (resp.json() or {}).get("rows") or []
        for r in rows:
            if r.get("token") == token:
                stats["market_cap_usd"] = float(r.get("last_mcap") or r.get("peak_mcap") or 0)
                stats["liquidity_usd"] = float(r.get("liquidity") or 0)
                stats["change_1h"] = float(r.get("change_1h") or 0) * 100
                vol24 = float(r.get("vol24") or 0)
                mcap = stats.get("market_cap_usd") or 1
                stats["ratio"] = vol24 / max(mcap, 1) if mcap > 0 else 0
                stats["vol24_usd"] = vol24
                stats["price"] = float(r.get("last_price") or 0)
                break
    except Exception:
        pass
    
    # Fallback to alerts.jsonl for initial data
    if not stats or stats.get("liquidity_usd", 0) == 0:
        try:
            alerts_path = os.path.join(os.path.dirname(__file__), "..", "data", "logs", "alerts.jsonl")
            if os.path.exists(alerts_path):
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
                                stats["price"] = float(alert.get("price") or 0)
                                break
                        except Exception:
                            continue
        except Exception:
            pass
    
    # Validation
    if not stats.get("market_cap_usd") or not stats.get("liquidity_usd"):
        return None
    
    # Ensure we have score and conviction
    if "final_score" not in stats:
        stats["final_score"] = 7
    if "conviction_type" not in stats:
        stats["conviction_type"] = "High Confidence (Strict)"
    
    return stats


def _exit_loop(trader: PaperTrader, stop_event: threading.Event) -> None:
    """Background thread to check exits"""
    last_status_log = 0
    
    while not stop_event.is_set():
        try:
            # Log status every 5 minutes
            now = time.time()
            if now - last_status_log > 300:
                stats = trader.get_stats()
                print(f"[PAPER] Status: ${stats['total_value']:.2f} | "
                      f"ROI: {stats['roi_pct']:.1f}% | "
                      f"Open: {stats['open_positions']} | "
                      f"WR: {stats['win_rate']:.1f}% ({stats['wins']}/{stats['total_trades']})")
                last_status_log = now
            
            # Check circuit breaker
            if trader.circuit_breaker.is_tripped():
                print(f"[PAPER] ⚠️ Circuit breaker tripped: {trader.circuit_breaker.trip_reason}")
                time.sleep(60)
                continue
            
            # Check exits for all open positions
            for token in list(trader.positions.keys()):
                try:
                    price = _get_last_price_usd(token)
                    if price > 0:
                        trader.update_and_check_exits(token, price)
                except Exception as e:
                    print(f"[PAPER] Exit check error for {token}: {e}")
            
            time.sleep(2)
            
        except Exception as e:
            print(f"[PAPER] Exit loop error: {e}")
            time.sleep(5)


def run() -> None:
    """Main paper trading loop"""
    parser = argparse.ArgumentParser(description="Paper trading system with realistic simulation")
    parser.add_argument("--capital", type=float, default=500.0, help="Starting capital (default: $500)")
    args = parser.parse_args()

    trader = PaperTrader(starting_capital=args.capital)
    
    print("")
    print(f"{'='*70}")
    print("  📊 PAPER TRADING SYSTEM - REALISTIC SIMULATION")
    print(f"{'='*70}")
    print(f"  Starting Capital: ${trader.starting_capital:.2f}")
    print("  Swap Fee: 0.25% (Jupiter typical)")
    print("  Slippage: 0.5-4% (liquidity dependent)")
    print("  Latency: 1-3 seconds (realistic execution delay)")
    print("  Stop Loss: 15% from entry")
    print("  Trailing Stop: 30% default (score-dependent)")
    print("  Circuit Breakers: 20% daily loss, 5 consecutive losses")
    print("  Max Concurrent: 5 positions")
    print("  Position Sizing: Optimized (Score 8 = $104, Smart Money = $80 base)")
    print(f"{'='*70}")
    print("")
    
    # Start exit loop
    stop_event = threading.Event()
    exit_thread = threading.Thread(target=_exit_loop, args=(trader, stop_event), daemon=True)
    exit_thread.start()

    # Counters
    signals_processed = 0
    signals_filtered = 0
    positions_opened = 0
    last_health_log = time.time()

    try:
        # Use Redis-based signal streaming (real-time)
        print("📡 Connecting to Redis signal stream...")
        for signal in follow_signals_redis(block_timeout=5):
            try:
                signals_processed += 1
                
                # Log health every 10 minutes
                if time.time() - last_health_log > 600:
                    stats = trader.get_stats()
                    print("\n[PAPER] Health Check:")
                    print(f"  Signals Processed: {signals_processed}")
                    print(f"  Positions Opened: {positions_opened}")
                    print(f"  Current Value: ${stats['total_value']:.2f}")
                    print(f"  ROI: {stats['roi_pct']:.1f}%")
                    print(f"  Win Rate: {stats['win_rate']:.1f}%")
                    print(f"  Circuit Breaker: {'TRIPPED' if stats['circuit_breaker_tripped'] else 'OK'}")
                    print("")
                    last_health_log = time.time()
                
                # Check trading toggle
                if not trading_enabled():
                    time.sleep(0.2)
                    continue
                
                # Check circuit breaker
                if trader.circuit_breaker.is_tripped():
                    time.sleep(5)
                    continue
                
                token = signal.get("ca")
                
                if not token:
                    continue
                
                # Skip if already have position
                if token in trader.positions:
                    continue
                
                # FILTER: Only pump.fun tokens (REMOVED - too restrictive)
                # Most Solana tokens don't end with "pump", only pump.fun vanity addresses do
                # Commenting out to allow all tokens through
                # if not token.endswith("pump"):
                #     signals_filtered += 1
                #     continue
                
                # Extract signal data directly from Redis payload
                signal_score = int(signal.get("score", 7))
                conviction_type = signal.get("conviction_type", "High Confidence (Strict)")
                price = float(signal.get("price", 0))
                liquidity = float(signal.get("liquidity", 0))
                market_cap = float(signal.get("market_cap", 0))
                volume_24h = float(signal.get("volume_24h", 0))
                change_1h = float(signal.get("change_1h", 0))
                
                # Validate we have minimum required data
                if price == 0 or liquidity == 0:
                    print(f"[PAPER] ⚠️ Skipping {token[:8]}... - missing price/liquidity data")
                    signals_filtered += 1
                    continue
                
                # Build stats dict for strategy decision
                stats = {
                    "final_score": signal_score,
                    "conviction_type": conviction_type,
                    "price": price,
                    "liquidity_usd": liquidity,
                    "market_cap_usd": market_cap,
                    "vol24_usd": volume_24h,
                    "change_1h": change_1h,
                    "ratio": volume_24h / max(market_cap, 1) if market_cap > 0 else 0,
                }
                
                # Make trade decision using optimized strategy
                plan = decide_trade(stats, signal_score, conviction_type)
                
                if not plan:
                    signals_filtered += 1
                    continue
                
                # Prepare signal data for paper trader
                signal_data = {
                    'score': signal_score,
                    'conviction_type': conviction_type,
                    'strategy': plan['strategy'],
                    'price': price,
                    'liquidity_usd': liquidity,
                    'change_1h': change_1h,
                }
                
                # Try to open position
                pos_id = trader.open_position(token, signal_data)
                
                if pos_id:
                    positions_opened += 1
                    stats_current = trader.get_stats()
                    print(f"\n[PAPER] 📈 OPENED Position #{pos_id}")
                    print(f"  Token: {token[:8]}...")
                    print(f"  Score: {signal_score}/10 | {conviction_type}")
                    print(f"  Entry: ${price:.8f}")
                    print(f"  Size: ${plan['usd_size']:.2f}")
                    print(f"  Trail: {plan['trail_pct']:.0f}%")
                    print(f"  Capital Remaining: ${stats_current['current_capital']:.2f}")
                    print(f"  Open Positions: {stats_current['open_positions']}/5")
                    print("")
                
            except Exception as e:
                print(f"[PAPER] Signal processing error: {e}")
                continue
    
    except KeyboardInterrupt:
        print("\n[PAPER] Shutting down...")
    except Exception as e:
        print(f"[PAPER] Fatal error: {e}")
    finally:
        stop_event.set()
        exit_thread.join(timeout=5)
        
        # Final stats
        final_stats = trader.get_stats()
        print(f"\n{'='*70}")
        print("  📊 PAPER TRADING FINAL RESULTS")
        print(f"{'='*70}")
        print(f"  Starting Capital: ${trader.starting_capital:.2f}")
        print(f"  Final Value: ${final_stats['total_value']:.2f}")
        print(f"  Total PnL: ${final_stats['total_pnl']:.2f}")
        print(f"  ROI: {final_stats['roi_pct']:.1f}%")
        print(f"  Total Trades: {final_stats['total_trades']}")
        print(f"  Wins: {final_stats['wins']} | Losses: {final_stats['losses']}")
        print(f"  Win Rate: {final_stats['win_rate']:.1f}%")
        print(f"  Open Positions: {final_stats['open_positions']}")
        print(f"  Signals Processed: {signals_processed}")
        print(f"  Positions Opened: {positions_opened}")
        print(f"{'='*70}")
        print("")


if __name__ == "__main__":
    run()

