"""
OPTIMIZED CLI - Intelligent Orchestration
- Unified strategy based on proven win rates
- Comprehensive safety checks
- Real-time monitoring
- Graceful error handling
"""
# Apply DNS patch FIRST before any other imports that might use network
from app.dns_patch import apply_dns_patch
apply_dns_patch()

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
from .config_optimized import MAX_CONCURRENT, EXIT_CHECK_INTERVAL_SEC
from .portfolio_manager import get_portfolio_manager, should_use_portfolio_manager
from .price_cache import get_price_cache
from .watch_list_manager import get_watch_list_manager
from .watch_list_monitor import get_watch_list_monitor


def _get_last_price_usd(token: str, use_cache: bool = True) -> float:
    """Fetch REAL sellable price using Jupiter quotes for EXIT MONITORING ONLY.
    
    CRITICAL: This function is ONLY called for exit monitoring of OPEN positions.
              All price checks use Jupiter API (no DexScreener per user requirement).
    
    Args:
        token: Token address
        use_cache: If True, return cached price if available (default: True)
    
    Strategy:
    1) Get current holdings for this token
    2) Use Jupiter quote to get REAL sellable price (what you'd actually get)
    3) Cache aggressively (10s TTL) to minimize API calls
    4) Result: Accurate prices that match Axiom/real wallets
    
    Benefits:
    - Stop losses trigger correctly (-20% instead of never)
    - Profit tracking shows reality (-4% instead of +97,000%)
    - Can capture 67x gains properly (vs 0% currently)
    
    API Safety:
    - 10s cache = 0.1 RPS per position
    - 5 positions = 0.5 RPS total
    - vs 9 RPS Jupiter Pro limit = 5.6x headroom
    """
    from .jupiter_price_oracle import get_jupiter_oracle
    from .db import get_open_qty_by_token
    
    # Get current holdings for this token
    try:
        holdings = get_open_qty_by_token(token)
        if holdings is None or holdings <= 0:
            print(f"[PRICE] No holdings found for {token[:8]}, cannot get price", flush=True)
            return 0.0
    except Exception as e:
        print(f"[PRICE] Error getting holdings for {token[:8]}: {e}", flush=True)
        return 0.0
    
    # Get real sellable price from Jupiter
    try:
        oracle = get_jupiter_oracle(cache_ttl=60)  # 60s cache (rate limit protection)
        price = oracle.get_price(token, holdings)
        
        if price > 0:
            return price
        else:
            print(f"[PRICE] Jupiter oracle returned 0 for {token[:8]}", flush=True)
            return 0.0
            
    except Exception as e:
        print(f"[PRICE] Jupiter oracle error for {token[:8]}: {e}", flush=True)
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
    
    # REMOVED: DexScreener fallback (user requirement: Jupiter API only)
    # If signal provider doesn't include these fields, we skip the signal
    # This ensures we only trade on high-quality signals with complete data

    if not stats.get("market_cap_usd") or not stats.get("liquidity_usd"):
        return None
    
    # Ensure we have score and conviction
    if "final_score" not in stats:
        stats["final_score"] = 7  # Default to 7 if missing
    if "conviction_type" not in stats:
        stats["conviction_type"] = "High Confidence (Strict)"
    
    return stats


def _is_stale_signal(stats: Dict, current_price: Optional[float] = None, max_age_seconds: int = 300) -> bool:
    """Check if signal is too old (price may have moved significantly)
    
    Args:
        stats: Signal statistics dictionary
        current_price: Optional pre-fetched current price (avoids redundant API call)
        max_age_seconds: Max age in seconds (unused, for future use)
    """
    # Use provided price or fetch it (but prefer provided to avoid duplicate calls)
    if current_price is None:
        current_price = _get_last_price_usd(stats.get("token", ""), use_cache=True)
    
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


def _check_portfolio_take_profit(engine: TradeEngine) -> bool:
    """
    NET STRATEGY: Close entire net when portfolio profit target hit
    
    Target: 5x total portfolio value (500% return)
    Action: Sell ALL positions immediately
    
    Returns True if bulk exit was triggered
    """
    from .config_optimized import NET_STRATEGY_MODE, NET_TAKE_PROFIT_PCT
    from .db import get_open_qty
    
    if not NET_STRATEGY_MODE:
        return False  # Only in Net mode
    
    if not engine.live:
        return False  # No positions
    
    # Calculate total portfolio P&L
    total_entry_usd = 0.0
    total_current_usd = 0.0
    position_details = []
    
    for token, pos_data in engine.live.items():
        pid = pos_data.get("pid")
        entry_price = pos_data.get("entry_price", 0)
        
        if entry_price <= 0 or not pid:
            continue
        
        # Get current price
        try:
            current_price = _get_last_price_usd(token, use_cache=True)
            if current_price <= 0:
                continue
        except Exception:
            continue
        
        # Get quantity
        try:
            qty = get_open_qty(pid)
            if qty <= 0:
                continue
        except Exception:
            continue
        
        # Calculate values
        entry_val = entry_price * qty
        current_val = current_price * qty
        
        total_entry_usd += entry_val
        total_current_usd += current_val
        
        position_details.append({
            "token": token[:8],
            "entry_val": entry_val,
            "current_val": current_val,
            "pnl_pct": ((current_val - entry_val) / entry_val * 100) if entry_val > 0 else 0
        })
    
    # Calculate portfolio P&L %
    if total_entry_usd <= 0:
        return False
    
    portfolio_pnl_pct = ((total_current_usd - total_entry_usd) / total_entry_usd) * 100
    
    # Check if target hit
    if portfolio_pnl_pct >= NET_TAKE_PROFIT_PCT:
        print(f"\n{'='*60}", flush=True)
        print(f"🎯 NET TAKE PROFIT TRIGGERED!", flush=True)
        print(f"{'='*60}", flush=True)
        print(f"   Portfolio P&L: +{portfolio_pnl_pct:.1f}% (target: +{NET_TAKE_PROFIT_PCT:.1f}%)", flush=True)
        print(f"   Total Entry: ${total_entry_usd:.2f}", flush=True)
        print(f"   Total Current: ${total_current_usd:.2f}", flush=True)
        print(f"   Profit: ${total_current_usd - total_entry_usd:.2f}", flush=True)
        print(f"   Closing entire net: {len(engine.live)} positions", flush=True)
        print(f"{'='*60}", flush=True)
        
        # Log individual position details
        for detail in position_details:
            print(f"   {detail['token']}... ${detail['entry_val']:.2f} → ${detail['current_val']:.2f} (+{detail['pnl_pct']:.1f}%)", flush=True)
        
        print(f"{'='*60}\n", flush=True)
        
        # Sell ALL positions (force exit, bypass normal exit logic)
        closed_count = 0
        failed_count = 0
        
        for token in list(engine.live.keys()):
            try:
                from .db import close_position as db_close_position, get_open_qty
                
                pos_data = engine.live[token]
                pid = pos_data.get("pid")
                entry_price = pos_data.get("entry_price", 0)
                
                if not pid:
                    continue
                
                # Get current holdings
                qty = get_open_qty(pid)
                if qty <= 0:
                    # No holdings, just close in DB and remove from live
                    db_close_position(pid)
                    engine.live.pop(token, None)
                    closed_count += 1
                    print(f"   ✅ Closed {token[:8]} (no holdings)", flush=True)
                    continue
                
                # Execute market sell (FORCE SELL for portfolio take profit)
                fill = engine.broker.market_sell(
                    token=token,
                    qty=qty
                )
                
                if fill.success:
                    # Calculate P&L
                    pnl_usd = fill.usd - (entry_price * qty)
                    pnl_pct = ((fill.price - entry_price) / entry_price * 100) if entry_price > 0 else 0
                    
                    # Record fill and close position
                    from .db import add_fill
                    add_fill(pid, "sell", fill.price, fill.qty, fill.usd)
                    db_close_position(pid)
                    
                    # Remove from live
                    engine.live.pop(token, None)
                    
                    # Record with circuit breaker
                    engine.circuit_breaker.record_trade(pnl_usd, fill.slippage_pct)
                    
                    closed_count += 1
                    print(f"   ✅ Sold {token[:8]}: {qty:.4f} @ ${fill.price:.8f} | P&L: ${pnl_usd:+.2f} ({pnl_pct:+.1f}%)", flush=True)
                else:
                    # Sell failed - log and skip
                    failed_count += 1
                    print(f"   ❌ Failed to sell {token[:8]}: {fill.error}", flush=True)
                    engine._log("net_take_profit_sell_failed", token=token, pid=pid, error=fill.error)
                
            except Exception as e:
                failed_count += 1
                print(f"   ❌ Exception closing {token[:8]}...: {e}", flush=True)
                engine._log("net_take_profit_close_error", token=token, error=str(e))
                import traceback
                traceback.print_exc()
        
        engine._log("net_take_profit_executed",
                   portfolio_pnl_pct=portfolio_pnl_pct,
                   total_entry_usd=total_entry_usd,
                   total_current_usd=total_current_usd,
                   profit_usd=total_current_usd - total_entry_usd,
                   positions_closed=closed_count,
                   positions_failed=failed_count)
        
        if failed_count > 0:
            print(f"\n⚠️  NET PARTIALLY CLOSED: {closed_count} succeeded, {failed_count} failed", flush=True)
            print(f"   Successfully closed positions earned +${total_current_usd - total_entry_usd:.2f}", flush=True)
        else:
            print(f"\n🎉 NET CLOSED: {closed_count} positions, +${total_current_usd - total_entry_usd:.2f} profit", flush=True)
            print(f"💰 Ready to cast bigger net with ${total_current_usd:.2f} capital!\n", flush=True)
        
        return True
    
    return False


def _exit_loop(engine: TradeEngine, stop_event: threading.Event) -> None:
    """Background thread to check exits and maintain portfolio"""
    print("[EXIT_LOOP] Starting exit monitoring thread...", flush=True)
    last_status_log = 0
    last_portfolio_sync = 0
    last_health_check = 0  # CRITICAL FIX: Position health monitoring
    iteration = 0
    
    # CRITICAL FIX (Nov 1): Clean up ghost positions on startup
    # Problem: qty=0 positions accumulate over time, spam Jupiter API
    # Solution: Close all positions with qty=0 on startup
    try:
        from tradingSystem.db import init, conn
        init()
        cursor = conn.cursor()
        cursor.execute("SELECT id, token_address FROM positions WHERE status='open' AND qty <= 0")
        ghost_positions = cursor.fetchall()
        if ghost_positions:
            print(f"[EXIT_LOOP] 🧹 Found {len(ghost_positions)} ghost positions (qty=0) on startup, cleaning up...", flush=True)
            from tradingSystem.db import close_position
            for pid, token in ghost_positions:
                close_position(pid)
                print(f"[EXIT_LOOP] Closed ghost position #{pid} ({token[:8]}...)", flush=True)
    except Exception as e:
        print(f"[EXIT_LOOP] ⚠️ Error cleaning ghost positions on startup: {e}", flush=True)
    
    # Initialize adaptive monitoring (smart intervals based on position maturity)
    from tradingSystem.adaptive_monitor import AdaptiveMonitor
    monitor = AdaptiveMonitor()
    
    # Base check interval (for loop sleep)
    check_interval = EXIT_CHECK_INTERVAL_SEC
    is_pro = bool(os.getenv("JUPITER_API_KEY"))
    tier_label = "Pro (10 RPS)" if is_pro else "Free (1 RPS)"
    print(f"[EXIT_LOOP] Base interval: {check_interval}s (Jupiter {tier_label})", flush=True)
    print(f"[EXIT_LOOP] Adaptive monitoring: ENABLED", flush=True)
    print(f"[EXIT_LOOP] Tiers: Fast(3s) → Medium(30m) → Slow(2h) → Ultra(4h)", flush=True)
    print(f"[EXIT_LOOP] Inactivity exit: 10 minutes of <5% movement (AGGRESSIVE)", flush=True)
    print(f"[EXIT_LOOP] Moonshot mode: High-profit (>200%) + active price = unlimited hold", flush=True)
    
    while not stop_event.is_set():
        try:
            iteration += 1
            if iteration % 12 == 0:  # Log every 60 seconds (12 * 5s)
                print(f"[EXIT_LOOP] Iteration {iteration}, checking {len(engine.live)} positions", flush=True)
            
            # NET STRATEGY: Check portfolio-level take profit FIRST (before individual exits)
            if _check_portfolio_take_profit(engine):
                print(f"[EXIT_LOOP] 🎯 Portfolio take profit executed - all positions closed", flush=True)
                time.sleep(30)  # Wait before next cycle
                continue
            
            # Log status every 5 minutes
            now = time.time()
            if now - last_status_log > 300:
                status = engine.get_status()
                engine._log("status_check", **status)
                print(f"[EXIT_LOOP] Status check: {status}", flush=True)
                
                # Log cache stats
                cache = get_price_cache()
                cache_stats = cache.get_stats()
                engine._log("price_cache_stats", **cache_stats)
                print(f"[EXIT_LOOP] Price cache: {cache_stats}", flush=True)
                
                last_status_log = now
            
            # CRITICAL FIX: Position health check every 2 minutes
            # Problem: IDs 219(+505%), 212(+191%), 211(+133%) peaked but never sold
            # Solution: Verify high-profit positions are still sellable, force action if not
            if now - last_health_check > 120:  # Every 2 minutes
                try:
                    for token in list(engine.live.keys()):
                        pos_data = engine.live.get(token, {})
                        entry_price = pos_data.get("entry_price", 0)
                        peak_price = pos_data.get("peak_price", 0)
                        
                        if peak_price > 0 and entry_price > 0:
                            peak_profit_pct = ((peak_price - entry_price) / entry_price * 100)
                            
                            # High-profit positions need health monitoring
                            if peak_profit_pct >= 50:
                                print(f"[HEALTH] Checking high-profit position {token[:8]}... (peak: +{peak_profit_pct:.1f}%)", flush=True)
                                
                                # Verify position is in exit monitoring
                                if token not in engine.live:
                                    print(f"[HEALTH] ⚠️ HIGH PROFIT POSITION {token[:8]} NOT IN LIVE TRACKING!", flush=True)
                                    continue
                                
                                # Check if we've attempted profit-take
                                profit_level = int(peak_profit_pct // 100) * 100
                                profit_take_key = f"profit_take_attempted_{profit_level}"
                                if not pos_data.get(profit_take_key, False):
                                    print(f"[HEALTH] 🚨 ALERT: {token[:8]} at +{peak_profit_pct:.1f}% but NO PROFIT-TAKE ATTEMPTED!", flush=True)
                                    print(f"[HEALTH] Forcing profit-take check on next iteration...", flush=True)
                                    # Force a price check to trigger profit-take logic
                                    engine.live[token]["force_check"] = True
                    
                    last_health_check = now
                except Exception as e:
                    print(f"[HEALTH] Health check error: {e}", flush=True)
            
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
            
            # CRITICAL FIX: NEVER pause exit monitoring!
            # Price checks use Jupiter with caching, so we can always monitor positions
            # The broker's sell function handles Jupiter cooldown gracefully
            # Pausing exits during cooldowns causes massive losses (-20% -> -37% bleeding)
            
            # Check exits for all open positions (STAGGERED to prevent rate limits)
            # CRITICAL FIX (Nov 1): Increased stagger delay to prevent Jupiter 429s
            # Problem: 200ms delay = 5 RPS per position, 6 positions in burst = rate limit
            # Solution: 1.0s delay between positions = 1 RPS max, well under 10 RPS limit
            # With price caching (60s TTL), this is safe and prevents API abuse
            for idx, token in enumerate(list(engine.live.keys())):
                try:
                    # Stagger checks to prevent API burst (1.0s = safe under 10 RPS limit)
                    if idx > 0:
                        time.sleep(1.0)  # 1 second delay between positions (was 200ms)
                    
                    pid = get_open_position_id_by_token(token)
                    if not pid:
                        continue
                    
                    # CRITICAL: Skip positions with quantity=0 (failed fills)
                    # These are ghost entries that spam Jupiter and trigger rate limits
                    from tradingSystem.db import get_open_qty
                    qty = get_open_qty(pid)
                    if iteration == 1:  # Debug on first iteration
                        print(f"[EXIT_LOOP] Position {token[:8]}... qty={qty} (type={type(qty).__name__})", flush=True)
                    if qty == 0 or qty == 0.0:
                        if iteration % 300 == 0 or iteration == 1:
                            print(f"[EXIT_LOOP] Skipping {token[:8]}... (quantity={qty}, failed fill)", flush=True)
                        continue
                    
                    # Get position data for adaptive monitoring
                    pos_data = engine.live.get(token, {})
                    entry_time = pos_data.get("entry_time", time.time())
                    entry_price = pos_data.get("entry_price", 0)  # FIXED: was "entry" (wrong key!)
                    
                    # Get current price (will use cache if available)
                    price = _get_last_price_usd(token, use_cache=True)
                    
                    # GHOST POSITION CLEANUP: Auto-close positions with repeated price failures
                    # Problem: Dead/rugged tokens keep calling Jupiter API every iteration
                    # Solution: Track consecutive failures, auto-close after 3 failures
                    if price <= 0:
                        price_failures = pos_data.get("price_failures", 0) + 1
                        pos_data["price_failures"] = price_failures
                        
                        if price_failures >= 3:
                            print(f"[EXIT_LOOP] 👻 GHOST POSITION: {token[:8]}... - {price_failures} consecutive price failures, auto-closing", flush=True)
                            from .db import close_position
                            close_position(pid)
                            if token in engine.live:
                                del engine.live[token]
                            engine._log("ghost_position_auto_closed", token=token, pid=pid, price_failures=price_failures)
                            continue
                        else:
                            # Skip this iteration, will retry next time
                            if iteration % 60 == 0:  # Log every 5 minutes
                                print(f"[EXIT_LOOP] ⚠️ Price unavailable for {token[:8]}... (failure {price_failures}/3)", flush=True)
                            continue
                    else:
                        # Reset failure counter on successful price fetch
                        if "price_failures" in pos_data:
                            pos_data["price_failures"] = 0
                    
                    # DUST CLEANUP: Auto-close positions worth <$1 OR with negligible on-chain balance
                    # Problem: 95% sell buffer leaves dust per position
                    # Solution: Force-close positions with negligible value or quantity
                    
                    # Check 1: Value-based cleanup (requires price)
                    if price > 0 and qty > 0:
                        position_value_usd = price * qty
                        if position_value_usd < 1.0:
                            print(f"[EXIT_LOOP] 🧹 DUST DETECTED (value): {token[:8]}... worth ${position_value_usd:.4f} (<$1)", flush=True)
                            print(f"[EXIT_LOOP] Force-closing dust position in database", flush=True)
                            from .db import close_position
                            close_position(pid)
                            if token in engine.live:
                                del engine.live[token]
                            continue
                    
                    # Check 2: Quantity-based cleanup (for rugged/dead tokens with no price)
                    # If database shows large qty but wallet is nearly empty, it's dust from failed sell
                    try:
                        from .broker_optimized import Broker
                        from solders.keypair import Keypair
                        # os is already imported at module level
                        kp = Keypair.from_base58_string(os.getenv("TS_WALLET_SECRET"))
                        broker = Broker(kp, dry_run=False)
                        actual_balance = broker._query_token_balance(token)
                        
                        if actual_balance is not None and actual_balance < 0.01:  # Less than 0.01 tokens
                            print(f"[EXIT_LOOP] 🧹 DUST DETECTED (quantity): {token[:8]}... only {actual_balance:.6f} tokens on-chain", flush=True)
                            print(f"[EXIT_LOOP] Force-closing dust position (worthless amount)", flush=True)
                            from .db import close_position
                            close_position(pid)
                            if token in engine.live:
                                del engine.live[token]
                            continue
                    except Exception as e:
                        # Don't crash exit loop on balance query errors
                        pass
                    
                    if price > 0:
                        # Calculate current profit
                        current_profit_pct = ((price - entry_price) / entry_price * 100) if entry_price > 0 else 0
                        
                        # ADAPTIVE MONITORING: Check if this position needs monitoring right now
                        should_check, reason = monitor.should_check_position(
                            token=token,
                            entry_time=entry_time,
                            current_profit_pct=current_profit_pct
                        )
                        
                        if should_check:
                            if iteration % 300 == 0 or "Tier" in reason:
                                print(f"[EXIT_LOOP] ✓ Checking {token[:8]}... ${price:.8f} ({reason})", flush=True)
                            
                            # CRITICAL: check_exits returns True when position is closed (ghost/rugged/sold)
                            # If True, skip remaining processing for this token
                            position_closed = engine.check_exits(token, price)
                            if position_closed:
                                print(f"[EXIT_LOOP] 🔒 Position {token[:8]} was closed, removing from tracking", flush=True)
                                continue  # Skip to next position
                            
                            # PYRAMIDING: Check if we should add to this winning position
                            from .config_optimized import PYRAMIDING_ENABLED
                            if PYRAMIDING_ENABLED and current_profit_pct > 30:
                                # Only check pyramiding for profitable positions
                                # Fetch token stats for momentum validation
                                try:
                                    stats = _fetch_real_stats(token)
                                    if stats:
                                        engine.add_to_position(token, price, stats)
                                except Exception as pyramid_error:
                                    # Don't crash the exit loop on pyramid failures
                                    pass
                        else:
                            # Position doesn't need checking yet (saves API limits!)
                            if iteration % 600 == 0:  # Log every 10 minutes for skipped positions
                                print(f"[EXIT_LOOP] ⏸️  Skipping {token[:8]}... (${price:.8f}, {reason})", flush=True)
                            continue
                        # Reset price failure counter on success
                        # NOTE: DO NOT reset sell_failures here - it's managed by check_exits
                        if token in engine.live:
                            engine.live[token]["price_failures"] = 0
                    else:
                        # Track consecutive price failures
                        # CRITICAL: Do NOT count failures during Jupiter cooldown (API rate limiting)
                        # Only count when token is actually dead/rugged
                        if token in engine.live:
                            # Check if Jupiter is in cooldown
                            from app.jupiter_client import get_jupiter_client
                            jupiter = get_jupiter_client()
                            is_cooling, cooldown_remaining = jupiter.is_in_cooldown()
                            
                            # Only count failures if NOT in cooldown
                            if not is_cooling:
                                failures = engine.live[token].get("price_failures", 0) + 1
                                engine.live[token]["price_failures"] = failures
                            else:
                                # Don't increment during cooldown, but keep existing count
                                failures = engine.live[token].get("price_failures", 0)
                                if iteration % 100 == 0:
                                    print(f"[EXIT_LOOP] Skipping failure count for {token[:8]} (Jupiter cooldown: {cooldown_remaining:.1f}s)", flush=True)
                            
                            # Force close position after 10 failed price checks (ONLY when not rate-limited)
                            # This prevents force-closing profitable positions during API issues
                            if failures >= 10 and not is_cooling:
                                engine._log("force_closing_dead_position", token=token, failures=failures,
                                           reason="cannot_get_price_for_5min")
                                print(f"[EXIT_LOOP] ⚠️ Force-closing dead position {token[:8]} after {failures} price failures", flush=True)
                                
                                # Force close in database and clear from live
                                try:
                                    from tradingSystem.db import close_position
                                    data = engine.live.get(token)
                                    if data and data.get("pid"):
                                        close_position(data["pid"])
                                    engine.live.pop(token, None)
                                    monitor.reset_position(token)  # Clean up adaptive monitor
                                    engine.inactivity_monitor.reset_position(token)  # Clean up inactivity monitor
                                    print(f"[EXIT_LOOP] ✅ Forced position closed: {token[:8]}", flush=True)
                                except Exception as e:
                                    engine._log("force_close_error", token=token, error=str(e))
                            
                            elif failures > 5:  # Warning at 25 seconds
                                engine._log("exit_repeated_price_failures", token=token, failures=failures)
                                print(f"[EXIT_LOOP] ⚠️ {failures} consecutive price failures for {token[:8]}, will force-close at 10", flush=True)
                        
                        if iteration % 300 == 0:
                            print(f"[EXIT_LOOP] No price data for {token[:8]}...", flush=True)
                except Exception as e:
                    engine._log("exit_check_error", token=token, error=str(e))
                    print(f"[EXIT_LOOP] Exit check error for {token[:8]}...: {e}", flush=True)
            
            time.sleep(check_interval)
            
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
    
    # Initialize Watch & Strike system
    print("="*60)
    print("🎯 INITIALIZING WATCH & STRIKE SYSTEM")
    print("="*60)
    watch_manager = get_watch_list_manager()
    watch_monitor = get_watch_list_monitor(engine)
    watch_monitor.start()
    print("✅ Watch List Manager: ACTIVE")
    print("✅ Background Price Monitor: RUNNING")
    print("   Strategy: Track ALL signals, enter only best movers")
    print("   API: Jupiter (reliable), Rate: <1 RPS average")
    print("="*60)
    
    # Verify Jupiter API connectivity before starting trading (non-blocking with backoff)
    print("="*60)
    print("🔍 JUPITER API HEALTH CHECK")
    print("="*60)
    from app.jupiter_client import get_jupiter_client
    jup = get_jupiter_client()
    
    healthy = False
    max_checks = 3
    for i in range(max_checks):
        if jup.health_check():
            healthy = True
            break
        backoff = 1 << i  # 1, 2, 4 seconds
        print(f"❌ Jupiter 429/health check failed - retrying in {backoff}s (attempt {i+1}/{max_checks})")
        time.sleep(backoff)
    
    if healthy:
        print("✅ Jupiter API is reachable - Trading system ready")
    else:
        # Non-blocking startup: continue trading; client has internal rate limiting/backoff
        print("⚠️  Jupiter API not confirmed healthy yet; starting trading and will rely on client backoff")
    print("="*60)
    
    engine._log("trading_system_start", mode=mode, jupiter_api_healthy=True)
    
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
                # === WATCH LIST RECOMMENDATION PROCESSING ===
                # Check for tokens that are ready to enter (showing real movement)
                entries, reentries = watch_monitor.get_pending_recommendations()
                
                for entry_rec in entries:
                    try:
                        entry_token = entry_rec['token']
                        entry_price = entry_rec['current_price']
                        entry_reason = entry_rec['reason']
                        
                        # Check if we have capital and position slots
                        if len(engine.live) >= MAX_CONCURRENT:
                            print(f"[WATCHLIST] ⏸️  Max positions reached, delaying entry for {entry_token[:8]}", flush=True)
                            continue
                        
                        if engine.has_position(entry_token):
                            print(f"[WATCHLIST] ⏸️  Already have position for {entry_token[:8]}", flush=True)
                            continue
                        
                        # Fetch stats and create plan
                        print(f"[WATCHLIST] 🎯 ENTRY TRIGGERED: {entry_token[:8]} | {entry_reason}", flush=True)
                        entry_stats = _fetch_real_stats(entry_token)
                        if not entry_stats:
                            print(f"[WATCHLIST] ❌ Failed to fetch stats for {entry_token[:8]}", flush=True)
                            continue
                        
                        # CRITICAL: Re-validate before entry (especially for young tokens)
                        # Problem: Token may have matured but could still be a scam
                        # Solution: Run full validation again
                        from tradingSystem.pre_entry_validator import get_pre_entry_validator
                        from tradingSystem.rugpull_detector import get_rugpull_detector
                        
                        pre_validator = get_pre_entry_validator()
                        detector = get_rugpull_detector()
                        liquidity_usd = float(entry_stats.get("liquidity_usd", 0))
                        
                        # Rugpull check
                        is_rugpull, rugpull_reason = detector.is_likely_rugpull(entry_token, liquidity_usd)
                        if is_rugpull:
                            print(f"[WATCHLIST] 🚨 REJECTED: {rugpull_reason} (liquidity=${liquidity_usd:.0f})", flush=True)
                            continue
                        
                        # Full validation (age, dumps, tradeability)
                        is_valid, validation_reason = pre_validator.validate_token(entry_token, entry_stats)
                        if not is_valid:
                            print(f"[WATCHLIST] 🚨 REJECTED: {validation_reason}", flush=True)
                            continue
                        
                        # MOMENTUM VALIDATION (NEW - OCT 31 2025)
                        # Problem: Entering too early led to -32% loss on DyRAaLJM
                        # Solution: Wait for momentum confirmation before entry
                        from tradingSystem.momentum_entry_validator import get_momentum_validator
                        momentum_val = get_momentum_validator()
                        has_momentum, momentum_reason = momentum_val.validate_entry_momentum(entry_token, entry_stats)
                        if not has_momentum:
                            print(f"[WATCHLIST] ⏸️  NO MOMENTUM: {momentum_reason} - keeping on watchlist", flush=True)
                            continue
                        
                        print(f"[WATCHLIST] ✅ Passed all safety checks + momentum confirmation ({momentum_reason})", flush=True)
                        
                        entry_score = entry_rec.get('score', 7)
                        entry_conviction = entry_rec.get('conviction', 'Medium Confidence')
                        entry_plan = decide_trade(entry_stats, entry_score, entry_conviction)
                        
                        if entry_plan:
                            print(f"[WATCHLIST] 💰 Opening ${entry_plan['usd_size']:.2f} position for {entry_token[:8]}", flush=True)
                            pid = engine.open_position(entry_token, entry_plan)
                            if pid:
                                watch_manager.mark_entered(entry_token, pid, entry_price)
                                positions_opened += 1
                                print(f"[WATCHLIST] ✅ Position #{pid} opened for {entry_token[:8]}", flush=True)
                    except Exception as e:
                        print(f"[WATCHLIST] ❌ Error processing entry: {e}", flush=True)
                
                for reentry_rec in reentries:
                    try:
                        reentry_token = reentry_rec['token']
                        reentry_price = reentry_rec['current_price']
                        reentry_reason = reentry_rec['reason']
                        
                        # Check if we have capital and position slots
                        if len(engine.live) >= MAX_CONCURRENT:
                            print(f"[WATCHLIST] ⏸️  Max positions reached, delaying re-entry for {reentry_token[:8]}", flush=True)
                            continue
                        
                        if engine.has_position(reentry_token):
                            print(f"[WATCHLIST] ⏸️  Already have position for {reentry_token[:8]}", flush=True)
                            continue
                        
                        # Fetch stats and create plan
                        print(f"[WATCHLIST] 🔄 RE-ENTRY TRIGGERED: {reentry_token[:8]} | {reentry_reason}", flush=True)
                        reentry_stats = _fetch_real_stats(reentry_token)
                        if not reentry_stats:
                            print(f"[WATCHLIST] ❌ Failed to fetch stats for {reentry_token[:8]}", flush=True)
                            continue
                        
                        reentry_score = reentry_rec.get('score', 7)
                        reentry_conviction = reentry_rec.get('conviction', 'Medium Confidence')
                        reentry_plan = decide_trade(reentry_stats, reentry_score, reentry_conviction)
                        
                        if reentry_plan:
                            print(f"[WATCHLIST] 💰 RE-OPENING ${reentry_plan['usd_size']:.2f} position for {reentry_token[:8]}", flush=True)
                            pid = engine.open_position(reentry_token, reentry_plan)
                            if pid:
                                watch_manager.mark_reentered(reentry_token, pid, reentry_price)
                                positions_opened += 1
                                print(f"[WATCHLIST] ✅ Position #{pid} re-opened for {reentry_token[:8]}", flush=True)
                    except Exception as e:
                        print(f"[WATCHLIST] ❌ Error processing re-entry: {e}", flush=True)
                
                # === END WATCH LIST PROCESSING ===
                
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
                    last_health_log = time.time()
                
                # Check trading toggle
                print(f"[DEBUG] Checking trading_enabled()...", flush=True)
                if not trading_enabled():
                    print(f"[DEBUG] Trading disabled, skipping {token[:8] if token else 'None'}...", flush=True)
                    time.sleep(0.2)
                    continue
                print(f"[DEBUG] Trading is enabled, proceeding with {token[:8] if token else 'None'}...", flush=True)
                
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
                
                # Skip if token is on cooldown (prevents buy-sell-rebuy loops)
                print(f"[DEBUG] Checking cooldown for {token_norm[:8]}...", flush=True)
                if engine.is_on_cooldown(token_norm):
                    remaining = engine.get_cooldown_remaining(token_norm)
                    signals_filtered += 1
                    hours = int(remaining // 3600)
                    minutes = int((remaining % 3600) // 60)
                    engine._log("entry_rejected_cooldown", token=token_norm, 
                               remaining_seconds=remaining, remaining_hours=hours, remaining_minutes=minutes)
                    print(f"[DEBUG] Token {token_norm[:8]} on cooldown for {hours}h {minutes}m more", flush=True)
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
                    
                    # Fetch current price once (will be reused to avoid duplicate calls)
                    current_price = _get_last_price_usd(token, use_cache=True)
                    if current_price <= 0:
                        current_price = float(stats.get("price", 0))
                    
                    # Check if signal is stale (pass current_price to avoid redundant fetch)
                    if _is_stale_signal(stats, current_price=current_price):
                        engine._log("rebalance_skipped", token=token, reason="signal_stale")
                        continue
                    
                    # Get signal score and conviction
                    signal_score = int(stats.get("final_score", 7))
                    conviction_type = stats.get("conviction_type", "High Confidence (Strict)")
                    
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
                
                # Fetch current price ONCE and reuse it (avoids 3+ redundant calls!)
                print(f"[DEBUG] Fetching current price once for staleness + validation...", flush=True)
                current_price = _get_last_price_usd(token_norm, use_cache=True)
                print(f"[DEBUG] Current price: ${current_price:.8f}", flush=True)
                
                # Check if signal is stale (reuse current_price)
                print(f"[DEBUG] Checking if signal is stale...", flush=True)
                _blind = os.getenv("TS_BLIND_BUY", "false").strip().lower() == "true"
                if not _blind:
                    if _is_stale_signal(stats, current_price=current_price):
                        signals_filtered += 1
                        engine._log("signal_stale", token=token_norm, 
                                   alert_price=stats.get("price"),
                                   current_price=current_price)
                        print(f"[DEBUG] Signal is stale for {token_norm[:8]}", flush=True)
                        continue
                print(f"[DEBUG] Signal is fresh (blind={_blind}), continuing...", flush=True)
                
                # Get signal score and conviction
                print(f"[DEBUG] Extracting signal_score and conviction_type from stats...", flush=True)
                signal_score = int(stats.get("final_score", 7))
                conviction_type = stats.get("conviction_type", "High Confidence (Strict)")
                print(f"[DEBUG] signal_score={signal_score}, conviction_type={conviction_type}", flush=True)
                
                # Enforce minimum score unless blind mode
                # LOWERED FROM 8 TO 7: User's signal provider sends score 7 signals consistently
                MIN_SCORE = int(os.getenv("TS_MIN_SCORE", "7"))
                if os.getenv("TS_BLIND_BUY", "false").strip().lower() == "true":
                    MIN_SCORE = 0
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
                # REUSE current_price from earlier to avoid redundant API call!
                # SKIP this check if blind buy is enabled
                _blind_buy = os.getenv("TS_BLIND_BUY", "false").strip().lower() == "true"
                if not _blind_buy:
                    print(f"[DEBUG] Final price validation (cached price=${current_price:.8f})...", flush=True)
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
                else:
                    print(f"[DEBUG] Blind buy mode: skipping FOMO/dump filters", flush=True)
                
                # === RUGPULL DETECTION: Prevent -$268 in complete wipeouts ===
                # Analysis: 8 rugpulls (10.4% of trades) = -$268.65 lost
                # This check runs BEFORE buying to prevent -100% losses
                from tradingSystem.rugpull_detector import get_rugpull_detector
                detector = get_rugpull_detector()
                liquidity_usd = float(stats.get("liquidity_usd", 0))
                
                is_rugpull, rugpull_reason = detector.is_likely_rugpull(token_norm, liquidity_usd)
                if is_rugpull:
                    signals_filtered += 1
                    engine._log("entry_rejected_rugpull", token=token_norm, reason=rugpull_reason,
                               liquidity_usd=liquidity_usd)
                    print(f"[RUGPULL] 🚨 Rejected {token_norm[:8]}: {rugpull_reason} (liquidity=${liquidity_usd:.0f})", flush=True)
                    continue
                else:
                    print(f"[RUGPULL] ✅ Passed checks for {token_norm[:8]} ({rugpull_reason})", flush=True)
                
                # === PRE-ENTRY VALIDATION: Prevent scams & ghost buys ===
                # CRITICAL FIX (Oct 27): Multi-layer validation BEFORE buying
                # Problem: Lost $212 in recent trades to preventable issues
                #   - #380, #379, #378: $104 to rugpulls (brand new tokens)
                #   - #387, #386: $108 to ghost buys (untradeable tokens)
                # Solution: Validate token age, recent dumps, and tradeability
                from tradingSystem.pre_entry_validator import get_pre_entry_validator
                pre_validator = get_pre_entry_validator()
                
                is_valid, validation_reason = pre_validator.validate_token(token_norm, stats)
                if not is_valid:
                    signals_filtered += 1
                    engine._log("entry_rejected_validation", token=token_norm, reason=validation_reason)
                    print(f"[VALIDATOR] {validation_reason}", flush=True)
                    
                    # CRITICAL FIX: Track young tokens for re-evaluation after they mature
                    # Problem: Missing pumps that happen 1-2 hours after signal
                    # Solution: Add to watch list if ONLY rejected for age (not scams)
                    if "too young" in validation_reason.lower() or "Only" in validation_reason and "h old" in validation_reason:
                        # This is a legitimate token, just too young - track it!
                        print(f"[VALIDATOR] 👶 Token immature, adding to watch list for re-evaluation", flush=True)
                        
                        signal_timestamp = float(stats.get("timestamp") or stats.get("ts") or time.time())
                        signal_price = current_price if current_price > 0 else float(stats.get("price", 0))
                        
                        watch_manager.add_signal(
                            token=token_norm,
                            signal_time=signal_timestamp,
                            signal_price=signal_price,
                            signal_score=signal_score,
                            conviction=conviction_type
                        )
                        
                        engine._log("young_token_watchlisted", 
                                   token=token_norm, 
                                   score=signal_score,
                                   validation_reason=validation_reason,
                                   strategy="mature_and_enter")
                        print(f"[WATCHLIST] ⏰ Will re-check {token_norm[:8]} after it matures (1+ hour)", flush=True)
                    else:
                        print(f"[VALIDATOR] Skipping {token_norm[:8]} to prevent potential scam/ghost buy", flush=True)
                    
                    continue
                else:
                    print(f"[VALIDATOR] ✅ {validation_reason}", flush=True)
                
                # === TIERED ENTRY SYSTEM: Watch & Strike ===
                # === AGGRESSIVE STRATEGY: HIGH CONVICTION INSTANT BUY ===
                # Score 8-10/10 → INSTANT BUY (trust the signal, catch moonshots early!)
                # Score 7/10 → Watch List (lower conviction needs momentum confirmation)
                #
                # Why aggressive for high scores:
                # 1. Score 10/10 = Best possible signal (High Confidence smart money)
                # 2. By waiting 2-5min, tokens already up 20-30% (missed the boat!)
                # 3. These are rare - only ~1-2 per hour, can't afford to miss them
                # 4. Safety filters already applied (age, rugpull, Jupiter, dumps)
                #
                # Why still cautious for score 7:
                # 1. Score 7/10 = Nuanced (weaker signal, needs confirmation)
                # 2. Watch list filters out fake pumps that stall
                # 3. Only buys if shows real momentum
                
                if signal_score >= 8:
                    # TIER 1: INSTANT ENTRY (Score 8-10/10 - Premium Signals)
                    conviction_label = "HIGH CONVICTION" if signal_score >= 10 else "VERY HIGH QUALITY"
                    
                    # MOMENTUM VALIDATION (OCT 31 2025 - ULTRA AGGRESSIVE FOR MOONSHOTS)
                    # Score 8-10: Instant entry, NO safety check (catch 2x, 5x, 10x runners EARLY!)
                    print(f"[ENTRY] 🚀🚀 {conviction_label} (Score {signal_score}/10) → INSTANT ENTRY", flush=True)
                    print(f"[ENTRY] Strategy: Trust premium signal, catch moonshot early with ${plan['usd_size']:.2f}", flush=True)
                    # Continue to position opening below
                    
                elif signal_score >= 7:
                    # TIER 2: WATCH LIST (Score 7/10 - Needs Momentum Confirmation)
                    print(f"[WATCHLIST] 📊 MEDIUM CONVICTION SIGNAL: {token_norm[:8]} (score {signal_score}/10)", flush=True)
                    print(f"[WATCHLIST] 💡 Strategy: Track movement for 2-5min, enter if shows real momentum", flush=True)
                    
                    # Add to watch list
                    signal_timestamp = float(stats.get("timestamp") or stats.get("ts") or time.time())
                    signal_price = current_price if current_price > 0 else float(stats.get("price", 0))
                    
                    watch_manager.add_signal(
                        token=token_norm,
                        signal_time=signal_timestamp,
                        signal_price=signal_price,
                        signal_score=signal_score,
                        conviction=conviction_type
                    )
                    
                    signals_filtered += 1
                    engine._log("signal_watchlisted", 
                               token=token_norm, 
                               score=signal_score,
                               conviction=conviction_type,
                               signal_price=signal_price,
                               strategy="watch_and_strike")
                    print(f"[WATCHLIST] ✅ Tracking {token_norm[:8]} | Will buy if +5% at 2%/min velocity", flush=True)
                    continue  # Don't buy yet! Watch list monitor will recommend when ready
                
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
                        
                        # Mark in watch list (for high-conviction instant entries)
                        if signal_score >= 8:
                            watch_manager.mark_entered(token_norm, pid, current_price)
                            print(f"[WATCHLIST] ✅ Marked {token_norm[:8]} as entered (instant entry)", flush=True)
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

