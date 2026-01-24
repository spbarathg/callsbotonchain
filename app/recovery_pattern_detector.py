"""
RECOVERY PATTERN DETECTOR
Detects "dip and rip" patterns in memecoins

PATTERN REQUIREMENTS:
1. Token hits ATH (all-time high)
2. Market cap at ATH: aligned with MIN/MAX market cap filters
3. Drops 30%+ from ATH
4. Recovers to ATH + 10% in minimum 5 candles
5. Signal when recovery completes

WHY THIS WORKS:
- Shakes out weak hands (30% dip)
- Proves strength (recovers + extra)
- Momentum confirmed (5+ candles = sustained)
- Market cap stays aligned with your configured filters

Example:
- ATH: $100K mcap
- Drops to: $60K (-40%)
- Recovers to: $110K (+10% above ATH)
- Takes 5+ candles
- → SIGNAL!
"""
import time
from typing import Dict, List, Optional, Tuple
from collections import deque
from dataclasses import dataclass
import threading

from app.config_unified import MIN_MARKET_CAP_USD, MAX_MARKET_CAP_USD


@dataclass
class Candle:
    """Price candle data"""
    timestamp: float
    market_cap: float
    price: float
    volume: float


@dataclass
class RecoveryPattern:
    """Detected recovery pattern"""
    token: str
    ath_mcap: float
    ath_time: float
    drop_mcap: float
    drop_percent: float
    recovery_mcap: float
    recovery_candles: int
    detection_time: float


class RecoveryPatternDetector:
    """
    Detects "dip and rip" recovery patterns in real-time
    
    Tracks price history and identifies strong recovery signals
    """
    
    def __init__(self):
        # Configuration - align with main signal filters
        self.MIN_MCAP = MIN_MARKET_CAP_USD
        self.MAX_MCAP = MAX_MARKET_CAP_USD
        self.MIN_DROP_PCT = 30.0  # Must drop at least 30%
        self.RECOVERY_BONUS_PCT = 10.0  # Must recover to ATH + 10%
        self.MIN_RECOVERY_CANDLES = 5  # Minimum candles for recovery
        
        # Candle settings
        self.CANDLE_DURATION_SEC = 60  # 1-minute candles
        self.MAX_CANDLES = 100  # Track last 100 candles
        
        # Tracking data
        self.token_candles: Dict[str, deque] = {}  # token -> deque of Candles
        self.token_ath: Dict[str, Tuple[float, float]] = {}  # token -> (ath_mcap, ath_time)
        self.detected_patterns: Dict[str, RecoveryPattern] = {}  # token -> pattern
        self.pattern_cooldown: Dict[str, float] = {}  # token -> last_detection_time
        
        # State tracking for recovery detection
        self.recovery_state: Dict[str, Dict] = {}  # token -> state dict
        
        # Lock for thread safety
        self.lock = threading.Lock()
        
        # Stats
        self.patterns_detected = 0
        self.tokens_tracked = 0
        self.candles_processed = 0
        
        # Cooldown to prevent duplicate signals
        self.PATTERN_COOLDOWN_SEC = 3600  # 1 hour cooldown per token
    
    def add_price_data(self, token: str, market_cap: float, price: float, volume: float = 0):
        """
        Add new price data for a token
        
        Args:
            token: Token address
            market_cap: Current market cap in USD
            price: Current price in USD
            volume: Current volume (optional)
        """
        with self.lock:
            now = time.time()
            
            # Initialize tracking for new token
            if token not in self.token_candles:
                self.token_candles[token] = deque(maxlen=self.MAX_CANDLES)
                self.token_ath[token] = (market_cap, now)
                self.recovery_state[token] = {
                    "in_drop": False,
                    "in_recovery": False,
                    "drop_start_candle": None,
                    "recovery_start_candle": None,
                    "ath_mcap": market_cap,
                    "ath_time": now,
                    "drop_low_mcap": market_cap,
                    "recovery_candle_count": 0
                }
                self.tokens_tracked += 1
            
            # Create new candle
            candle = Candle(
                timestamp=now,
                market_cap=market_cap,
                price=price,
                volume=volume
            )
            
            # Add to history
            self.token_candles[token].append(candle)
            self.candles_processed += 1
            
            # Update ATH if applicable
            current_ath_mcap, current_ath_time = self.token_ath[token]
            if market_cap > current_ath_mcap:
                # DON'T reset recovery if we're currently recovering
                # (exceeding old ATH during recovery is good! That's the goal!)
                if not self.recovery_state[token]["in_recovery"]:
                    self.token_ath[token] = (market_cap, now)
                    self.recovery_state[token]["ath_mcap"] = market_cap
                    self.recovery_state[token]["ath_time"] = now
                    # Reset recovery tracking on new ATH (only if not currently recovering)
                    self.recovery_state[token]["in_drop"] = False
                    self.recovery_state[token]["in_recovery"] = False
            
            # Check for pattern
            pattern = self._check_pattern(token)
            if pattern:
                self.detected_patterns[token] = pattern
                self.pattern_cooldown[token] = now
                self.patterns_detected += 1
                return pattern
            
            return None
    
    def _check_pattern(self, token: str) -> Optional[RecoveryPattern]:
        """
        Check if token has completed a recovery pattern
        
        Returns:
            RecoveryPattern if detected, None otherwise
        """
        # Get data
        candles = self.token_candles[token]
        if len(candles) < self.MIN_RECOVERY_CANDLES + 1:
            return None  # Not enough data
        
        state = self.recovery_state[token]
        ath_mcap = state["ath_mcap"]
        ath_time = state["ath_time"]
        
        current_candle = candles[-1]
        current_mcap = current_candle.market_cap
        
        # Check cooldown (don't signal same token repeatedly)
        if token in self.pattern_cooldown:
            last_detection = self.pattern_cooldown[token]
            if time.time() - last_detection < self.PATTERN_COOLDOWN_SEC:
                return None
        
        # Filter 1: Market cap range at ATH
        if not (self.MIN_MCAP <= ath_mcap <= self.MAX_MCAP):
            return None
        
        # Filter 2: Current market cap still in range
        if current_mcap > self.MAX_MCAP:
            return None
        
        # Calculate drop from ATH
        drop_pct = ((ath_mcap - current_mcap) / ath_mcap) * 100 if ath_mcap > 0 else 0
        
        # STATE MACHINE: Track drop → recovery progression
        
        # State 1: Detect significant drop from ATH
        if not state["in_drop"] and not state["in_recovery"]:
            if drop_pct >= self.MIN_DROP_PCT:
                # Entered drop phase
                state["in_drop"] = True
                state["drop_start_candle"] = len(candles) - 1
                state["drop_low_mcap"] = current_mcap
                # print(f"[RECOVERY] {token[:8]}... entered drop phase: -{drop_pct:.1f}% from ATH", flush=True)
        
        # State 2: Track lowest point during drop
        if state["in_drop"] and not state["in_recovery"]:
            if current_mcap < state["drop_low_mcap"]:
                state["drop_low_mcap"] = current_mcap
            
            # Check if starting to recover (crossed 80% of the way back to ATH)
            recovery_threshold = state["drop_low_mcap"] + (ath_mcap - state["drop_low_mcap"]) * 0.8
            if current_mcap >= recovery_threshold:
                # Start tracking recovery
                state["in_recovery"] = True
                state["recovery_start_candle"] = len(candles) - 1
                state["recovery_candle_count"] = 1
                print(f"[RECOVERY] {token[:8]}... recovery started: ${current_mcap:,.0f} (target: ${ath_mcap * 1.1:,.0f})", flush=True)
        
        # State 3: Track recovery progression
        if state["in_recovery"]:
            recovery_target = ath_mcap * (1 + self.RECOVERY_BONUS_PCT / 100)
            
            # Count candles in recovery
            recovery_start_idx = state["recovery_start_candle"]
            current_idx = len(candles) - 1
            candles_in_recovery = current_idx - recovery_start_idx + 1
            
            # Check if recovery failed (dropped back below 70% recovery threshold)
            recovery_threshold = state["drop_low_mcap"] + (ath_mcap - state["drop_low_mcap"]) * 0.7
            if current_mcap < recovery_threshold:
                # Recovery failed, reset
                state["in_drop"] = False
                state["in_recovery"] = False
                state["recovery_candle_count"] = 0
                print(f"[RECOVERY] {token[:8]}... recovery failed (dropped to ${current_mcap:,.0f}), reset", flush=True)
                return None
            
            # Check if recovery completed (with small epsilon for floating point comparison)
            EPSILON = 0.01  # $0.01 tolerance for floating point errors
            
            if current_mcap >= (recovery_target - EPSILON) and candles_in_recovery >= self.MIN_RECOVERY_CANDLES:
                # PATTERN DETECTED!
                drop_pct_from_ath = ((ath_mcap - state["drop_low_mcap"]) / ath_mcap) * 100
                
                pattern = RecoveryPattern(
                    token=token,
                    ath_mcap=ath_mcap,
                    ath_time=ath_time,
                    drop_mcap=state["drop_low_mcap"],
                    drop_percent=drop_pct_from_ath,
                    recovery_mcap=current_mcap,
                    recovery_candles=candles_in_recovery,
                    detection_time=time.time()
                )
                
                # Reset state for next pattern
                state["in_drop"] = False
                state["in_recovery"] = False
                state["recovery_candle_count"] = 0
                # Update ATH to current (since we exceeded it)
                state["ath_mcap"] = current_mcap
                state["ath_time"] = time.time()
                self.token_ath[token] = (current_mcap, time.time())
                
                print(f"[RECOVERY] *** PATTERN DETECTED: {token[:8]}...", flush=True)
                print(f"[RECOVERY]   ATH: ${ath_mcap:,.0f} -> Drop: ${state['drop_low_mcap']:,.0f} (-{drop_pct_from_ath:.1f}%)", flush=True)
                print(f"[RECOVERY]   Recovery: ${current_mcap:,.0f} (+{((current_mcap-ath_mcap)/ath_mcap)*100:.1f}% above ATH)", flush=True)
                print(f"[RECOVERY]   Candles: {candles_in_recovery} (min: {self.MIN_RECOVERY_CANDLES})", flush=True)
                
                return pattern
        
        return None
    
    def is_pattern_detected(self, token: str, max_age_sec: int = 300) -> bool:
        """
        Check if a recovery pattern was recently detected for this token
        
        Args:
            token: Token address
            max_age_sec: Maximum age of pattern in seconds (default 5 minutes)
        
        Returns:
            True if pattern detected recently
        """
        with self.lock:
            if token not in self.detected_patterns:
                return False
            
            pattern = self.detected_patterns[token]
            age = time.time() - pattern.detection_time
            
            return age <= max_age_sec
    
    def get_pattern(self, token: str) -> Optional[RecoveryPattern]:
        """Get detected pattern for a token"""
        with self.lock:
            return self.detected_patterns.get(token)
    
    def get_stats(self) -> Dict:
        """Get detector statistics"""
        with self.lock:
            return {
                "patterns_detected": self.patterns_detected,
                "tokens_tracked": self.tokens_tracked,
                "candles_processed": self.candles_processed,
                "active_patterns": len(self.detected_patterns),
                "detection_rate": f"{self.patterns_detected/max(self.tokens_tracked, 1)*100:.1f}%"
            }
    
    def cleanup_old_patterns(self, max_age_sec: int = 3600):
        """Remove old patterns to free memory"""
        with self.lock:
            now = time.time()
            to_remove = [
                token for token, pattern in self.detected_patterns.items()
                if now - pattern.detection_time > max_age_sec
            ]
            for token in to_remove:
                del self.detected_patterns[token]


# Global singleton
_detector: Optional[RecoveryPatternDetector] = None


def get_recovery_detector() -> RecoveryPatternDetector:
    """Get or create global recovery pattern detector"""
    global _detector
    if _detector is None:
        _detector = RecoveryPatternDetector()
    return _detector


def add_token_data(token: str, market_cap: float, price: float, volume: float = 0) -> Optional[RecoveryPattern]:
    """
    Convenience function to add token data and check for pattern
    
    Returns:
        RecoveryPattern if detected, None otherwise
    """
    detector = get_recovery_detector()
    return detector.add_price_data(token, market_cap, price, volume)


def is_recovery_signal(token: str, max_age_sec: int = 300) -> bool:
    """
    Check if token has a recent recovery pattern signal
    
    Use this in your signal scoring to boost tokens with recovery patterns
    """
    detector = get_recovery_detector()
    return detector.is_pattern_detected(token, max_age_sec)

