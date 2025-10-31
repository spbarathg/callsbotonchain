"""
Circuit Breaker and Loss Limits
Prevents catastrophic losses by halting trading when risk thresholds are exceeded
"""

import time
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import threading


class CircuitBreaker:
    """
    Circuit breaker system to halt trading under dangerous conditions
    
    Triggers:
    1. Daily loss limit exceeded
    2. Weekly loss limit exceeded
    3. Consecutive losing trades (>=3)
    4. Excessive slippage events
    5. Manual emergency stop
    """
    
    def __init__(self):
        self.lock = threading.Lock()
        
        # Configuration (can be overridden via env vars)
        self.daily_loss_limit_usd = 100.0  # $100 per day
        self.weekly_loss_limit_usd = 300.0  # $300 per week
        self.consecutive_loss_limit = 3  # Halt after 3 consecutive losses
        self.excessive_slippage_threshold = 10.0  # 10% slippage is excessive
        self.slippage_event_limit = 5  # 5 excessive slippage events triggers circuit breaker
        
        # State tracking
        self.is_tripped = False
        self.trip_reason = None
        self.trip_time = None
        self.manual_override = False
        
        # Loss tracking
        self.daily_pnl_history: Dict[str, float] = {}  # date -> pnl_usd
        self.weekly_pnl: float = 0.0
        self.last_week_reset = time.time()
        
        # Consecutive loss tracking
        self.consecutive_losses = 0
        self.last_trade_result = None  # "win" or "loss"
        
        # Slippage tracking
        self.slippage_events: list = []  # List of (timestamp, slippage_pct)
        self.excessive_slippage_count = 0
    
    def check_can_trade(self) -> Tuple[bool, Optional[str]]:
        """
        Check if trading is allowed
        
        Returns:
            (can_trade, reason_if_blocked)
        """
        with self.lock:
            if self.manual_override:
                return False, "Manual emergency stop activated"
            
            if self.is_tripped:
                # Check if cooldown period has passed
                if self.trip_time:
                    elapsed = time.time() - self.trip_time
                    cooldown = 3600  # 1 hour cooldown after circuit breaker trips
                    
                    if elapsed < cooldown:
                        remaining = cooldown - elapsed
                        return False, f"Circuit breaker tripped: {self.trip_reason} (cooldown: {remaining/60:.1f}m remaining)"
                    else:
                        # Reset circuit breaker after cooldown
                        self.reset()
                        return True, None
            
            return True, None
    
    def record_trade(self, pnl_usd: float, slippage_pct: float = 0.0):
        """
        Record a completed trade and check circuit breaker conditions
        
        Args:
            pnl_usd: P&L in USD (positive for profit, negative for loss)
            slippage_pct: Execution slippage percentage
        """
        with self.lock:
            # Update daily P&L
            today = datetime.now().date().isoformat()
            if today not in self.daily_pnl_history:
                self.daily_pnl_history[today] = 0.0
            self.daily_pnl_history[today] += pnl_usd
            
            # Update weekly P&L
            now = time.time()
            if now - self.last_week_reset > (7 * 24 * 3600):
                # Reset weekly counter
                self.weekly_pnl = 0.0
                self.last_week_reset = now
            self.weekly_pnl += pnl_usd
            
            # Track consecutive losses
            if pnl_usd < 0:
                if self.last_trade_result == "loss":
                    self.consecutive_losses += 1
                else:
                    self.consecutive_losses = 1
                self.last_trade_result = "loss"
            else:
                self.consecutive_losses = 0
                self.last_trade_result = "win"
            
            # Track excessive slippage
            if slippage_pct > self.excessive_slippage_threshold:
                self.slippage_events.append((now, slippage_pct))
                self.excessive_slippage_count += 1
                
                # Clean old events (last 1 hour)
                cutoff = now - 3600
                self.slippage_events = [(t, s) for t, s in self.slippage_events if t > cutoff]
                self.excessive_slippage_count = len(self.slippage_events)
            
            # Check circuit breaker conditions
            self._check_trip_conditions()
    
    def _check_trip_conditions(self):
        """Internal: Check if any circuit breaker condition is met"""
        # 1. Daily loss limit
        today = datetime.now().date().isoformat()
        daily_pnl = self.daily_pnl_history.get(today, 0.0)
        if daily_pnl < -self.daily_loss_limit_usd:
            self._trip(f"Daily loss limit exceeded: ${daily_pnl:.2f} (limit: -${self.daily_loss_limit_usd:.2f})")
            return
        
        # 2. Weekly loss limit
        if self.weekly_pnl < -self.weekly_loss_limit_usd:
            self._trip(f"Weekly loss limit exceeded: ${self.weekly_pnl:.2f} (limit: -${self.weekly_loss_limit_usd:.2f})")
            return
        
        # 3. Consecutive losses
        if self.consecutive_losses >= self.consecutive_loss_limit:
            self._trip(f"{self.consecutive_losses} consecutive losing trades")
            return
        
        # 4. Excessive slippage
        if self.excessive_slippage_count >= self.slippage_event_limit:
            self._trip(f"{self.excessive_slippage_count} excessive slippage events in last hour")
            return
    
    def _trip(self, reason: str):
        """Internal: Trip the circuit breaker"""
        self.is_tripped = True
        self.trip_reason = reason
        self.trip_time = time.time()
        
        print(f"[CIRCUIT_BREAKER] 🚨 TRADING HALTED: {reason}", flush=True)
        print(f"[CIRCUIT_BREAKER] System will resume in 1 hour or after manual reset", flush=True)
    
    def reset(self):
        """Reset the circuit breaker (admin action)"""
        with self.lock:
            self.is_tripped = False
            self.trip_reason = None
            self.trip_time = None
            self.consecutive_losses = 0
            self.excessive_slippage_count = 0
            self.slippage_events = []
            
            print(f"[CIRCUIT_BREAKER] ✅ Reset - trading resumed", flush=True)
    
    def emergency_stop(self):
        """Manual emergency stop (requires manual reset)"""
        with self.lock:
            self.manual_override = True
            self._trip("Manual emergency stop")
            
            print(f"[CIRCUIT_BREAKER] 🛑 EMERGENCY STOP ACTIVATED", flush=True)
            print(f"[CIRCUIT_BREAKER] Requires manual reset to resume trading", flush=True)
    
    def get_status(self) -> Dict:
        """Get current circuit breaker status"""
        with self.lock:
            today = datetime.now().date().isoformat()
            daily_pnl = self.daily_pnl_history.get(today, 0.0)
            
            can_trade, reason = self.check_can_trade()
            
            return {
                "can_trade": can_trade,
                "is_tripped": self.is_tripped,
                "trip_reason": self.trip_reason,
                "manual_override": self.manual_override,
                "daily_pnl_usd": daily_pnl,
                "daily_loss_limit_usd": self.daily_loss_limit_usd,
                "weekly_pnl_usd": self.weekly_pnl,
                "weekly_loss_limit_usd": self.weekly_loss_limit_usd,
                "consecutive_losses": self.consecutive_losses,
                "consecutive_loss_limit": self.consecutive_loss_limit,
                "excessive_slippage_count": self.excessive_slippage_count,
                "slippage_event_limit": self.slippage_event_limit,
                "reason_if_blocked": reason,
            }


# Global circuit breaker instance
_circuit_breaker = None

def get_circuit_breaker() -> CircuitBreaker:
    """Get global circuit breaker instance"""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker()
    return _circuit_breaker







