#!/usr/bin/env python3
"""
Price Performance Tracker for Alerted Tokens
Runs continuously to track price movements and detect rugs

Uses free APIs (DexScreener, Jupiter, GeckoTerminal) for tracking.
"""
import sys
import os
import time
import json
from typing import Optional
from datetime import datetime, timezone

# Add parent and src directory to path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
src_dir = os.path.join(repo_root, "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from app.storage import (
    get_alerted_tokens_for_tracking,
    record_price_snapshot,
    update_token_performance,
    get_performance_summary
)
from app.logger_utils import _out, log_tracking, log_process


def get_token_price_free(token_address: str) -> dict:
    """
    Get token price using free APIs (DexScreener, Jupiter, GeckoTerminal).
    Tries multiple sources for reliability.
    
    Returns dict with price data in the same format as get_token_stats()
    """
    from app.http_client import request_json
    
    # Try 0: Birdeye (paid, rate-limited)
    try:
        from app.birdeye_client import get_price as birdeye_price, birdeye_enabled
        if birdeye_enabled():
            start = time.time()
            stats = birdeye_price(token_address)
            if stats:
                log_tracking({
                    "type": "price_fetch",
                    "token": token_address,
                    "source": "birdeye",
                    "status": "ok",
                    "elapsed_ms": int((time.time() - start) * 1000),
                })
                return stats
            log_tracking({
                "type": "price_fetch",
                "token": token_address,
                "source": "birdeye",
                "status": "empty",
                "elapsed_ms": int((time.time() - start) * 1000),
            })
    except Exception as e:
        log_tracking({
            "type": "price_fetch",
            "token": token_address,
            "source": "birdeye",
            "status": "error",
            "error": str(e),
        })

    # Try 1: DexScreener (most reliable for Solana)
    try:
        start = time.time()
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        result = request_json("GET", url, timeout=10)
        
        if result.get("status_code") == 200:
            data = result.get("json") or {}
            pairs = data.get("pairs") or []
            
            if pairs:
                # Pick the most liquid pair
                best_pair = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
                
                price_usd = float(best_pair.get("priceUsd", 0))
                if price_usd > 0:
                    price_change = best_pair.get("priceChange") or {}
                    volume = best_pair.get("volume") or {}
                    
                    return {
                        "price": {
                            "price_usd": price_usd,
                            "price_change_1h": float(price_change.get("h1", 0) or 0),
                            "price_change_6h": float(price_change.get("h6", 0) or 0),
                            "price_change_24h": float(price_change.get("h24", 0) or 0),
                        },
                        "volume": {
                            "volume_24h": float(volume.get("h24", 0) or 0),
                        },
                        "liquidity": {
                            "liquidity_usd": float(best_pair.get("liquidity", {}).get("usd", 0) or 0),
                        },
                        "market_cap_usd": best_pair.get("marketCap"),
                        "source": "dexscreener_free"
                    }
        log_tracking({
            "type": "price_fetch",
            "token": token_address,
            "source": "dexscreener_free",
            "status": "empty",
            "elapsed_ms": int((time.time() - start) * 1000),
        })
    except Exception as e:
        _out(f"DexScreener free API failed: {e}")
        log_tracking({
            "type": "price_fetch",
            "token": token_address,
            "source": "dexscreener_free",
            "status": "error",
            "error": str(e),
        })
    
    # Try 2: Jupiter Price API (free, no key needed)
    try:
        start = time.time()
        url = f"https://price.jup.ag/v4/price?ids={token_address}"
        result = request_json("GET", url, timeout=8)
        
        if result.get("status_code") == 200:
            data = result.get("json") or {}
            price_data = data.get("data", {}).get(token_address)
            
            if price_data:
                price_usd = float(price_data.get("price", 0))
                if price_usd > 0:
                    return {
                        "price": {
                            "price_usd": price_usd,
                            "price_change_1h": 0,  # Jupiter doesn't provide historical
                            "price_change_6h": 0,
                            "price_change_24h": 0,
                        },
                        "source": "jupiter_free"
                    }
        log_tracking({
            "type": "price_fetch",
            "token": token_address,
            "source": "jupiter_free",
            "status": "empty",
            "elapsed_ms": int((time.time() - start) * 1000),
        })
    except Exception as e:
        _out(f"Jupiter free API failed: {e}")
        log_tracking({
            "type": "price_fetch",
            "token": token_address,
            "source": "jupiter_free",
            "status": "error",
            "error": str(e),
        })
    
    # Try 3: GeckoTerminal (free, good for trending tokens)
    try:
        start = time.time()
        url = f"https://api.geckoterminal.com/api/v2/networks/solana/tokens/{token_address}"
        result = request_json("GET", url, timeout=10)
        
        if result.get("status_code") == 200:
            data = result.get("json") or {}
            attrs = (data.get("data") or {}).get("attributes") or {}
            
            price_usd = float(attrs.get("price_usd", 0) or 0)
            if price_usd > 0:
                return {
                    "price": {
                        "price_usd": price_usd,
                        "price_change_1h": float(attrs.get("price_change_percentage_1h", 0) or 0),
                        "price_change_6h": float(attrs.get("price_change_percentage_6h", 0) or 0),
                        "price_change_24h": float(attrs.get("price_change_percentage_24h", 0) or 0),
                    },
                    "volume": {
                        "volume_24h": float(attrs.get("volume_usd_24h", 0) or 0),
                    },
                    "market_cap_usd": attrs.get("market_cap_usd"),
                    "source": "geckoterminal_free"
                }
        log_tracking({
            "type": "price_fetch",
            "token": token_address,
            "source": "geckoterminal_free",
            "status": "empty",
            "elapsed_ms": int((time.time() - start) * 1000),
        })
    except Exception as e:
        _out(f"GeckoTerminal free API failed: {e}")
        log_tracking({
            "type": "price_fetch",
            "token": token_address,
            "source": "geckoterminal_free",
            "status": "error",
            "error": str(e),
        })
    
    return {}


def _load_rejection_state(state_path: str) -> dict:
    try:
        import json
        if os.path.exists(state_path):
            with open(state_path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def _save_rejection_state(state_path: str, state: dict) -> None:
    try:
        import json
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def evaluate_rejected_signals() -> None:
    enabled = os.getenv("REJECTION_WINNER_TRACKING_ENABLED", "true").strip().lower() == "true"
    if not enabled:
        return
    log_path = os.getenv("REJECTION_LOG_PATH", "data/logs/rejections.jsonl")
    if not os.path.exists(log_path):
        return
    state_path = os.getenv("REJECTION_STATE_PATH", "data/logs/rejection_state.json")
    min_age_min = float(os.getenv("REJECTION_WINNER_MIN_AGE_MINUTES", "30"))
    max_age_h = float(os.getenv("REJECTION_WINNER_MAX_AGE_HOURS", "24"))
    min_mult = float(os.getenv("REJECTION_WINNER_MULTIPLIER", "2.0"))
    max_per_cycle = int(os.getenv("REJECTION_WINNER_MAX_PER_CYCLE", "30"))
    
    state = _load_rejection_state(state_path)
    processed = state.get("processed", {})
    now = datetime.now(timezone.utc)
    processed_count = 0
    winners = 0
    
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if processed_count >= max_per_cycle:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                token = event.get("token")
                ts = event.get("ts")
                if not token or not ts:
                    continue
                key = f"{token}|{ts}|{event.get('source','')}"
                if key in processed:
                    continue
                ts_dt = _parse_ts(ts)
                if not ts_dt:
                    continue
                age_min = (now - ts_dt).total_seconds() / 60.0
                if age_min < min_age_min or age_min > (max_age_h * 60):
                    continue
                base_price = event.get("price_usd")
                try:
                    base_price = float(base_price)
                except Exception:
                    base_price = None
                if not base_price or base_price <= 0:
                    continue
                
                stats = get_token_price_free(token)
                current_price = None
                try:
                    current_price = float(((stats.get("price") or {}).get("price_usd") or 0))
                except Exception:
                    current_price = None
                if not current_price or current_price <= 0:
                    continue
                
                multiple = current_price / base_price if base_price > 0 else 0
                is_winner = multiple >= min_mult
                if is_winner:
                    winners += 1
                log_tracking({
                    "type": "rejection_winner_check",
                    "token": token,
                    "source": event.get("source"),
                    "reason": event.get("reason"),
                    "base_price": base_price,
                    "current_price": current_price,
                    "multiple": multiple,
                    "age_minutes": int(age_min),
                    "winner": is_winner,
                })
                processed[key] = ts
                processed_count += 1
    except Exception as e:
        _out(f"Rejection winner tracking error: {e}")
        return
    
    if processed_count:
        log_process({
            "type": "rejection_winner_cycle",
            "checked": processed_count,
            "winners": winners,
        })
    
    # Prune state older than max_age_h
    pruned = {}
    for k, v in processed.items():
        ts_dt = _parse_ts(str(v))
        if ts_dt and (now - ts_dt).total_seconds() <= (max_age_h * 3600):
            pruned[k] = v
    state["processed"] = pruned
    _save_rejection_state(state_path, state)


def track_token_performance(token_address: str, retry_count: int = 0) -> bool:
    """
    Fetch current stats for a token and update performance metrics.
    Returns True if successful, False if token no longer exists.
    
    For very new pump.fun tokens, they may not appear on DexScreener for 5-30 minutes.
    We handle this gracefully and keep trying.
    """
    try:
        # Use free APIs for historical tracking
        stats = get_token_price_free(token_address)
        
        if not stats:
            # For very new tokens, this is expected - they're not indexed yet
            # We'll keep trying on subsequent cycles
            return False
        
        # Check if we actually have price data
        price_data = stats.get('price', {})
        current_price = price_data.get('price_usd', 0)
        
        if not current_price or current_price == 0:
            # Token exists on API but no price data yet
            return False
        
        # Record snapshot for historical tracking
        record_price_snapshot(token_address, stats)
        
        # Update performance metrics
        update_token_performance(token_address, stats)
        
        # Log significant movements
        change_1h = price_data.get('price_change_1h', 0)
        
        if abs(change_1h or 0) > 20:
            emoji = "🚀" if change_1h > 0 else "💥"
            _out(f"{emoji} {token_address[:8]}... {change_1h:+.1f}% (1h) | ${current_price:.8f}")
        
        log_tracking({
            "type": "alerted_token_snapshot",
            "token": token_address,
            "price_usd": current_price,
            "change_1h": change_1h,
            "source": stats.get("source"),
        })
        return True
        
    except Exception as e:
        # Only log unexpected errors (not expected API failures)
        if "404" not in str(e) and "not found" not in str(e).lower():
            _out(f"❌ Error tracking {token_address[:8]}...: {e}")
            log_tracking({
                "type": "alerted_token_snapshot",
                "token": token_address,
                "status": "error",
                "error": str(e),
            })
        return False


def track_open_positions() -> int:
    """Track price movements for open positions using Jupiter oracle."""
    from src.tradingSystem.db import init as init_trading_db
    from src.tradingSystem.db import get_open_positions, record_position_price_snapshot
    from src.tradingSystem.jupiter_price_oracle import get_jupiter_oracle

    # Ensure trading DB schema exists before inserting snapshots
    init_trading_db()
    positions = get_open_positions()
    if not positions:
        return 0

    oracle = get_jupiter_oracle(cache_ttl=15)
    tracked = 0
    for pos in positions:
        token = pos.get("token_address")
        qty = float(pos.get("qty") or 0)
        entry = float(pos.get("entry_price") or 0)
        if not token or qty <= 0:
            continue
        price = oracle.get_price(token, qty)
        if price <= 0:
            log_tracking({
                "type": "position_snapshot",
                "position_id": pos.get("id"),
                "token": token,
                "status": "no_price",
                "source": "jupiter_oracle",
            })
            continue
        record_position_price_snapshot(
            position_id=int(pos.get("id")),
            token_address=token,
            price_usd=price,
            qty=qty,
            entry_price=entry,
            source="jupiter_oracle",
        )
        pnl_pct = ((price - entry) / entry * 100.0) if entry > 0 else 0.0
        log_tracking({
            "type": "position_snapshot",
            "position_id": pos.get("id"),
            "token": token,
            "price_usd": price,
            "qty": qty,
            "pnl_pct": pnl_pct,
            "source": "jupiter_oracle",
        })
        tracked += 1
        time.sleep(1)
    return tracked


def print_summary():
    """Print performance summary"""
    try:
        summary = get_performance_summary()
        
        print("\n" + "="*60)
        print("📊 PERFORMANCE SUMMARY")
        print("="*60)
        
        total = summary.get('total_alerts', 0)
        if total == 0:
            print("No alerted tokens tracked yet.")
            return
        
        print("\n📈 Overall Statistics:")
        print(f"  Total Alerts: {total}")
        print(f"  Avg Max Gain: {summary.get('avg_max_gain', 0):.1f}%")
        print(f"  Avg 1h Change: {summary.get('avg_1h', 0):.1f}%")
        print(f"  Avg 6h Change: {summary.get('avg_6h', 0):.1f}%")
        print(f"  Avg 24h Change: {summary.get('avg_24h', 0):.1f}%")
        
        print("\n🎯 Success Metrics:")
        print(f"  50%+ Pumps: {summary.get('pumps_50plus', 0)} ({summary.get('pumps_50plus', 0)/total*100:.1f}%)")
        print(f"  100%+ Pumps: {summary.get('pumps_100plus', 0)} ({summary.get('pumps_100plus', 0)/total*100:.1f}%)")
        print(f"  Rugs: {summary.get('rugs', 0)} ({summary.get('rugs', 0)/total*100:.1f}%)")
        print(f"  -20%+ Dumps: {summary.get('dumps_20plus', 0)} ({summary.get('dumps_20plus', 0)/total*100:.1f}%)")
        
        print("\n🏆 Performance by Conviction Type:")
        for conv_type, data in summary.get('by_conviction', {}).items():
            print(f"  {conv_type}:")
            print(f"    Count: {data['count']}")
            print(f"    Avg Gain: {data.get('avg_gain', 0):.1f}%")
            print(f"    Rugs: {data['rug_count']}")
        
        print("\n🔍 Feature Performance:")
        for feature in ['smart_money_involved', 'lp_locked', 'mint_revoked', 'passed_senior_strict']:
            key = f'{feature}_performance'
            if key in summary:
                data = summary[key]
                print(f"  {feature.replace('_', ' ').title()}:")
                total = data.get('total', 0)
                avg_gain = data.get('avg_gain', 0)
                rug_count = data.get('rug_count', 0)
                
                # Safe formatting with None checks
                total_val = total if total is not None else 0
                avg_gain_val = avg_gain if avg_gain is not None else 0
                rug_count_val = rug_count if rug_count is not None else 0
                
                print(f"    Total: {total_val}")
                print(f"    Avg Gain: {avg_gain_val:.1f}%")
                if total_val and total_val > 0:
                    print(f"    Rugs: {rug_count_val} ({rug_count_val/total_val*100:.1f}%)")
                else:
                    print(f"    Rugs: {rug_count_val} (0.0%)")
        
        print("="*60)
        
    except Exception as e:
        _out(f"Error printing summary: {e}")


def main():
    """Main tracking loop"""
    _out("🔍 Starting Price Performance Tracker...")
    _out("Tracking alerted tokens from last 24 hours...")
    _out("✅ ZERO CREDIT MODE: Using only FREE APIs (DexScreener, Jupiter, GeckoTerminal)")
    _out("⏱️  Checking every 10 minutes for price movements")
    track_positions_enabled = os.getenv("TRACK_POSITIONS_ENABLED", "true").strip().lower() == "true"
    if track_positions_enabled:
        _out("📌 Position tracking enabled (Jupiter oracle)")
    
    cycle = 0
    consecutive_failures = 0
    
    while True:
        try:
            cycle += 1
            _out(f"\n📊 Tracking Cycle #{cycle} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            cycle_start = time.time()
            
            # Get tokens to track
            tokens = get_alerted_tokens_for_tracking()
            
            if not tokens:
                _out("No tokens to track.")
            else:
                _out(f"Tracking {len(tokens)} tokens...")
                
                success_count = 0
                failed_count = 0
                for token in tokens:
                    if track_token_performance(token):
                        success_count += 1
                        consecutive_failures = 0  # Reset on success
                    else:
                        failed_count += 1
                    # Increased delay between tokens to avoid rate limits
                    time.sleep(5)
                
                if success_count > 0:
                    _out(f"✅ Updated {success_count}/{len(tokens)} tokens")
                    log_process({
                        "type": "tracking_cycle_tokens",
                        "cycle": cycle,
                        "tracked_ok": success_count,
                        "tracked_failed": failed_count,
                        "total": len(tokens),
                    })
                
                # Detect persistent API failures and back off
                if failed_count == len(tokens) and len(tokens) > 10:
                    consecutive_failures += 1
                    _out(f"⚠️  Warning: 0/{len(tokens)} tokens updated - possible API issue (failure #{consecutive_failures})")
                    
                    # If API is persistently failing, increase backoff
                    if consecutive_failures >= 3:
                        backoff_time = min(1800, 600 * consecutive_failures)  # Max 30 min
                        _out(f"🛑 API appears down. Backing off for {backoff_time//60} minutes...")
                        time.sleep(backoff_time)
                        consecutive_failures = 0
                        continue
                elif failed_count > 0:
                    _out(f"ℹ️  {failed_count} tokens not yet indexed (too new for DexScreener)")
                    log_process({
                        "type": "tracking_cycle_tokens",
                        "cycle": cycle,
                        "tracked_ok": success_count,
                        "tracked_failed": failed_count,
                        "total": len(tokens),
                    })

            # Track open positions (Jupiter oracle)
            if track_positions_enabled:
                try:
                    tracked_positions = track_open_positions()
                    log_process({
                        "type": "tracking_cycle_positions",
                        "cycle": cycle,
                        "tracked_positions": tracked_positions,
                    })
                except Exception as e:
                    _out(f"❌ Error tracking positions: {e}")
                    log_process({
                        "type": "tracking_cycle_positions",
                        "cycle": cycle,
                        "status": "error",
                        "error": str(e),
                    })
            
            # Evaluate rejected signals for missed winners
            try:
                evaluate_rejected_signals()
            except Exception as e:
                _out(f"❌ Error evaluating rejected signals: {e}")
            
            # Print summary every 6 cycles (roughly every hour)
            if cycle % 6 == 0:
                print_summary()
            
            # OPTIMIZED: 10 minute interval to save API credits while still capturing movements
            # Uses cache (15min) so most calls won't hit external APIs
            elapsed_ms = int((time.time() - cycle_start) * 1000)
            log_process({
                "type": "tracking_cycle_complete",
                "cycle": cycle,
                "elapsed_ms": elapsed_ms,
                "positions_tracking": track_positions_enabled,
            })
            _out("Sleeping for 10 minutes...")
            time.sleep(600)
            
        except KeyboardInterrupt:
            _out("\n👋 Tracker stopped by user")
            print_summary()
            break
        except Exception as e:
            _out(f"❌ Error in tracking loop: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()
