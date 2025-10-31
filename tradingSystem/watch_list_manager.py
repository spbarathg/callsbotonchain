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
"""
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
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
    
    def __init__(self):
        self.watch_list: Dict[str, WatchedSignal] = {}
        
        # Tracking intervals (in seconds) - OPTIMIZED FOR JUPITER 10 RPS
        # Strategy: Jupiter only with smart rate limiting for RELIABLE prices
        self.INTERVAL_NEW = 30  # New signals (<5 min old) - catch early pumps
        self.INTERVAL_ACTIVE = 45  # Active movement detected - monitor closely
        self.INTERVAL_STABLE = 90  # Stable/slow moving - conserve API
        self.INTERVAL_EXITED = 180  # Exited positions (check for re-entry) - low priority
        
        # Rate limiting
        self.last_api_call = 0
        self.min_call_interval = 0.15  # 150ms between calls = ~6.7 RPS max (safe margin under 10)
        
        # Entry thresholds
        self.ENTRY_MIN_GAIN = 5.0  # Min +5% from signal to consider entry
        self.ENTRY_MIN_VELOCITY = 2.0  # Min +2%/min velocity
        self.ENTRY_MIN_SCORE = 6  # Min signal score
        
        # Re-entry thresholds
        self.REENTRY_MIN_GAIN = 15.0  # If exited, re-enter at +15% from signal
        self.REENTRY_MIN_VELOCITY = 3.0  # Strong pump needed for re-entry
        
        # Stats
        self.signals_added = 0
        self.entries_made = 0
        self.reentries_made = 0
        self.price_checks = 0
    
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
    
    def _get_price_from_jupiter(self, token: str) -> Optional[float]:
        """
        Get RELIABLE price from Jupiter (ONLY API ALLOWED)
        
        User requirement: No DexScreener usage
        - Jupiter provides real-time prices from actual DEX aggregation
        - Rate limited to stay under 10 RPS with smart intervals
        - Aggressive caching prevents API abuse
        """
        try:
            # Use broker's get_token_price (already implemented and efficient)
            from .broker_optimized import Broker
            from solders.keypair import Keypair
            import os
            import json
            import base58
            
            # Get keypair (needed for broker init)
            pk_env = os.getenv("TS_WALLET_SECRET", "")
            if pk_env.strip().startswith("["):
                arr = json.loads(pk_env)
                kp = Keypair.from_bytes(bytes(arr))
            else:
                pk_bytes = base58.b58decode(pk_env)
                kp = Keypair.from_bytes(pk_bytes)
            
            # Get price via broker (uses Jupiter)
            from solana.rpc.api import Client
            rpc = Client(os.getenv("TS_RPC_URL", "https://api.mainnet-beta.solana.com"))
            broker = Broker(rpc, kp)
            price = broker.get_token_price(token)
            
            return price if price > 0 else None
        except Exception as e:
            # Fallback: Return None, will skip this update cycle
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
        
        # Classify movement
        recent_samples = 3
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
            
            # Skip if checked too recently
            if now - signal.last_check < interval:
                continue
            
            # Rate limiting: Ensure we don't exceed ~6.7 RPS
            time_since_last_call = now - self.last_api_call
            if time_since_last_call < self.min_call_interval:
                time.sleep(self.min_call_interval - time_since_last_call)
            
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
            
            # === ENTRY LOGIC ===
            if not signal.entered and not signal.exited:
                # Should we enter this signal?
                if (signal.signal_score >= self.ENTRY_MIN_SCORE and
                    signal.current_gain >= self.ENTRY_MIN_GAIN and
                    signal.velocity >= self.ENTRY_MIN_VELOCITY and
                    signal.is_pumping):
                    
                    recommendations["enter"].append({
                        "token": token,
                        "current_price": price,
                        "gain": signal.current_gain,
                        "velocity": signal.velocity,
                        "score": signal.signal_score,
                        "reason": f"Pumping +{signal.current_gain:.1f}% at {signal.velocity:.1f}%/min"
                    })
            
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
    
    def mark_exited(self, token: str, exit_price: float, reason: str):
        """Mark a signal as exited (but keep watching!)"""
        if token in self.watch_list:
            signal = self.watch_list[token]
            signal.exited = True
            signal.exit_price = exit_price
            signal.exit_reason = reason
            print(f"[WATCHLIST] 🚪 Exited {token[:8]} at ${exit_price:.8f} ({reason})", flush=True)
            print(f"[WATCHLIST] 👀 Still watching for re-entry opportunity...", flush=True)
    
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

