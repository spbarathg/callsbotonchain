"""
WATCH LIST MANAGER
Smart signal tracking without buying everything

STRATEGY:
1. ALL signals → Watch list (track prices)
2. Identify "movers" (pumping >5% in 2min)
3. Enter best movers with big positions ($80-100)
4. Exit losers at -10% BUT keep watching
5. Re-enter if exited token starts pumping

API EFFICIENCY:
- Use Jupiter for all price tracking (user requirement: Jupiter only)
- Respects 10 RPS limit with smart caching
- Rate limiting: 150ms between calls = ~6.7 RPS (safe margin)
- Smart intervals: New signals = 30s, stable = 90s

CAPITAL MANAGEMENT:
- $600 balance → Max 6 positions @ $100 each
- Only enter signals showing REAL movement
- Exit bad trades quickly, reallocate capital

PERSISTENCE:
- Watch list persisted to Redis (survives restarts)
- Auto-saves on every state change
- Auto-loads on startup
"""
import time
import json
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
import requests
from datetime import datetime


@dataclass
class WatchedSignal:
    """Represents a signal being watched"""
    token: str
    signal_time: float
    signal_price: float
    signal_score: int
    conviction: str
    
    # Tracking data
    prices: List[float] = field(default_factory=list)
    timestamps: List[float] = field(default_factory=list)
    last_check: float = 0
    
    # Status
    entered: bool = False
    exited: bool = False
    position_id: Optional[int] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    
    # Movement tracking
    max_gain: float = 0  # Peak % from signal price
    current_gain: float = 0  # Current % from signal price
    velocity: float = 0  # % per minute
    is_pumping: bool = False
    is_dumping: bool = False


class WatchListManager:
    """
    Manages watch list of all signals
    Tracks prices efficiently
    Identifies best entry opportunities
    """
    
    REDIS_KEY = "watchlist:signals"  # Redis key for persistent storage
    
    def __init__(self):
        print("[WATCHLIST] Initializing WatchListManager...", flush=True)
        self.watch_list: Dict[str, WatchedSignal] = {}
        
        # Tracking intervals (in seconds) - AGGRESSIVE for fast memecoin pumps
        # Strategy: Jupiter only with smart rate limiting for RELIABLE prices
        self.INTERVAL_NEW = 15  # New signals (<5 min old) - FAST reaction (lowered from 30s)
        self.INTERVAL_ACTIVE = 20  # Active movement detected - monitor very closely
        self.INTERVAL_STABLE = 60  # Stable/slow moving - conserve API
        self.INTERVAL_EXITED = 180  # Exited positions (check for re-entry) - low priority
        
        # Rate limiting
        self.last_api_call = 0
        self.min_call_interval = 0.15  # 150ms between calls = ~6.7 RPS max (safe margin under 10)
        
        # Entry thresholds - AGGRESSIVE for fast memecoins
        self.ENTRY_MIN_GAIN = 3.0  # Min +3% from signal to consider entry (lowered from 5%)
        self.ENTRY_MIN_VELOCITY = 1.5  # Min +1.5%/min velocity (lowered from 2%)
        self.ENTRY_MIN_SCORE = 6  # Min signal score
        
        # Re-entry thresholds
        self.REENTRY_MIN_GAIN = 15.0  # If exited, re-enter at +15% from signal
        self.REENTRY_MIN_VELOCITY = 3.0  # Strong pump needed for re-entry
        
        # Stats
        self.signals_added = 0
        self.entries_made = 0
        self.reentries_made = 0
        self.price_checks = 0
        
        # Redis client for persistence
        self._redis = None
        print("[WATCHLIST] Connecting to Redis for persistence...", flush=True)
        self._init_redis()
        
        # CRITICAL: Load watch list from Redis on startup
        print("[WATCHLIST] Loading persisted signals from Redis...", flush=True)
        self._load_from_redis()
        print("[WATCHLIST] Initialization complete!", flush=True)
    
    def _init_redis(self):
        """Initialize Redis connection for persistence"""
        try:
            import redis
            redis_url = os.getenv("REDIS_URL") or os.getenv("CALLSBOT_REDIS_URL") or "redis://localhost:6379/0"
            self._redis = redis.from_url(redis_url, decode_responses=True, socket_timeout=5)
            self._redis.ping()
            print("[WATCHLIST] ✅ Redis persistence enabled", flush=True)
        except Exception as e:
            print(f"[WATCHLIST] ⚠️ Redis unavailable, watch list won't persist: {e}", flush=True)
            self._redis = None
    
    def _save_to_redis(self):
        """Save watch list to Redis (async, non-blocking)"""
        if not self._redis:
            return
        
        try:
            # Serialize all signals to JSON
            data = {}
            for token, signal in self.watch_list.items():
                data[token] = asdict(signal)
            
            # Save to Redis with 24h TTL
            self._redis.setex(
                self.REDIS_KEY,
                86400,  # 24 hours
                json.dumps(data)
            )
        except Exception as e:
            # Don't crash if Redis fails, just log
            if not hasattr(self, '_save_errors'):
                self._save_errors = 0
            self._save_errors += 1
            if self._save_errors % 10 == 1:  # Log every 10 failures
                print(f"[WATCHLIST] ⚠️ Redis save error (#{self._save_errors}): {e}", flush=True)
    
    def _load_from_redis(self):
        """Load watch list from Redis on startup"""
        if not self._redis:
            return
        
        try:
            data_str = self._redis.get(self.REDIS_KEY)
            if not data_str:
                print("[WATCHLIST] No persisted watch list found (clean start)", flush=True)
                return
            
            data = json.loads(data_str)
            count = 0
            for token, signal_dict in data.items():
                # Reconstruct WatchedSignal from dict
                signal = WatchedSignal(
                    token=signal_dict['token'],
                    signal_time=signal_dict['signal_time'],
                    signal_price=signal_dict['signal_price'],
                    signal_score=signal_dict['signal_score'],
                    conviction=signal_dict['conviction'],
                    prices=signal_dict.get('prices', []),
                    timestamps=signal_dict.get('timestamps', []),
                    last_check=signal_dict.get('last_check', 0),
                    entered=signal_dict.get('entered', False),
                    exited=signal_dict.get('exited', False),
                    position_id=signal_dict.get('position_id'),
                    entry_price=signal_dict.get('entry_price'),
                    exit_price=signal_dict.get('exit_price'),
                    exit_reason=signal_dict.get('exit_reason'),
                    max_gain=signal_dict.get('max_gain', 0),
                    current_gain=signal_dict.get('current_gain', 0),
                    velocity=signal_dict.get('velocity', 0),
                    is_pumping=signal_dict.get('is_pumping', False),
                    is_dumping=signal_dict.get('is_dumping', False)
                )
                self.watch_list[token] = signal
                count += 1
            
            print(f"[WATCHLIST] ✅ Loaded {count} signals from Redis (survived restart!)", flush=True)
            
        except Exception as e:
            print(f"[WATCHLIST] ⚠️ Failed to load from Redis: {e}", flush=True)
    
    def add_signal(self, token: str, signal_time: float, signal_price: float, 
                   signal_score: int, conviction: str):
        """Add new signal to watch list"""
        if token not in self.watch_list:
            self.watch_list[token] = WatchedSignal(
                token=token,
                signal_time=signal_time,
                signal_price=signal_price,
                signal_score=signal_score,
                conviction=conviction
            )
            self.signals_added += 1
            print(f"[WATCHLIST] ➕ Added {token[:8]} (score {signal_score}) to watch list", flush=True)
            
            # CRITICAL: Save to Redis immediately
            self._save_to_redis()
    
    def _get_price_from_jupiter(self, token: str) -> Optional[float]:
        """
        Get RELIABLE price from Jupiter (ONLY API ALLOWED)
        
        User requirement: No DexScreener usage
        - Jupiter provides real-time prices from actual DEX aggregation
        - Rate limited to stay under 10 RPS with smart intervals
        - Aggressive caching prevents API abuse
        """
        try:
            # CRITICAL FIX (Nov 1): Use jupiter_price_oracle for consistency
            # Problem: Creating new Broker instances was failing silently
            # Solution: Reuse the same oracle as exit monitoring
            from .jupiter_price_oracle import get_jupiter_price_oracle
            oracle = get_jupiter_price_oracle()
            
            # Get sellable price from Jupiter (same as exit monitoring uses)
            price = oracle.get_sellable_price(token, cache_ttl=5)  # 5s cache for watch list
            
            if price and price > 0:
                return price
            else:
                # Price fetch failed - log every 10 failures per token
                if not hasattr(self, '_price_failures'):
                    self._price_failures = {}
                self._price_failures[token] = self._price_failures.get(token, 0) + 1
                
                if self._price_failures[token] % 10 == 1:  # Log 1st, 11th, 21st...
                    print(f"[WATCHLIST] ⚠️ Price unavailable for {token[:8]} (failure #{self._price_failures[token]})", flush=True)
                
                return None
            
        except Exception as e:
            # Log critical errors
            if not hasattr(self, '_logged_errors'):
                self._logged_errors = set()
            
            error_key = f"{token[:8]}:{type(e).__name__}"
            if error_key not in self._logged_errors:
                print(f"[WATCHLIST] ❌ Price fetch error for {token[:8]}: {e}", flush=True)
                self._logged_errors.add(error_key)
            
            return None
    
    def _calculate_metrics(self, signal: WatchedSignal, current_price: float):
        """Calculate movement metrics for a signal"""
        if signal.signal_price <= 0:
            return
        
        # Current gain from signal price
        signal.current_gain = ((current_price - signal.signal_price) / signal.signal_price) * 100
        
        # Update max gain
        if signal.current_gain > signal.max_gain:
            signal.max_gain = signal.current_gain
        
        # Calculate velocity (% per minute)
        if len(signal.timestamps) >= 2:
            time_elapsed = signal.timestamps[-1] - signal.timestamps[0]
            if time_elapsed > 0:
                price_change = ((signal.prices[-1] - signal.prices[0]) / signal.prices[0]) * 100
                signal.velocity = (price_change / (time_elapsed / 60))  # % per minute
        
        # Classify movement - FAST REACTION (only need 2 samples, not 3)
        recent_samples = 2  # Changed from 3 to 2 for faster detection
        if len(signal.prices) >= recent_samples:
            recent_prices = signal.prices[-recent_samples:]
            signal.is_pumping = all(recent_prices[i] <= recent_prices[i+1] for i in range(len(recent_prices)-1))
            signal.is_dumping = all(recent_prices[i] >= recent_prices[i+1] for i in range(len(recent_prices)-1))
    
    def update_prices(self) -> Dict[str, Dict]:
        """
        Update prices for all watched tokens
        Returns dict of entry/re-entry recommendations
        """
        now = time.time()
        recommendations = {
            "enter": [],  # New entries
            "reenter": [],  # Re-entries for exited positions
        }
        
        # CRITICAL DEBUG (Nov 1): Log why prices aren't being checked
        if not hasattr(self, '_debug_logged'):
            self._debug_logged = False
        
        for token, signal in list(self.watch_list.items()):
            # Determine check interval
            signal_age = now - signal.signal_time
            
            if signal.exited:
                interval = self.INTERVAL_EXITED
            elif signal_age < 300:  # <5 min
                interval = self.INTERVAL_NEW
            elif signal.is_pumping or abs(signal.velocity) > 2:
                interval = self.INTERVAL_ACTIVE
            else:
                interval = self.INTERVAL_STABLE
            
            # CRITICAL DEBUG: Log first iteration details
            if not self._debug_logged and len(self.watch_list) > 0:
                print(f"[WATCHLIST_DEBUG] Token: {token[:8]}, signal_age: {signal_age:.1f}s, "
                      f"last_check: {signal.last_check}, interval: {interval}s, "
                      f"time_since_check: {now - signal.last_check:.1f}s, "
                      f"entered: {signal.entered}, exited: {signal.exited}", flush=True)
                self._debug_logged = True
            
            # Skip if checked too recently
            if now - signal.last_check < interval:
                continue
            
            # Rate limiting: Ensure we don't exceed ~6.7 RPS
            time_since_last_call = now - self.last_api_call
            if time_since_last_call < self.min_call_interval:
                time.sleep(self.min_call_interval - time_since_last_call)
            
            # Log that we're actually checking
            print(f"[WATCHLIST_DEBUG] Checking price for {token[:8]}...", flush=True)
            
            # Get current price from Jupiter (RELIABLE)
            price = self._get_price_from_jupiter(token)
            self.last_api_call = time.time()
            
            if not price:
                continue
            
            # Update tracking data
            signal.prices.append(price)
            signal.timestamps.append(now)
            signal.last_check = now
            self.price_checks += 1
            
            # Keep only last 10 samples (sliding window)
            if len(signal.prices) > 10:
                signal.prices = signal.prices[-10:]
                signal.timestamps = signal.timestamps[-10:]
            
            # Calculate metrics
            self._calculate_metrics(signal, price)
            
            # Save to Redis every 10 price checks to avoid excessive writes
            if self.price_checks % 10 == 0:
                self._save_to_redis()
            
            # DEBUG: Log price tracking
            print(f"[WATCHLIST_DEBUG] {token[:8]} | Price: ${price:.8f} | Samples: {len(signal.prices)} | "
                  f"Gain: {signal.current_gain:+.1f}% | Vel: {signal.velocity:+.1f}%/min | "
                  f"Pumping: {signal.is_pumping} | Score: {signal.signal_score}", flush=True)
            
            # === ENTRY LOGIC ===
            if not signal.entered and not signal.exited:
                # Should we enter this signal?
                # Check all conditions
                score_ok = signal.signal_score >= self.ENTRY_MIN_SCORE
                gain_ok = signal.current_gain >= self.ENTRY_MIN_GAIN
                velocity_ok = signal.velocity >= self.ENTRY_MIN_VELOCITY
                pumping_ok = signal.is_pumping
                
                if score_ok and gain_ok and velocity_ok and pumping_ok:
                    print(f"[WATCHLIST_DEBUG] ✅ ENTRY TRIGGERED for {token[:8]} | "
                          f"+{signal.current_gain:.1f}% at {signal.velocity:.1f}%/min", flush=True)
                    
                    recommendations["enter"].append({
                        "token": token,
                        "current_price": price,
                        "gain": signal.current_gain,
                        "velocity": signal.velocity,
                        "score": signal.signal_score,
                        "reason": f"Pumping +{signal.current_gain:.1f}% at {signal.velocity:.1f}%/min"
                    })
                else:
                    # DEBUG: Log why entry was not triggered
                    failed_checks = []
                    if not score_ok: failed_checks.append(f"score={signal.signal_score}<{self.ENTRY_MIN_SCORE}")
                    if not gain_ok: failed_checks.append(f"gain={signal.current_gain:.1f}%<{self.ENTRY_MIN_GAIN}%")
                    if not velocity_ok: failed_checks.append(f"vel={signal.velocity:.1f}<{self.ENTRY_MIN_VELOCITY}")
                    if not pumping_ok: failed_checks.append("not_pumping")
                    
                    print(f"[WATCHLIST_DEBUG] ❌ {token[:8]} not ready: {', '.join(failed_checks)}", flush=True)
            
            # === RE-ENTRY LOGIC ===
            elif signal.exited and signal.exit_reason == "stop_loss":
                # We exited at -10%, but should we re-enter?
                if (signal.current_gain >= self.REENTRY_MIN_GAIN and
                    signal.velocity >= self.REENTRY_MIN_VELOCITY and
                    signal.is_pumping):
                    
                    recommendations["reenter"].append({
                        "token": token,
                        "current_price": price,
                        "gain": signal.current_gain,
                        "velocity": signal.velocity,
                        "score": signal.signal_score,
                        "reason": f"Recovery pump +{signal.current_gain:.1f}% from signal (exited earlier)"
                    })
        
        return recommendations
    
    def mark_entered(self, token: str, position_id: int, entry_price: float):
        """Mark a signal as entered"""
        if token in self.watch_list:
            signal = self.watch_list[token]
            signal.entered = True
            signal.position_id = position_id
            signal.entry_price = entry_price
            self.entries_made += 1
            print(f"[WATCHLIST] ✅ Entered {token[:8]} at ${entry_price:.8f}", flush=True)
            
            # Save state change to Redis
            self._save_to_redis()
    
    def mark_exited(self, token: str, exit_price: float, reason: str):
        """Mark a signal as exited (but keep watching!)"""
        if token in self.watch_list:
            signal = self.watch_list[token]
            signal.exited = True
            signal.exit_price = exit_price
            signal.exit_reason = reason
            print(f"[WATCHLIST] 🚪 Exited {token[:8]} at ${exit_price:.8f} ({reason})", flush=True)
            print(f"[WATCHLIST] 👀 Still watching for re-entry opportunity...", flush=True)
            
            # Save state change to Redis
            self._save_to_redis()
    
    def mark_reentered(self, token: str, position_id: int, entry_price: float):
        """Mark a signal as re-entered"""
        if token in self.watch_list:
            signal = self.watch_list[token]
            signal.entered = True
            signal.exited = False
            signal.position_id = position_id
            signal.entry_price = entry_price
            self.reentries_made += 1
            print(f"[WATCHLIST] 🔄 RE-ENTERED {token[:8]} at ${entry_price:.8f}", flush=True)
    
    def get_watch_summary(self) -> str:
        """Get summary of watch list"""
        total = len(self.watch_list)
        watching = sum(1 for s in self.watch_list.values() if not s.entered and not s.exited)
        entered = sum(1 for s in self.watch_list.values() if s.entered and not s.exited)
        exited_watching = sum(1 for s in self.watch_list.values() if s.exited)
        
        return (f"Watch List: {total} total | "
                f"{watching} watching | "
                f"{entered} entered | "
                f"{exited_watching} exited (watching for re-entry)")
    
    def get_stats(self) -> Dict:
        """Get detailed stats"""
        return {
            "signals_added": self.signals_added,
            "entries_made": self.entries_made,
            "reentries_made": self.reentries_made,
            "price_checks": self.price_checks,
            "watch_list_size": len(self.watch_list),
        }
    
    def cleanup_old_signals(self, max_age_hours: int = 24):
        """Remove old signals from watch list"""
        now = time.time()
        removed = 0
        for token in list(self.watch_list.keys()):
            signal = self.watch_list[token]
            age_hours = (now - signal.signal_time) / 3600
            
            # Remove if: old AND (not entered OR exited with no recovery)
            if age_hours > max_age_hours:
                if not signal.entered or (signal.exited and signal.current_gain < 0):
                    del self.watch_list[token]
                    removed += 1
        
        if removed > 0:
            print(f"[WATCHLIST] 🧹 Cleaned up {removed} old signals", flush=True)


# Global instance
_manager: Optional[WatchListManager] = None


def get_watch_list_manager() -> WatchListManager:
    """Get or create global watch list manager"""
    global _manager
    if _manager is None:
        _manager = WatchListManager()
    return _manager

