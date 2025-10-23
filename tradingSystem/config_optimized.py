"""
OPTIMIZED CONFIG - Based on PROVEN Performance Data
- 42% WR at 1.4x overall
- Score 8: 50% WR, 254% avg gain (BEST)
- Score 7: 50% WR, 68% avg gain  
- Smart Money: 57% WR, 99% avg gain
- 21% WR at 2x
- 96% avg gain overall
"""
import os


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# ==================== WALLET & EXECUTION ====================
RPC_URL = os.getenv("TS_RPC_URL", "https://api.mainnet-beta.solana.com")
WALLET_SECRET = os.getenv("TS_WALLET_SECRET", "")
SLIPPAGE_BPS = _get_int("TS_SLIPPAGE_BPS", 2000)  # 20.0% default per strategy
# Priority fee policy (free/low-cost): dynamic bump within [min,max]
# INCREASED from 5000 to 10000 min to improve transaction success rate
# Error 6024 often caused by low priority → transaction gets dropped
PRIORITY_FEE_MIN_MICROLAMPORTS = _get_int("TS_PRIORITY_FEE_MIN_MICROLAMPORTS", 10000)
PRIORITY_FEE_MAX_MICROLAMPORTS = _get_int("TS_PRIORITY_FEE_MAX_MICROLAMPORTS", 50000)
# Backward-compat constant if referenced elsewhere
PRIORITY_FEE_MICROLAMPORTS = PRIORITY_FEE_MAX_MICROLAMPORTS
MAX_SLIPPAGE_PCT = _get_float("TS_MAX_SLIPPAGE_PCT", 5.0)
# Separate price impact caps (per user decision): buys 25%, sells 50%
MAX_PRICE_IMPACT_BUY_PCT = _get_float("TS_MAX_PRICE_IMPACT_BUY_PCT", 25.0)
MAX_PRICE_IMPACT_SELL_PCT = _get_float("TS_MAX_PRICE_IMPACT_SELL_PCT", 50.0)
MAX_PRICE_IMPACT_PCT = MAX_PRICE_IMPACT_BUY_PCT  # backward-compat for older imports

# Base asset
SOL_MINT = os.getenv("TS_SOL_MINT", "So11111111111111111111111111111111111111112")
USDC_MINT = os.getenv("TS_USDC_MINT", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
BASE_MINT = os.getenv("TS_BASE_MINT", SOL_MINT)  # Buys funded by SOL
SELL_MINT = os.getenv("TS_SELL_MINT", SOL_MINT)  # Sells exit to SOL (user preference)

# ==================== RISK & POSITION SIZING ====================
# Based on proven performance: 42% WR overall, 50% WR for Score 8

# Dynamic wallet balance (DO NOT HARDCODE!)
# Default 20 is fallback only - system reads actual balance at runtime
BANKROLL_USD = _get_float("TS_BANKROLL_USD", 20)

# NOTE: Position sizing uses get_position_size() which will query actual balance
# This default is only used for circuit breaker calculations

MAX_CONCURRENT = _get_int("TS_MAX_CONCURRENT", 5)  # 5 positions max

# OPTIMIZED SIZING - Based on proven win rates by score
# Score 8: 50% WR, 254% avg gain = BEST (allocate most)
# Score 9: 33% WR, 37% avg gain = Good
# Score 7: 50% WR, 68% avg gain = Strong
# Smart Money: 57% WR = Premium multiplier

# Base sizes by conviction type (scaled for $20 bankroll)
SMART_MONEY_BASE = _get_float("TS_SMART_MONEY_BASE", 4.5)  # ~$4.50 per position
STRICT_BASE = _get_float("TS_STRICT_BASE", 4.0)  # ~$4.00 per position
GENERAL_BASE = _get_float("TS_GENERAL_BASE", 3.5)  # ~$3.50 per position

# Score multipliers (applied to base)
SCORE_10_MULT = _get_float("TS_SCORE_10_MULT", 1.2)  # 120%
SCORE_9_MULT = _get_float("TS_SCORE_9_MULT", 1.0)   # 100%
SCORE_8_MULT = _get_float("TS_SCORE_8_MULT", 1.3)   # 130% - BEST PERFORMER!
SCORE_7_MULT = _get_float("TS_SCORE_7_MULT", 0.9)   # 90%

# Max position size (safety) - Reduced for testing with small capital
MAX_POSITION_SIZE_PCT = _get_float("TS_MAX_POSITION_SIZE_PCT", 15.0)  # Max 15% of bankroll (was 20%)
MAX_POSITION_SIZE_USD = BANKROLL_USD * (MAX_POSITION_SIZE_PCT / 100.0)

# ==================== STOPS & TRAILS ====================
# Optimized for 96% avg gain and 42% WR

# Stop losses (from ENTRY price, not peak) - FIXED BUG
STOP_LOSS_PCT = _get_float("TS_STOP_LOSS_PCT", 15.0)  # -15% from entry for all

# Trailing stops - TIGHTENED based on live performance analysis
# OBSERVED: Signals peak at +60-200% but bot misses them with 15-20% trails
# NEW STRATEGY: Tighter trails (5-10%) to capture peaks before dumps
# Example: PING +60% → -1% because 20% trail never triggered
TRAIL_AGGRESSIVE = _get_float("TS_TRAIL_AGGRESSIVE", 5.0)  # For Score 9-10 (very tight)
TRAIL_DEFAULT = _get_float("TS_TRAIL_DEFAULT", 8.0)  # For Score 8 (tight)
TRAIL_CONSERVATIVE = _get_float("TS_TRAIL_CONSERVATIVE", 10.0)  # For Score 7 (moderate)

# ADAPTIVE TRAILING STOPS - NEW! Prevents selling late pumpers too early
ADAPTIVE_TRAILING_ENABLED = _get_bool("TS_ADAPTIVE_TRAILING_ENABLED", False)
EARLY_TRAIL_PCT = _get_float("TS_EARLY_TRAIL_PCT", 25.0)  # 0-30 min: Wide trail (let it run)
MID_TRAIL_PCT = _get_float("TS_MID_TRAIL_PCT", 15.0)      # 30-60 min: Standard trail
LATE_TRAIL_PCT = _get_float("TS_LATE_TRAIL_PCT", 12.0)    # 60+ min: Tight trail

# TIME-BASED EXIT - Automatically sell stagnant positions
# Prevents capital from being stuck in dead/inactive tokens
MAX_HOLD_TIME_SECONDS = _get_int("TS_MAX_HOLD_TIME_SEC", 3600)  # Default: 1 hour

# ==================== CIRCUIT BREAKERS ====================
# NEW: Protect against catastrophic losses
MAX_DAILY_LOSS_PCT = _get_float("TS_MAX_DAILY_LOSS_PCT", 20.0)  # Max 20% daily loss
MAX_CONSECUTIVE_LOSSES = _get_int("TS_MAX_CONSECUTIVE_LOSSES", 5)  # Pause after 5 losses

# ==================== ENTRY FILTERS ====================
# These are for additional validation beyond signal score
# Align with signal bot defaults to avoid integration mismatch

MIN_LIQUIDITY_USD = _get_float("TS_MIN_LIQUIDITY_USD", 30000)  # Must match signal bot filter!
MIN_VOLUME_RATIO = _get_float("TS_MIN_VOLUME_RATIO", 0.1)  # Vol/MC ratio min

# ==================== PATHS ====================
DB_PATH = os.getenv("TS_DB_PATH", "var/trading.db")
LOG_JSON_PATH = os.getenv("TS_LOG_JSON", "data/logs/trading.jsonl")
LOG_TEXT_PATH = os.getenv("TS_LOG_TEXT", "data/logs/trading.log")

# ==================== MODE ====================
DRY_RUN = _get_bool("TS_DRY_RUN", True)

# ==================== PORTFOLIO REBALANCING ====================
# "Circle Strategy" - Dynamic portfolio management
PORTFOLIO_REBALANCING_ENABLED = _get_bool("PORTFOLIO_REBALANCING_ENABLED", False)
PORTFOLIO_MAX_POSITIONS = _get_int("PORTFOLIO_MAX_POSITIONS", 5)  # Circle size
PORTFOLIO_MIN_MOMENTUM_ADVANTAGE = _get_float("PORTFOLIO_MIN_MOMENTUM_ADVANTAGE", 15.0)  # Minimum advantage to swap
PORTFOLIO_REBALANCE_COOLDOWN = _get_int("PORTFOLIO_REBALANCE_COOLDOWN", 300)  # 5 min between rebalances
PORTFOLIO_MIN_POSITION_AGE = _get_int("PORTFOLIO_MIN_POSITION_AGE", 600)  # 10 min before can be replaced


# ==================== HELPER FUNCTIONS ====================
def get_current_bankroll() -> float:
    """
    Get current wallet balance dynamically.
    Reads actual SOL+USDC balance instead of using hardcoded value.
    """
    # Try to read actual balance
    try:
        from .wallet_balance import get_wallet_balance_cached
        balance = get_wallet_balance_cached(RPC_URL, WALLET_SECRET, USDC_MINT)
        if balance > 0:
            return balance
    except Exception as e:
        print(f"[CONFIG] Could not read wallet balance: {e}, using env/default")
    
    # Fallback to configured value
    return BANKROLL_USD


def get_position_size(score: int, conviction_type: str) -> float:
    """
    Calculate optimal position size based on proven performance AND current balance.
    
    Based on actual data:
    - Score 8: 50% WR, 254% avg gain
    - Score 7: 50% WR, 68% avg gain
    - Score 9: 33% WR, 37% avg gain
    - Smart Money: 57% WR
    - Strict: 30% WR
    """
    # Get ACTUAL current bankroll (not hardcoded)
    current_bankroll = get_current_bankroll()
    
    # Calculate base percentage (not absolute USD)
    # This way it scales with balance automatically
    # TESTING MODE: Reduced to 10-12% for small balance testing
    # With $6 balance: $0.60-$0.72 per trade (safe for verification)
    # With $100 balance: $10-$12 per trade (scales up automatically)
    if "Smart Money" in conviction_type:
        base_pct = 12.0  # 12% of balance (was 22.5%)
    elif "Strict" in conviction_type:
        base_pct = 11.0  # 11% of balance (was 20%)
    else:
        base_pct = 10.0  # 10% of balance (was 17.5%)
    
    # Apply score multiplier
    if score >= 10:
        multiplier = SCORE_10_MULT
    elif score >= 9:
        multiplier = SCORE_9_MULT
    elif score >= 8:
        multiplier = SCORE_8_MULT  # Best performer!
    else:
        multiplier = SCORE_7_MULT
    
    # Calculate size as percentage of CURRENT balance
    size_pct = base_pct * multiplier
    size = current_bankroll * (size_pct / 100.0)
    
    # Kelly overlay as ceiling (using current bankroll)
    try:
        # Lazy import to avoid circulars at module import time
        from .strategy_optimized import get_expected_win_rate, get_expected_avg_gain, get_kelly_fraction
        win_rate = get_expected_win_rate(score, conviction_type)
        avg_gain = get_expected_avg_gain(score, conviction_type)
        kelly = get_kelly_fraction(win_rate, avg_gain)
        fractional_kelly = max(0.0, min(kelly * 0.25, 0.25))
        kelly_size = current_bankroll * fractional_kelly
        # Use the minimum of heuristic size and Kelly ceiling for safety
        size = min(size, kelly_size)
    except Exception:
        pass
    
    # Cap at max percentage of current balance
    max_size = current_bankroll * (MAX_POSITION_SIZE_PCT / 100.0)
    size = min(size, max_size)
    
    return size


def get_trailing_stop(score: int, momentum: float = 0.0, age_minutes: float = 0.0, pnl_percent: float = 0.0) -> float:
    """
    Get optimal trailing stop based on signal quality, momentum, age, and PnL.
    
    ADAPTIVE STRATEGY (when enabled):
    - Phase 1 (0-30 min): Wide trail (25%) - let winners run
    - Phase 2 (30-60 min): Standard trail (15%) - detect late pumpers
    - Phase 3 (60+ min): Tight trail (12%) - lock gains
    
    LATE PUMP DETECTION:
    - If PnL > 50% after 30 minutes = late pumper
    - Give extra room (20% trail) to capture full pump
    
    Args:
        score: Signal score (7-10)
        momentum: Current momentum score
        age_minutes: Position age in minutes
        pnl_percent: Current PnL percentage
    """
    if ADAPTIVE_TRAILING_ENABLED and age_minutes > 0:
        # Phase 1: Early hold (0-30 min) - WIDE trail
        if age_minutes < 30:
            if pnl_percent > 100:
                return 20.0  # Big winner early, give room
            elif pnl_percent > 50:
                return EARLY_TRAIL_PCT  # 25% - let it run
            else:
                return 30.0  # Very wide for development
        
        # Phase 2: Momentum check (30-60 min)
        elif age_minutes < 60:
            if pnl_percent > 50 and momentum > 20:
                # LATE PUMPER DETECTED!
                return 20.0  # Protect but give room
            elif pnl_percent > 20:
                return MID_TRAIL_PCT  # 15% - standard
            else:
                return 10.0  # Tight on weak positions
        
        # Phase 3: Late stage (60+ min)
        else:
            if pnl_percent > 100:
                return 15.0  # Lock in big gains
            elif pnl_percent > 50:
                return LATE_TRAIL_PCT  # 12% - tight
            else:
                return 10.0  # Very tight on weak
    
    # FALLBACK: Original logic (when adaptive disabled)
    if score >= 9 and momentum > 30.0:
        return TRAIL_AGGRESSIVE  # Lock gains on hot Score 9-10
    elif score >= 8:
        return TRAIL_DEFAULT  # Standard for Score 8 (best performer)
    else:
        return TRAIL_CONSERVATIVE  # More room for Score 7


# ==================== PERFORMANCE EXPECTATIONS ====================
"""
Based on verified data with 19 tracked signals:

Overall Expected Performance:
- Win Rate (1.2x+): 52.6%
- Win Rate (1.4x+): 42.1%
- Win Rate (2x+): 21.1%
- Win Rate (6x+): 5.3%
- Average Gain: 95.8%

By Score:
- Score 10: 0% WR (sample too small)
- Score 9: 33% WR, 37% avg gain
- Score 8: 50% WR, 254% avg gain ← PRIORITIZE
- Score 7: 50% WR, 68% avg gain

By Conviction:
- Smart Money: 57% WR, 99% avg gain ← PRIORITIZE
- Strict: 30% WR, 103% avg gain

Expected Monthly Performance (with 30 signals/day):
- Starting: $500
- Signals: ~900/month (focus on Score 8-9 = ~270 quality signals)
- Winners at 42% WR: ~113 winners
- Average gain: 96%
- With compounding: $500 → $700-800 Month 1 (+40-60%)

Risk Management:
- Circuit breaker prevents >20% daily loss
- Stop losses limit individual losses to -15%
- Max 5 concurrent positions
- Trailing stops capture 60-70% of peaks
"""

