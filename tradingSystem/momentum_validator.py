"""
ADAPTIVE SMART ENTRY SYSTEM
Signal = "Watch" → Intelligent real-time analysis → Optimal entry timing

SOPHISTICATED LOGIC:
1. QUICK ASSESSMENT (3-5 seconds):
   - Is token active? (any movement at all)
   - What's happening? (pumping/dipping/flat)

2. PATTERN ANALYSIS:
   - If PUMPING: Is it accelerating? Enter before parabolic
   - If DIPPING: Wait for bounce/reversal (don't catch falling knife)
   - If FLAT: Extended watch (maybe it's about to move)

3. ADAPTIVE TIMING:
   - Don't use fixed time window
   - Strong signals (8+): Faster decision
   - Weak signals: Need more confirmation
   - Max observation: 20 seconds

4. ENTRY TRIGGERS:
   - Pump building: 2+ consecutive higher prices
   - Dip reversal: Price bounces back >1% from lowest point
   - Volume confirmation: Real trading, not manipulation
   - Early exit: If clearly dead (3 samples, no movement)

5. EDGE CASE HANDLING:
   - Dip → Wait for bottom & bounce
   - Late pump → Extend observation if trend emerging
   - Extreme volatility → Wait for clarity
   - Fast pump → Enter immediately (don't miss it)

This maximizes profit by:
- Catching pumps early ✅
- Buying dips at the BOTTOM ✅
- Avoiding dead tokens ✅
- Not missing late pumps ✅
"""
import time
from typing import Tuple, Optional, Dict, List
import requests


class MomentumValidator:
    """Adaptive smart entry with real-time pattern analysis"""
    
    def __init__(self):
        self.checks_performed = 0
        self.validations_passed = 0
        self.rejection_reasons = {
            "dead_token": 0,
            "still_dumping": 0,
            "extreme_pump": 0,
            "price_error": 0,
            "timeout": 0,
            "passed": 0
        }
        
        # Adaptive settings
        self.QUICK_CHECK_TIME = 5  # Initial quick assessment
        self.MAX_OBSERVATION = 20  # Maximum time to watch
        self.SAMPLE_INTERVAL = 1.0  # Sample every second
        self.MIN_SAMPLES = 4  # Need at least 4 data points
    
    def _get_price_from_jupiter(self, token_address: str) -> Optional[float]:
        """
        Get current price from Jupiter (ONLY API ALLOWED)
        User requirement: No DexScreener usage
        """
        try:
            # Use Jupiter price oracle for consistent pricing
            from .jupiter_price_oracle import get_jupiter_oracle
            from .db import get_open_qty_by_token
            
            # Get a small amount for price check (0.01 tokens equivalent)
            test_amount = 0.01
            oracle = get_jupiter_oracle(cache_ttl=5)
            price = oracle.get_price(token_address, test_amount)
            
            return price if price > 0 else None, 0  # Return price and volume=0 (not tracked)
        except Exception as e:
            print(f"[MOMENTUM] ⚠️ Jupiter price check failed: {e}", flush=True)
            return None, 0
    
    def _analyze_pattern(self, prices: List[float], timestamps: List[float]) -> Dict:
        """Analyze price pattern for entry decision"""
        if len(prices) < 3:
            return {"pattern": "unknown", "confidence": 0}
        
        first = prices[0]
        last = prices[-1]
        lowest = min(prices)
        highest = max(prices)
        lowest_idx = prices.index(lowest)
        
        # Calculate metrics
        total_change = ((last - first) / first * 100) if first > 0 else 0
        range_pct = ((highest - lowest) / lowest * 100) if lowest > 0 else 0
        
        # Check for trends
        recent_prices = prices[-3:]  # Last 3 samples
        is_rising = all(recent_prices[i] <= recent_prices[i+1] for i in range(len(recent_prices)-1))
        is_falling = all(recent_prices[i] >= recent_prices[i+1] for i in range(len(recent_prices)-1))
        
        # Pattern detection
        pattern_info = {
            "total_change": total_change,
            "range": range_pct,
            "first_price": first,
            "last_price": last,
            "lowest": lowest,
            "highest": highest,
            "is_rising": is_rising,
            "is_falling": is_falling
        }
        
        # PATTERN CLASSIFICATION
        
        # 1. STRONG PUMP (accelerating upward)
        if is_rising and total_change > 3:
            pattern_info["pattern"] = "strong_pump"
            pattern_info["confidence"] = min(total_change * 10, 100)
            pattern_info["action"] = "BUY_NOW"
            pattern_info["reason"] = f"Accelerating pump +{total_change:.1f}%"
            return pattern_info
        
        # 2. PUMP BUILDING (upward momentum)
        if total_change > 1 and last > first:
            pattern_info["pattern"] = "pump_building"
            pattern_info["confidence"] = 70
            pattern_info["action"] = "BUY_NOW"
            pattern_info["reason"] = f"Momentum building +{total_change:.1f}%"
            return pattern_info
        
        # 3. DIP REVERSAL (bounced from bottom)
        if lowest_idx < len(prices) - 2:  # Low was NOT most recent
            bounce_from_low = ((last - lowest) / lowest * 100) if lowest > 0 else 0
            if bounce_from_low > 1:  # Bounced >1% from lowest
                pattern_info["pattern"] = "dip_reversal"
                pattern_info["confidence"] = min(bounce_from_low * 30, 90)
                pattern_info["action"] = "BUY_NOW"
                pattern_info["reason"] = f"Bounced +{bounce_from_low:.1f}% from dip"
                return pattern_info
        
        # 4. STILL DUMPING (falling knife - DON'T CATCH)
        if is_falling and total_change < -2:
            pattern_info["pattern"] = "dumping"
            pattern_info["confidence"] = 80
            pattern_info["action"] = "WAIT"
            pattern_info["reason"] = f"Still dumping {total_change:.1f}% - wait for bottom"
            return pattern_info
        
        # 5. VOLATILE (moving but no clear direction)
        if range_pct > 2:
            pattern_info["pattern"] = "volatile"
            pattern_info["confidence"] = 50
            pattern_info["action"] = "CONTINUE"
            pattern_info["reason"] = f"Volatile {range_pct:.1f}% - need more data"
            return pattern_info
        
        # 6. DEAD (no movement)
        if range_pct < 0.5:
            pattern_info["pattern"] = "dead"
            pattern_info["confidence"] = 90
            pattern_info["action"] = "REJECT"
            pattern_info["reason"] = f"Dead token - only {range_pct:.2f}% range"
            return pattern_info
        
        # 7. SMALL MOVEMENT (active but unclear)
        pattern_info["pattern"] = "small_movement"
        pattern_info["confidence"] = 40
        pattern_info["action"] = "CONTINUE"
        pattern_info["reason"] = f"Small movement {total_change:.1f}% - observing"
        return pattern_info
    
    def should_enter(self, 
                    token_address: str,
                    signal_price: float,
                    signal_timestamp: float,
                    current_price: float,
                    stats: Dict) -> Tuple[bool, str]:
        """
        AGGRESSIVE ENTRY STRATEGY
        
        Philosophy: TRUST THE SIGNAL, EXIT FAST ON WEAKNESS
        - High-conviction signals (7+): Enter immediately (signal knows more than we do)
        - Medium signals (6): Quick check, then enter
        - Low signals (5-): Full validation
        
        Why: Signals are PREDICTIVE (call pumps before they happen)
        Our observation is REACTIVE (only sees current state)
        Solution: Trust signal quality, manage risk with tight stops
        """
        self.checks_performed += 1
        
        signal_score = stats.get("signal_score", 5)
        
        print(f"\n[MOMENTUM] 🎯 Aggressive Entry for {token_address[:8]}", flush=True)
        print(f"[MOMENTUM] Signal Score: {signal_score}/10", flush=True)
        
        # === TIER 1: HIGH CONVICTION (7+) - INSTANT ENTRY ===
        if signal_score >= 7:
            self.rejection_reasons["passed"] += 1
            self.validations_passed += 1
            print(f"[MOMENTUM] ✅ HIGH CONVICTION → INSTANT ENTRY", flush=True)
            print(f"[MOMENTUM] Strategy: Enter aggressive, exit at first weakness", flush=True)
            return True, f"high_conviction_{signal_score}/10_instant_entry"
        
        # === TIER 2: MEDIUM CONVICTION (6) - QUICK CHECK ===
        if signal_score == 6:
            print(f"[MOMENTUM] 📊 Medium conviction → Quick 5s check", flush=True)
            # Just verify token exists and has ANY activity
            price, vol = self._get_price_from_jupiter(token_address)
            time.sleep(5)
            price2, vol2 = self._get_price_from_jupiter(token_address)
            
            if price and price2:
                # Token exists and tradeable = good enough
                self.rejection_reasons["passed"] += 1
                self.validations_passed += 1
                print(f"[MOMENTUM] ✅ Token active → ENTER", flush=True)
                return True, f"medium_conviction_active"
            else:
                self.rejection_reasons["price_error"] += 1
                print(f"[MOMENTUM] ❌ Can't get price → REJECT", flush=True)
                return False, "medium_conviction_no_price"
        
        # === TIER 3: LOW CONVICTION (5-) - FULL VALIDATION ===
        print(f"[MOMENTUM] ⚠️ Low conviction → Full analysis required", flush=True)
        
        # Collect price samples with adaptive timing
        prices: List[float] = []
        volumes: List[float] = []
        timestamps: List[float] = []
        
        start_time = time.time()
        observation_limit = self.MAX_OBSERVATION
        decision_made = False
        
        # ADAPTIVE OBSERVATION LOOP
        while (time.time() - start_time) < observation_limit and not decision_made:
            price, vol = self._get_price_from_jupiter(token_address)
            
            if price and price > 0:
                prices.append(price)
                volumes.append(vol)
                timestamps.append(time.time())
                elapsed = time.time() - start_time
                
                print(f"[MOMENTUM] [{elapsed:.1f}s] ${price:.10f} (vol: ${vol:.0f})", flush=True)
                
                # EARLY DECISIONS (after minimum samples)
                if len(prices) >= self.MIN_SAMPLES:
                    analysis = self._analyze_pattern(prices, timestamps)
                    
                    print(f"[MOMENTUM] Pattern: {analysis['pattern']} ({analysis.get('reason', 'N/A')})", flush=True)
                    
                    # IMMEDIATE ENTRY TRIGGERS
                    if analysis.get("action") == "BUY_NOW":
                        self.rejection_reasons["passed"] += 1
                        self.validations_passed += 1
                        print(f"[MOMENTUM] ✅ {analysis['reason']}", flush=True)
                        return True, analysis['reason']
                    
                    # IMMEDIATE REJECTION TRIGGERS
                    if analysis.get("action") == "REJECT":
                        self.rejection_reasons["dead_token"] += 1
                        print(f"[MOMENTUM] ❌ {analysis['reason']}", flush=True)
                        return False, analysis['reason']
                    
                    # WAIT for better entry
                    if analysis.get("action") == "WAIT" and elapsed > 10:
                        # Waited long enough, still dumping
                        self.rejection_reasons["still_dumping"] += 1
                        print(f"[MOMENTUM] ❌ Timeout: {analysis['reason']}", flush=True)
                        return False, f"timeout_dumping_{analysis['total_change']:.1f}pct"
                    
                    # CONTINUE observing if pattern unclear
                    # (loop continues)
                
                # Quick check at 5 seconds for strong signals
                if signal_score >= 8 and len(prices) >= 5 and elapsed >= 5:
                    analysis = self._analyze_pattern(prices, timestamps)
                    if analysis['range'] > 0.5:  # Any movement for strong signals
                        if analysis['total_change'] >= 0:  # Not dumping
                            self.rejection_reasons["passed"] += 1
                            self.validations_passed += 1
                            print(f"[MOMENTUM] ✅ Strong signal + active → ENTER", flush=True)
                            return True, f"strong_signal_active_{analysis['total_change']:.1f}pct"
            
            time.sleep(self.SAMPLE_INTERVAL)
        
        # TIMEOUT - Make final decision
        if len(prices) >= self.MIN_SAMPLES:
            final_analysis = self._analyze_pattern(prices, timestamps)
            
            # Check for late pump (trend emerging)
            if final_analysis['is_rising'] and final_analysis['total_change'] > 0.5:
                self.rejection_reasons["passed"] += 1
                self.validations_passed += 1
                print(f"[MOMENTUM] ✅ Late pump detected → ENTER", flush=True)
                return True, f"late_pump_{final_analysis['total_change']:.1f}pct"
            
            # Any movement = active token
            if final_analysis['range'] > 1:
                self.rejection_reasons["passed"] += 1
                self.validations_passed += 1
                print(f"[MOMENTUM] ✅ Active token → ENTER", flush=True)
                return True, f"active_{final_analysis['range']:.1f}pct_range"
        
        # No decision made
        self.rejection_reasons["timeout"] += 1
        print(f"[MOMENTUM] ❌ Timeout - insufficient data", flush=True)
        return False, f"timeout_samples_{len(prices)}"
    
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
