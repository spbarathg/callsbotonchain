"""
BULLETPROOF CLI - Safe orchestration with comprehensive error handling
"""
import argparse
import json
import os
import signal
import sys
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Dict

import requests

from .watcher import follow_decisions
from .strategy_safe import decide_runner, decide_scout, decide_strict, decide_nuanced
from .trader_safe import TradeEngine
from app.toggles import trading_enabled
from .db import get_open_position_id_by_token


# Global shutdown flag
shutdown_requested = False


def signal_handler(sig, frame):
    """Handle graceful shutdown on SIGINT/SIGTERM"""
    global shutdown_requested
    print("\n🛑 Shutdown requested, closing positions safely...")
    shutdown_requested = True


class PriceCache:
    """Thread-safe price cache with staleness detection"""
    def __init__(self, max_age_seconds: int = 30):
        self.prices: Dict[str, tuple] = {}  # token -> (price, timestamp)
        self.max_age = max_age_seconds
        self._lock = threading.Lock()
    
    def update(self, token: str, price: float):
        """Update price with current timestamp"""
        with self._lock:
            self.prices[token] = (price, time.time())
    
    def get(self, token: str) -> Optional[float]:
        """Get price if not stale, None otherwise"""
        with self._lock:
            if token not in self.prices:
                return None
            price, ts = self.prices[token]
            age = time.time() - ts
            if age > self.max_age:
                return None  # Stale price
            return price
    
    def is_stale(self, token: str) -> bool:
        """Check if cached price is stale"""
        with self._lock:
            if token not in self.prices:
                return True
            _, ts = self.prices[token]
            return (time.time() - ts) > self.max_age


price_cache = PriceCache(max_age_seconds=30)


def _get_last_price_usd(token: str) -> float:
    """Fetch last price with caching and error handling"""
    # Check cache first
    cached = price_cache.get(token)
    if cached is not None:
        return cached
    
    # Fetch fresh price
    try:
        resp = requests.get("http://127.0.0.1/api/tracked?limit=200", timeout=5)
        resp.raise_for_status()
        rows = (resp.json() or {}).get("rows") or []
        for r in rows:
            if r.get("token") == token:
                lp = r.get("last_price") or r.get("peak_price") or r.get("first_price")
                price = float(lp or 0.0)
                if price > 0:
                    price_cache.update(token, price)
                return price
    except Exception as e:
        print(f"⚠️ Failed to fetch price for {token[:8]}: {e}")
    return 0.0


def _fetch_real_stats(token: str) -> Optional[Dict[str, float]]:
    """Fetch real-time stats with comprehensive error handling"""
    if not token or len(token) < 32:
        return None
    
    stats = {}
    
    # Try tracking API first (has latest price updates)
    try:
        resp = requests.get("http://127.0.0.1/api/tracked?limit=500", timeout=5)
        resp.raise_for_status()
        rows = (resp.json() or {}).get("rows") or []
        for r in rows:
            if r.get("token") == token:
                stats["market_cap_usd"] = float(r.get("last_mcap") or r.get("peak_mcap") or 0)
                stats["liquidity_usd"] = float(r.get("liquidity") or 0)
                stats["change_1h"] = float(r.get("change_1h") or 0) * 100  # Convert to percentage
                vol24 = float(r.get("vol24") or 0)
                mcap = stats.get("market_cap_usd") or 1
                stats["ratio"] = vol24 / max(mcap, 1) if mcap > 0 else 0
                stats["vol24_usd"] = vol24
                stats["price"] = float(r.get("last_price") or r.get("first_price") or 0)
                break
    except Exception as e:
        print(f"⚠️ Tracking API failed: {e}")
    
    # Fallback to alerts.jsonl for initial alert data
    if not stats or stats.get("liquidity_usd", 0) == 0:
        try:
            alerts_path = os.path.join(os.path.dirname(__file__), "..", "data", "logs", "alerts.jsonl")
            if os.path.exists(alerts_path):
                # Read last 1000 lines for recent alerts
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
        except Exception as e:
            print(f"⚠️ alerts.jsonl fallback failed: {e}")
    
    # Validation: reject if critical stats missing or invalid
    if not stats:
        return None
    
    if not stats.get("market_cap_usd") or stats["market_cap_usd"] <= 0:
        return None
    
    if not stats.get("ratio") or stats["ratio"] <= 0:
        return None
    
    if not stats.get("liquidity_usd") or stats["liquidity_usd"] <= 0:
        return None
    
    return stats


def _exit_loop(engine: TradeEngine, stop_event: threading.Event) -> None:
    """Monitor positions and execute exits when stops/trails hit"""
    print("✅ Exit monitoring loop started")
    consecutive_errors = 0
    max_errors = 10
    
    while not stop_event.is_set() and not shutdown_requested:
        try:
            # Check circuit breaker
            if engine.circuit_breaker.is_tripped():
                status = engine.circuit_breaker.get_status()
                print(f"🚨 CIRCUIT BREAKER TRIPPED: {status['reason']}")
                print(f"   Daily P&L: ${status['daily_pnl']:.2f}")
                print(f"   Consecutive losses: {status['consecutive_losses']}")
                time.sleep(60)  # Wait a minute before checking again
                continue
            
            # Iterate over a snapshot to avoid dict size change during loop
            tokens = list(engine.live.keys())
            
            for token in tokens:
                if stop_event.is_set() or shutdown_requested:
                    break
                
                # Verify position still exists in DB
                pid = get_open_position_id_by_token(token)
                if not pid:
                    # Position closed elsewhere, remove from live
                    engine.live.pop(token, None)
                    continue
                
                # Get current price
                price = _get_last_price_usd(token)
                
                # Skip if price is stale or zero
                if price <= 0 or price_cache.is_stale(token):
                    continue
                
                # Check exits
                try:
                    exited = engine.check_exits(token, price)
                    if exited:
                        print(f"✅ Position closed: {token[:8]}...")
                except Exception as e:
                    print(f"⚠️ Exit check failed for {token[:8]}: {e}")
                    consecutive_errors += 1
                    if consecutive_errors >= max_errors:
                        print(f"🚨 Too many exit errors ({consecutive_errors}), pausing...")
                        time.sleep(30)
                        consecutive_errors = 0
            
            # Reset error counter on successful iteration
            if consecutive_errors > 0:
                consecutive_errors = max(0, consecutive_errors - 1)
            
            time.sleep(2)  # Check every 2 seconds
            
        except Exception as e:
            print(f"⚠️ Exit loop error: {e}")
            consecutive_errors += 1
            time.sleep(5)
    
    print("✅ Exit monitoring loop stopped")


def run() -> None:
    """Main trading loop with comprehensive error handling"""
    global shutdown_requested
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    parser = argparse.ArgumentParser(description="Bulletproof trading system")
    parser.add_argument("--dry", action="store_true", help="Dry run (no real trades)")
    args = parser.parse_args()
    
    print("=" * 80)
    print("🚀 CallsBotOnChain - Bulletproof Trading System")
    print("=" * 80)
    
    # Initialize engine
    try:
        engine = TradeEngine()
        mode = "DRY-RUN" if engine.broker._dry else "🔥 LIVE TRADING"
        print(f"Mode: {mode}")
        print(f"Bankroll: ${engine.broker.BANKROLL_USD if hasattr(engine.broker, 'BANKROLL_USD') else 'N/A'}")
        engine._log("trading_system_start", mode="dry_run" if engine.broker._dry else "live")
    except Exception as e:
        print(f"❌ Failed to initialize engine: {e}")
        sys.exit(1)
    
    # Start exit loop thread
    stop_event = threading.Event()
    exit_thread = threading.Thread(target=_exit_loop, args=(engine, stop_event), daemon=False)
    exit_thread.start()
    
    print("✅ Monitoring signals...")
    print("-" * 80)
    
    consecutive_errors = 0
    max_consecutive_errors = 20
    
    try:
        for ev in follow_decisions(start_at_end=True):
            if shutdown_requested:
                break
            
            try:
                # Respect trading toggle
                if not trading_enabled():
                    time.sleep(0.2)
                    continue
                
                # Circuit breaker check
                if engine.circuit_breaker.is_tripped():
                    status = engine.circuit_breaker.get_status()
                    print(f"🚨 Trading disabled: {status['reason']}")
                    time.sleep(10)
                    continue
                
                token = ev.get("ca")
                event_type = ev.get("type")
                
                # Validate token
                if not token or len(token) < 32:
                    continue
                
                # Skip if already have position
                if engine.has_position(token):
                    continue
                
                # FILTER: Only trade pump.fun or bonk tokens
                if not (token.endswith("pump") or token.endswith("bonk")):
                    engine._log("token_filtered", token=token, reason="not_pump_or_bonk")
                    continue
                
                # Fetch real-time stats
                stats = _fetch_real_stats(token)
                if not stats:
                    engine._log("stats_fetch_failed", token=token, event_type=event_type)
                    continue
                
                # Route to appropriate strategy
                plan = None
                conviction = stats.get("conviction_type", "")
                
                if event_type == "pass_strict_smart":
                    plan = decide_runner(stats, is_smart=True)
                    
                elif event_type == "final":
                    if "Smart Money" in conviction:
                        plan = decide_runner(stats, is_smart=True)
                    elif "Strict" in conviction:
                        plan = decide_strict(stats)
                    elif "Nuanced" in conviction:
                        plan = decide_nuanced(stats)
                    else:
                        # Fallback: scout for high velocity
                        final_score = int(stats.get("final_score", 0))
                        if final_score >= 6:
                            plan = decide_scout(stats)
                
                # Execute trade if plan approved
                if plan:
                    # Final validation: anti-dump check
                    current_price = _get_last_price_usd(token)
                    alert_price = stats.get("price", 0)
                    
                    if current_price > 0 and alert_price > 0:
                        price_change = (current_price - alert_price) / alert_price
                        
                        # Reject if already dumped >30% from alert
                        if price_change < -0.30:
                            engine._log("entry_rejected_dumped", 
                                       token=token, 
                                       alert_price=alert_price,
                                       current_price=current_price,
                                       price_change_pct=price_change * 100)
                            print(f"⚠️  Rejected {token[:8]}: Already dumped {price_change*100:.1f}%")
                            continue
                        
                        # Also reject if pumped too much (>100%) - likely late
                        if price_change > 1.0:
                            engine._log("entry_rejected_pumped",
                                       token=token,
                                       alert_price=alert_price,
                                       current_price=current_price,
                                       price_change_pct=price_change * 100)
                            print(f"⚠️  Rejected {token[:8]}: Already pumped {price_change*100:.1f}% (too late)")
                            continue
                    
                    # Execute
                    print(f"🎯 Opening {plan['strategy']} position: {token[:8]}... (${plan['usd_size']:.0f})")
                    pid = engine.open_position(token, plan)
                    
                    if pid:
                        print(f"✅ Position #{pid} opened successfully")
                        consecutive_errors = 0
                    else:
                        print(f"⚠️  Failed to open position for {token[:8]}")
                        consecutive_errors += 1
                
            except Exception as e:
                print(f"⚠️ Error processing signal: {e}")
                engine._log("main_loop_error", error=str(e))
                consecutive_errors += 1
                
                if consecutive_errors >= max_consecutive_errors:
                    print(f"🚨 Too many consecutive errors ({consecutive_errors}), exiting...")
                    break
                
                time.sleep(1)
    
    except KeyboardInterrupt:
        print("\n🛑 Keyboard interrupt received")
    except Exception as e:
        print(f"❌ Fatal error in main loop: {e}")
        engine._log("fatal_error", error=str(e))
    finally:
        print("\n" + "=" * 80)
        print("🛑 Shutting down gracefully...")
        print("=" * 80)
        
        # Stop exit loop
        stop_event.set()
        exit_thread.join(timeout=10)
        
        # Print final status
        status = engine.get_status()
        print(f"\nFinal Status:")
        print(f"  Open positions: {status['open_positions']}")
        if status['tokens']:
            print(f"  Tokens: {', '.join([t[:8] + '...' for t in status['tokens']])}")
        
        cb_status = status['circuit_breaker']
        print(f"\nCircuit Breaker:")
        print(f"  Status: {'🔴 TRIPPED' if cb_status['tripped'] else '🟢 OK'}")
        print(f"  Daily P&L: ${cb_status['daily_pnl']:.2f}")
        print(f"  Consecutive losses: {cb_status['consecutive_losses']}")
        
        print("\n✅ Shutdown complete")


if __name__ == "__main__":
    run()

