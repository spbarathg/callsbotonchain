"""
ADAPTIVE POSITION MONITORING
Adjust check frequency based on position maturity and profit level

KEY INSIGHT: Not all tokens are short-term pumps
- New/volatile positions need frequent checks (protect capital)
- Established moonshots need LESS checking (room to breathe for days-long pumps)
- This saves API limits AND captures multi-day gains
"""
import time
from typing import Dict, Tuple


class AdaptiveMonitor:
    """Determines optimal check interval for each position"""
    
    def __init__(self):
        # Intervals in seconds
        self.FAST_INTERVAL = 1.5      # New/volatile positions
        self.MEDIUM_INTERVAL = 1800   # 30 min - Established positions
        self.SLOW_INTERVAL = 7200     # 2 hours - Confirmed moonshots
        self.ULTRA_SLOW_INTERVAL = 14400  # 4 hours - Mega pumpers (500%+)
        
        # Track last check time per position
        self.last_check: Dict[str, float] = {}
    
    def should_check_position(self, 
                             token: str, 
                             entry_time: float,
                             current_profit_pct: float,
                             peak_profit_pct: float = 0.0) -> Tuple[bool, str]:
        """
        Determine if we should check this position for exit
        
        Returns: (should_check: bool, reason: str)
        """
        now = time.time()
        position_age_hours = (now - entry_time) / 3600
        
        # First check is always immediate
        if token not in self.last_check:
            self.last_check[token] = now
            return True, "Initial check"
        
        time_since_last_check = now - self.last_check[token]
        
        # === TIER 1: NEW & VOLATILE (Fast checks - protect capital) ===
        # Age < 1 hour OR profit < 50%
        if position_age_hours < 1.0 or current_profit_pct < 50.0:
            if time_since_last_check >= self.FAST_INTERVAL:
                self.last_check[token] = now
                return True, f"Tier 1: New/Volatile (age={position_age_hours:.1f}h, profit={current_profit_pct:.1f}%)"
            return False, "Tier 1: Too soon"
        
        # === TIER 2: ESTABLISHED (Medium checks - give room to grow) ===
        # Age 1-4 hours AND profit 50-200%
        if position_age_hours < 4.0 and 50.0 <= current_profit_pct < 200.0:
            if time_since_last_check >= self.MEDIUM_INTERVAL:
                self.last_check[token] = now
                return True, f"Tier 2: Established (age={position_age_hours:.1f}h, profit={current_profit_pct:.1f}%)"
            return False, "Tier 2: Too soon"
        
        # === TIER 3: CONFIRMED MOONSHOT (Slow checks - let it pump for days) ===
        # Profit 200-500% OR age > 4 hours with profit > 100%
        if (200.0 <= current_profit_pct < 500.0) or \
           (position_age_hours > 4.0 and current_profit_pct > 100.0):
            if time_since_last_check >= self.SLOW_INTERVAL:
                self.last_check[token] = now
                return True, f"Tier 3: Moonshot (age={position_age_hours:.1f}h, profit={current_profit_pct:.1f}%)"
            return False, "Tier 3: Too soon"
        
        # === TIER 4: MEGA PUMPER (Ultra slow - multi-day hold) ===
        # Profit >= 500% - These are stable mooners, check every 4 hours
        if current_profit_pct >= 500.0:
            if time_since_last_check >= self.ULTRA_SLOW_INTERVAL:
                self.last_check[token] = now
                return True, f"Tier 4: Mega Pumper (age={position_age_hours:.1f}h, profit={current_profit_pct:.1f}%)"
            return False, "Tier 4: Too soon"
        
        # Default: Use medium interval
        if time_since_last_check >= self.MEDIUM_INTERVAL:
            self.last_check[token] = now
            return True, f"Default check (age={position_age_hours:.1f}h, profit={current_profit_pct:.1f}%)"
        
        return False, "Default: Too soon"
    
    def reset_position(self, token: str):
        """Remove position from tracking (after it's closed)"""
        if token in self.last_check:
            del self.last_check[token]
    
    def get_stats(self) -> Dict:
        """Get monitoring statistics"""
        return {
            "tracked_positions": len(self.last_check),
            "intervals": {
                "fast": f"{self.FAST_INTERVAL}s",
                "medium": f"{self.MEDIUM_INTERVAL/60:.0f}min",
                "slow": f"{self.SLOW_INTERVAL/3600:.0f}h",
                "ultra_slow": f"{self.ULTRA_SLOW_INTERVAL/3600:.0f}h"
            }
        }


