"""
Dynamic Position & Capital Controller

Intelligent position management that:
- Scales max concurrent positions based on API load
- Blocks new positions when system is stressed
- Enforces daily and per-position limits
- Provides real-time capacity metrics

Design Philosophy:
- System health > individual trade opportunities
- Graceful degradation under load
- Full observability for debugging
"""
import os
import time
import threading
from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass
from collections import deque


@dataclass
class PositionCapacity:
    """Current position capacity state"""
    max_positions: int
    current_positions: int
    available_slots: int
    api_load_pct: float
    is_restricted: bool
    restriction_reason: Optional[str]
    daily_usd_remaining: float
    daily_trades_remaining: int


class PositionController:
    """
    Dynamic position controller with API-aware scaling.
    
    Features:
    - Base max positions configurable (default 10)
    - Scales down when API is stressed (429s, high latency)
    - Scales up when system is healthy
    - Blocks new positions when:
      - Daily USD cap reached
      - Daily trade count cap reached
      - API in cooldown mode
      - Queue depth too high (processing backlog)
    """
    
    def __init__(self):
        # Base configuration
        self._base_max_positions = int(os.getenv("POSITION_BASE_MAX", "10"))
        self._min_positions = int(os.getenv("POSITION_MIN", "3"))
        self._max_positions = int(os.getenv("POSITION_MAX", "15"))
        
        # Daily limits
        self._daily_max_usd = float(os.getenv("POSITION_DAILY_MAX_USD", "500.0"))
        self._daily_max_trades = int(os.getenv("POSITION_DAILY_MAX_TRADES", "20"))
        
        # Per-position limits
        self._max_position_usd = float(os.getenv("POSITION_MAX_USD", "50.0"))
        self._min_position_usd = float(os.getenv("POSITION_MIN_USD", "5.0"))
        
        # API health tracking
        self._api_429_window = deque()  # Recent 429 timestamps
        self._api_latency_window = deque()  # Recent latency samples
        self._api_health_window_sec = 300  # 5 minute window
        
        # State
        self._current_positions = 0
        self._daily_usd_spent = 0.0
        self._daily_trade_count = 0
        self._daily_reset_date = time.strftime("%Y-%m-%d")
        
        self._lock = threading.Lock()
        
        # Position tracking
        self._open_positions: Dict[str, Dict[str, Any]] = {}  # token -> {usd, ts, ...}
        
        # Load state from trading system if available
        self._sync_from_trading_system()
    
    def _sync_from_trading_system(self):
        """Sync state from trading system on startup"""
        try:
            from src.tradingSystem.trader_optimized import TradeEngine
            # This will be called during runtime, not initialization
            pass
        except Exception:
            pass
    
    def _check_daily_reset(self):
        """Reset daily counters if day changed"""
        today = time.strftime("%Y-%m-%d")
        if today != self._daily_reset_date:
            self._daily_usd_spent = 0.0
            self._daily_trade_count = 0
            self._daily_reset_date = today
    
    def _calculate_api_health(self) -> float:
        """
        Calculate API health score (0.0 = dead, 1.0 = perfect).
        
        Factors:
        - 429 rate in last 5 minutes
        - Average latency
        """
        now = time.time()
        cutoff = now - self._api_health_window_sec
        
        # Clean old entries
        while self._api_429_window and self._api_429_window[0] < cutoff:
            self._api_429_window.popleft()
        while self._api_latency_window and self._api_latency_window[0][0] < cutoff:
            self._api_latency_window.popleft()
        
        # Calculate 429 rate (per minute)
        rate_429 = len(self._api_429_window) / (self._api_health_window_sec / 60)
        
        # Score: 0 = many 429s, 1 = no 429s
        # Each 429/min reduces score by 0.2
        score_429 = max(0.0, 1.0 - (rate_429 * 0.2))
        
        # Calculate latency score
        if self._api_latency_window:
            avg_latency = sum(lat for _, lat in self._api_latency_window) / len(self._api_latency_window)
            # Target: <500ms = perfect, >2000ms = poor
            score_latency = max(0.0, min(1.0, (2000 - avg_latency) / 1500))
        else:
            score_latency = 1.0  # No data = assume healthy
        
        # Combined score (429s weighted more heavily)
        return score_429 * 0.7 + score_latency * 0.3
    
    def _calculate_dynamic_max(self) -> int:
        """
        Calculate current maximum positions based on system health.
        
        Formula: max_positions = base * api_health, clamped to [min, max]
        """
        health = self._calculate_api_health()
        
        if health >= 0.9:
            # System healthy - use full capacity
            dynamic_max = self._max_positions
        elif health >= 0.7:
            # Minor stress - use base capacity
            dynamic_max = self._base_max_positions
        elif health >= 0.5:
            # Moderate stress - reduce capacity
            dynamic_max = int(self._base_max_positions * 0.7)
        else:
            # High stress - minimum capacity
            dynamic_max = self._min_positions
        
        return max(self._min_positions, min(self._max_positions, dynamic_max))
    
    def record_api_429(self):
        """Record a 429 response from Jupiter"""
        with self._lock:
            self._api_429_window.append(time.time())
    
    def record_api_latency(self, latency_ms: float):
        """Record API latency sample"""
        with self._lock:
            self._api_latency_window.append((time.time(), latency_ms))
    
    def can_open_position(self, usd_size: float, token: str) -> Tuple[bool, str]:
        """
        Check if a new position can be opened.
        
        Args:
            usd_size: Proposed position size in USD
            token: Token address
        
        Returns:
            (can_open, reason)
        """
        with self._lock:
            self._check_daily_reset()
            
            # 1. Check if already have position
            if token in self._open_positions:
                return False, f"Already have position in {token[:8]}"
            
            # 2. Check max positions (dynamic based on API health)
            dynamic_max = self._calculate_dynamic_max()
            if self._current_positions >= dynamic_max:
                api_health = self._calculate_api_health()
                return False, f"Max positions ({dynamic_max}) reached (API health: {api_health:.0%})"
            
            # 3. Check daily USD limit
            if self._daily_usd_spent + usd_size > self._daily_max_usd:
                remaining = self._daily_max_usd - self._daily_usd_spent
                return False, f"Daily USD cap (${remaining:.2f} remaining of ${self._daily_max_usd:.2f})"
            
            # 4. Check daily trade limit
            if self._daily_max_trades > 0 and self._daily_trade_count >= self._daily_max_trades:
                return False, f"Daily trade cap ({self._daily_trade_count}/{self._daily_max_trades})"
            
            # 5. Check position size limits
            if usd_size > self._max_position_usd:
                return False, f"Position too large (${usd_size:.2f} > ${self._max_position_usd:.2f})"
            if usd_size < self._min_position_usd:
                return False, f"Position too small (${usd_size:.2f} < ${self._min_position_usd:.2f})"
            
            # 6. Check Jupiter cooldown
            try:
                from app.jupiter_client import get_jupiter_client
                jupiter = get_jupiter_client()
                in_cooldown, remaining = jupiter.is_in_cooldown()
                if in_cooldown:
                    return False, f"Jupiter API in cooldown ({remaining:.0f}s remaining)"
            except Exception:
                pass
            
            # 7. Check signal queue depth (if processing is backed up)
            try:
                from app.signal_queue import get_signal_queue
                queue = get_signal_queue()
                queue_size = queue.size()
                if queue_size > 50:  # Large backlog
                    return False, f"Processing backlog too high ({queue_size} signals queued)"
            except Exception:
                pass
            
            return True, "Position allowed"
    
    def open_position(self, token: str, usd_size: float) -> bool:
        """
        Record opening a position.
        
        Call this AFTER successfully opening a position.
        """
        with self._lock:
            self._check_daily_reset()
            
            self._open_positions[token] = {
                "usd": usd_size,
                "ts": time.time(),
            }
            self._current_positions = len(self._open_positions)
            self._daily_usd_spent += usd_size
            self._daily_trade_count += 1
            
            return True
    
    def close_position(self, token: str) -> bool:
        """
        Record closing a position.
        
        Call this AFTER successfully closing a position.
        """
        with self._lock:
            if token in self._open_positions:
                del self._open_positions[token]
                self._current_positions = len(self._open_positions)
                return True
            return False
    
    def get_capacity(self) -> PositionCapacity:
        """Get current position capacity"""
        with self._lock:
            self._check_daily_reset()
            
            dynamic_max = self._calculate_dynamic_max()
            api_health = self._calculate_api_health()
            available = dynamic_max - self._current_positions
            
            # Check for restrictions
            is_restricted = False
            restriction_reason = None
            
            if self._current_positions >= dynamic_max:
                is_restricted = True
                restriction_reason = f"Max positions ({dynamic_max}) reached"
            elif self._daily_usd_spent >= self._daily_max_usd:
                is_restricted = True
                restriction_reason = f"Daily USD cap reached"
            elif self._daily_max_trades > 0 and self._daily_trade_count >= self._daily_max_trades:
                is_restricted = True
                restriction_reason = f"Daily trade cap reached"
            elif api_health < 0.5:
                is_restricted = True
                restriction_reason = f"API health critical ({api_health:.0%})"
            
            return PositionCapacity(
                max_positions=dynamic_max,
                current_positions=self._current_positions,
                available_slots=max(0, available),
                api_load_pct=(1.0 - api_health) * 100,
                is_restricted=is_restricted,
                restriction_reason=restriction_reason,
                daily_usd_remaining=max(0, self._daily_max_usd - self._daily_usd_spent),
                daily_trades_remaining=max(0, self._daily_max_trades - self._daily_trade_count) if self._daily_max_trades > 0 else 999,
            )
    
    def get_recommended_position_size(self, base_size: float, score: int) -> float:
        """
        Get recommended position size based on score and capacity.
        
        Args:
            base_size: Requested base size
            score: Signal score (1-10)
        
        Returns:
            Recommended USD size (may be reduced or increased)
        """
        with self._lock:
            self._check_daily_reset()
            
            capacity = self.get_capacity()
            
            # Base multiplier from score
            # Score 8+: 150% | Score 7: 100% | Score 6: 75% | Score 5: 50%
            if score >= 8:
                score_mult = 1.5
            elif score == 7:
                score_mult = 1.0
            elif score == 6:
                score_mult = 0.75
            else:
                score_mult = 0.5
            
            # Capacity multiplier (reduce size when slots are limited)
            if capacity.available_slots <= 1:
                cap_mult = 0.5  # Only 1 slot left - be conservative
            elif capacity.available_slots <= 3:
                cap_mult = 0.75
            else:
                cap_mult = 1.0
            
            # API health multiplier (reduce when API stressed)
            api_health = self._calculate_api_health()
            if api_health < 0.5:
                api_mult = 0.5
            elif api_health < 0.7:
                api_mult = 0.75
            else:
                api_mult = 1.0
            
            # Calculate final size
            recommended = base_size * score_mult * cap_mult * api_mult
            
            # Clamp to limits
            recommended = max(self._min_position_usd, min(self._max_position_usd, recommended))
            
            # Ensure doesn't exceed daily remaining
            recommended = min(recommended, capacity.daily_usd_remaining)
            
            return recommended


# Global instance
_position_controller: Optional[PositionController] = None


def get_position_controller() -> PositionController:
    """Get or create global position controller instance"""
    global _position_controller
    if _position_controller is None:
        _position_controller = PositionController()
    return _position_controller
