"""
AGGRESSIVE SCAM MARKET CONFIG - Asymmetric Risk/Reward

STRATEGY: Cut losers FAST, let winners RUN BIG
- Bigger positions ($100-150) → One winner covers many losses
- Tight stop loss (10%) → Exit scams before they dump 80%
- Remove early profit-taking → Let moonshots run to 100%+
- Only trail when deep in profit → Exit on real reversal

MATH:
- 39 losses × 10% = -$390 (tight stop cuts losses fast)
- 7 wins × 100%+ = $700+ (let winners run)
- Net: +$310 vs -$461 with old strategy

PHILOSOPHY: In scam markets, most tokens fail fast.
Cut them immediately. The few that moon need to cover many small losses.
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
SLIPPAGE_BPS = _get_int("TS_SLIPPAGE_BPS", 2000)  # 20%
PRIORITY_FEE_MIN_MICROLAMPORTS = _get_int("TS_PRIORITY_FEE_MIN_MICROLAMPORTS", 10000)
PRIORITY_FEE_MAX_MICROLAMPORTS = _get_int("TS_PRIORITY_FEE_MAX_MICROLAMPORTS", 50000)
PRIORITY_FEE_MICROLAMPORTS = PRIORITY_FEE_MAX_MICROLAMPORTS
MAX_SLIPPAGE_PCT = _get_float("TS_MAX_SLIPPAGE_PCT", 5.0)
MAX_PRICE_IMPACT_BUY_PCT = _get_float("TS_MAX_PRICE_IMPACT_BUY_PCT", 25.0)
MAX_PRICE_IMPACT_SELL_PCT = _get_float("TS_MAX_PRICE_IMPACT_SELL_PCT", 50.0)
MAX_PRICE_IMPACT_PCT = MAX_PRICE_IMPACT_BUY_PCT

# Base mints
SOL_MINT = os.getenv("TS_SOL_MINT", "So11111111111111111111111111111111111111112")
USDC_MINT = os.getenv("TS_USDC_MINT", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
BASE_MINT = os.getenv("TS_BASE_MINT", SOL_MINT)
SELL_MINT = os.getenv("TS_SELL_MINT", SOL_MINT)

# ==================== AGGRESSIVE POSITION SIZING ====================
# BIGGER POSITIONS = One moonshot covers many small losses
# Goal: $100-150 per trade (vs current $40-50)

BANKROLL_USD = _get_float("TS_BANKROLL_USD", 750)  # Will auto-detect actual balance

MAX_CONCURRENT = _get_int("TS_MAX_CONCURRENT", 3)  # Fewer concurrent = bigger size

# AGGRESSIVE SIZING - 13-20% per position (vs 5-6% before)
# With $750 balance: 13% = $97.50, 20% = $150
SMART_MONEY_BASE = _get_float("TS_SMART_MONEY_BASE", 20.0)  # $150 (best signals)
STRICT_BASE = _get_float("TS_STRICT_BASE", 15.0)  # $112.50
GENERAL_BASE = _get_float("TS_GENERAL_BASE", 13.0)  # $97.50

# Score multipliers (keep same)
SCORE_10_MULT = _get_float("TS_SCORE_10_MULT", 1.2)
SCORE_9_MULT = _get_float("TS_SCORE_9_MULT", 1.0)
SCORE_8_MULT = _get_float("TS_SCORE_8_MULT", 1.3)
SCORE_7_MULT = _get_float("TS_SCORE_7_MULT", 0.9)

# Max 25% per position (safety)
MAX_POSITION_SIZE_PCT = _get_float("TS_MAX_POSITION_SIZE_PCT", 25.0)
MAX_POSITION_SIZE_USD = BANKROLL_USD * (MAX_POSITION_SIZE_PCT / 100.0)

# ==================== TIGHT STOP LOSS - CUT LOSERS FAST ====================
# KEY CHANGE: 10% stop loss (vs 30% before)
# Most scams dump 80%+ → Need to exit at first sign of trouble
# Goal: Lose $10 on scams, not $40

STOP_LOSS_PCT = _get_float("TS_STOP_LOSS_PCT", 10.0)  # -10% from entry = TIGHT!
EMERGENCY_HARD_STOP_PCT = _get_float("TS_EMERGENCY_HARD_STOP_PCT", 10.0)  # -10% absolute max

# ==================== LET WINNERS RUN - REMOVE EARLY EXITS ====================
# PROFIT-BASED TRAILING: Don't touch winners until they're DEEP in profit

ADAPTIVE_TRAILING_ENABLED = _get_bool("TS_ADAPTIVE_TRAILING_ENABLED", True)

# DELAY PROFIT-TAKING: Start trailing at +100% (not +40%)
# This lets small winners become big winners
PROFIT_TIER_1 = _get_float("TS_PROFIT_TIER_1", 100.0)   # First trail tier: +100%
PROFIT_TIER_2 = _get_float("TS_PROFIT_TIER_2", 200.0)   # Second tier: +200%
PROFIT_TIER_3 = _get_float("TS_PROFIT_TIER_3", 500.0)   # Third tier: +500%
PROFIT_TIER_4 = _get_float("TS_PROFIT_TIER_4", 1000.0)  # Fourth tier: +1000%
PROFIT_TIER_5 = _get_float("TS_PROFIT_TIER_5", 2000.0)  # Fifth tier: +2000%

# TIGHT TRAILS FOR WINNERS: Once profitable, protect gains
# 0-100%: 15% trail (tight - lock in profits quickly)
# 100%+: 20-25% trail (moderate - let it breathe)
# 500%+: 30% trail (loose - moonshot mode)
TRAIL_TIER_0 = _get_float("TS_TRAIL_TIER_0", 15.0)  # 0-100%: 15% trail
TRAIL_TIER_1 = _get_float("TS_TRAIL_TIER_1", 20.0)  # 100-200%: 20% trail
TRAIL_TIER_2 = _get_float("TS_TRAIL_TIER_2", 25.0)  # 200-500%: 25% trail
TRAIL_TIER_3 = _get_float("TS_TRAIL_TIER_3", 30.0)  # 500-1000%: 30% trail
TRAIL_TIER_4 = _get_float("TS_TRAIL_TIER_4", 35.0)  # 1000-2000%: 35% trail
TRAIL_TIER_5 = _get_float("TS_TRAIL_TIER_5", 40.0)  # 2000%+: 40% trail

# Legacy (unused)
TRAIL_AGGRESSIVE = _get_float("TS_TRAIL_AGGRESSIVE", 5.0)
TRAIL_DEFAULT = _get_float("TS_TRAIL_DEFAULT", 8.0)
TRAIL_CONSERVATIVE = _get_float("TS_TRAIL_CONSERVATIVE", 10.0)
EARLY_TRAIL_PCT = _get_float("TS_EARLY_TRAIL_PCT", 15.0)
MID_TRAIL_PCT = _get_float("TS_MID_TRAIL_PCT", 20.0)
LATE_TRAIL_PCT = _get_float("TS_LATE_TRAIL_PCT", 25.0)

# Max hold time: 24 hours
MAX_HOLD_TIME_SECONDS = _get_int("TS_MAX_HOLD_TIME_SEC", 86400)

# ==================== EXIT MONITORING ====================
EXIT_CHECK_INTERVAL_SEC = _get_float("TS_EXIT_CHECK_INTERVAL", 3.0)
JUPITER_PRICE_CACHE_TTL = _get_int("TS_JUPITER_PRICE_CACHE_TTL", 10)

# ==================== CIRCUIT BREAKERS ====================
MAX_DAILY_LOSS_USD = _get_float("TS_MAX_DAILY_LOSS_USD", 200.0)  # Max -$200/day
MAX_DRAWDOWN_PCT = _get_float("TS_MAX_DRAWDOWN_PCT", 30.0)  # Max -30% from peak

# ==================== DRY RUN ====================
DRY_RUN = _get_bool("TS_DRY_RUN", False)

# ==================== SIGNAL FILTERING ====================
# TIGHTER FILTERS: Only trade highest quality signals
MIN_SIGNAL_SCORE = _get_int("TS_MIN_SIGNAL_SCORE", 8)  # Score 8+ only (was 7)
REQUIRE_SMART_MONEY = _get_bool("TS_REQUIRE_SMART_MONEY", False)  # Optional: smart money only

# Cooldown between trades on same token (4 hours)
TOKEN_COOLDOWN_SECONDS = _get_int("TS_TOKEN_COOLDOWN_SEC", 14400)

print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    AGGRESSIVE SCAM MARKET CONFIG LOADED                      ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  STRATEGY: Cut losers FAST (-10%), Let winners RUN (+100%+)                 ║
║                                                                              ║
║  📊 Position Size: $100-150 per trade (20% of bankroll)                     ║
║  🔴 Stop Loss: -10% (tight - exit scams immediately)                        ║
║  🟢 Profit Trail: Start at +100% (let winners grow)                         ║
║  💰 Risk/Reward: 10 losses = -$100, 1 winner = +$100+                       ║
║                                                                              ║
║  🎯 Goal: Asymmetric payoff in scam-heavy markets                           ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")


