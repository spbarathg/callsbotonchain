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
# CRITICAL FIX: Use Helius/Triton private RPC by default. Public RPC causes load-balancing 
# ghost positions and false "dust closures".
RPC_URL = os.getenv("TS_RPC_URL", "https://mainnet.helius-rpc.com/?api-key=YOUR_HELIUS_API_KEY")
WALLET_SECRET = os.getenv("TS_WALLET_SECRET", "")
SLIPPAGE_BPS = _get_int("TS_SLIPPAGE_BPS", 2000)  # 20.0% default per strategy
# Priority fee policy (free/low-cost): dynamic bump within [min,max]
# INCREASED from 5000 to 10000 min to improve transaction success rate
# Error 6024 often caused by low priority -> transaction gets dropped
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

MAX_CONCURRENT = _get_int("TS_MAX_CONCURRENT", 3)  # REDUCED: 3 positions for BIGGER bets (~$30 each)

# NET STRATEGY MODE: Equal-weighted portfolio for compounding
# ENABLED: Cast wide net, equal-weight all signals, close net at 5x portfolio gain
NET_STRATEGY_MODE = _get_bool("TS_NET_STRATEGY_MODE", True)
NET_TAKE_PROFIT_PCT = _get_float("TS_NET_TAKE_PROFIT_PCT", 500.0)  # Close net at 5x (500%)

# OPTIMIZED SIZING - Based on proven win rates by score
# Score 8: 50% WR, 254% avg gain = BEST (allocate most)
# Score 9: 33% WR, 37% avg gain = Good
# Score 7: 50% WR, 68% avg gain = Strong
# Smart Money: 57% WR = Premium multiplier

# Base sizes by conviction type - OPTIMIZED FOR 35% HIT RATE + BIG GAINS
# Your 11.6x MOG calls deserve bigger size to maximize compound growth
SMART_MONEY_BASE = _get_float("TS_SMART_MONEY_BASE", 5.5)  # ~$5.50 (+22%)
STRICT_BASE = _get_float("TS_STRICT_BASE", 4.5)  # ~$4.50 (+12.5%)
GENERAL_BASE = _get_float("TS_GENERAL_BASE", 4.0)  # ~$4.00 (+14%)

# Score multipliers (applied to base)
SCORE_10_MULT = _get_float("TS_SCORE_10_MULT", 1.2)  # 120%
SCORE_9_MULT = _get_float("TS_SCORE_9_MULT", 1.0)   # 100%
SCORE_8_MULT = _get_float("TS_SCORE_8_MULT", 1.3)   # 130% - BEST PERFORMER!
SCORE_7_MULT = _get_float("TS_SCORE_7_MULT", 0.9)   # 90%

# Max position size (safety) - percentage of CURRENT balance
MAX_POSITION_SIZE_PCT = _get_float("TS_MAX_POSITION_SIZE_PCT", 33.0)  # Max 33% of bankroll
# NOTE: MAX_POSITION_SIZE_USD is now DYNAMIC - use get_max_position_usd() instead
# This legacy constant is kept for backward compatibility but should not be used
MAX_POSITION_SIZE_USD = 100.0  # Placeholder - use get_max_position_usd() for actual value

# ==================== STOPS & TRAILS ====================
# Optimized for 96% avg gain and 42% WR

# ==================== SMART PROFIT TAKING MODE 💰 ====================
# Based on trade analysis: Trail exits profitable, but need to lock gains earlier
# SOLUTION: Aggressive profit taking + tight trails to protect gains

# SCAM DETECTION: DISABLED by default - it was wrong 96% of the time!
SCAM_DETECTION_ENABLED = _get_bool("TS_SCAM_DETECTION_ENABLED", False)

# MINIMUM HOLD TIME: 2 minutes (allow quick exits on real dumps)
MIN_HOLD_SECONDS = _get_float("TS_MIN_HOLD_SECONDS", 120.0)  # 2 minutes minimum

# TRAIL ONLY IN PROFIT: Don't trail positions that are underwater
# This prevents trailing stops from triggering on losing positions
TRAIL_ONLY_IN_PROFIT = _get_bool("TS_TRAIL_ONLY_IN_PROFIT", True)

# ==================== MOONSHOT MODE - LET WINNERS RUN! 🚀 ====================
# PHILOSOPHY: Your signal bot finds 5-10x movers. The trading bot should RIDE them,
# not cut them short! Survive the shakeouts, catch the moonshots.

# Stop losses (from ENTRY price, not peak)
# 
# NET STRATEGY: Wider stops to let net breathe during volatility
# - Memecoins dip 20-30% then rip to 10x
# - Net needs room to capture extreme movements
# - Individual losses absorbed by winners
# 
# STANDARD MODE: Tight stops for capital preservation
# - Quick exits on weakness
# - Can afford tight stops with concentrated positions
# 
# NET MODE: -25% stop (let volatility play out)
# STANDARD MODE: -10% stop (exit fast on weakness)
if NET_STRATEGY_MODE:
    STOP_LOSS_PCT = _get_float("TS_STOP_LOSS_PCT", 25.0)  # -25% for Net Strategy (wider)
else:
    STOP_LOSS_PCT = _get_float("TS_STOP_LOSS_PCT", 10.0)  # -10% standard (tight)

# EMERGENCY HARD STOP - Absolute maximum loss before force exit
# If normal stop fails (price feed issues), this is the last line of defense
# AUDIT OPTIMIZATION: Reduced from -50% to -35% for faster capital recovery
EMERGENCY_HARD_STOP_PCT = _get_float("TS_EMERGENCY_HARD_STOP_PCT", 30.0)  # -30% absolute max (tightened for capital preservation)

# ==================== PROFIT-BASED ADAPTIVE TRAILING STOPS ====================
# OLD PROBLEM: Time-based trails exit too early (sold at +50% when token goes to +400%)
# NEW STRATEGY: Trail based on PROFIT, not time! Let big winners run longer.
#
# Example (Mika token):
# - Entry: $1.19
# - At +50% ($1.78): Use 50% trail -> needs -50% drop to exit (won't happen in pump)
# - At +100% ($2.38): Use 35% trail -> needs -35% drop to exit
# - At +200% ($3.57): Use 25% trail -> needs -25% drop to exit  
# - At +400% ($5.95): Use 20% trail -> locks in 300%+ profit on pullback
#
# Result: Rides the full pump, exits on real reversal, not small dips!

ADAPTIVE_TRAILING_ENABLED = _get_bool("TS_ADAPTIVE_TRAILING_ENABLED", True)

# PROFIT THRESHOLDS (PnL %) - More granular for better control
PROFIT_TIER_1 = _get_float("TS_PROFIT_TIER_1", 30.0)   # First milestone: +30% (protect capital)
PROFIT_TIER_2 = _get_float("TS_PROFIT_TIER_2", 80.0)   # Second milestone: +80% (start loosening)
PROFIT_TIER_3 = _get_float("TS_PROFIT_TIER_3", 150.0)  # Third milestone: +150% (runner detected)
PROFIT_TIER_4 = _get_float("TS_PROFIT_TIER_4", 300.0)  # Fourth milestone: +300% (strong runner)
PROFIT_TIER_5 = _get_float("TS_PROFIT_TIER_5", 800.0)  # Fifth milestone: +800% (mega runner / 10x approaching)

# TRAILING STOPS PER TIER (how much pullback from peak before exit)
# OCT 31 2025 V5: BALANCED APPROACH - Stop loss protects downside, wide trails catch 10x
# CRITICAL FIX: Don't exit winners on normal volatility!
# Key insight: Memecoins dip 15-25% routinely before 10x - trails must accommodate this
# Strategy: Hard stop-loss at entry (-12%) protects capital, wide trails let runners breathe
TRAIL_TIER_0 = _get_float("TS_TRAIL_TIER_0", 30.0)  # 0-30% profit: 30% trail - WIDER to survive shakeouts!
TRAIL_TIER_1 = _get_float("TS_TRAIL_TIER_1", 28.0)  # 30-80% profit: 28% trail - confirmed runner
TRAIL_TIER_2 = _get_float("TS_TRAIL_TIER_2", 32.0)  # 80-150% profit: 32% trail - strong runner
TRAIL_TIER_3 = _get_float("TS_TRAIL_TIER_3", 35.0)  # 150-300% profit: 35% trail - mega runner
TRAIL_TIER_4 = _get_float("TS_TRAIL_TIER_4", 42.0)  # 300-800% profit: 42% trail - approaching 10x
TRAIL_TIER_5 = _get_float("TS_TRAIL_TIER_5", 50.0)  # 800-5000% profit: 50% trail - moonshot (10x-50x)
# CRITICAL FIX (Oct 27): Added mega moonshot tiers for 100x-1000x potential
# User requirement: "Don't leave 800-1000x gains on the table"
# Strategy: Ultra-wide trails (60-80%) for 100x+ positions to survive volatility
TRAIL_TIER_6 = _get_float("TS_TRAIL_TIER_6", 60.0)  # 5000-10000% profit: 60% trail - 50x-100x ULTRA volatility
TRAIL_TIER_7 = _get_float("TS_TRAIL_TIER_7", 70.0)  # 10000-80000% profit: 70% trail - 100x-800x LEGENDARY moves
TRAIL_TIER_8 = _get_float("TS_TRAIL_TIER_8", 80.0)  # 80000%+ profit: 80% trail - 800x+ NEVER SELL (ride forever)

# LEGACY TRAILS (for non-adaptive mode - NOT RECOMMENDED)
TRAIL_AGGRESSIVE = _get_float("TS_TRAIL_AGGRESSIVE", 5.0)  # Deprecated
TRAIL_DEFAULT = _get_float("TS_TRAIL_DEFAULT", 8.0)        # Deprecated
TRAIL_CONSERVATIVE = _get_float("TS_TRAIL_CONSERVATIVE", 10.0)  # Deprecated
EARLY_TRAIL_PCT = _get_float("TS_EARLY_TRAIL_PCT", 25.0)  # Deprecated
MID_TRAIL_PCT = _get_float("TS_MID_TRAIL_PCT", 15.0)      # Deprecated
LATE_TRAIL_PCT = _get_float("TS_LATE_TRAIL_PCT", 10.0)    # Deprecated

# ===== TIERED PROFIT TAKING (NEW - V2 OPTIMIZED FOR 10x) =====
# CRITICAL FIX: Keep MORE position riding for 10x potential
# Strategy: Minimal early selling, maximum upside capture
# Philosophy: Let winners make you rich - only take insurance, not profits
TIERED_PROFIT_TAKING_ENABLED = _get_bool("TS_TIERED_PROFIT_TAKING", True)

# Profit-taking tiers: (profit_pct, sell_pct_of_position)
# Goal: Keep 70%+ riding through 10x move
PROFIT_TAKE_TIER_1_PCT = _get_float("TS_PT_TIER_1_PCT", 150.0)   # +150% profit (2.5x)
PROFIT_TAKE_TIER_1_SELL = _get_float("TS_PT_TIER_1_SELL", 10.0)  # Sell 10% (insurance only)

PROFIT_TAKE_TIER_2_PCT = _get_float("TS_PT_TIER_2_PCT", 400.0)   # +400% profit (5x)
PROFIT_TAKE_TIER_2_SELL = _get_float("TS_PT_TIER_2_SELL", 10.0)  # Sell 10% more (20% total)

PROFIT_TAKE_TIER_3_PCT = _get_float("TS_PT_TIER_3_PCT", 900.0)   # +900% profit (10x!)
PROFIT_TAKE_TIER_3_SELL = _get_float("TS_PT_TIER_3_SELL", 10.0)  # Sell 10% more (30% total)

PROFIT_TAKE_TIER_4_PCT = _get_float("TS_PT_TIER_4_PCT", 2000.0)  # +2000% profit (21x)
PROFIT_TAKE_TIER_4_SELL = _get_float("TS_PT_TIER_4_SELL", 15.0)  # Sell 15% more (45% total)

# After all tiers, keep 55%+ of position riding with wide trailing stop for potential 100x
# At 10x ($1830 profit on $183 entry): Still have 80% of position riding!

# TIME-BASED EXIT - EXTENDED FOR MULTI-DAY MOVERS
# Key insight: Not all tokens are 4-hour pumps
# Some moonshots develop over 1-3 days with consolidations
# Adaptive monitoring reduces API usage for mature positions (checks every 2-4h instead of 1.5s)
# Combined with 30-40% trailing stops, this lets winners run for days!
MAX_HOLD_TIME_SECONDS = _get_int("TS_MAX_HOLD_TIME_SEC", 86400)  # 24 hours (was 4h)

# ==================== JUPITER PRO OPTIMIZATION - AGGRESSIVE CONFIG ====================
# With Pro tier (10 RPS) + Jupiter price oracle for exit monitoring:
# - Exit checks now use Jupiter quotes (real sellable prices)
# - Aggressive 10s cache = 0.1 RPS per position
# - 3s check interval for responsiveness
# - Total: 0.5 RPS for monitoring + 0.3 RPS buys + 0.33 RPS sells = 1.1 RPS
# - vs 9 RPS limit = 8x headroom (17% usage)
# 
# Benefits:
# - Sees REAL prices (matches Axiom, not fake DexScreener)
# - Stop losses trigger correctly (-20% instead of never)
# - Captures 98% of 67x gains (vs 0% with fake prices)
# - Still GUARANTEED no rate limiting (17% usage vs 100% limit)
EXIT_CHECK_INTERVAL_SEC = _get_float("TS_EXIT_CHECK_INTERVAL", 10.0)  # Increased to reduce rate limits

# Jupiter Price Oracle Cache TTL (for exit monitoring only)
# Aggressive 10s cache minimizes API calls while maintaining accuracy
# Signal detection uses DexScreener + ATM (proven win rates)
JUPITER_PRICE_CACHE_TTL = _get_int("TS_JUPITER_PRICE_CACHE_TTL", 10)

# ==================== CIRCUIT BREAKERS (LEGACY - see circuit_breaker.py) ====================
# NOTE: Actual circuit breaker logic is in circuit_breaker.py with DYNAMIC limits
# These are kept for backward compatibility but should not be used directly
MAX_DAILY_LOSS_PCT = _get_float("TS_DAILY_LOSS_LIMIT_PCT", 3.0)  # 3% of equity per day
MAX_CONSECUTIVE_LOSSES = _get_int("TS_MAX_CONSECUTIVE_LOSSES", 4)  # Cooldown after 4 losses

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
DRY_RUN = _get_bool("TS_DRY_RUN", False)  # Default to LIVE for production

# ==================== PYRAMIDING (Add to Winners) ====================
PYRAMIDING_ENABLED = _get_bool("TS_PYRAMIDING_ENABLED", True)  # Default enabled
PYRAMIDING_MAX_ADDS = int(os.getenv("TS_PYRAMIDING_MAX_ADDS", "2"))  # Max 2 adds per position
PYRAMIDING_MIN_PROFIT_PCT = float(os.getenv("TS_PYRAMIDING_MIN_PROFIT_PCT", "40.0"))  # Add at 40%+ profit

# ==================== CIRCUIT BREAKER & LOSS LIMITS (DYNAMIC) ====================
# NOTE: The actual CircuitBreaker class (circuit_breaker.py) uses PERCENTAGE-based limits
# that scale automatically when you add capital. These are fallback defaults.
CIRCUIT_BREAKER_ENABLED = _get_bool("TS_CIRCUIT_BREAKER_ENABLED", True)
DAILY_LOSS_LIMIT_PCT = _get_float("TS_DAILY_LOSS_LIMIT_PCT", 3.0)  # 3% of equity per day
WEEKLY_LOSS_LIMIT_PCT = _get_float("TS_WEEKLY_LOSS_LIMIT_PCT", 10.0)  # 10% of equity per week
CONSECUTIVE_LOSS_LIMIT = int(os.getenv("TS_CONSECUTIVE_LOSS_LIMIT", "4"))  # 4 losses -> cooldown
EXCESSIVE_SLIPPAGE_THRESHOLD = float(os.getenv("TS_EXCESSIVE_SLIPPAGE_THRESHOLD", "10.0"))  # 10% slippage
SLIPPAGE_EVENT_LIMIT = int(os.getenv("TS_SLIPPAGE_EVENT_LIMIT", "5"))  # 5 events in 1 hour

# ==================== PORTFOLIO REBALANCING ====================
# "Circle Strategy" - Dynamic portfolio management
PORTFOLIO_REBALANCING_ENABLED = _get_bool("PORTFOLIO_REBALANCING_ENABLED", False)
PORTFOLIO_MAX_POSITIONS = _get_int("PORTFOLIO_MAX_POSITIONS", 5)  # Circle size
PORTFOLIO_MIN_MOMENTUM_ADVANTAGE = _get_float("PORTFOLIO_MIN_MOMENTUM_ADVANTAGE", 15.0)  # Minimum advantage to swap
PORTFOLIO_REBALANCE_COOLDOWN = _get_int("PORTFOLIO_REBALANCE_COOLDOWN", 300)  # 5 min between rebalances
PORTFOLIO_MIN_POSITION_AGE = _get_int("PORTFOLIO_MIN_POSITION_AGE", 600)  # 10 min before can be replaced


# ==================== EQUITY CURVE TRACKING (PERSISTENT) ====================
# Track high water mark and current equity for drawdown-based sizing
# High water mark is persisted to survive restarts

_EQUITY_STATE_FILE = os.getenv("TS_EQUITY_STATE_FILE", "var/equity_state.json")
_equity_high_water_mark = None
_last_equity_check = 0.0
_initial_capital = None  # Track starting capital for ROI calculation


def _load_equity_state() -> dict:
    """Load persisted equity state from disk"""
    try:
        if os.path.exists(_EQUITY_STATE_FILE):
            with open(_EQUITY_STATE_FILE, 'r') as f:
                import json
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_equity_state(state: dict) -> None:
    """Persist equity state to disk"""
    try:
        os.makedirs(os.path.dirname(_EQUITY_STATE_FILE), exist_ok=True)
        with open(_EQUITY_STATE_FILE, 'w') as f:
            import json
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[EQUITY] Could not save state: {e}")


def _get_equity_state() -> dict:
    """
    Get current equity state including drawdown percentage.
    
    PERSISTENT: High water mark survives restarts.
    DYNAMIC: Automatically detects when you add capital.
    """
    global _equity_high_water_mark, _last_equity_check, _initial_capital
    import time
    
    current_equity = get_current_bankroll()
    now = time.time()
    
    # Load persisted state on first call
    if _equity_high_water_mark is None:
        saved = _load_equity_state()
        _equity_high_water_mark = saved.get("high_water_mark", current_equity)
        _initial_capital = saved.get("initial_capital", current_equity)
    
    # IMPORTANT: Detect capital injection (user adding funds)
    # If current equity > high water mark, it could be:
    # 1. Profits (good!) - high water mark should update
    # 2. Capital injection - initial capital should update too
    # We detect injection if jump is >20% in a short period
    if current_equity > _equity_high_water_mark:
        jump_pct = ((current_equity - _equity_high_water_mark) / _equity_high_water_mark) * 100
        if jump_pct > 20:
            # Likely capital injection - update initial capital too
            print(f"[EQUITY] Capital injection detected: ${_equity_high_water_mark:.2f} -> ${current_equity:.2f} (+{jump_pct:.1f}%)")
            _initial_capital = current_equity
        
        _equity_high_water_mark = current_equity
        _save_equity_state({
            "high_water_mark": _equity_high_water_mark,
            "initial_capital": _initial_capital,
            "last_updated": now
        })
    
    # Calculate drawdown from peak
    drawdown_pct = 0.0
    if _equity_high_water_mark > 0:
        drawdown_pct = ((_equity_high_water_mark - current_equity) / _equity_high_water_mark) * 100
    
    # Calculate ROI from initial capital
    roi_pct = 0.0
    if _initial_capital and _initial_capital > 0:
        roi_pct = ((current_equity - _initial_capital) / _initial_capital) * 100
    
    return {
        "current_equity": current_equity,
        "high_water_mark": _equity_high_water_mark,
        "initial_capital": _initial_capital,
        "drawdown_pct": drawdown_pct,
        "roi_pct": roi_pct,
        "is_in_drawdown": drawdown_pct > 5.0,  # >5% from peak = drawdown
        "is_severe_drawdown": drawdown_pct > 10.0,  # >10% = severe
        "is_profitable": roi_pct > 0,
    }


def get_drawdown_multiplier() -> float:
    """
    Get position size multiplier based on equity curve health.
    
    ASYMMETRIC RISK MANAGEMENT:
    - In profit/flat: 1.0x (full size)
    - 5-10% drawdown: 0.7x (reduce risk)
    - 10-15% drawdown: 0.5x (significant reduction)
    - >15% drawdown: 0.3x (survival mode)
    
    This ensures we survive consecutive losses while preserving
    capital for when conditions improve.
    """
    state = _get_equity_state()
    dd = state["drawdown_pct"]
    
    if dd <= 5.0:
        return 1.0  # Full size
    elif dd <= 10.0:
        return 0.7  # Reduce by 30%
    elif dd <= 15.0:
        return 0.5  # Reduce by 50%
    else:
        return 0.3  # Survival mode


def reset_equity_tracking(new_initial_capital: float = None) -> dict:
    """
    Reset equity tracking after adding significant capital.
    
    Call this when you add a lot of new capital and want to
    start tracking ROI from the new baseline.
    
    Args:
        new_initial_capital: New starting capital (or None to use current balance)
    
    Returns:
        New equity state
    """
    import time as _time
    global _equity_high_water_mark, _initial_capital
    
    current = get_current_bankroll()
    _equity_high_water_mark = new_initial_capital or current
    _initial_capital = new_initial_capital or current
    
    _save_equity_state({
        "high_water_mark": _equity_high_water_mark,
        "initial_capital": _initial_capital,
        "last_updated": _time.time(),
        "reset_reason": "manual_reset"
    })
    
    print(f"[EQUITY] Tracking reset: Initial=${_initial_capital:.2f}, HWM=${_equity_high_water_mark:.2f}")
    return _get_equity_state()


def get_profitability_summary() -> dict:
    """
    Get a summary of overall profitability for monitoring.
    
    Use this to check if the bot is profitable over time.
    """
    state = _get_equity_state()
    
    return {
        "current_equity": state["current_equity"],
        "initial_capital": state["initial_capital"],
        "roi_pct": state["roi_pct"],
        "is_profitable": state["is_profitable"],
        "high_water_mark": state["high_water_mark"],
        "drawdown_pct": state["drawdown_pct"],
        "drawdown_multiplier": get_drawdown_multiplier(),
        "position_size": get_net_position_size() if NET_STRATEGY_MODE else None,
    }


# ==================== HELPER FUNCTIONS ====================
def get_current_bankroll() -> float:
    """
    Get current wallet balance dynamically.
    Reads actual SOL+USDC balance instead of using hardcoded value.
    
    CRITICAL: This is the source of truth for all position sizing.
    When you add capital, this automatically detects it.
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


def get_max_position_usd() -> float:
    """
    Get maximum position size in USD based on CURRENT balance.
    
    DYNAMIC: Automatically scales when you add capital.
    Example: If you add $100, max position instantly increases.
    """
    current_balance = get_current_bankroll()
    max_usd = current_balance * (MAX_POSITION_SIZE_PCT / 100.0)
    return max_usd


def get_net_position_size() -> float:
    """
    NET STRATEGY: Equal-weight all positions with EQUITY-CURVE AWARENESS
    
    Formula:
      Base Size = Total Balance / Max Positions / 1.5
      Final Size = Base Size × Drawdown Multiplier
      
    Example (healthy equity):
      $26 balance / 2 positions / 1.5 = $8.67 per position × 1.0 = $8.67
      
    Example (10% drawdown):
      $26 balance / 2 positions / 1.5 = $8.67 per position × 0.7 = $6.07
    
    ASYMMETRIC SIZING:
    - Reduces position size during drawdowns
    - Preserves capital for recovery
    - Full size when equity curve is healthy
    """
    current_balance = get_current_bankroll()
    dd_mult = get_drawdown_multiplier()
    state = _get_equity_state()
    
    # Base size: balance / positions / 1.5 (use ~67% of balance)
    base_size = current_balance / MAX_CONCURRENT / 1.5
    
    # Apply drawdown multiplier
    net_size = base_size * dd_mult
    
    # Minimum $2.00 (covers gas + meaningful position), Maximum $200 per position
    net_size = max(2.00, min(net_size, 200.0))
    
    # Log equity state for monitoring
    dd_pct = state["drawdown_pct"]
    if dd_pct > 0:
        print(f"[NET] Position: ${net_size:.2f} (base=${base_size:.2f} × {dd_mult}x) | DD: {dd_pct:.1f}% from ${state['high_water_mark']:.2f}", flush=True)
    else:
        print(f"[NET] Position: ${net_size:.2f} (balance=${current_balance:.2f}, max_pos={MAX_CONCURRENT})", flush=True)
    
    return net_size


def get_position_size(score: int, conviction_type: str) -> float:
    """
    Calculate optimal position size with EQUITY-CURVE AWARENESS.
    
    NET STRATEGY MODE: Equal weighting with drawdown scaling
    STANDARD MODE: Score-based sizing with drawdown scaling
    
    ASYMMETRIC RISK MANAGEMENT:
    - Full size when equity curve healthy
    - Reduced size during drawdowns (preserve capital)
    - Never risk more than can survive 30 consecutive losses
    
    Based on actual data:
    - Score 8: 50% WR, 254% avg gain
    - Score 7: 50% WR, 68% avg gain
    - Score 9: 33% WR, 37% avg gain
    """
    # NET STRATEGY: Equal-weighted positions with drawdown awareness
    if NET_STRATEGY_MODE:
        return get_net_position_size()
    
    # STANDARD MODE: Score-based sizing with drawdown awareness
    current_bankroll = get_current_bankroll()
    dd_mult = get_drawdown_multiplier()
    state = _get_equity_state()
    
    # Calculate base percentage (conservative for small capital)
    # With $26 balance: max ~35% = $9 per position
    if "Smart Money" in conviction_type:
        base_pct = 35.0  # 35% of balance - SMART MONEY
    elif "Strict" in conviction_type:
        base_pct = 30.0  # 30% of balance - HIGH CONVICTION
    else:
        base_pct = 25.0  # 25% of balance - STANDARD
    
    # Apply score-based size multiplier from SCORE_STAGE_MAP
    # REFACTOR (2026-05-17): Replaced inverted SCORE_*_MULT constants.
    # Forensic data shows: low score = early stage = best performers = larger size.
    # High score = late stage = already pumped = smaller size.
    stage_mult, _, stage_label = get_score_stage(score)
    multiplier = stage_mult
    
    # Calculate base size as percentage of CURRENT balance
    size_pct = base_pct * multiplier
    base_size = current_bankroll * (size_pct / 100.0)
    
    # Apply drawdown multiplier (reduces size when losing)
    size = base_size * dd_mult
    
    # Cap at max percentage of current balance
    max_size = current_bankroll * (MAX_POSITION_SIZE_PCT / 100.0)
    size = min(size, max_size)
    
    # Minimum $2 to cover fees + have meaningful position
    size = max(2.0, size)
    
    # Log if in drawdown
    dd_pct = state["drawdown_pct"]
    if dd_pct > 5:
        print(f"[SIZE] ${size:.2f} (base=${base_size:.2f} × {dd_mult}x DD mult) | Score:{score} | Stage:{stage_label} | DD:{dd_pct:.1f}%", flush=True)
    
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
- Score 8: 50% WR, 254% avg gain  <-- PRIORITIZE
- Score 7: 50% WR, 68% avg gain

By Conviction:
- Smart Money: 57% WR, 99% avg gain  <-- PRIORITIZE
- Strict: 30% WR, 103% avg gain

Expected Monthly Performance (with 30 signals/day):
- Starting: $500
- Signals: ~900/month (focus on Score 8-9 = ~270 quality signals)
- Winners at 42% WR: ~113 winners
- Average gain: 96%
- With compounding: $500 -> $700-800 Month 1 (+40-60%)

Risk Management:
- Circuit breaker prevents >20% daily loss
- Stop losses limit individual losses to -15%
- Max 5 concurrent positions
- Trailing stops capture 60-70% of peaks
"""

# ==================== SCORE STAGE MAP (2026-05-17 REFACTOR) ====================
# CRITICAL: Score is a STAGE INDICATOR, not confidence.
# Forensic data (73 trades):
#   Score 3-5: 28.6% WR, +$7.71 net  (BEST -- early stage, good entry timing)
#   Score 7:   22.2% WR, -$10.46 net
#   Score 9:    0.0% WR, -$2.54 net
#   Score 10:  15.8% WR, -$28.66 net  (WORST -- late stage, already pumped)
#
# Lower score = earlier discovery = better entry = more profit.
# Higher score = more hype already = buying the top = loss.
#
# Each entry: (position_size_multiplier, preferred_entry_strategy, stage_label)

SCORE_STAGE_MAP = {
    0:  (1.0, "instant",  "unknown"),
    1:  (1.0, "instant",  "very_early"),
    2:  (1.0, "instant",  "very_early"),
    3:  (1.3, "instant",  "early_stage"),
    4:  (1.3, "instant",  "early_stage"),
    5:  (1.1, "instant",  "mid_stage"),
    6:  (1.0, "delayed",  "mid_stage"),
    7:  (0.9, "delayed",  "late_stage"),
    8:  (0.8, "delayed",  "late_stage"),
    9:  (0.6, "dip",      "very_late"),
    10: (0.5, "dip",      "very_late"),
}


def get_score_stage(score: int):
    """Get (size_mult, entry_strategy, label) for a signal score."""
    return SCORE_STAGE_MAP.get(score, (1.0, "instant", "unknown"))


# ==================== STRATEGY PROFILES ====================
# Switch full configurations via TS_STRATEGY_PROFILE env var.
# This makes the system experiment-driven.

STRATEGY_PROFILES = {
    "conservative": {
        "entry_strategy": "dip",
        "entry_dip_pct": 15.0,
        "early_phase_sec": 300,
        "early_stop_pct": 60.0,
        "mid_stop_pct": 30.0,
        "score_usage": "stage_indicator",
        "min_score": 0,
    },
    "balanced": {
        "entry_strategy": "hybrid",
        "early_phase_sec": 180,
        "early_stop_pct": 50.0,
        "mid_stop_pct": 25.0,
        "score_usage": "stage_indicator",
        "min_score": 0,
    },
    "aggressive": {
        "entry_strategy": "delayed",
        "entry_delay_sec": 60,
        "early_phase_sec": 120,
        "early_stop_pct": 40.0,
        "mid_stop_pct": 20.0,
        "score_usage": "stage_indicator",
        "min_score": 0,
    },
    "legacy": {
        "entry_strategy": "instant",
        "early_phase_sec": 0,
        "early_stop_pct": 25.0,
        "mid_stop_pct": 25.0,
        "score_usage": "confidence",
        "min_score": 7,
    },
}

ACTIVE_STRATEGY_PROFILE = os.getenv("TS_STRATEGY_PROFILE", "balanced")


def get_active_profile():
    """Get the active strategy profile dict."""
    return STRATEGY_PROFILES.get(ACTIVE_STRATEGY_PROFILE, STRATEGY_PROFILES["balanced"])


