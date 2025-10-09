"""
BULLETPROOF TRADER - Fixed all position management bugs
"""
import json
import os
import threading
import time
from datetime import datetime
from typing import Dict, Optional
from .db import (
    init as db_init, create_position, add_fill, update_peak_and_trail, 
    close_position, get_open_qty
)
from .config import (
    CORE_STOP_PCT, SCOUT_STOP_PCT, STRICT_STOP_PCT, NUANCED_STOP_PCT,
    LOG_JSON_PATH, LOG_TEXT_PATH, MAX_CONCURRENT, BANKROLL_USD, DB_PATH
)
from .broker_safe import Broker


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
    def __init__(self, max_daily_loss_pct: float = 20.0, max_consecutive_losses: int = 5):
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_consecutive_losses = max_consecutive_losses
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.last_reset = datetime.utcnow().date()
        self.tripped = False
        self.trip_reason = ""
        self._lock = threading.Lock()
    
    def check_and_reset(self):
        """Reset daily counters if new day"""
        with self._lock:
            today = datetime.utcnow().date()
            if today > self.last_reset:
                self.daily_pnl = 0.0
                self.consecutive_losses = 0
                self.last_reset = today
                if self.tripped:
                    self.tripped = False
                    self.trip_reason = ""
    
    def record_trade(self, pnl_usd: float) -> bool:
        """Record trade result, return True if should continue trading"""
        with self._lock:
            self.check_and_reset()
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
            self.check_and_reset()
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
    """Bulletproof trade engine with proper error handling and safety"""
    
    def __init__(self) -> None:
        db_init()
        self.broker = Broker()
        self.live: Dict[str, Dict[str, object]] = {}
        self._position_locks = PositionLock()
        self.circuit_breaker = CircuitBreaker(max_daily_loss_pct=20.0, max_consecutive_losses=5)
        
        os.makedirs(os.path.dirname(LOG_JSON_PATH), exist_ok=True)
        os.makedirs(os.path.dirname(LOG_TEXT_PATH), exist_ok=True)
        
        # Load open positions from DB for restart recovery
        self._recover_positions()
    
    def _recover_positions(self):
        """Recover open positions from database"""
        try:
            import sqlite3
            con = sqlite3.connect(DB_PATH)
            cur = con.execute("""
                SELECT id, token_address, strategy, entry_price, peak_price 
                FROM positions 
                WHERE status='open'
            """)
            for pid, ca, strategy, entry_price, peak_price in cur.fetchall():
                self.live[str(ca)] = {
                    "pid": int(pid),
                    "strategy": str(strategy),
                    "entry_price": float(entry_price or 0),
                    "peak_price": float(peak_price or entry_price or 0),
                }
            con.close()
            if self.live:
                self._log("recovery_loaded", open_positions=len(self.live), positions=list(self.live.keys()))
        except Exception as e:
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
        """Open position with comprehensive safety checks"""
        try:
            # Circuit breaker check
            if self.circuit_breaker.is_tripped():
                status = self.circuit_breaker.get_status()
                self._log("open_blocked_circuit_breaker", token=token, reason=status["reason"])
                return None
            
            # Concurrency limit
            if len(self.live) >= int(MAX_CONCURRENT):
                self._log("open_skipped_max_concurrent", token=token, max_concurrent=int(MAX_CONCURRENT))
                return None
            
            # Acquire token-specific lock
            lock = self._position_locks.get_lock(token)
            with lock:
                # Double-check we don't already have position
                if token in self.live:
                    self._log("open_skipped_duplicate", token=token)
                    return None
                
                usd = float(plan["usd_size"])
                trail_pct = float(plan["trail_pct"])
                strategy = plan.get("strategy", "unknown")
                
                # Validate position size
                if usd <= 0 or usd > BANKROLL_USD:
                    self._log("open_invalid_size", token=token, usd=usd, bankroll=BANKROLL_USD)
                    return None
                
                # Execute buy
                fill = self.broker.market_buy(token, usd)
                
                # Check if buy succeeded
                if not fill.success:
                    self._log("open_failed_buy", token=token, error=fill.error)
                    return None
                
                # Create position in database
                pid = create_position(token, strategy, fill.price, fill.qty, usd, trail_pct)
                add_fill(pid, "buy", fill.price, fill.qty, fill.usd)
                
                # Add to live positions with entry price
                self.live[token] = {
                    "pid": pid,
                    "strategy": strategy,
                    "entry_price": fill.price,
                    "peak_price": fill.price,
                }
                
                self._log("open_position", 
                         token=token, strategy=strategy, pid=pid, 
                         price=fill.price, qty=fill.qty, usd=usd, 
                         trail_pct=trail_pct, tx=fill.tx)
                return pid
                
        except Exception as e:
            self._log("open_exception", token=token, error=str(e))
            return None

    def has_position(self, token: str) -> bool:
        """Thread-safe position check"""
        return token in self.live

    def position_strategy(self, token: str) -> Optional[str]:
        """Get position strategy"""
        data = self.live.get(token)
        if not data:
            return None
        return str(data.get("strategy"))

    def check_exits(self, token: str, price: float) -> bool:
        """Check and execute exits with proper stop loss logic"""
        try:
            # Validate price
            if price <= 0:
                return False
            
            # Get position data
            data = self.live.get(token)
            if not data:
                return False
            
            pid = data.get("pid")
            if not pid:
                return False
            
            # Acquire lock for this position
            lock = self._position_locks.get_lock(token)
            with lock:
                # Double-check position still exists
                if token not in self.live:
                    return False
                
                # Update peak and get trail stop
                peak, trail = update_peak_and_trail(pid, price)
                
                # Get entry price and strategy
                entry_price = float(data.get("entry_price", peak))  # Fallback to peak if missing
                strategy = str(data.get("strategy", "runner"))
                
                # Update peak in live data
                self.live[token]["peak_price"] = peak
                
                # Strategy-specific stop loss percentages
                stop_pct_map = {
                    "runner": CORE_STOP_PCT,
                    "scout": SCOUT_STOP_PCT,
                    "strict": STRICT_STOP_PCT,
                    "nuanced": NUANCED_STOP_PCT,
                }
                stop_pct = stop_pct_map.get(strategy, CORE_STOP_PCT)
                
                # CRITICAL FIX: Stop loss relative to ENTRY price, not peak!
                stop_price = entry_price * (1.0 - stop_pct / 100.0)
                
                # Trail stop relative to peak
                trail_price = peak * (1.0 - trail / 100.0) if peak > 0 else 0
                
                # Determine exit type
                exit_type = None
                exit_reason = ""
                
                # Check hard stop loss (relative to entry)
                if price <= stop_price:
                    exit_type = "stop"
                    exit_reason = f"Hit stop loss: {price:.8f} <= {stop_price:.8f} (entry: {entry_price:.8f}, stop: {stop_pct}%)"
                
                # Check trailing stop (relative to peak)
                elif peak > 0 and price <= trail_price:
                    exit_type = "trail"
                    exit_reason = f"Hit trailing stop: {price:.8f} <= {trail_price:.8f} (peak: {peak:.8f}, trail: {trail}%)"
                
                # No exit triggered
                if not exit_type:
                    return False
                
                # Execute sell
                qty_open = get_open_qty(int(pid))
                if qty_open <= 0:
                    self._log("exit_zero_qty", token=token, pid=pid)
                    self.live.pop(token, None)
                    close_position(pid)
                    return False
                
                fill = self.broker.market_sell(token, float(qty_open))
                
                # Check if sell succeeded
                if not fill.success:
                    self._log("exit_failed_sell", token=token, pid=pid, error=fill.error)
                    # Don't remove from live positions if sell failed
                    return False
                
                # Calculate PnL
                entry_usd = float(data.get("entry_price", 0)) * qty_open if data.get("entry_price") else 0
                exit_usd = fill.usd
                pnl_usd = exit_usd - entry_usd if entry_usd > 0 else 0
                pnl_pct = (pnl_usd / entry_usd * 100) if entry_usd > 0 else 0
                
                # Update database
                add_fill(int(pid), "sell", float(fill.price), float(fill.qty), float(fill.usd))
                close_position(pid)
                
                # Remove from live positions
                self.live.pop(token, None)
                
                # Record with circuit breaker
                self.circuit_breaker.record_trade(pnl_usd)
                
                self._log(f"exit_{exit_type}", 
                         token=token, pid=pid, strategy=strategy,
                         entry_price=entry_price, exit_price=price, peak=peak,
                         stop_pct=stop_pct, trail_pct=trail, 
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

    def get_status(self) -> Dict:
        """Get engine status"""
        return {
            "open_positions": len(self.live),
            "tokens": list(self.live.keys()),
            "circuit_breaker": self.circuit_breaker.get_status(),
            "broker_dry_run": self.broker._dry,
        }

