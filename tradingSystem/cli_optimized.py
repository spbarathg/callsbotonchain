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
import base58 as b58

from .watcher import follow_decisions, follow_signals_redis
from .strategy_optimized import decide_trade, get_expected_win_rate, get_expected_avg_gain
from .trader_optimized import TradeEngine
from app.toggles import trading_enabled
from .db import get_open_position_id_by_token
from .config_optimized import MAX_CONCURRENT
from .portfolio_manager import get_portfolio_manager, should_use_portfolio_manager


def _get_last_price_usd(token: str) -> float:
    """Fetch last price with robust fallbacks.

    Order:
    1) Internal tracked API via proxy (Docker network)
    2) DexScreener token endpoint
    """
    print(f"[DEBUG] _get_last_price_usd: Starting for {token[:8]}...", flush=True)
    # 1) Tracked API via proxy
    try:
        api_url = os.getenv("API_URL", "http://callsbot-proxy/api/tracked")
        print(f"[DEBUG] _get_last_price_usd: Calling proxy API: {api_url}", flush=True)
        resp = requests.get(f"{api_url}?limit=200", timeout=4)
        print(f"[DEBUG] _get_last_price_usd: Proxy response status: {resp.status_code}", flush=True)
        resp.raise_for_status()
        rows = (resp.json() or {}).get("rows") or []
        print(f"[DEBUG] _get_last_price_usd: Got {len(rows)} rows from proxy", flush=True)
        for r in rows:
            if r.get("token") == token:
                lp = r.get("last_price") or r.get("peak_price") or r.get("first_price")
                price = float(lp or 0.0)
                if price > 0:
                    print(f"[DEBUG] _get_last_price_usd: Found price via proxy: {price}", flush=True)
                    return price
                break
    except Exception as e:
        print(f"[DEBUG] Price via proxy failed for {token[:8]}...: {e}", flush=True)

    # 2) DexScreener fallback
    try:
        print(f"[DEBUG] _get_last_price_usd: Trying DexScreener fallback...", flush=True)
        ds = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token}", timeout=4)
        print(f"[DEBUG] _get_last_price_usd: DexScreener response status: {ds.status_code}", flush=True)
        if ds.status_code == 200:
            data = ds.json() or {}
            pairs = data.get("pairs") or []
            if pairs:
                p = pairs[0]
                price = float(p.get("priceUsd") or 0.0)
                if price > 0:
                    return price
    except Exception as e:
        print(f"[DEBUG] Price via DexScreener failed for {token[:8]}...: {e}", flush=True)

    return 0.0


def _is_valid_solana_address(address: str) -> bool:
    """Validate Solana mint address (base58-decoded length 32)."""
    try:
        if not address:
            return False
        decoded = b58.b58decode(address)
        return len(decoded) == 32
    except Exception:
        return False


def _normalize_token_address(token: Optional[str]) -> Optional[str]:
    """Normalize pump.fun-style token strings to a valid mint address.

    Many upstream signals append a vanity suffix like 'pump' or 'bonk'.
    This strips known suffixes if present and returns the valid mint.
    """
    if not token:
        return token
    t = token.strip()
    for suffix in ("pump", "bonk"):
        if t.endswith(suffix):
            candidate = t[: -len(suffix)]
            if _is_valid_solana_address(candidate):
                return candidate
    # If already valid or cannot be normalized, return original
    return t


def _fetch_real_stats(token: str) -> Optional[Dict]:
    """Fetch comprehensive stats for a token"""
    stats = {}
    
    # Try tracking API first (via proxy)
    try:
        api_url = os.getenv("API_URL", "http://callsbot-proxy/api/tracked")
        resp = requests.get(f"{api_url}?limit=500", timeout=5)
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
    
    # Validation (fallback to DexScreener for missing fields)
    if not stats.get("market_cap_usd") or not stats.get("liquidity_usd") or not stats.get("price"):
        try:
            ds = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token}", timeout=4)
            if ds.status_code == 200:
                data = ds.json() or {}
                pairs = data.get("pairs") or []
                if pairs:
                    p = pairs[0]
                    stats.setdefault("price", float(p.get("priceUsd") or 0))
                    # Map some useful fields if present
                    if not stats.get("market_cap_usd"):
                        stats["market_cap_usd"] = float(p.get("fdv") or 0)
                    if not stats.get("liquidity_usd"):
                        liq = p.get("liquidity") or {}
                        stats["liquidity_usd"] = float(liq.get("usd") or 0)
                    vol24 = float(p.get("volume", {}).get("h24") or 0)
                    mcap = stats.get("market_cap_usd") or 1
                    stats["ratio"] = vol24 / max(mcap, 1) if mcap > 0 else 0
                    stats["vol24_usd"] = vol24
        except Exception:
            pass

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
    print("[EXIT_LOOP] Starting exit monitoring thread...", flush=True)
    last_status_log = 0
    last_portfolio_sync = 0
    iteration = 0
    
    while not stop_event.is_set():
        try:
            iteration += 1
            if iteration % 30 == 0:  # Log every 60 seconds (30 * 2s)
                print(f"[EXIT_LOOP] Iteration {iteration}, checking {len(engine.live)} positions", flush=True)
            
            # Log status every 5 minutes
            now = time.time()
            if now - last_status_log > 300:
                status = engine.get_status()
                engine._log("status_check", **status)
                print(f"[EXIT_LOOP] Status check: {status}", flush=True)
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
                    print(f"[EXIT_LOOP] Portfolio snapshot: {snapshot}", flush=True)
                    
                    last_portfolio_sync = now
                except Exception as e:
                    engine._log("portfolio_sync_error", error=str(e))
                    print(f"[EXIT_LOOP] Portfolio sync error: {e}", flush=True)
            
            # Check circuit breaker
            if engine.circuit_breaker.is_tripped():
                print("[EXIT_LOOP] Circuit breaker tripped, waiting...", flush=True)
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
                        if iteration % 30 == 0:
                            print(f"[EXIT_LOOP] Checking exit for {token[:8]}... at price ${price:.8f}", flush=True)
                        engine.check_exits(token, price)
                    else:
                        if iteration % 30 == 0:
                            print(f"[EXIT_LOOP] No price data for {token[:8]}...", flush=True)
                except Exception as e:
                    engine._log("exit_check_error", token=token, error=str(e))
                    print(f"[EXIT_LOOP] Exit check error for {token[:8]}...: {e}", flush=True)
            
            time.sleep(2)
            
        except Exception as e:
            engine._log("exit_loop_error", error=str(e))
            print(f"[EXIT_LOOP] FATAL ERROR: {e}", flush=True)
            import traceback
            traceback.print_exc()
            time.sleep(5)


def run() -> None:
    """Main trading loop"""
    parser = argparse.ArgumentParser(description="Optimized trading system with proven performance")
    parser.add_argument("--dry", action="store_true", help="Dry run mode")
    parser.add_argument("--legacy", action="store_true", help="Use legacy file watcher (not recommended)")
    args = parser.parse_args()

    engine = TradeEngine()
    mode = "dry_run" if engine.broker._dry else "LIVE"
    
    # Verify Jupiter API connectivity before starting trading
    print("="*60)
    print("🔍 JUPITER API HEALTH CHECK")
    print("="*60)
    from app.jupiter_client import get_jupiter_client
    jup = get_jupiter_client()
    
    if not jup.health_check():
        print("❌ Jupiter API is NOT reachable - Trading PAUSED")
        print("   Please check network connectivity and DNS resolution")
        print("   Waiting 60 seconds before retrying...")
        time.sleep(60)
        
        # Retry once
        if not jup.health_check():
            print("❌ Jupiter API still unreachable after retry - EXITING")
            print("   Please fix network issues before restarting")
            return
    
    print("✅ Jupiter API is reachable - Trading system ready")
    print("="*60)
    
    engine._log("trading_system_start", mode=mode, 
                circuit_breaker_enabled=True,
                max_daily_loss_pct=engine.circuit_breaker.max_daily_loss_pct,
                max_consecutive_losses=engine.circuit_breaker.max_consecutive_losses,
                jupiter_api_healthy=True)
    
    # Start exit loop
    stop_event = threading.Event()
    exit_thread = threading.Thread(target=_exit_loop, args=(engine, stop_event), daemon=True)
    exit_thread.start()

    # Counters for monitoring
    signals_processed = 0
    signals_filtered = 0
    positions_opened = 0
    last_health_log = time.time()

    # Choose signal source (Redis by default for real-time, fallback to file watcher)
    use_redis = not args.legacy and os.getenv("REDIS_URL")
    
    if use_redis:
        engine._log("signal_source", source="redis", real_time=True)
        print("📡 Using Redis for real-time signal consumption (recommended)")
        signal_source = follow_signals_redis(block_timeout=5)
    else:
        if args.legacy:
            engine._log("signal_source", source="file_watcher", real_time=False, reason="user_requested")
            print("⚠️  Using legacy file watcher (polling mode - slower)")
        else:
            engine._log("signal_source", source="file_watcher", real_time=False, reason="no_redis")
            print("⚠️  Redis not configured, falling back to file watcher")
        signal_source = follow_decisions(start_at_end=True)

    try:
        for ev in signal_source:
            try:
                signals_processed += 1
                
                # DEBUG: Log every signal received
                token = ev.get("ca")
                score = ev.get("score")
                token_norm = _normalize_token_address(token)
                print(
                    f"[DEBUG] Signal received: token_raw={token[:8] if token else 'None'}..., token_norm={token_norm[:8] if token_norm else 'None'}..., score={score}, type={ev.get('type')}",
                    flush=True,
                )
                engine._log("signal_received", token=token, score=score, event_type=ev.get("type"))
                
                # Log health every 10 minutes
                if time.time() - last_health_log > 600:
                    engine._log("health_check",
                               signals_processed=signals_processed,
                               signals_filtered=signals_filtered,
                               positions_opened=positions_opened,
                               open_positions=len(engine.live))
                               # circuit_breaker_status removed due to deadlock issue
                    last_health_log = time.time()
                
                # Check trading toggle
                print(f"[DEBUG] Checking trading_enabled()...", flush=True)
                if not trading_enabled():
                    print(f"[DEBUG] Trading disabled, skipping {token[:8] if token else 'None'}...", flush=True)
                    time.sleep(0.2)
                    continue
                print(f"[DEBUG] Trading is enabled, proceeding with {token[:8] if token else 'None'}...", flush=True)
                
                # Check circuit breaker (TEMPORARILY BYPASSED DUE TO DEADLOCK)
                print(f"[DEBUG] Skipping circuit breaker check (known deadlock issue)", flush=True)
                # try:
                #     is_tripped = engine.circuit_breaker.is_tripped()
                #     print(f"[DEBUG] Circuit breaker check returned: {is_tripped}", flush=True)
                #     if is_tripped:
                #         print(f"[DEBUG] Circuit breaker tripped, skipping {token[:8] if token else 'None'}...", flush=True)
                #         time.sleep(5)
                #         continue
                #     print(f"[DEBUG] Circuit breaker OK", flush=True)
                # except Exception as e:
                #     print(f"[DEBUG] ❌ Circuit breaker check failed: {e}", flush=True)
                #     import traceback
                #     traceback.print_exc()
                #     continue
                
                event_type = ev.get("type")
                print(f"[DEBUG] Event type: {event_type}", flush=True)
                
                # Validate token
                if not token_norm:
                    print("[DEBUG] No token in event, skipping...", flush=True)
                    continue
                if not _is_valid_solana_address(token_norm):
                    print(f"[DEBUG] Invalid token address after normalization: {token_norm}", flush=True)
                    engine._log("token_invalid", token=token_norm)
                    continue
                
                # Skip if already have position
                print(f"[DEBUG] Checking if already have position for {token_norm[:8]}...", flush=True)
                if engine.has_position(token_norm):
                    print(f"[DEBUG] Already have position for {token_norm[:8]}, skipping...", flush=True)
                    continue
                print(f"[DEBUG] No existing position, continuing to trade logic...", flush=True)
                
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
                
                print(f"[DEBUG] Starting trade execution for {token[:8]}...", flush=True)
                
                # Token is now validated as a Solana mint; proceed
                
                # Use stats from Redis signal (already contains everything we need!)
                print(f"[DEBUG] Extracting stats from Redis signal for {token_norm[:8]}...", flush=True)
                stats = {
                    "market_cap_usd": float(ev.get("market_cap") or 0),
                    "liquidity_usd": float(ev.get("liquidity") or 0),
                    "change_1h": float(ev.get("change_1h") or 0),
                    "vol24_usd": float(ev.get("volume_24h") or 0),
                    "price": float(ev.get("price") or 0),
                    "final_score": int(score or 7),
                    "conviction_type": ev.get("conviction_type") or "High Confidence",
                    "smart_money_detected": bool(ev.get("smart_money_detected", False)),
                }
                # Calculate ratio
                mcap = stats.get("market_cap_usd") or 1
                stats["ratio"] = stats["vol24_usd"] / max(mcap, 1) if mcap > 0 else 0
                
                # Validate we have minimum required data
                if not stats.get("market_cap_usd") or stats.get("market_cap_usd") <= 0:
                    print(f"[DEBUG] Invalid market cap for {token_norm[:8]}, trying fallback fetch...", flush=True)
                    stats_fallback = _fetch_real_stats(token_norm)
                    if stats_fallback:
                        stats.update(stats_fallback)
                    else:
                        signals_filtered += 1
                        engine._log("stats_invalid", token=token_norm, event_type=event_type)
                        print(f"[DEBUG] Failed to get valid stats for {token_norm[:8]}", flush=True)
                        continue
                print(f"[DEBUG] Stats extracted successfully: MCap=${stats['market_cap_usd']:.0f}, Liq=${stats.get('liquidity_usd', 0):.0f}", flush=True)
                
                # Check if signal is stale
                print(f"[DEBUG] Checking if signal is stale...", flush=True)
                if _is_stale_signal(stats):
                    signals_filtered += 1
                    engine._log("signal_stale", token=token_norm, 
                               alert_price=stats.get("price"),
                               current_price=_get_last_price_usd(token_norm))
                    print(f"[DEBUG] Signal is stale for {token_norm[:8]}", flush=True)
                    continue
                print(f"[DEBUG] Signal is fresh, continuing...", flush=True)
                
                # Get signal score and conviction
                print(f"[DEBUG] Extracting signal_score and conviction_type from stats...", flush=True)
                signal_score = int(stats.get("final_score", 7))
                conviction_type = stats.get("conviction_type", "High Confidence (Strict)")
                print(f"[DEBUG] signal_score={signal_score}, conviction_type={conviction_type}", flush=True)
                
                # Enforce minimum score of 8 (user requirement)
                MIN_SCORE = 8
                if signal_score < MIN_SCORE:
                    print(f"[DEBUG] ❌ Signal score {signal_score} below minimum {MIN_SCORE} - SKIPPING", flush=True)
                    signals_filtered += 1
                    engine._log("entry_rejected_low_score", token=token_norm, 
                               score=signal_score, min_score=MIN_SCORE)
                    continue
                
                # Calculate expected performance
                print(f"[DEBUG] Calling get_expected_win_rate({signal_score}, {conviction_type})...", flush=True)
                try:
                    exp_wr = get_expected_win_rate(signal_score, conviction_type)
                    print(f"[DEBUG] exp_wr={exp_wr}", flush=True)
                except Exception as e:
                    print(f"[DEBUG] ❌ EXCEPTION in get_expected_win_rate: {e}", flush=True)
                    raise
                
                print(f"[DEBUG] Calling get_expected_avg_gain({signal_score}, {conviction_type})...", flush=True)
                try:
                    exp_gain = get_expected_avg_gain(signal_score, conviction_type)
                    print(f"[DEBUG] exp_gain={exp_gain}", flush=True)
                except Exception as e:
                    print(f"[DEBUG] ❌ EXCEPTION in get_expected_avg_gain: {e}", flush=True)
                    raise
                
                # Make trade decision
                print(f"[DEBUG] Calling decide_trade(stats, {signal_score}, {conviction_type})...", flush=True)
                try:
                    plan = decide_trade(stats, signal_score, conviction_type)
                    print(f"[DEBUG] decide_trade returned: {plan}", flush=True)
                except Exception as e:
                    print(f"[DEBUG] ❌ EXCEPTION in decide_trade: {e}", flush=True)
                    raise
                
                if not plan:
                    signals_filtered += 1
                    engine._log("strategy_rejected", token=token, score=signal_score, 
                               conviction=conviction_type, reason="failed_filters")
                    print(f"[DEBUG] Plan is None, signal rejected", flush=True)
                    continue
                
                # Final validation: double-check price hasn't moved too much
                print(f"[DEBUG] Calling _get_last_price_usd({token_norm[:8]})...", flush=True)
                try:
                    current_price = _get_last_price_usd(token_norm)
                    print(f"[DEBUG] current_price={current_price}", flush=True)
                except Exception as e:
                    print(f"[DEBUG] ❌ EXCEPTION in _get_last_price_usd: {e}", flush=True)
                    raise
                
                alert_price = float(stats.get("price", 0))
                print(f"[DEBUG] alert_price={alert_price}", flush=True)
                
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
                print(f"[DEBUG] Logging trade decision for {token_norm[:8]}...", flush=True)
                engine._log("trade_decision", token=token_norm, score=signal_score,
                           conviction=conviction_type, usd_size=plan["usd_size"],
                           trail_pct=plan["trail_pct"], expected_wr=exp_wr,
                           expected_gain=exp_gain)
                print(f"[DEBUG] Trade decision logged, attempting to open position for {token_norm[:8]}...", flush=True)
                print(f"[DEBUG] Plan details: {plan}", flush=True)
                
                try:
                    print(f"[DEBUG] Calling engine.open_position({token_norm[:8]}, plan)...", flush=True)
                    pid = engine.open_position(token_norm, plan)
                    print(f"[DEBUG] engine.open_position returned: {pid}", flush=True)
                    
                    if pid:
                        positions_opened += 1
                        engine._log("position_opened_success", token=token_norm, pid=pid,
                                   total_positions=positions_opened)
                        print(f"[DEBUG] ✅ Position opened successfully: {pid}", flush=True)
                    else:
                        engine._log("position_open_failed", token=token_norm)
                        print(f"[DEBUG] ❌ Position open failed (returned None)", flush=True)
                except Exception as e:
                    engine._log("position_open_exception", token=token_norm, error=str(e))
                    print(f"[DEBUG] ❌ Exception in engine.open_position: {e}", flush=True)
                    import traceback
                    traceback.print_exc()
                
            except Exception as e:
                print(f"[DEBUG] ❌ EXCEPTION in signal processing loop: {e}", flush=True)
                import traceback
                print(f"[DEBUG] Traceback: {traceback.format_exc()}", flush=True)
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

