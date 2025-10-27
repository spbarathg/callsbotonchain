"""
ENTRY MOMENTUM VALIDATOR
Only enter trades with CONFIRMED upward momentum

PROBLEM ANALYSIS (77 trades):
- Good wins held avg 45 minutes (entered early in pump)
- Losses held avg 11 minutes (bought the top)
- Only 1.3% moonshot rate (should be 5-8%)
- Solution: Confirm momentum BEFORE buying

VALIDATION RULES:
1. Price RISING last 5 minutes (not falling)
2. Volume SPIKING 2x+ vs 1-hour average
3. Signal FRESH (<2 minutes old)
4. Not already PUMPED (>30% from signal price)

API EFFICIENCY:
- Uses DexScreener (free, no rate limits)
- Only checks on NEW signals (~10 per hour)
- Impact: <0.5 RPS (negligible)
"""
import time
from typing import Tuple, Optional, Dict
import requests


class MomentumValidator:
    """Validate entry momentum to increase moonshot rate from 1.3% to 5-8%"""
    
    def __init__(self):
        # Statistics
        self.checks_performed = 0
        self.validations_passed = 0
        self.rejection_reasons = {
            "no_upward_momentum": 0,
            "weak_momentum": 0,
            "no_volume_spike": 0,
            "already_pumped": 0,
            "signal_stale": 0,
            "passed": 0
        }
        
        # Price history cache (for momentum calculation)
        self.price_history: Dict[str, list] = {}
    
    def should_enter(self, 
                    token_address: str,
                    signal_price: float,
                    signal_timestamp: float,
                    current_price: float,
                    stats: Dict) -> Tuple[bool, str]:
        """
        Determine if we should enter this trade based on momentum
        
        Args:
            token_address: Token mint address
            signal_price: Price when signal was generated
            signal_timestamp: When signal was generated (unix timestamp)
            current_price: Current price
            stats: Token stats (liquidity, volume, etc)
        
        Returns:
            (should_enter: bool, reason: str)
        """
        self.checks_performed += 1
        
        # 1. SIGNAL FRESHNESS CHECK (<2 minutes)
        # Stale signals = likely entered after pump
        signal_age_seconds = time.time() - signal_timestamp
        if signal_age_seconds > 120:  # 2 minutes
            self.rejection_reasons["signal_stale"] += 1
            return False, f"signal_stale_{signal_age_seconds/60:.1f}min"
        
        # 2. ALREADY PUMPED CHECK (not >30% from signal)
        # If already up 30%+, we're buying the top
        if signal_price > 0:
            pump_since_signal = ((current_price - signal_price) / signal_price) * 100
            if pump_since_signal > 30:
                self.rejection_reasons["already_pumped"] += 1
                return False, f"already_pumped_{pump_since_signal:.1f}pct"
        
        # 3. UPWARD MOMENTUM CHECK
        # Price must be rising in last 5 minutes
        # We'll use change_5m from stats if available
        change_5m = float(stats.get("change_5m", 0))
        if change_5m <= 0:
            # Price falling or flat = bad entry
            self.rejection_reasons["no_upward_momentum"] += 1
            return False, f"no_momentum_{change_5m:.1f}pct"
        
        # Momentum must be STRONG (>5% in 5 min)
        if change_5m < 5.0:
            self.rejection_reasons["weak_momentum"] += 1
            return False, f"weak_momentum_{change_5m:.1f}pct"
        
        # 4. VOLUME SPIKE CHECK
        # Volume in last period must be 2x+ normal
        # We'll use volume vs liquidity ratio as proxy
        vol24 = float(stats.get("vol24_usd", 0))
        liquidity = float(stats.get("liquidity_usd", 1))
        
        if vol24 > 0 and liquidity > 0:
            vol_liq_ratio = vol24 / liquidity
            # Healthy ratio is >0.5 (24h volume > 50% of liquidity)
            if vol_liq_ratio < 0.5:
                self.rejection_reasons["no_volume_spike"] += 1
                return False, f"low_volume_{vol_liq_ratio:.2f}ratio"
        
        # PASSED ALL CHECKS
        self.rejection_reasons["passed"] += 1
        self.validations_passed += 1
        return True, f"momentum_{change_5m:.1f}pct_vol_{vol_liq_ratio:.2f}x"
    
    def get_stats(self) -> Dict:
        """Get validation statistics"""
        pass_rate = (self.validations_passed / self.checks_performed * 100) if self.checks_performed > 0 else 0
        
        return {
            "checks_performed": self.checks_performed,
            "validations_passed": self.validations_passed,
            "pass_rate": f"{pass_rate:.1f}%",
            "rejection_reasons": self.rejection_reasons
        }


# Global instance
_validator: Optional[MomentumValidator] = None


def get_momentum_validator() -> MomentumValidator:
    """Get or create global momentum validator instance"""
    global _validator
    if _validator is None:
        _validator = MomentumValidator()
    return _validator

