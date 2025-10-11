"""
Unified Configuration Module

Consolidates all configuration from config/config.py and tradingSystem/config_optimized.py
into a single, well-organized module with clear sections.
"""
import os
from typing import Optional, List


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
SSRF_ALLOWED_HOSTS = [
    "api.cielo.finance",
    "api.dexscreener.com",
    "api.geckoterminal.com",
    "price.jup.ag",
    "quote-api.jup.ag",
    "api.telegram.org",
]

# HTTP Settings
HTTP_TIMEOUT_SECONDS = _get_int("HTTP_TIMEOUT_SECONDS", 15)
HTTP_MAX_RETRIES = _get_int("HTTP_MAX_RETRIES", 3)
HTTP_BACKOFF_FACTOR = _get_float("HTTP_BACKOFF_FACTOR", 0.5)


# ============================================================================
# API KEYS & SECRETS
# ============================================================================

# Cielo API (Primary data source)
CIELO_API_KEY = _load_secret("CIELO_API_KEY", min_len=10)
CIELO_BASE_URL = os.getenv("CIELO_BASE_URL", "https://api.cielo.finance").rstrip("/")

# Telegram Bot (Alerts)
TELEGRAM_BOT_TOKEN = _load_secret("TELEGRAM_BOT_TOKEN", min_len=20)
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Telethon (User client for groups)
TELETHON_API_ID = os.getenv("TELETHON_API_ID", "").strip()
TELETHON_API_HASH = _load_secret("TELETHON_API_HASH", min_len=16)
TELETHON_SESSION_FILE = os.getenv("TELETHON_SESSION_FILE", "var/relay_user.session")
TELETHON_TARGET_CHAT_ID = os.getenv("TELETHON_TARGET_CHAT_ID", "").strip()

# Solana Wallet (Trading)
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com").rstrip("/")
SOLANA_WALLET_SECRET = _load_secret("SOLANA_WALLET_SECRET", min_len=20)

# Redis (Optional - for signal passing)
REDIS_URL = os.getenv("REDIS_URL", "").strip()


# ============================================================================
# BOT CORE SETTINGS
# ============================================================================

# Scoring thresholds
HIGH_CONFIDENCE_SCORE = _get_int("HIGH_CONFIDENCE_SCORE", 5)  # FIX: Was 7, blocking everything

# Feed processing
FETCH_INTERVAL = _get_int("FETCH_INTERVAL", 60)
SMART_FEED_SCOPE = os.getenv("SMART_FEED_SCOPE", "trending").strip().lower()
GENERAL_FEED_SCOPE = os.getenv("GENERAL_FEED_SCOPE", "moonshot").strip().lower()

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
PRELIM_USD_MED = _get_float("PRELIM_USD_MED", 10000.0)
PRELIM_DETAILED_MIN = _get_int("PRELIM_DETAILED_MIN", 5)  # CRITICAL FIX: Was 3

# Volume Thresholds (ADJUSTED based on moonshots' median volume)
VOL_VERY_HIGH = _get_float("VOL_VERY_HIGH", 150000.0)
VOL_HIGH = _get_float("VOL_HIGH", 50000.0)
VOL_MED = _get_float("VOL_MED", 10000.0)

# Market Cap
MCAP_VERY_LOW = _get_float("MCAP_VERY_LOW", 50000.0)
MCAP_LOW = _get_float("MCAP_LOW", 200000.0)
MCAP_MED = _get_float("MCAP_MED", 1000000.0)

# Momentum
MOMENTUM_1H_HIGH = _get_float("MOMENTUM_1H_HIGH", 10.0)
MOMENTUM_1H_MED = _get_float("MOMENTUM_1H_MED", 5.0)
MOMENTUM_24H_HIGH = _get_float("MOMENTUM_24H_HIGH", 50.0)

# ANTI-FOMO FILTER: Reject tokens that already pumped (late entry risk)
# Based on 615 signals analysis: 15.6% win rate, 119% avg gain
# Pattern: Winners at 0-50% momentum, Late entries >50% often dump
MAX_24H_CHANGE_FOR_ALERT = _get_float("MAX_24H_CHANGE_FOR_ALERT", 50.0)  # OPTIMIZED: Was 100%, now 50%
MAX_1H_CHANGE_FOR_ALERT = _get_float("MAX_1H_CHANGE_FOR_ALERT", 200.0)   # OPTIMIZED: Was 300%, now 200%


# ============================================================================
# DATABASE & STORAGE
# ============================================================================

STORAGE_BASE_DIR = os.getenv("STORAGE_BASE_DIR", "var")
STORAGE_DB_FILE = os.getenv("STORAGE_DB_FILE", "var/admin.db")
STORAGE_RETENTION_DAYS = _get_int("STORAGE_RETENTION_DAYS", 30)


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

# Market cap limits
MAX_MARKET_CAP_USD = _get_float("MAX_MARKET_CAP_USD", 50_000_000.0)


# ============================================================================
# RISK GATES (Data-Driven)
# ============================================================================

# Liquidity Gate - ADJUSTED: $25k threshold for better signal flow
USE_LIQUIDITY_FILTER = _get_bool("USE_LIQUIDITY_FILTER", True)
MIN_LIQUIDITY_USD = _get_float("MIN_LIQUIDITY_USD", min(
    max(_get_float("MIN_LIQUIDITY_USD_RAW", 25000.0), 25000.0),
    50000.0
))
EXCELLENT_LIQUIDITY_USD = _get_float("EXCELLENT_LIQUIDITY_USD", 50000.0)

# Volume to Liquidity Ratio
VOL_TO_LIQ_RATIO_MIN = _get_float("VOL_TO_LIQ_RATIO_MIN", 0.0)

# Security Gates
REQUIRE_LP_LOCKED = _get_bool("REQUIRE_LP_LOCKED", False)
REQUIRE_MINT_REVOKED = _get_bool("REQUIRE_MINT_REVOKED", False)
ALLOW_UNKNOWN_SECURITY = _get_bool("ALLOW_UNKNOWN_SECURITY", True)

# Holder Concentration - CRITICAL: Tightened to 18%
MAX_TOP10_CONCENTRATION = _get_float("MAX_TOP10_CONCENTRATION", 18.0)
MAX_BUNDLERS_PERCENT = _get_float("MAX_BUNDLERS_PERCENT", 100.0)
MAX_INSIDERS_PERCENT = _get_float("MAX_INSIDERS_PERCENT", 100.0)

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

# Cycle Balance
SMART_CYCLE_MIN_SCORE = _get_int("SMART_CYCLE_MIN_SCORE", 5)
GENERAL_CYCLE_MIN_SCORE = _get_int("GENERAL_CYCLE_MIN_SCORE", 6)  # ADJUSTED for better flow

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
        "HIGH_CONFIDENCE_SCORE": 5,
        "GENERAL_CYCLE_MIN_SCORE": 5,
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

