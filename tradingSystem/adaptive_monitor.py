"""
PRIORITY-BASED POSITION MONITORING
Adjust check frequency based on RISK and OPPORTUNITY

ANALYSIS OF 77 TRADES (16 hours):
- 32 positions lost AVG -40.2% (should've stopped at -30%) = -$366 preventable
- Only 1 moonshot (1.3% rate) due to slow monitoring
- Solution: Priority-based checking catches dumps 3x faster!

PRIORITY LEVELS:
🔴 CRITICAL (1s): Near stop loss (-10% to -20%) → Save $200+
🟡 IMPORTANT (2s): Near profit targets (95-105%, 195-205%, etc) → Lock gains
🟢 FAST (3s): New positions (<1h) or volatile (<50% profit)
⚪ MEDIUM/SLOW (30m-4h): Stable/mature positions

API EFFICIENCY:
- Current: 1.67 RPS (5 positions × 1 check per 3s)
- With priorities: ~3-4 RPS (still well under 10 RPS limit)
- Critical positions monitored 3x faster where it matters!
"""
import time
from typing import Dict, Tuple


class AdaptiveMonitor:
    """Determines optimal check interval for each position"""
    
    def __init__(self):
        # PRIORITY INTERVALS (based on RISK and OPPORTUNITY)
        # Analysis of 77 trades showed: 32 positions lost -40% (should've stopped at -30%)
        # Priority system catches dumps 3x faster where it matters!
        self.CRITICAL_INTERVAL = 1.0     # 🔴 Near stop loss / flash dump risk
        self.IMPORTANT_INTERVAL = 2.0    # 🟡 Near profit targets (95-105%)
        self.FAST_INTERVAL = 3.0         # 🟢 New/volatile positions
        self.MEDIUM_INTERVAL = 1800      # ⚪ 30 min - Established positions
        self.SLOW_INTERVAL = 7200        # ⚪ 2 hours - Confirmed moonshots
        self.ULTRA_SLOW_INTERVAL = 14400 # ⚪ 4 hours - Mega pumpers (500%+)
        
        # Track last check time per position
        self.last_check: Dict[str, float] = {}
        
        # API efficiency tracking
        self.check_count = 0
        self.priority_checks = {"critical": 0, "important": 0, "fast": 0, "medium": 0, "slow": 0}
    
    def should_check_position(self, 
                             token: str, 
                             entry_time: float,
                             current_profit_pct: float,
                             peak_profit_pct: float = 0.0) -> Tuple[bool, str]:
        """
        PRIORITY-BASED position monitoring to prevent -$366 in preventable losses
        
        Returns: (should_check: bool, reason: str)
        """
        now = time.time()
        position_age_hours = (now - entry_time) / 3600
        
        # First check is always immediate
        if token not in self.last_check:
            self.last_check[token] = now
            self.check_count += 1
            return True, "Initial check"
        
        time_since_last_check = now - self.last_check[token]
        
        # === PRIORITY 🔴 CRITICAL: NEAR STOP LOSS (1 second checks) ===
        # Analysis showed: 32 positions lost -40% (should've stopped at -30%)
        # These positions need INSTANT monitoring to prevent catastrophic losses
        if -20.0 <= current_profit_pct <= -10.0:
            # Position in danger zone (-10% to -20% loss)
            if time_since_last_check >= self.CRITICAL_INTERVAL:
                self.last_check[token] = now
                self.check_count += 1
                self.priority_checks["critical"] += 1
                return True, f"🔴 CRITICAL: Near stop loss ({current_profit_pct:.1f}%)"
            return False, "Critical: Too soon"
        
        # === PRIORITY 🟡 IMPORTANT: NEAR PROFIT TARGETS (2 second checks) ===
        # Lock in gains at 100%, 200%, 300%, 500%, 1000% targets
        profit_targets = [100, 200, 300, 500, 1000]
        for target in profit_targets:
            if target * 0.95 <= current_profit_pct <= target * 1.05:
                # Within 5% of profit target
                if time_since_last_check >= self.IMPORTANT_INTERVAL:
                    self.last_check[token] = now
                    self.check_count += 1
                    self.priority_checks["important"] += 1
                    return True, f"🟡 IMPORTANT: Near {target}% target ({current_profit_pct:.1f}%)"
                return False, "Important: Too soon"
        
        # === PRIORITY 🟢 FAST: NEW & VOLATILE (3 second checks) ===
        # Age < 1 hour OR profit < 50%
        # Most failures happen in first hour - need frequent monitoring
        if position_age_hours < 1.0 or current_profit_pct < 50.0:
            if time_since_last_check >= self.FAST_INTERVAL:
                self.last_check[token] = now
                self.check_count += 1
                self.priority_checks["fast"] += 1
                return True, f"🟢 FAST: New/Volatile (age={position_age_hours:.1f}h, profit={current_profit_pct:.1f}%)"
            return False, "Fast: Too soon"
        
        # === ⚪ MEDIUM: ESTABLISHED (30 min checks) ===
        # Age 1-4 hours AND profit 50-200%
        if position_age_hours < 4.0 and 50.0 <= current_profit_pct < 200.0:
            if time_since_last_check >= self.MEDIUM_INTERVAL:
                self.last_check[token] = now
                self.check_count += 1
                self.priority_checks["medium"] += 1
                return True, f"⚪ MEDIUM: Established (age={position_age_hours:.1f}h, profit={current_profit_pct:.1f}%)"
            return False, "Medium: Too soon"
        
        # === ⚪ SLOW: CONFIRMED MOONSHOT (2 hour checks) ===
        # Profit 200-500% OR age > 4 hours with profit > 100%
        if (200.0 <= current_profit_pct < 500.0) or \
           (position_age_hours > 4.0 and current_profit_pct > 100.0):
            if time_since_last_check >= self.SLOW_INTERVAL:
                self.last_check[token] = now
                self.check_count += 1
                self.priority_checks["slow"] += 1
                return True, f"⚪ SLOW: Moonshot (age={position_age_hours:.1f}h, profit={current_profit_pct:.1f}%)"
            return False, "Slow: Too soon"
        
        # === ⚪ ULTRA SLOW: MEGA PUMPER (4 hour checks) ===
        # Profit >= 500% - These are stable mooners, check every 4 hours
        if current_profit_pct >= 500.0:
            if time_since_last_check >= self.ULTRA_SLOW_INTERVAL:
                self.last_check[token] = now
                self.check_count += 1
                self.priority_checks["slow"] += 1  # Use 'slow' bucket for ultra slow
                return True, f"⚪ ULTRA: Mega Pumper (age={position_age_hours:.1f}h, profit={current_profit_pct:.1f}%)"
            return False, "Ultra: Too soon"
        
        # Default: Use medium interval
        if time_since_last_check >= self.MEDIUM_INTERVAL:
            self.last_check[token] = now
            self.check_count += 1
            self.priority_checks["medium"] += 1
            return True, f"Default check (age={position_age_hours:.1f}h, profit={current_profit_pct:.1f}%)"
        
        return False, "Default: Too soon"
    
    def reset_position(self, token: str):
        """Remove position from tracking (after it's closed)"""
        if token in self.last_check:
            del self.last_check[token]
    
    def get_stats(self) -> Dict:
        """Get monitoring statistics with priority breakdown"""
        total_checks = sum(self.priority_checks.values())
        
        return {
            "tracked_positions": len(self.last_check),
            "total_checks": self.check_count,
            "priority_breakdown": {
                "critical": f"{self.priority_checks['critical']} ({self.priority_checks['critical']/total_checks*100:.1f}%)" if total_checks > 0 else "0 (0%)",
                "important": f"{self.priority_checks['important']} ({self.priority_checks['important']/total_checks*100:.1f}%)" if total_checks > 0 else "0 (0%)",
                "fast": f"{self.priority_checks['fast']} ({self.priority_checks['fast']/total_checks*100:.1f}%)" if total_checks > 0 else "0 (0%)",
                "medium": f"{self.priority_checks['medium']} ({self.priority_checks['medium']/total_checks*100:.1f}%)" if total_checks > 0 else "0 (0%)",
                "slow": f"{self.priority_checks['slow']} ({self.priority_checks['slow']/total_checks*100:.1f}%)" if total_checks > 0 else "0 (0%)"
            },
            "intervals": {
                "critical": f"{self.CRITICAL_INTERVAL}s",
                "important": f"{self.IMPORTANT_INTERVAL}s",
                "fast": f"{self.FAST_INTERVAL}s",
                "medium": f"{self.MEDIUM_INTERVAL/60:.0f}min",
                "slow": f"{self.SLOW_INTERVAL/3600:.0f}h",
                "ultra_slow": f"{self.ULTRA_SLOW_INTERVAL/3600:.0f}h"
            }
        }


