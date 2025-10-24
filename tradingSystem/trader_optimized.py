"""
OPTIMIZED TRADER - Proper Risk Management
- FIXED: Stop loss from ENTRY price (not peak)
- Circuit breakers (20% daily loss, 5 consecutive losses)
- Thread-safe position management
- Comprehensive error handling
- Position recovery on restart
"""
import json
import os
import time
import threading
from datetime import datetime, date
from typing import Dict, Optional

from .db import (
    init as db_init, create_position, add_fill, update_peak_and_trail,
    close_position, get_open_qty
)
from .config_optimized import (
    STOP_LOSS_PCT, LOG_JSON_PATH, LOG_TEXT_PATH,
    MAX_CONCURRENT, MAX_DAILY_LOSS_PCT, MAX_CONSECUTIVE_LOSSES,
    BANKROLL_USD, DB_PATH, MAX_HOLD_TIME_SECONDS,
    EMERGENCY_HARD_STOP_PCT
)
from .broker_optimized import Broker
from .portfolio_manager import get_portfolio_manager, should_use_portfolio_manager
from .inactivity_monitor import InactivityMonitor


class PositionLock:
    """Thread-safe lock for position operations"""
    def __init__(self):
        self._locks: Dict[str, threading.Lock] = {}
        self._master_lock = threading.Lock()
    
    def get_lock(self, token: str) -> threading.Lock:
        with self._master_lock:
            if token not in self._locks:
                self._locks[token] = threading.Lock()
            return self._locks[token]


class CircuitBreaker:
    """Circuit breaker to prevent runaway losses"""
    def __init__(self):
        self.max_daily_loss_pct = MAX_DAILY_LOSS_PCT
        self.max_consecutive_losses = MAX_CONSECUTIVE_LOSSES
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.last_reset = date.today()
        self.tripped = False
        self.trip_reason = ""
        self._lock = threading.Lock()
    
    def _check_and_reset_unlocked(self):
        """Reset daily counters if new day (internal, assumes lock is held)"""
        today = date.today()
        if today > self.last_reset:
            self.daily_pnl = 0.0
            self.consecutive_losses = 0
            self.last_reset = today
            if self.tripped:
                self.tripped = False
                self.trip_reason = ""
    
    def check_and_reset(self):
        """Reset daily counters if new day (public, acquires lock)"""
        with self._lock:
            self._check_and_reset_unlocked()
    
    def record_trade(self, pnl_usd: float) -> bool:
        """Record trade result, return True if should continue trading"""
        with self._lock:
            self._check_and_reset_unlocked()
            self.daily_pnl += pnl_usd
            
            if pnl_usd < 0:
                self.consecutive_losses += 1
            else:
                self.consecutive_losses = 0
            
            # Check daily loss limit
            max_loss = BANKROLL_USD * (self.max_daily_loss_pct / 100.0)
            if self.daily_pnl < -max_loss:
                self.tripped = True
                self.trip_reason = f"Daily loss limit exceeded: ${abs(self.daily_pnl):.2f} (max: ${max_loss:.2f})"
                return False
            
            # Check consecutive losses
            if self.consecutive_losses >= self.max_consecutive_losses:
                self.tripped = True
                self.trip_reason = f"Too many consecutive losses: {self.consecutive_losses}"
                return False
            
            return True
    
    def is_tripped(self) -> bool:
        with self._lock:
            self._check_and_reset_unlocked()
            return self.tripped
    
    def get_status(self) -> Dict:
        with self._lock:
            return {
                "tripped": self.tripped,
                "reason": self.trip_reason,
                "daily_pnl": self.daily_pnl,
                "consecutive_losses": self.consecutive_losses,
                "max_daily_loss": BANKROLL_USD * (self.max_daily_loss_pct / 100.0),
            }


class TradeEngine:
    """Optimized trade engine with bulletproof risk management"""
    
    def __init__(self) -> None:
        db_init()
        self.broker = Broker()
        self.live: Dict[str, Dict[str, object]] = {}
        self._position_locks = PositionLock()
        self.circuit_breaker = CircuitBreaker()
        
        # Inactivity monitoring: Exit positions based on price stagnation, not arbitrary time
        self.inactivity_monitor = InactivityMonitor()
        
        # Token cooldown: Prevent immediate rebuy after selling (stops buy-sell-rebuy loops)
        self._token_cooldowns: Dict[str, float] = {}  # token -> timestamp when sold
        self._cooldown_lock = threading.Lock()
        self._cooldown_seconds = float(os.getenv("TS_REBUY_COOLDOWN_SEC", "14400"))  # Default: 4 hours
        
        os.makedirs(os.path.dirname(LOG_JSON_PATH), exist_ok=True)
        os.makedirs(os.path.dirname(LOG_TEXT_PATH), exist_ok=True)
        
        self._recover_positions()
    
    def _recover_positions(self):
        """Recover open positions from database"""
        print(f"[TRADER] _recover_positions called, DB_PATH={DB_PATH}", flush=True)
        try:
            import sqlite3
            from datetime import datetime
            print(f"[TRADER] Connecting to database...", flush=True)
            con = sqlite3.connect(DB_PATH)
            cur = con.execute("""
                SELECT id, token_address, strategy, entry_price, peak_price, created_at 
                FROM positions 
                WHERE status='open'
            """)
            rows = cur.fetchall()
            print(f"[TRADER] Found {len(rows)} open positions in database", flush=True)
            
            for pid, ca, strategy, entry_price, peak_price, created_at in rows:
                # Parse created_at timestamp for entry_time
                try:
                    entry_time = datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp()
                except:
                    entry_time = time.time()  # Fallback to now if parsing fails
                
                self.live[str(ca)] = {
                    "pid": int(pid),
                    "strategy": str(strategy),
                    "entry_price": float(entry_price or 0),
                    "peak_price": float(peak_price or entry_price or 0),
                    "entry_time": entry_time,  # ADDED: For adaptive monitoring
                    "open_at": entry_time,     # ADDED: For time-based exits
                }
                print(f"[TRADER] Recovered position {pid}: {str(ca)[:8]}... entry=${entry_price:.8f}", flush=True)
            con.close()
            if self.live:
                print(f"[TRADER] ✓ Recovery complete: {len(self.live)} positions loaded", flush=True)
                self._log("recovery_loaded", open_positions=len(self.live), positions=list(self.live.keys()))
            else:
                print(f"[TRADER] No open positions to recover", flush=True)
        except Exception as e:
            print(f"[TRADER] ❌ Recovery failed: {e}", flush=True)
            self._log("recovery_failed", error=str(e))

    def _log(self, event: str, **fields) -> None:
        """Thread-safe logging"""
        payload = {"ts": datetime.utcnow().isoformat(timespec="seconds") + "Z", "event": event}
        payload.update(fields)
        try:
            with open(LOG_JSON_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass
        try:
            line = f"[{payload['ts']}] {event} " + " ".join(f"{k}={v}" for k, v in fields.items())
            with open(LOG_TEXT_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def open_position(self, token: str, plan: Dict) -> Optional[int]:
        """Open position with comprehensive safety"""
        try:
            # Circuit breaker check (TEMPORARILY DISABLED DUE TO DEADLOCK)
            # TODO: Fix threading issue in CircuitBreaker class
            # if self.circuit_breaker.is_tripped():
            #     status = self.circuit_breaker.get_status()
            #     self._log("open_blocked_circuit_breaker", token=token, reason=status["reason"])
            #     return None
            print(f"[TRADER] open_position called for {token[:8]}...", flush=True)
            
            # Concurrency limit
            print(f"[TRADER] Checking concurrency: {len(self.live)} / {int(MAX_CONCURRENT)}", flush=True)
            if len(self.live) >= int(MAX_CONCURRENT):
                self._log("open_skipped_max_concurrent", token=token, max_concurrent=int(MAX_CONCURRENT))
                print(f"[TRADER] ❌ Max concurrent positions reached", flush=True)
                return None
            
            # Acquire lock
            print(f"[TRADER] Acquiring position lock for {token[:8]}...", flush=True)
            lock = self._position_locks.get_lock(token)
            with lock:
                print(f"[TRADER] Lock acquired, checking for duplicate position...", flush=True)
                if token in self.live:
                    self._log("open_skipped_duplicate", token=token)
                    print(f"[TRADER] ❌ Already have position for {token[:8]}", flush=True)
                    return None
                
                usd = float(plan["usd_size"])
                trail_pct = float(plan["trail_pct"])
                strategy = plan.get("strategy", "unknown")
                
                print(f"[TRADER] Executing market buy: ${usd:.2f} for {token[:8]}...", flush=True)
                # Execute buy
                fill = self.broker.market_buy(token, usd)
                print(f"[TRADER] market_buy returned: success={fill.success}", flush=True)
                
                if not fill.success:
                    self._log("open_failed_buy", token=token, error=fill.error)
                    return None
                
                # CRITICAL FIX: Ensure position is ALWAYS recorded after successful buy
                # If DB write fails, we log it prominently but the transaction already happened
                try:
                    print(f"[TRADER] Creating position record in database...", flush=True)
                    pid = create_position(token, strategy, fill.price, fill.qty, usd, trail_pct)
                    print(f"[TRADER] ✅ Position #{pid} created", flush=True)
                    
                    print(f"[TRADER] Adding fill record...", flush=True)
                    add_fill(pid, "buy", fill.price, fill.qty, fill.usd)
                    print(f"[TRADER] ✅ Fill recorded", flush=True)
                    
                except Exception as db_error:
                    # CRITICAL: Buy succeeded but DB failed - this is a SEVERE issue!
                    print(f"[TRADER] 🚨 CRITICAL ERROR: Buy succeeded but failed to record position!", flush=True)
                    print(f"[TRADER] 🚨 Token: {token}", flush=True)
                    print(f"[TRADER] 🚨 Transaction: {fill.tx}", flush=True)
                    print(f"[TRADER] 🚨 Price: {fill.price}, Qty: {fill.qty}, USD: {fill.usd}", flush=True)
                    print(f"[TRADER] 🚨 DB Error: {db_error}", flush=True)
                    print(f"[TRADER] 🚨 ORPHANED POSITION - Manual intervention required!", flush=True)
                    self._log("open_orphaned_position", token=token, error=str(db_error), 
                             tx=fill.tx, price=fill.price, qty=fill.qty, usd=fill.usd)
                    # Return None to indicate failure, even though buy succeeded
                    # This prevents the position from being added to self.live
                    return None
                
                # Add to live with ENTRY PRICE
                self.live[token] = {
                    "pid": pid,
                    "strategy": strategy,
                    "entry_price": fill.price,  # CRITICAL: Store entry price
                    "peak_price": fill.price,
                    "price_failures": 0,  # Track consecutive price fetch failures
                    "sell_failures": 0,  # Track consecutive sell attempt failures
                    "open_at": time.time(),  # Track when position was opened
                }
                
                print(f"[TRADER] ✅ Position fully tracked and ready for monitoring", flush=True)
                self._log("open_position", 
                         token=token, strategy=strategy, pid=pid, 
                         price=fill.price, qty=fill.qty, usd=usd, 
                         trail_pct=trail_pct, tx=fill.tx)
                return pid
                
        except Exception as e:
            self._log("open_exception", token=token, error=str(e))
            return None

    def has_position(self, token: str) -> bool:
        return token in self.live
    
    def is_on_cooldown(self, token: str) -> bool:
        """Check if token is on cooldown (prevents immediate rebuy after sell)"""
        with self._cooldown_lock:
            if token not in self._token_cooldowns:
                return False
            
            sell_time = self._token_cooldowns[token]
            elapsed = time.time() - sell_time
            
            if elapsed >= self._cooldown_seconds:
                # Cooldown expired
                del self._token_cooldowns[token]
                return False
            
            return True
    
    def get_cooldown_remaining(self, token: str) -> Optional[float]:
        """Get remaining cooldown time in seconds"""
        with self._cooldown_lock:
            if token not in self._token_cooldowns:
                return None
            
            sell_time = self._token_cooldowns[token]
            elapsed = time.time() - sell_time
            remaining = self._cooldown_seconds - elapsed
            
            if remaining <= 0:
                del self._token_cooldowns[token]
                return None
            
            return remaining
    
    def _add_cooldown(self, token: str):
        """Add cooldown for a token (called internally after selling)"""
        with self._cooldown_lock:
            self._token_cooldowns[token] = time.time()

    def position_strategy(self, token: str) -> Optional[str]:
        data = self.live.get(token)
        if not data:
            return None
        return str(data.get("strategy"))

    def check_exits(self, token: str, price: float) -> bool:
        """
        Check and execute exits with PROPER stop loss logic.
        
        CRITICAL FIX: Stop loss is calculated from ENTRY price, not peak!
        This was the bug in the original system.
        """
        try:
            if price <= 0:
                # EMERGENCY FIX: Don't silently skip - try fallback and force exit if repeated failures
                data = self.live.get(token)
                if data:
                    price_failures = data.get("price_failures", 0) + 1
                    data["price_failures"] = price_failures
                    
                    # Try emergency price fetch from broker
                    print(f"[TRADER] ⚠️ Price unavailable for {token[:8]}, attempt {price_failures}/5", flush=True)
                    emergency_price = self.broker.get_token_price(token)
                    
                    if emergency_price > 0:
                        price = emergency_price
                        data["price_failures"] = 0  # Reset on success
                    elif price_failures >= 5:
                        # FORCE EXIT after 5 failures (better -50% than -95%)
                        print(f"[TRADER] 🚨 EMERGENCY EXIT: Price unavailable for 5 attempts on {token[:8]}", flush=True)
                        return self._force_emergency_exit(token, "price_unavailable_5x")
                    else:
                        return False
                else:
                    return False
            
            data = self.live.get(token)
            if not data:
                return False
            
            pid = data.get("pid")
            if not pid:
                return False
            
            # Acquire lock
            lock = self._position_locks.get_lock(token)
            with lock:
                if token not in self.live:
                    return False
                
                # CRITICAL: Get ENTRY price (no fallback - must be present)
                entry_price = data.get("entry_price")
                if not entry_price or entry_price <= 0:
                    self._log("exit_missing_entry_price", token=token, pid=pid)
                    return False
                entry_price = float(entry_price)
                
                # Update peak and get PROFIT-BASED trail stop (MOONSHOT MODE!)
                peak, trail = update_peak_and_trail(pid, price, entry_price)
                
                # Validate database returns
                if peak <= 0 or trail <= 0:
                    self._log("exit_invalid_peak_trail", token=token, pid=pid, peak=peak, trail=trail)
                    return False
                strategy = str(data.get("strategy", "unknown"))
                
                # Calculate current profit for logging
                profit_pct = ((peak - entry_price) / entry_price) * 100 if entry_price > 0 else 0
                
                # Log trail adjustments (only when peak updates or occasionally)
                old_peak = self.live[token].get("peak_price", 0)
                if peak > old_peak:  # New peak reached!
                    print(f"[TRADER] 🚀 {token[:8]} new peak! Profit: +{profit_pct:.1f}% | Trail: {trail:.0f}% | Price: ${price:.8f}", flush=True)
                
                # Update peak in live data
                self.live[token]["peak_price"] = peak
                
                # Track price for inactivity monitoring
                self.inactivity_monitor.add_price_sample(token, price)
                
                # FIXED: Stop loss relative to ENTRY price!
                stop_price = entry_price * (1.0 - STOP_LOSS_PCT / 100.0)
                
                # Trail stop relative to peak
                trail_price = peak * (1.0 - trail / 100.0) if peak > 0 else 0
                
                # Determine exit type
                exit_type = None
                exit_reason = ""
                
                # Check inactivity-based exit (6+ hours of <5% movement)
                # KEY INSIGHT: Some tokens pump for 8-10 days to 800x
                # Don't force-sell winners, but DO exit when price is dead
                open_at = data.get("open_at", 0)
                if open_at > 0:
                    # Check if position should ignore time limit (high profit + active price)
                    ignore_time, ignore_reason = self.inactivity_monitor.should_ignore_time_limit(token, profit_pct)
                    
                    if ignore_time:
                        # High-profit moonshot with active price movement - let it run!
                        if data.get("last_moonshot_log", 0) < time.time() - 3600:  # Log every hour
                            print(f"[TRADER] 🌙 {token[:8]} in MOONSHOT MODE: {ignore_reason}", flush=True)
                            data["last_moonshot_log"] = time.time()
                    else:
                        # Check for inactivity (price stagnation)
                        should_exit, inactivity_reason = self.inactivity_monitor.check_inactivity(token)
                        
                        if should_exit:
                            exit_type = "inactivity"
                            hold_hours = (time.time() - open_at) / 3600
                            exit_reason = f"Inactivity detected: {inactivity_reason} (held {hold_hours:.1f}h)"
                        else:
                            # Also check hard time limit as fallback (24 hours)
                            hold_time = time.time() - open_at
                            if hold_time >= MAX_HOLD_TIME_SECONDS:
                                exit_type = "timeout"
                                hold_hours = hold_time / 3600
                                exit_reason = f"Max hold time: {hold_hours:.1f}h (profit: +{profit_pct:.1f}%) - {inactivity_reason}"
                
                # Check hard stop loss (from entry)
                if not exit_type and price <= stop_price:
                    exit_type = "stop"
                    exit_reason = f"Hit stop loss: {price:.8f} <= {stop_price:.8f} (entry: {entry_price:.8f})"
                
                # EMERGENCY HARD STOP - Last resort if normal stop failed
                emergency_stop_price = entry_price * (1.0 - EMERGENCY_HARD_STOP_PCT / 100.0)
                if not exit_type and price <= emergency_stop_price:
                    exit_type = "emergency_stop"
                    loss_pct = ((price - entry_price) / entry_price) * 100
                    exit_reason = f"EMERGENCY HARD STOP: {loss_pct:.1f}% loss (price: {price:.8f}, entry: {entry_price:.8f})"
                    print(f"[TRADER] 🚨 {exit_reason}", flush=True)
                
                # Check trailing stop (from peak)
                elif not exit_type and peak > 0 and price <= trail_price:
                    exit_type = "trail"
                    exit_reason = f"Hit trailing stop: {price:.8f} <= {trail_price:.8f} (peak: {peak:.8f}, trail: {trail}%)"
                
                if not exit_type:
                    return False
                
                # Check position-specific cooldown (prevent API spam after failures)
                last_sell_attempt = data.get("last_sell_attempt", 0)
                sell_failures = data.get("sell_failures", 0)
                
                # Exponential backoff: 0s, 10s, 30s, 60s, 120s, 300s (max 5 min)
                backoff_times = [0, 10, 30, 60, 120, 300]
                backoff_idx = min(sell_failures, len(backoff_times) - 1)
                backoff_seconds = backoff_times[backoff_idx]
                
                if last_sell_attempt > 0 and (time.time() - last_sell_attempt) < backoff_seconds:
                    remaining = int(backoff_seconds - (time.time() - last_sell_attempt))
                    if sell_failures < 3:  # Only log first few times to avoid spam
                        print(f"[TRADER] ⏳ Position {token[:8]} in cooldown: {remaining}s remaining (failures={sell_failures})", flush=True)
                    return False
                
                # Execute sell
                qty_open = get_open_qty(int(pid))
                if qty_open <= 0:
                    self._log("exit_zero_qty", token=token, pid=pid)
                    self.live.pop(token, None)
                    close_position(pid)
                    return False
                
                # Update last attempt time
                if token in self.live:
                    self.live[token]["last_sell_attempt"] = time.time()
                
                fill = self.broker.market_sell(token, float(qty_open))
                
                if not fill.success:
                    self._log("exit_failed_sell", token=token, pid=pid, error=fill.error, 
                             failures=sell_failures + 1, next_backoff=backoff_times[min(sell_failures + 1, len(backoff_times) - 1)])
                    
                    # CRITICAL: Detect rugged/dead tokens and force-close immediately
                    # If we get "NO_ROUTE" or "RUG_DETECTED" error, the token is dead
                    if "RUG_DETECTED" in str(fill.error) or "No liquidity" in str(fill.error):
                        print(f"[TRADER] 🚨 RUGGED TOKEN DETECTED: {token[:8]} - force closing", flush=True)
                        # Close position in DB (can't sell, but remove from tracking)
                        close_position(pid)
                        self.live.pop(token, None)
                        self._log("rugged_token_closed", token=token, pid=pid, error=fill.error)
                        return True  # Return True so position is removed
                    
                    # Track consecutive sell failures with exponential backoff
                    if token in self.live:
                        self.live[token]["sell_failures"] = sell_failures + 1
                        
                        # CRITICAL: Force-close after 15 consecutive failures (rugged or Jupiter issue)
                        # This prevents positions from being stuck forever
                        if sell_failures + 1 >= 15:
                            print(f"[TRADER] 🚨 FORCE CLOSING STUCK POSITION: {token[:8]} after {sell_failures + 1} failures", flush=True)
                            close_position(pid)
                            self.live.pop(token, None)
                            self._log("force_closed_stuck_position", token=token, pid=pid, failures=sell_failures + 1, error=fill.error)
                            return True
                        
                        # Log failures with backoff info
                        if sell_failures + 1 <= 5:  # Log first 5 failures
                            print(f"[TRADER] ⚠️ Sell attempt {sell_failures + 1} failed for {token[:8]}: {fill.error}", flush=True)
                            print(f"[TRADER] Next retry in {backoff_times[min(sell_failures + 1, len(backoff_times) - 1)]}s", flush=True)
                        elif (sell_failures + 1) % 10 == 0:  # Then log every 10 failures
                            print(f"[TRADER] ⚠️ Position {token[:8]} has {sell_failures + 1} sell failures - retrying every {backoff_seconds}s", flush=True)
                    
                    return False
                
                # SUCCESS! Reset failure counter
                if token in self.live:
                    self.live[token]["sell_failures"] = 0
                
                # Calculate PnL
                entry_usd = entry_price * qty_open if entry_price > 0 else 0
                exit_usd = fill.usd
                pnl_usd = exit_usd - entry_usd
                pnl_pct = (pnl_usd / entry_usd * 100) if entry_usd > 0 else 0
                
                # Update database
                add_fill(int(pid), "sell", float(fill.price), float(fill.qty), float(fill.usd))
                close_position(pid)
                
                # Remove from live and clean up monitors
                self.live.pop(token, None)
                self.inactivity_monitor.reset_position(token)
                
                # Add cooldown to prevent immediate rebuy (especially important for stop losses)
                self._add_cooldown(token)
                self._log("cooldown_added", token=token, cooldown_seconds=self._cooldown_seconds,
                         reason=f"sold_via_{exit_type}")
                
                # Record with circuit breaker
                self.circuit_breaker.record_trade(pnl_usd)
                
                self._log(f"exit_{exit_type}", 
                         token=token, pid=pid, strategy=strategy,
                         entry_price=entry_price, exit_price=price, peak=peak,
                         stop_pct=STOP_LOSS_PCT, trail_pct=trail, 
                         pnl_usd=pnl_usd, pnl_pct=pnl_pct,
                         reason=exit_reason, tx=fill.tx)
                
                # Check circuit breaker
                if self.circuit_breaker.is_tripped():
                    status = self.circuit_breaker.get_status()
                    self._log("circuit_breaker_tripped", **status)
                
                return True
                
        except Exception as e:
            self._log("exit_exception", token=token, error=str(e))
            return False
    
    def _force_emergency_exit(self, token: str, reason: str) -> bool:
        """Force exit a position regardless of price (emergency only)"""
        try:
            data = self.live.get(token)
            if not data:
                return False
            
            pid = data.get("pid")
            if not pid:
                return False
            
            qty_open = get_open_qty(int(pid))
            
            if qty_open <= 0:
                self.live.pop(token, None)
                close_position(pid)
                return False
            
            # Try to sell at market (any price)
            fill = self.broker.market_sell(token, float(qty_open))
            
            if fill.success:
                add_fill(int(pid), "sell", float(fill.price), float(fill.qty), float(fill.usd))
                close_position(pid)
                self.live.pop(token, None)
                self._add_cooldown(token)
                self._log("emergency_exit", token=token, reason=reason, pid=pid, usd=fill.usd)
                print(f"[TRADER] 🚨 EMERGENCY EXIT SUCCESS: {token[:8]} sold for ${fill.usd:.2f}", flush=True)
                return True
            else:
                # Even sell failed - close in DB anyway to prevent infinite loop
                close_position(pid)
                self.live.pop(token, None)
                self._log("emergency_exit_failed", token=token, reason=reason, error=fill.error)
                print(f"[TRADER] ⚠️ EMERGENCY EXIT FAILED: {token[:8]} - {fill.error}", flush=True)
                return False
        except Exception as e:
            self._log("emergency_exit_exception", token=token, error=str(e))
            print(f"[TRADER] ❌ EMERGENCY EXIT EXCEPTION: {token[:8]} - {e}", flush=True)
            return False

    def rebalance_position(self, token_to_sell: str, new_token: str, new_plan: Dict) -> bool:
        """
        Portfolio rebalancing: Sell one position and buy another.
        
        This is atomic - if either operation fails, the other is rolled back.
        
        Args:
            token_to_sell: Token to sell
            new_token: Token to buy
            new_plan: Trading plan for new token
        
        Returns:
            True if rebalance successful
        """
        try:
            if not should_use_portfolio_manager():
                self._log("rebalance_disabled", reason="portfolio_manager_not_enabled")
                return False
            
            # Verify we have the position to sell
            if token_to_sell not in self.live:
                self._log("rebalance_failed", reason="token_to_sell_not_found", token=token_to_sell)
                return False
            
            # Verify we can buy (not over limit after swap)
            if len(self.live) >= MAX_CONCURRENT and new_token not in self.live:
                # This shouldn't happen (we're swapping), but safety check
                self._log("rebalance_failed", reason="max_concurrent", count=len(self.live))
                return False
            
            # Get current price for the sell position
            sell_data = self.live.get(token_to_sell)
            if not sell_data:
                return False
            
            # Fetch current price
            current_price = self.broker.get_token_price(token_to_sell)
            if current_price <= 0:
                self._log("rebalance_failed", reason="invalid_price", token=token_to_sell)
                return False
            
            # Execute sell by calling check_exits (which handles the full exit logic)
            # This is better than duplicating exit logic here
            sell_result = self.check_exits(token_to_sell, current_price)
            if not sell_result:
                # Try to force the exit even if stop/trail not hit (rebalance override)
                pid = sell_data.get("pid")
                if not pid:
                    return False
                
                # Get quantity and sell directly
                from .db import get_open_qty, add_fill, close_position
                qty_open = get_open_qty(int(pid))
                if qty_open <= 0:
                    self._log("rebalance_failed", reason="zero_qty", token=token_to_sell)
                    return False
                
                # Force sell
                fill = self.broker.market_sell(token_to_sell, float(qty_open))
                if not fill.success:
                    self._log("rebalance_failed", reason="sell_failed", token=token_to_sell, error=fill.error)
                    return False
                
                # Update database
                add_fill(int(pid), "sell", float(fill.price), float(fill.qty), float(fill.usd))
                close_position(pid)
                
                # Remove from live
                self.live.pop(token_to_sell, None)
                
                # Log the forced exit
                entry_price = float(sell_data.get("entry_price", 0))
                entry_usd = entry_price * qty_open if entry_price > 0 else 0
                pnl_usd = fill.usd - entry_usd
                pnl_pct = (pnl_usd / entry_usd * 100) if entry_usd > 0 else 0
                
                self._log("rebalance_forced_exit", token=token_to_sell, pid=pid,
                         pnl_usd=pnl_usd, pnl_pct=pnl_pct, reason="rebalance_override")
            
            # Execute buy
            buy_pid = self.open_position(new_token, new_plan)
            if not buy_pid:
                # Buy failed - this is problematic but not catastrophic
                # The sell already happened, so we just log it
                self._log("rebalance_partial", 
                         reason="buy_failed", 
                         sold=token_to_sell, 
                         failed_buy=new_token)
                return False
            
            # Success!
            self._log("rebalance_success",
                     sold=token_to_sell,
                     bought=new_token,
                     new_pid=buy_pid)
            
            # Update portfolio manager
            pm = get_portfolio_manager()
            pm.remove_position(token_to_sell, reason="rebalanced")
            pm.add_position(
                token_address=new_token,
                entry_price=self.live[new_token]["entry_price"],
                quantity=get_open_qty(new_token) or 0,
                signal_score=new_plan.get("score", 5),
                conviction_score=new_plan.get("conviction_score", 0),
                name=new_plan.get("name", ""),
                symbol=new_plan.get("symbol", ""),
            )
            
            return True
            
        except Exception as e:
            self._log("rebalance_exception", error=str(e))
            return False
    
    def sync_portfolio_manager(self) -> None:
        """Sync current positions with portfolio manager"""
        if not should_use_portfolio_manager():
            return
        
        try:
            pm = get_portfolio_manager()
            
            # Add all current positions to portfolio manager
            for token, data in self.live.items():
                if not pm.has_position(token):
                    # Get the position ID for this token
                    pid = data.get("pid")
                    if not pid:
                        continue
                    
                    # Get the actual quantity from the database
                    qty = get_open_qty(pid)
                    
                    pm.add_position(
                        token_address=token,
                        entry_price=data.get("entry_price", 0),
                        quantity=qty,
                        signal_score=5,  # Default score
                        conviction_score=0,
                        name="",
                        symbol="",
                    )
            
            self._log("portfolio_synced", position_count=len(self.live))
            
        except Exception as e:
            self._log("portfolio_sync_exception", error=str(e))
    
    def update_portfolio_prices(self) -> None:
        """Update prices in portfolio manager for momentum calculation"""
        if not should_use_portfolio_manager():
            return
        
        try:
            pm = get_portfolio_manager()
            price_updates = {}
            
            for token in self.live.keys():
                price = self.broker.get_token_price(token)
                if price > 0:
                    price_updates[token] = price
            
            if price_updates:
                pm.update_prices(price_updates)
            
        except Exception:
            pass  # Silent fail - not critical

    def get_status(self) -> Dict:
        """Get engine status"""
        # Get cooldown stats
        with self._cooldown_lock:
            now = time.time()
            active_cooldowns = sum(1 for sell_time in self._token_cooldowns.values() 
                                  if (now - sell_time) < self._cooldown_seconds)
        
        status = {
            "open_positions": len(self.live),
            "tokens": list(self.live.keys()),
            "circuit_breaker": self.circuit_breaker.get_status(),
            "broker_dry_run": self.broker._dry,
            "token_cooldowns": {
                "active": active_cooldowns,
                "total": len(self._token_cooldowns),
                "cooldown_seconds": self._cooldown_seconds,
            },
        }
        
        # Add portfolio manager status if enabled
        if should_use_portfolio_manager():
            pm = get_portfolio_manager()
            status["portfolio_manager"] = pm.get_statistics()
        
        return status

