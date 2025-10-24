"""
INACTIVITY-BASED EXIT SYSTEM
Exit positions based on price stagnation, not arbitrary time limits

KEY INSIGHT: Some tokens pump for 8-10 days to 800x
- Don't force-sell winners that are still moving
- DO exit when price is dead/stagnant (pump is over)
- Track price velocity and movement patterns
"""
import time
from typing import Dict, Optional, Tuple
from collections import deque


class InactivityMonitor:
    """Track price movement and detect dead positions"""
    
    def __init__(self):
        # Track price history for each position (last N prices)
        self.price_history: Dict[str, deque] = {}
        
        # Thresholds
        self.MIN_SAMPLES = 10  # Need 10 price checks before judging
        self.INACTIVITY_THRESHOLD_PCT = 5.0  # <5% movement = inactive
        self.INACTIVITY_DURATION_HOURS = 6.0  # 6 hours of no movement = exit
        
        # Track when position entered "inactive" state
        self.inactive_since: Dict[str, float] = {}
    
    def add_price_sample(self, token: str, price: float, timestamp: Optional[float] = None):
        """Record a price observation"""
        if timestamp is None:
            timestamp = time.time()
        
        if token not in self.price_history:
            self.price_history[token] = deque(maxlen=50)  # Keep last 50 samples
        
        self.price_history[token].append((timestamp, price))
    
    def check_inactivity(self, token: str) -> Tuple[bool, str]:
        """
        Check if position is inactive and should be exited
        
        Returns: (should_exit: bool, reason: str)
        """
        if token not in self.price_history:
            return False, "No price history"
        
        history = list(self.price_history[token])
        
        # Need minimum samples to judge
        if len(history) < self.MIN_SAMPLES:
            return False, f"Insufficient data ({len(history)}/{self.MIN_SAMPLES} samples)"
        
        # Get recent time window (last 6 hours or all data if < 6 hours)
        now = time.time()
        six_hours_ago = now - (self.INACTIVITY_DURATION_HOURS * 3600)
        recent_samples = [(t, p) for t, p in history if t >= six_hours_ago]
        
        if len(recent_samples) < self.MIN_SAMPLES:
            # Not enough recent data - use all available
            recent_samples = history
        
        # Calculate price range in recent window
        prices = [p for _, p in recent_samples]
        min_price = min(prices)
        max_price = max(prices)
        
        if min_price == 0:
            return False, "Invalid price data"
        
        # Calculate % movement
        price_range_pct = ((max_price - min_price) / min_price) * 100
        
        # Check if inactive
        is_inactive = price_range_pct < self.INACTIVITY_THRESHOLD_PCT
        
        if is_inactive:
            # Track when inactivity started
            if token not in self.inactive_since:
                self.inactive_since[token] = now
            
            inactive_duration_hours = (now - self.inactive_since[token]) / 3600
            
            # Exit if inactive for full duration
            if inactive_duration_hours >= self.INACTIVITY_DURATION_HOURS:
                oldest_sample_age = (now - recent_samples[0][0]) / 3600
                return True, (f"INACTIVE: {price_range_pct:.2f}% movement in {oldest_sample_age:.1f}h "
                             f"(threshold: {self.INACTIVITY_THRESHOLD_PCT}%)")
            else:
                return False, (f"Entering inactivity: {price_range_pct:.2f}% movement, "
                              f"{inactive_duration_hours:.1f}h/{self.INACTIVITY_DURATION_HOURS}h")
        else:
            # Price is moving - reset inactivity tracker
            if token in self.inactive_since:
                del self.inactive_since[token]
            
            return False, f"Active: {price_range_pct:.2f}% movement (healthy)"
    
    def should_ignore_time_limit(self, token: str, current_profit_pct: float) -> Tuple[bool, str]:
        """
        Determine if this position should ignore MAX_HOLD_TIME
        
        Big winners with active price movement should run indefinitely
        
        Returns: (ignore_time_limit: bool, reason: str)
        """
        # High-profit positions (>200%) get special treatment
        if current_profit_pct < 200.0:
            return False, f"Profit too low ({current_profit_pct:.1f}% < 200%)"
        
        # Check if price is actively moving
        is_inactive, reason = self.check_inactivity(token)
        
        if is_inactive:
            # Even high-profit positions should exit if dead
            return False, f"High profit but inactive: {reason}"
        else:
            # Price is moving + high profit = let it run!
            return True, f"MOONSHOT MODE: {current_profit_pct:.1f}% profit + active price movement"
    
    def reset_position(self, token: str):
        """Remove position from tracking (after it's closed)"""
        if token in self.price_history:
            del self.price_history[token]
        if token in self.inactive_since:
            del self.inactive_since[token]
    
    def get_position_stats(self, token: str) -> Dict:
        """Get statistics for a position"""
        if token not in self.price_history:
            return {"samples": 0, "status": "no_data"}
        
        history = list(self.price_history[token])
        is_inactive, reason = self.check_inactivity(token)
        
        return {
            "samples": len(history),
            "is_inactive": is_inactive,
            "reason": reason,
            "inactive_duration_hours": (time.time() - self.inactive_since[token]) / 3600 if token in self.inactive_since else 0
        }

