"""
OPTIMIZED CLI - Intelligent Orchestration
- Unified strategy based on proven win rates
- Comprehensive safety checks
- Real-time monitoring
- Graceful error handling
"""
import argparse
import json
import os
import threading
import time
from typing import Optional, Dict

import requests

from .watcher import follow_decisions
from .strategy_optimized import decide_trade, get_expected_win_rate, get_expected_avg_gain
from .trader_optimized import TradeEngine
from app.toggles import trading_enabled
from .db import get_open_position_id_by_token
from .config_optimized import MAX_CONCURRENT
from .portfolio_manager import get_portfolio_manager, should_use_portfolio_manager


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
        stats["final_score"] = 7  # Default to 7 if missing
    if "conviction_type" not in stats:
        stats["conviction_type"] = "High Confidence (Strict)"
    
    return stats


def _is_stale_signal(stats: Dict, max_age_seconds: int = 300) -> bool:
    """Check if signal is too old (price may have moved significantly)"""
    # Check if price has already moved too much
    current_price = _get_last_price_usd(stats.get("token", ""))
    alert_price = float(stats.get("price", 0))
    
    if current_price > 0 and alert_price > 0:
        price_change_pct = ((current_price - alert_price) / alert_price) * 100
        
        # Reject if already dumped >25%
        if price_change_pct < -25.0:
            return True
        
        # Reject if already pumped >50% (FOMO risk)
        if price_change_pct > 50.0:
            return True
    
    return False


def _exit_loop(engine: TradeEngine, stop_event: threading.Event) -> None:
    """Background thread to check exits and maintain portfolio"""
    last_status_log = 0
    last_portfolio_sync = 0
    
    while not stop_event.is_set():
        try:
            # Log status every 5 minutes
            now = time.time()
            if now - last_status_log > 300:
                status = engine.get_status()
                engine._log("status_check", **status)
                last_status_log = now
            
            # Sync portfolio manager every minute
            if should_use_portfolio_manager() and (now - last_portfolio_sync > 60):
                try:
                    engine.sync_portfolio_manager()
                    engine.update_portfolio_prices()
                    
                    # Log portfolio snapshot
                    pm = get_portfolio_manager()
                    snapshot = pm.get_portfolio_snapshot()
                    engine._log("portfolio_snapshot", **snapshot)
                    
                    last_portfolio_sync = now
                except Exception as e:
                    engine._log("portfolio_sync_error", error=str(e))
            
            # Check circuit breaker
            if engine.circuit_breaker.is_tripped():
                time.sleep(60)  # Wait a minute before checking again
                continue
            
            # Check exits for all open positions
            for token in list(engine.live.keys()):
                try:
                    pid = get_open_position_id_by_token(token)
                    if not pid:
                        continue
                    
                    price = _get_last_price_usd(token)
                    if price > 0:
                        engine.check_exits(token, price)
                except Exception as e:
                    engine._log("exit_check_error", token=token, error=str(e))
            
            time.sleep(2)
            
        except Exception as e:
            engine._log("exit_loop_error", error=str(e))
            time.sleep(5)


def run() -> None:
    """Main trading loop"""
    parser = argparse.ArgumentParser(description="Optimized trading system with proven performance")
    parser.add_argument("--dry", action="store_true", help="Dry run mode")
    parser.parse_args()

    engine = TradeEngine()
    mode = "dry_run" if engine.broker._dry else "LIVE"
    engine._log("trading_system_start", mode=mode, 
                circuit_breaker_enabled=True,
                max_daily_loss_pct=engine.circuit_breaker.max_daily_loss_pct,
                max_consecutive_losses=engine.circuit_breaker.max_consecutive_losses)
    
    # Start exit loop
    stop_event = threading.Event()
    exit_thread = threading.Thread(target=_exit_loop, args=(engine, stop_event), daemon=True)
    exit_thread.start()

    # Counters for monitoring
    signals_processed = 0
    signals_filtered = 0
    positions_opened = 0
    last_health_log = time.time()

    try:
        for ev in follow_decisions(start_at_end=True):
            try:
                signals_processed += 1
                
                # Log health every 10 minutes
                if time.time() - last_health_log > 600:
                    engine._log("health_check",
                               signals_processed=signals_processed,
                               signals_filtered=signals_filtered,
                               positions_opened=positions_opened,
                               open_positions=len(engine.live),
                               circuit_breaker_status=engine.circuit_breaker.get_status())
                    last_health_log = time.time()
                
                # Check trading toggle
                if not trading_enabled():
                    time.sleep(0.2)
                    continue
                
                # Check circuit breaker
                if engine.circuit_breaker.is_tripped():
                    time.sleep(5)
                    continue
                
                token = ev.get("ca")
                event_type = ev.get("type")
                
                if not token:
                    continue
                
                # Skip if already have position
                if engine.has_position(token):
                    continue
                
                # Check if portfolio is full - evaluate rebalancing
                if should_use_portfolio_manager() and len(engine.live) >= MAX_CONCURRENT:
                    signals_filtered += 1
                    
                    # Update current prices for accurate momentum calculation
                    pm = get_portfolio_manager()
                    price_updates = {}
                    for open_token in list(engine.live.keys()):
                        try:
                            open_price = _get_last_price_usd(open_token)
                            if open_price > 0:
                                price_updates[open_token] = open_price
                        except Exception:
                            pass
                    
                    if price_updates:
                        pm.update_prices(price_updates)
                    
                    # Get stats and make plan first (need for evaluation)
                    stats = _fetch_real_stats(token)
                    if not stats:
                        engine._log("rebalance_skipped", token=token, reason="stats_fetch_failed")
                        continue
                    
                    # Check if signal is stale
                    if _is_stale_signal(stats):
                        engine._log("rebalance_skipped", token=token, reason="signal_stale")
                        continue
                    
                    # Get signal score and conviction
                    signal_score = int(stats.get("final_score", 7))
                    conviction_type = stats.get("conviction_type", "High Confidence (Strict)")
                    
                    # Prepare signal for evaluation
                    current_price = _get_last_price_usd(token)
                    if current_price <= 0:
                        current_price = float(stats.get("price", 0))
                    
                    new_signal = {
                        "token": token,
                        "score": signal_score,
                        "conviction_type": conviction_type,
                        "price": current_price,
                        "quantity": 0,  # Will be calculated in plan
                        "prelim_score": signal_score,
                        "name": stats.get("name", ""),
                        "symbol": stats.get("symbol", ""),
                    }
                    
                    # Evaluate rebalancing opportunity
                    should_rebalance, token_to_replace, reason = pm.evaluate_rebalance(new_signal)
                    
                    if should_rebalance:
                        # Make trade decision
                        plan = decide_trade(stats, signal_score, conviction_type)
                        
                        if plan:
                            engine._log("rebalance_attempt", 
                                       old_token=token_to_replace[:8],
                                       new_token=token[:8],
                                       new_score=signal_score,
                                       reason=reason)
                            
                            # Execute atomic rebalance
                            success = engine.rebalance_position(token_to_replace, token, plan)
                            
                            if success:
                                positions_opened += 1
                                engine._log("rebalance_success",
                                           sold=token_to_replace[:8],
                                           bought=token[:8],
                                           total_rebalances=positions_opened)
                            else:
                                engine._log("rebalance_failed",
                                           old_token=token_to_replace[:8],
                                           new_token=token[:8])
                        else:
                            engine._log("rebalance_skipped", 
                                       token=token[:8],
                                       reason="plan_failed")
                    else:
                        engine._log("rebalance_rejected", 
                                   token=token[:8],
                                   score=signal_score,
                                   reason=reason)
                    
                    # Continue to next signal after rebalancing attempt
                    continue
                
                # FILTER: Only pump.fun tokens (bot generates these)
                if not token.endswith("pump"):
                    signals_filtered += 1
                    engine._log("token_filtered", token=token, reason="not_pump_token")
                    continue
                
                # Fetch real-time stats
                stats = _fetch_real_stats(token)
                if not stats:
                    signals_filtered += 1
                    engine._log("stats_fetch_failed", token=token, event_type=event_type)
                    continue
                
                # Check if signal is stale
                if _is_stale_signal(stats):
                    signals_filtered += 1
                    engine._log("signal_stale", token=token, 
                               alert_price=stats.get("price"),
                               current_price=_get_last_price_usd(token))
                    continue
                
                # Get signal score and conviction
                signal_score = int(stats.get("final_score", 7))
                conviction_type = stats.get("conviction_type", "High Confidence (Strict)")
                
                # Calculate expected performance
                exp_wr = get_expected_win_rate(signal_score, conviction_type)
                exp_gain = get_expected_avg_gain(signal_score, conviction_type)
                
                # Make trade decision
                plan = decide_trade(stats, signal_score, conviction_type)
                
                if not plan:
                    signals_filtered += 1
                    engine._log("strategy_rejected", token=token, score=signal_score, 
                               conviction=conviction_type, reason="failed_filters")
                    continue
                
                # Final validation: double-check price hasn't moved too much
                current_price = _get_last_price_usd(token)
                alert_price = float(stats.get("price", 0))
                
                if current_price > 0 and alert_price > 0:
                    price_change_pct = ((current_price - alert_price) / alert_price) * 100
                    
                    if price_change_pct < -25.0:
                        signals_filtered += 1
                        engine._log("entry_rejected_dumped", token=token, 
                                   price_change_pct=price_change_pct)
                        continue
                    
                    if price_change_pct > 50.0:
                        signals_filtered += 1
                        engine._log("entry_rejected_fomo", token=token,
                                   price_change_pct=price_change_pct)
                        continue
                
                # Execute trade
                engine._log("trade_decision", token=token, score=signal_score,
                           conviction=conviction_type, usd_size=plan["usd_size"],
                           trail_pct=plan["trail_pct"], expected_wr=exp_wr,
                           expected_gain=exp_gain)
                
                pid = engine.open_position(token, plan)
                
                if pid:
                    positions_opened += 1
                    engine._log("position_opened_success", token=token, pid=pid,
                               total_positions=positions_opened)
                else:
                    engine._log("position_open_failed", token=token)
                
            except Exception as e:
                engine._log("signal_processing_error", error=str(e), token=token)
                continue
    
    except KeyboardInterrupt:
        engine._log("trading_system_shutdown", reason="keyboard_interrupt",
                   signals_processed=signals_processed,
                   positions_opened=positions_opened)
    except Exception as e:
        engine._log("trading_system_error", error=str(e))
    finally:
        stop_event.set()
        exit_thread.join(timeout=5)
        engine._log("trading_system_stopped")


if __name__ == "__main__":
    run()

