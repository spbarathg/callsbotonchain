"""
BULLETPROOF STRATEGY - Comprehensive input validation and error handling
"""
from typing import Optional, Dict
import math
from .config import (
    CORE_SIZE_USD, SCOUT_SIZE_USD, STRICT_SIZE_USD, NUANCED_SIZE_USD,
    MIN_LP_USD, RATIO_MIN, MCAP_MAX, MOMENTUM_1H_GATE,
    TRAIL_DEFAULT_PCT, TRAIL_TIGHT_PCT, TRAIL_WIDE_PCT,
    STRICT_MIN_LP_USD, STRICT_RATIO_MIN, STRICT_MCAP_MAX,
    NUANCED_MIN_LP_USD, NUANCED_RATIO_MIN, NUANCED_MCAP_MAX,
    BANKROLL_USD,
)


def _safe_float(value, default: float = 0.0) -> float:
    """Safely convert to float with validation"""
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _validate_stats(stats: Optional[Dict]) -> bool:
    """Validate stats dict has required fields"""
    if not stats or not isinstance(stats, dict):
        return False
    
    # Required fields
    required = ["liquidity_usd", "market_cap_usd", "ratio"]
    for field in required:
        if field not in stats:
            return False
        val = _safe_float(stats.get(field))
        if val <= 0:
            return False
    
    return True


def decide_runner(stats: Dict[str, float], is_smart: bool) -> Optional[Dict]:
    """Strict + Smart path with comprehensive validation"""
    # Input validation
    if not _validate_stats(stats):
        return None
    
    if not is_smart:
        return None
    
    # Safe extraction
    liq = _safe_float(stats.get("liquidity_usd"))
    ratio = _safe_float(stats.get("ratio"))
    mcap = _safe_float(stats.get("market_cap_usd"))
    ch1 = _safe_float(stats.get("change_1h"))
    
    # Entry gates
    if liq < MIN_LP_USD:
        return None
    if ratio < RATIO_MIN:
        return None
    if not (mcap <= MCAP_MAX or ch1 >= MOMENTUM_1H_GATE):
        return None
    
    # Dynamic trailing based on conditions
    trail = TRAIL_DEFAULT_PCT
    if ch1 >= 35.0 and ratio >= 0.7:
        trail = TRAIL_TIGHT_PCT
    elif ratio >= 1.0 and -5.0 <= ch1 <= 10.0:
        trail = TRAIL_WIDE_PCT
    
    # Validate position size doesn't exceed bankroll
    size = min(CORE_SIZE_USD, BANKROLL_USD * 0.25)  # Max 25% of bankroll per position
    
    return {
        "strategy": "runner",
        "usd_size": size,
        "trail_pct": trail,
    }


def decide_scout(stats: Dict[str, float]) -> Optional[Dict]:
    """High-velocity scout path with validation"""
    if not _validate_stats(stats):
        return None
    
    liq = _safe_float(stats.get("liquidity_usd"))
    ratio = _safe_float(stats.get("ratio"))
    mcap = _safe_float(stats.get("market_cap_usd"))
    ch1 = _safe_float(stats.get("change_1h"))
    vel = _safe_float(stats.get("vel_score"))
    unique = _safe_float(stats.get("unique_traders_15m"))
    
    if liq < MIN_LP_USD:
        return None
    
    # Velocity route
    if (vel >= 8 and unique >= 25 and ratio >= 0.8 and mcap <= 1_200_000) or (
        ch1 >= 25 and ratio >= 0.7 and mcap <= 1_000_000
    ):
        size = min(SCOUT_SIZE_USD, BANKROLL_USD * 0.20)  # Max 20% per position
        return {
            "strategy": "scout",
            "usd_size": size,
            "trail_pct": TRAIL_TIGHT_PCT,
        }
    return None


def decide_strict(stats: Dict[str, float]) -> Optional[Dict]:
    """High Confidence (Strict) with validation"""
    if not _validate_stats(stats):
        return None
    
    liq = _safe_float(stats.get("liquidity_usd"))
    ratio = _safe_float(stats.get("ratio"))
    mcap = _safe_float(stats.get("market_cap_usd"))
    ch1 = _safe_float(stats.get("change_1h"))
    final_score = int(_safe_float(stats.get("final_score"), 5))
    
    # Entry gates (slightly relaxed)
    if liq < STRICT_MIN_LP_USD:
        return None
    if ratio < STRICT_RATIO_MIN:
        return None
    if mcap > STRICT_MCAP_MAX and ch1 < MOMENTUM_1H_GATE:
        return None
    
    # Score-based sizing with validation
    size = STRICT_SIZE_USD
    if final_score >= 8:
        size = STRICT_SIZE_USD * 1.5  # 150% for excellent signals
    elif final_score <= 5:
        size = STRICT_SIZE_USD * 0.75  # 75% for marginal signals
    
    # Cap at 25% of bankroll
    size = min(size, BANKROLL_USD * 0.25)
    
    # Dynamic trailing based on momentum
    trail = TRAIL_DEFAULT_PCT
    if ch1 >= 30.0 and ratio >= 0.6:
        trail = TRAIL_TIGHT_PCT  # Lock gains on hot movers
    elif ratio >= 0.8 and 0 <= ch1 <= 15.0:
        trail = TRAIL_WIDE_PCT  # Give room for consolidation
    
    return {
        "strategy": "strict",
        "usd_size": size,
        "trail_pct": trail,
    }


def decide_nuanced(stats: Dict[str, float]) -> Optional[Dict]:
    """Nuanced Conviction with validation"""
    if not _validate_stats(stats):
        return None
    
    liq = _safe_float(stats.get("liquidity_usd"))
    ratio = _safe_float(stats.get("ratio"))
    mcap = _safe_float(stats.get("market_cap_usd"))
    ch1 = _safe_float(stats.get("change_1h"))
    vel = _safe_float(stats.get("vel_score"))
    unique = _safe_float(stats.get("unique_traders_15m"))
    
    # Stricter gates for nuanced signals
    if liq < NUANCED_MIN_LP_USD:
        return None
    if ratio < NUANCED_RATIO_MIN:
        return None
    if mcap > NUANCED_MCAP_MAX:
        return None
    
    # Only take nuanced if velocity OR momentum is exceptional
    has_velocity = vel >= 9 and unique >= 30
    has_momentum = ch1 >= 35 and ratio >= 0.8
    
    if not (has_velocity or has_momentum):
        return None
    
    size = min(NUANCED_SIZE_USD, BANKROLL_USD * 0.15)  # Max 15% per position
    
    return {
        "strategy": "nuanced",
        "usd_size": size,
        "trail_pct": TRAIL_TIGHT_PCT,  # Always tight for risky plays
    }

