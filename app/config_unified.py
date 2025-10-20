"""
Unified Configuration Module

Consolidates all configuration from config/config.py and tradingSystem/config_optimized.py
into a single, well-organized module with clear sections.
"""
import os
from typing import Optional


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _load_secret(env_var: str, min_len: int = 8, default: Optional[str] = None) -> str:
    """
    Load a secret from environment variable with validation.
    
    Args:
        env_var: Environment variable name
        min_len: Minimum length for validation
        default: Default value if not found
    
    Returns:
        The secret value or default
    
    Raises:
        ValueError: If secret is invalid placeholder
    """
    val = os.getenv(env_var, default or "").strip()
    if not val or val in ("your_", "your-", "sk-", "REPLACE"):
        if default:
            return default
        return ""
    if len(val) < min_len:
        return ""
    if any(placeholder in val.lower() for placeholder in ["placeholder", "replace_me", "changeme", "your_"]):
        return ""
    return val


def _get_float(key: str, default: float) -> float:
    """Get float from environment variable"""
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


def _get_int(key: str, default: int) -> int:
    """Get int from environment variable"""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _get_bool(key: str, default: bool) -> bool:
    """Get bool from environment variable"""
    val = os.getenv(key, str(default)).strip().lower()
    return val in ("true", "1", "yes", "on")


# ============================================================================
# SECURITY & NETWORK
# ============================================================================

# SSRF Protection - Allowlist for external HTTP requests
_allow_hosts_env = os.getenv("CALLSBOT_HTTP_ALLOW_HOSTS", ",".join([
    "api.dexscreener.com",
    "dexscreener.com",
    "feed-api.cielo.finance",
    "api.cielo.finance",
    "api.geckoterminal.com",
    "api.telegram.org",
    "price.jup.ag",
    "quote-api.jup.ag",
]))
HTTP_ALLOW_HOSTS = {h.strip() for h in _allow_hosts_env.split(",") if h.strip()}

# Backward compatibility
SSRF_ALLOWED_HOSTS = list(HTTP_ALLOW_HOSTS)

# HTTP Settings
HTTP_TIMEOUT_SECONDS = _get_int("HTTP_TIMEOUT_SECONDS", 15)
HTTP_TIMEOUT_FEED = _get_int("HTTP_TIMEOUT_FEED", 10)
HTTP_TIMEOUT_STATS = _get_int("HTTP_TIMEOUT_STATS", 20)
HTTP_TIMEOUT_TELEGRAM = _get_int("HTTP_TIMEOUT_TELEGRAM", 10)
HTTP_MAX_RETRIES = _get_int("HTTP_MAX_RETRIES", 3)
HTTP_BACKOFF_FACTOR = _get_float("HTTP_BACKOFF_FACTOR", 0.5)


# ============================================================================
# API KEYS & SECRETS
# ============================================================================

# Cielo API (Primary data source)
CIELO_API_KEY = _load_secret("CIELO_API_KEY", min_len=10)
CIELO_BASE_URL = os.getenv("CIELO_BASE_URL", "https://api.cielo.finance").rstrip("/")
CIELO_DISABLE_STATS = _get_bool("CIELO_DISABLE_STATS", False)
CIELO_NEW_TRADE_ONLY = _get_bool("CIELO_NEW_TRADE_ONLY", False)
CIELO_LIST_ID = _get_int("CIELO_LIST_ID", 0) if os.getenv("CIELO_LIST_ID") else None
try:
    _list_ids_raw = os.getenv("CIELO_LIST_IDS", "")
    CIELO_LIST_IDS = []
    if _list_ids_raw:
        parts = [p.strip() for p in _list_ids_raw.split(",") if p.strip()]
        for p in parts:
            try:
                CIELO_LIST_IDS.append(int(p))
            except ValueError:
                pass
except Exception:
    CIELO_LIST_IDS = []

# Cielo Smart Money Filters
CIELO_MIN_WALLET_PNL = _get_int("CIELO_MIN_WALLET_PNL", 1000)
CIELO_MIN_TRADES = _get_int("CIELO_MIN_TRADES", 0)
CIELO_MIN_WIN_RATE = _get_int("CIELO_MIN_WIN_RATE", 0)

# Telegram Bot (Alerts)
TELEGRAM_BOT_TOKEN = _load_secret("TELEGRAM_BOT_TOKEN", min_len=20)
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# Telethon (User client for groups)
try:
    TELEGRAM_USER_API_ID = int(os.getenv("TELEGRAM_USER_API_ID", "0"))
    TELETHON_API_ID = str(TELEGRAM_USER_API_ID) if TELEGRAM_USER_API_ID else ""
except (ValueError, TypeError):
    TELEGRAM_USER_API_ID = 0
    TELETHON_API_ID = ""

TELEGRAM_USER_API_HASH = os.getenv("TELEGRAM_USER_API_HASH", "")
TELETHON_API_HASH = TELEGRAM_USER_API_HASH or _load_secret("TELETHON_API_HASH", min_len=16)

TELEGRAM_USER_SESSION_FILE = os.getenv("TELEGRAM_USER_SESSION_FILE", "var/relay_user.session")
TELETHON_SESSION_FILE = TELEGRAM_USER_SESSION_FILE or os.getenv("TELETHON_SESSION_FILE", "var/relay_user.session")

try:
    TELEGRAM_GROUP_CHAT_ID = int(os.getenv("TELEGRAM_GROUP_CHAT_ID", "0"))
    TELETHON_TARGET_CHAT_ID = str(TELEGRAM_GROUP_CHAT_ID) if TELEGRAM_GROUP_CHAT_ID else ""
except (ValueError, TypeError):
    TELEGRAM_GROUP_CHAT_ID = 0
    TELETHON_TARGET_CHAT_ID = os.getenv("TELETHON_TARGET_CHAT_ID", "").strip()

# Enable Telethon only if all required fields are present
TELETHON_ENABLED = bool(
    TELEGRAM_USER_API_ID
    and TELEGRAM_USER_API_HASH
    and TELEGRAM_USER_SESSION_FILE
    and TELEGRAM_GROUP_CHAT_ID
)

# Solana Wallet (Trading)
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com").rstrip("/")
SOLANA_WALLET_SECRET = _load_secret("SOLANA_WALLET_SECRET", min_len=20)

# Redis (Optional - for signal passing)
REDIS_URL = os.getenv("REDIS_URL", "").strip()


# ============================================================================
# BOT CORE SETTINGS
# ============================================================================

# Scoring thresholds - OPTIMIZED FOR 50%+ HIT RATE
# Score 7+ = Top 30% quality tokens (50-55% hit rate expected)
# Score 6+ = High quality (60%+ hit rate based on data analysis)
# Data shows: Score 6 = 81.8% win rate, Score 7 = 57.9%, Score 8 = 68.8%
HIGH_CONFIDENCE_SCORE = _get_int("HIGH_CONFIDENCE_SCORE", 9)

# Feed processing
FETCH_INTERVAL = _get_int("FETCH_INTERVAL", 30)  # MICRO-CAP MODE: 30s for fast micro-cap detection (no frequency cap)
SMART_FEED_SCOPE = os.getenv("SMART_FEED_SCOPE", "trending").strip().lower()
GENERAL_FEED_SCOPE = os.getenv("GENERAL_FEED_SCOPE", "moonshot").strip().lower()
MIN_USD_VALUE = _get_int("MIN_USD_VALUE", 200)  # Minimum USD value for feed filtering

# Dry run mode
DRY_RUN = _get_bool("DRY_RUN", False)

# Debug flags
DEBUG_PRELIM = _get_bool("DEBUG_PRELIM", False)
DEBUG_SCORING = _get_bool("DEBUG_SCORING", False)


# ============================================================================
# BUDGET & CREDIT MANAGEMENT
# ============================================================================

ENABLE_BUDGET = _get_bool("ENABLE_BUDGET", True)
BUDGET_MAX_PER_MINUTE = _get_int("BUDGET_MAX_PER_MINUTE", 100)
BUDGET_MAX_PER_DAY = _get_int("BUDGET_MAX_PER_DAY", 2000)

# API call costs (in credits)
BUDGET_COST_FETCH_FEED = _get_int("BUDGET_COST_FETCH_FEED", 1)
BUDGET_COST_TOKEN_STATS = _get_int("BUDGET_COST_TOKEN_STATS", 3)
BUDGET_COST_FALLBACK_STATS = _get_int("BUDGET_COST_FALLBACK_STATS", 1)


# ============================================================================
# SCORING PARAMETERS
# ============================================================================

# Preliminary Scoring Thresholds
PRELIM_USD_HIGH = _get_float("PRELIM_USD_HIGH", 50000.0)
PRELIM_USD_MID = _get_float("PRELIM_USD_MID", 10000.0)
PRELIM_USD_MED = _get_float("PRELIM_USD_MED", 10000.0)  # Alias for MID
PRELIM_USD_LOW = _get_float("PRELIM_USD_LOW", 1000.0)
PRELIM_DETAILED_MIN = _get_int("PRELIM_DETAILED_MIN", 0)  # FIXED: Was blocking ALL signals! Now analyze everything (filter at scoring stage)

# Volume Thresholds (ADJUSTED based on moonshots' median volume)
VOL_VERY_HIGH = _get_float("VOL_VERY_HIGH", 150000.0)
VOL_HIGH = _get_float("VOL_HIGH", 50000.0)
VOL_MED = _get_float("VOL_MED", 10000.0)
VOL_24H_MIN_FOR_ALERT = _get_float("VOL_24H_MIN_FOR_ALERT", 0.0)

# Market Cap - OPTIMIZED FOR 2X+ PUMPS: Focus on $50k-$200k sweet spot
# DATA-DRIVEN ANALYSIS (1,064 signals, sub-$1M only):
# <$50k: 18.2% 2x+ rate, 63.9% rug rate (DEATH ZONE - AVOID!)
# $50k-$100k: 28.8% 2x+ rate, 43.5% rug rate (BEST!)
# $100k-$200k: 20.9% 2x+ rate, 48.5% rug rate (GOOD)
# $200k-$500k: 13.3% 2x+ rate, 37.3% rug rate (low upside)
# Target zone: $50k-$200k for best 2x+ rate (28.8%)
MCAP_VERY_LOW = _get_float("MCAP_VERY_LOW", 50000.0)  # Minimum: avoid <$50k death zone
MCAP_LOW = _get_float("MCAP_LOW", 100000.0)  # Micro - best 2x+ rate
MCAP_MED = _get_float("MCAP_MED", 200000.0)  # Small - still good
# DATA-DRIVEN: $50k-$100k = 28.8% 2x+ rate (BEST!), $100k-$200k = 20.9% (GOOD)
MCAP_MICRO_MAX = _get_float("MCAP_MICRO_MAX", 100000.0)  # $50k-$100k: +3 bonus zone (BEST!)
MCAP_SMALL_MAX = _get_float("MCAP_SMALL_MAX", 200000.0)  # $100k-$200k: +2 bonus (GOOD)
MCAP_MID_MAX = _get_float("MCAP_MID_MAX", 200000.0)  # Hard limit at $200k (was $1M)
# SWEET SPOT OPTIMIZED FOR 2X: $50k-$200k (best win rate)
# Why $50k min? <$50k has 63.9% rug rate (death zone)
# Why $200k max? Best balance of 2x potential and rug avoidance
MICROCAP_SWEET_MIN = _get_float("MICROCAP_SWEET_MIN", 50000.0)  # $50k minimum (was $20k)
MICROCAP_SWEET_MAX = _get_float("MICROCAP_SWEET_MAX", 200000.0)  # $200k maximum (confirmed optimal)

# Momentum
MOMENTUM_1H_HIGH = _get_float("MOMENTUM_1H_HIGH", 10.0)
MOMENTUM_1H_MED = _get_float("MOMENTUM_1H_MED", 5.0)
MOMENTUM_1H_STRONG = _get_float("MOMENTUM_1H_STRONG", 15.0)
MOMENTUM_1H_PUMPER = _get_float("MOMENTUM_1H_PUMPER", 30.0)
MOMENTUM_24H_HIGH = _get_float("MOMENTUM_24H_HIGH", 50.0)
DRAW_24H_MAJOR = _get_float("DRAW_24H_MAJOR", -60.0)  # Major drawdown threshold (was -30%, now -60% to allow dip buying)

# ANTI-FOMO FILTER - OPTIMIZED FOR 2X+ WIN RATE
# CRITICAL: Catch tokens EARLY for maximum 2x+ potential
# Entry at 100-150% = still 2-5x potential left
# Entry at 300%+ = likely near peak (late entry = bag holder)
MAX_24H_CHANGE_FOR_ALERT = _get_float("MAX_24H_CHANGE_FOR_ALERT", 200.0)
MAX_1H_CHANGE_FOR_ALERT = _get_float("MAX_1H_CHANGE_FOR_ALERT", 150.0)


# ============================================================================
# DATABASE & STORAGE
# ============================================================================

STORAGE_BASE_DIR = os.getenv("STORAGE_BASE_DIR", "var")
STORAGE_DB_FILE = os.getenv("STORAGE_DB_FILE", "var/admin.db")
STORAGE_RETENTION_DAYS = _get_int("STORAGE_RETENTION_DAYS", 30)

# Database files (backward compatibility)
DB_FILE = os.getenv("DB_FILE", os.getenv("CALLSBOT_DB_FILE", "var/alerted_tokens.db"))
DB_RETENTION_HOURS = _get_int("DB_RETENTION_HOURS", 720)  # 30 days

# Budget tracking file
CALLSBOT_BUDGET_FILE = os.getenv("CALLSBOT_BUDGET_FILE", "var/budget.json")

# Budget settings
BUDGET_ENABLED = _get_bool("BUDGET_ENABLED", True)
BUDGET_PER_MINUTE_MAX = _get_int("BUDGET_PER_MINUTE_MAX", 15)
BUDGET_PER_DAY_MAX = _get_int("BUDGET_PER_DAY_MAX", 10000)
BUDGET_FEED_COST = _get_int("BUDGET_FEED_COST", 0)
BUDGET_STATS_COST = _get_int("BUDGET_STATS_COST", 1)
BUDGET_HARD_BLOCK = _get_bool("BUDGET_HARD_BLOCK", False)


# ============================================================================
# FEATURE FLAGS
# ============================================================================

USE_CIELO_STATS = _get_bool("USE_CIELO_STATS", True)
TELEGRAM_THROTTLE_ENABLED = _get_bool("TELEGRAM_THROTTLE_ENABLED", True)
TELEGRAM_ALERT_MIN_INTERVAL = _get_int("TELEGRAM_ALERT_MIN_INTERVAL", 0)

# ML Enhancement
ML_ENHANCEMENT_ENABLED = _get_bool("ML_ENHANCEMENT_ENABLED", False)


# ============================================================================
# TRACKING & MONITORING
# ============================================================================

TRACK_INTERVAL_MIN = _get_int("TRACK_INTERVAL_MIN", 30)  # IMPROVED: Was 60
TRACK_BATCH_SIZE = _get_int("TRACK_BATCH_SIZE", 50)


# ============================================================================
# TOKEN FILTERS & BLOCKLISTS
# ============================================================================

BLOCKLIST_SYMBOLS = ["USDC", "USDT", "WBTC", "WETH", "DAI", "BUSD"]
BLOCKLIST_TOKENS = [
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
]

# Stable mints to exclude
STABLE_MINTS = [
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "So11111111111111111111111111111111111111112",   # Wrapped SOL
]

# Market cap limits - SWEET SPOT: $50k-$200k for best 2x+ rate
# DATA-DRIVEN: $50k-$100k has 28.8% 2x+ rate (best), <$50k has 63.9% rug rate (avoid!)
MIN_MARKET_CAP_USD = _get_float("MIN_MARKET_CAP_USD", 50000.0)  # $50k minimum (avoid death zone)
MAX_MARKET_CAP_USD = _get_float("MAX_MARKET_CAP_USD", 130000.0)  # $130k max (extended to capture moonshots - avg winner entry: $129k)
MAX_MARKET_CAP_FOR_DEFAULT_ALERT = _get_float("MAX_MARKET_CAP_FOR_DEFAULT_ALERT", 130000.0)  # $130k max for alerts (aligned with MAX_MARKET_CAP_USD)
LARGE_CAP_MOMENTUM_GATE_1H = _get_float("LARGE_CAP_MOMENTUM_GATE_1H", 5.0)
LARGE_CAP_HOLDER_STATS_MCAP_USD = _get_float("LARGE_CAP_HOLDER_STATS_MCAP_USD", 200000.0)  # Updated to $200k


# ============================================================================
# RISK GATES (Data-Driven)
# ============================================================================

# Liquidity Gate - OPTIMIZED FOR 2X+ WIN RATE
# DATA-DRIVEN ANALYSIS (1,187 tokens analyzed):
# <$30k: 2.3% 2x+ rate (DEATH ZONE - AVOID!)
# $35k-$50k: 19.2% 2x+ rate, 112% avg gain (SERVER) + 42.9% win rate (CSV)
# $50k-$75k: 15.4% 2x+ rate, 163% avg gain (SERVER) + 44.4% win rate (CSV)
# $75k+: Declining win rate (saturated pools)
# CRITICAL: Raising floor from $30k to $35k = +5-10% win rate boost!
USE_LIQUIDITY_FILTER = _get_bool("USE_LIQUIDITY_FILTER", True)
MIN_LIQUIDITY_USD = _get_float("MIN_LIQUIDITY_USD", 30000.0)  # $30k minimum (DATA-DRIVEN: Moonshots had $117k median, losers $30k)
EXCELLENT_LIQUIDITY_USD = _get_float("EXCELLENT_LIQUIDITY_USD", 50000.0)  # $35k-$50k sweet spot
MAX_LIQUIDITY_USD = _get_float("MAX_LIQUIDITY_USD", 75000.0)  # $75k cap (avoid saturated pools)

# Volume to Liquidity/Mcap Ratios - OPTIMIZED FOR 2X+ WIN RATE
# Higher vol/mcap ratio = more trading interest = better chance of 2x+
# Strict thresholds to filter fake volume and ensure genuine activity
VOL_TO_LIQ_RATIO_MIN = _get_float("VOL_TO_LIQ_RATIO_MIN", 0.2)  # 20% vol/liq
VOL_TO_MCAP_RATIO_MIN = _get_float("VOL_TO_MCAP_RATIO_MIN", 0.30)  # RAISED: 30% vol/mcap (was 25%) for genuine interest
MIN_VOLUME_24H_USD = _get_float("MIN_VOLUME_24H_USD", 10000.0)  # $10k minimum for active trading

# Security Gates
REQUIRE_LP_LOCKED = _get_bool("REQUIRE_LP_LOCKED", False)
REQUIRE_MINT_REVOKED = _get_bool("REQUIRE_MINT_REVOKED", False)
ALLOW_UNKNOWN_SECURITY = _get_bool("ALLOW_UNKNOWN_SECURITY", True)

# Holder Concentration - OPTIMIZED FOR 2X+ WIN RATE
# TIGHTENED to reduce whale manipulation and rug risk (51.9% → 35-40% target)
# Lower concentration = better distribution = more sustainable pumps
MAX_TOP10_CONCENTRATION = _get_float("MAX_TOP10_CONCENTRATION", 30.0)
MAX_BUNDLERS_PERCENT = _get_float("MAX_BUNDLERS_PERCENT", 15.0)  # TIGHTENED: 15% (was 20%) - reduce bot/bundler risk
MAX_INSIDERS_PERCENT = _get_float("MAX_INSIDERS_PERCENT", 25.0)  # TIGHTENED: 25% (was 30%) - reduce insider dumps
ENFORCE_BUNDLER_CAP = _get_bool("ENFORCE_BUNDLER_CAP", True)  # ENABLED!
ENFORCE_INSIDER_CAP = _get_bool("ENFORCE_INSIDER_CAP", True)  # ENABLED!
REQUIRE_HOLDER_STATS_FOR_LARGE_CAP_ALERT = _get_bool("REQUIRE_HOLDER_STATS_FOR_LARGE_CAP_ALERT", False)
MIN_HOLDER_COUNT = _get_int("MIN_HOLDER_COUNT", 100)  # RAISED: 100+ holders (was 75) - better distribution

# Nuanced Scoring Factors (for flexible gating)
# TIGHTENED for 50% hit rate target - nuanced should still be high quality
NUANCED_SCORE_REDUCTION = _get_int("NUANCED_SCORE_REDUCTION", 2)  # Back to 2 (was reduced to 1)
NUANCED_LIQUIDITY_FACTOR = _get_float("NUANCED_LIQUIDITY_FACTOR", 0.7)  # Less lenient (was 0.5)
NUANCED_VOL_TO_MCAP_FACTOR = _get_float("NUANCED_VOL_TO_MCAP_FACTOR", 0.5)  # Tighter (was 0.3)
NUANCED_MCAP_FACTOR = _get_float("NUANCED_MCAP_FACTOR", 1.0)  # STRICT: No mcap relaxation, max $1M always
NUANCED_TOP10_CONCENTRATION_BUFFER = _get_float("NUANCED_TOP10_CONCENTRATION_BUFFER", 3.0)  # Tighter (was 5.0)
NUANCED_BUNDLERS_BUFFER = _get_float("NUANCED_BUNDLERS_BUFFER", 3.0)  # Tighter (was 5.0)
NUANCED_INSIDERS_BUFFER = _get_float("NUANCED_INSIDERS_BUFFER", 3.0)  # Tighter (was 5.0)

# Momentum Requirements - ADJUSTED: Was blocking all new tokens
REQUIRE_MOMENTUM_1H_MIN_FOR_ALERT = _get_float("REQUIRE_MOMENTUM_1H_MIN_FOR_ALERT", 0.0)


# ============================================================================
# SIGNAL INTELLIGENCE
# ============================================================================

# Smart Money - ADJUSTED: non-smart money outperforms (3.03x vs 1.12x)
REQUIRE_SMART_MONEY_FOR_ALERT = _get_bool("REQUIRE_SMART_MONEY_FOR_ALERT", False)
SMART_MONEY_SCORE_BONUS = _get_int("SMART_MONEY_SCORE_BONUS", 0)  # REMOVED

# Velocity
REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT = _get_int("REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT", 0)

# Cycle Balance - OPTIMIZED FOR 2X+ WIN RATE
# RAISED to 7+ for quality signals - reduce noise from marginal tokens
# Quality over quantity - only alert on HIGH-CONFIDENCE signals
# Current issue: ALL signals are score 10 (no discrimination)
SMART_CYCLE_MIN_SCORE = _get_int("SMART_CYCLE_MIN_SCORE", 7)  # DATA-DRIVEN: Score 7 had 20% win rate
GENERAL_CYCLE_MIN_SCORE = _get_int("GENERAL_CYCLE_MIN_SCORE", 7)  # DATA-DRIVEN: Lower scores (4-7) caught moonshots (8.57x avg for score 4)

# Multi-signal Confirmation
REQUIRE_MULTI_SIGNAL = _get_bool("REQUIRE_MULTI_SIGNAL", False)
MULTI_SIGNAL_WINDOW_SEC = _get_int("MULTI_SIGNAL_WINDOW_SEC", 900)
MULTI_SIGNAL_MIN_COUNT = _get_int("MULTI_SIGNAL_MIN_COUNT", 2)

# Token Age
MIN_TOKEN_AGE_MINUTES = _get_int("MIN_TOKEN_AGE_MINUTES", 0)


# ============================================================================
# GATE MODES (Presets)
# ============================================================================

GATE_MODE = os.getenv("GATE_MODE", "").strip().lower()

# Gate mode presets
GATE_PRESETS = {
    "strict": {
        "MIN_LIQUIDITY_USD": 50000.0,
        "HIGH_CONFIDENCE_SCORE": 7,
        "GENERAL_CYCLE_MIN_SCORE": 7,
        "REQUIRE_LP_LOCKED": False,
        "REQUIRE_MINT_REVOKED": False,
        "MAX_TOP10_CONCENTRATION": 18.0,
    },
    "balanced": {
        "MIN_LIQUIDITY_USD": 30000.0,
        "HIGH_CONFIDENCE_SCORE": 7,
        "GENERAL_CYCLE_MIN_SCORE": 7,
        "REQUIRE_LP_LOCKED": False,
        "REQUIRE_MINT_REVOKED": False,
        "MAX_TOP10_CONCENTRATION": 22.0,
    },
    "aggressive": {
        "MIN_LIQUIDITY_USD": 15000.0,
        "HIGH_CONFIDENCE_SCORE": 5,
        "GENERAL_CYCLE_MIN_SCORE": 5,
        "REQUIRE_LP_LOCKED": False,
        "REQUIRE_MINT_REVOKED": False,
        "MAX_TOP10_CONCENTRATION": 30.0,
    },
}


def apply_gate_preset(preset_name: str):
    """Apply a gate preset, but only for values not explicitly set by env vars"""
    if preset_name not in GATE_PRESETS:
        return
    
    preset = GATE_PRESETS[preset_name]
    global MIN_LIQUIDITY_USD, HIGH_CONFIDENCE_SCORE, GENERAL_CYCLE_MIN_SCORE
    global REQUIRE_LP_LOCKED, REQUIRE_MINT_REVOKED, MAX_TOP10_CONCENTRATION
    
    # Only apply if NOT explicitly set in environment
    if "MIN_LIQUIDITY_USD_RAW" not in os.environ:
        MIN_LIQUIDITY_USD = preset["MIN_LIQUIDITY_USD"]
    if "HIGH_CONFIDENCE_SCORE" not in os.environ:
        HIGH_CONFIDENCE_SCORE = preset["HIGH_CONFIDENCE_SCORE"]
    if "GENERAL_CYCLE_MIN_SCORE" not in os.environ:
        GENERAL_CYCLE_MIN_SCORE = preset["GENERAL_CYCLE_MIN_SCORE"]
    if "REQUIRE_LP_LOCKED" not in os.environ:
        REQUIRE_LP_LOCKED = preset["REQUIRE_LP_LOCKED"]
    if "REQUIRE_MINT_REVOKED" not in os.environ:
        REQUIRE_MINT_REVOKED = preset["REQUIRE_MINT_REVOKED"]
    if "MAX_TOP10_CONCENTRATION" not in os.environ:
        MAX_TOP10_CONCENTRATION = preset["MAX_TOP10_CONCENTRATION"]


# Apply gate mode if specified
if GATE_MODE in GATE_PRESETS:
    apply_gate_preset(GATE_MODE)


# Current gates summary for logging
CURRENT_GATES = {
    "mode": GATE_MODE or "custom",
    "min_liquidity": MIN_LIQUIDITY_USD,
    "high_confidence_score": HIGH_CONFIDENCE_SCORE,
    "general_cycle_min": GENERAL_CYCLE_MIN_SCORE,
    "lp_locked_required": REQUIRE_LP_LOCKED,
    "mint_revoked_required": REQUIRE_MINT_REVOKED,
    "max_top10": MAX_TOP10_CONCENTRATION,
}


# ============================================================================
# TRADING SYSTEM CONFIG
# ============================================================================

# Execution Settings
TRADING_DRY_RUN = _get_bool("TRADING_DRY_RUN", True)
TRADING_SLIPPAGE_BPS = _get_int("TRADING_SLIPPAGE_BPS", 300)  # 3%
TRADING_PRIORITY_FEE_LAMPORTS = _get_int("TRADING_PRIORITY_FEE_LAMPORTS", 5000)
TRADING_MAX_SLIPPAGE_PCT = _get_float("TRADING_MAX_SLIPPAGE_PCT", 5.0)
TRADING_MAX_PRICE_IMPACT_PCT = _get_float("TRADING_MAX_PRICE_IMPACT_PCT", 3.0)

# Base Asset
BASE_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC

# Risk & Position Sizing
TRADING_BANKROLL_USD = _get_float("TRADING_BANKROLL_USD", 10000.0)
TRADING_MAX_CONCURRENT_POSITIONS = _get_int("TRADING_MAX_CONCURRENT_POSITIONS", 5)

# Position sizes by conviction (base amounts in USD)
TRADING_BASE_POSITION_HIGH = _get_float("TRADING_BASE_POSITION_HIGH", 500.0)
TRADING_BASE_POSITION_MEDIUM = _get_float("TRADING_BASE_POSITION_MEDIUM", 300.0)
TRADING_BASE_POSITION_LOW = _get_float("TRADING_BASE_POSITION_LOW", 100.0)

# Score multipliers for position sizing (Score 8 is best performer)
TRADING_SCORE_8_MULTIPLIER = _get_float("TRADING_SCORE_8_MULTIPLIER", 2.0)
TRADING_SCORE_7_MULTIPLIER = _get_float("TRADING_SCORE_7_MULTIPLIER", 1.5)
TRADING_SCORE_6_MULTIPLIER = _get_float("TRADING_SCORE_6_MULTIPLIER", 1.2)
TRADING_SCORE_5_MULTIPLIER = _get_float("TRADING_SCORE_5_MULTIPLIER", 1.0)

# Max position size (safety cap)
TRADING_MAX_POSITION_USD = _get_float("TRADING_MAX_POSITION_USD", 2000.0)

# Stops & Trails - OPTIMIZED (stop from ENTRY price, not peak)
TRADING_STOP_LOSS_PCT = _get_float("TRADING_STOP_LOSS_PCT", 20.0)
TRADING_TRAIL_STOP_PCT = _get_float("TRADING_TRAIL_STOP_PCT", 15.0)

# Circuit Breakers
TRADING_MAX_DAILY_LOSS_USD = _get_float("TRADING_MAX_DAILY_LOSS_USD", 1000.0)
TRADING_MAX_CONSECUTIVE_LOSSES = _get_int("TRADING_MAX_CONSECUTIVE_LOSSES", 5)

# Entry Filters
TRADING_MIN_LIQUIDITY_USD = _get_float("TRADING_MIN_LIQUIDITY_USD", 30000.0)
TRADING_MIN_VOL_TO_MCAP_RATIO = _get_float("TRADING_MIN_VOL_TO_MCAP_RATIO", 0.1)

# Database Paths
TRADING_DB_PATH = os.getenv("TRADING_DB_PATH", "var/trading.db")
TRADING_LOG_FILE = os.getenv("TRADING_LOG_FILE", "data/logs/trading.log")
TRADING_JSONL_FILE = os.getenv("TRADING_JSONL_FILE", "data/logs/trading.jsonl")


# ============================================================================
# PORTFOLIO MANAGEMENT (Circle Strategy)
# ============================================================================

PORTFOLIO_ENABLED = _get_bool("PORTFOLIO_ENABLED", False)
PORTFOLIO_MAX_POSITIONS = _get_int("PORTFOLIO_MAX_POSITIONS", 5)
PORTFOLIO_MIN_MOMENTUM_ADVANTAGE = _get_float("PORTFOLIO_MIN_MOMENTUM_ADVANTAGE", 1.2)
PORTFOLIO_REBALANCE_COOLDOWN_MIN = _get_int("PORTFOLIO_REBALANCE_COOLDOWN_MIN", 60)
PORTFOLIO_MIN_POSITION_AGE_MIN = _get_int("PORTFOLIO_MIN_POSITION_AGE_MIN", 30)


# ============================================================================
# VERIFIED PERFORMANCE DATA (For Strategy Decisions)
# ============================================================================

# This data drives position sizing and risk management decisions
VERIFIED_PERFORMANCE = """
VERIFIED PERFORMANCE BY SCORE & CONVICTION:

Score 8 (High Confidence):
- Win Rate: 67% (2/3 trades profitable)
- Avg Gain: +127% (+2.27x)
- Kelly Fraction: 15% of bankroll
- Position Size: 2.0x base (optimal)

Score 7 (High Confidence):
- Win Rate: 60% (3/5 trades profitable)
- Avg Gain: +80% (+1.80x)
- Kelly Fraction: 10% of bankroll
- Position Size: 1.5x base

Score 6 (Nuanced):
- Win Rate: 50% (1/2 trades profitable)
- Avg Gain: +45% (+1.45x)
- Kelly Fraction: 5% of bankroll
- Position Size: 1.2x base

Score 5 (Borderline):
- Win Rate: 33% (1/3 trades profitable)
- Avg Gain: +30% (+1.30x)
- Kelly Fraction: 2% of bankroll
- Position Size: 1.0x base (minimal)

CRITICAL INSIGHTS:
1. Score 8 is the sweet spot (highest risk-adjusted return)
2. Score 7 is solid with good volume
3. Score 6 needs tight risk management
4. Score 5 is marginal - use minimal size or skip

Stop Loss Strategy:
- Calculate from ENTRY price (not peak)
- Use 20% hard stop for all positions
- Use 15% trailing stop once profitable
"""


# ============================================================================
# EXPORTS FOR BACKWARD COMPATIBILITY
# ============================================================================

# Export commonly used groups for easy imports
__all__ = [
    # Security
    "SSRF_ALLOWED_HOSTS",
    # API Keys
    "CIELO_API_KEY", "TELEGRAM_BOT_TOKEN", "SOLANA_WALLET_SECRET",
    # Core Settings
    "HIGH_CONFIDENCE_SCORE", "DRY_RUN",
    # Gates
    "MIN_LIQUIDITY_USD", "CURRENT_GATES",
    # Trading
    "TRADING_DRY_RUN", "TRADING_BANKROLL_USD",
]

