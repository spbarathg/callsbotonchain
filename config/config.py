# config.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ==============================================
# CIELO API INTEGRATION
# ==============================================
# Treat CIELO key as optional; when missing, code paths will rely on fallbacks
CIELO_API_KEY = os.getenv("CIELO_API_KEY", "")

# ==============================================
# TELEGRAM PUBLISHER SETTINGS (optional)
# ==============================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# If either is missing, treat Telegram as disabled; do not raise
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# ==============================================
# BOT SETTINGS
# ==============================================
try:
    # ADJUSTED: Set to 5 to allow more signals through (was blocking everything at 7)
    HIGH_CONFIDENCE_SCORE = int(os.getenv("HIGH_CONFIDENCE_SCORE", "5"))
    MIN_USD_VALUE = int(os.getenv("MIN_USD_VALUE", "200"))
    FETCH_INTERVAL = int(os.getenv("FETCH_INTERVAL", "120"))
    # Optional feed scoping
    _list_id_raw = os.getenv("CIELO_LIST_ID")
    if _list_id_raw is not None and _list_id_raw != "":
        CIELO_LIST_ID = int(_list_id_raw)
    else:
        CIELO_LIST_ID = None
    # Optional: support multiple list ids via comma-separated env
    _list_ids_raw = os.getenv("CIELO_LIST_IDS", "")
    CIELO_LIST_IDS = []
    if _list_ids_raw:
        parts = [p.strip() for p in _list_ids_raw.split(",") if p.strip()]
        for p in parts:
            try:
                CIELO_LIST_IDS.append(int(p))
            except ValueError:
                continue
    CIELO_NEW_TRADE_ONLY = os.getenv("CIELO_NEW_TRADE_ONLY", "false").lower() == "true"
    DEBUG_PRELIM = os.getenv("DEBUG_PRELIM", "false").lower() == "true"
except ValueError as e:
    raise ValueError(f"Invalid numeric value in .env file: {e}")

# Validate settings
if HIGH_CONFIDENCE_SCORE < 1 or HIGH_CONFIDENCE_SCORE > 10:
    raise ValueError("HIGH_CONFIDENCE_SCORE must be between 1 and 10")

if MIN_USD_VALUE < 0:
    raise ValueError("MIN_USD_VALUE must be positive")

if FETCH_INTERVAL < 30:
    raise ValueError("FETCH_INTERVAL should be at least 30 seconds to avoid rate limiting")

# ==============================================
# HTTP/NETWORK SETTINGS
# ==============================================
# Centralize HTTP knobs to tune behavior without code changes
HTTP_TIMEOUT_FEED = int(os.getenv("HTTP_TIMEOUT_FEED", "10"))
HTTP_TIMEOUT_STATS = int(os.getenv("HTTP_TIMEOUT_STATS", "20"))
HTTP_TIMEOUT_TELEGRAM = int(os.getenv("HTTP_TIMEOUT_TELEGRAM", "10"))
HTTP_MAX_RETRIES = int(os.getenv("HTTP_MAX_RETRIES", "3"))
HTTP_BACKOFF_FACTOR = float(os.getenv("HTTP_BACKOFF_FACTOR", "0.5"))

# ==============================================
# BUDGET / CREDITS CONTROL
# ==============================================
BUDGET_ENABLED = os.getenv("BUDGET_ENABLED", "true").lower() == "true"
BUDGET_PER_MINUTE_MAX = int(os.getenv("BUDGET_PER_MINUTE_MAX", "60"))  # 1 req/sec avg
BUDGET_PER_DAY_MAX = int(os.getenv("BUDGET_PER_DAY_MAX", "5000"))      # daily ceiling
BUDGET_FEED_COST = int(os.getenv("BUDGET_FEED_COST", "1"))
BUDGET_STATS_COST = int(os.getenv("BUDGET_STATS_COST", "1"))
BUDGET_HARD_BLOCK = os.getenv("BUDGET_HARD_BLOCK", "true").lower() == "true"
CALLSBOT_BUDGET_FILE = os.getenv("CALLSBOT_BUDGET_FILE", os.path.join(
    os.path.dirname(__file__), "var", "credits_budget.json"))

# ==============================================
# SCORING THRESHOLDS (override via .env)
# ==============================================


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


# Preliminary USD thresholds
PRELIM_USD_HIGH = _get_int("PRELIM_USD_HIGH", 2000)
PRELIM_USD_MID = _get_int("PRELIM_USD_MID", 750)
PRELIM_USD_LOW = _get_int("PRELIM_USD_LOW", 250)

# Market cap buckets (USD)
MCAP_MICRO_MAX = _get_int("MCAP_MICRO_MAX", 100_000)
MCAP_SMALL_MAX = _get_int("MCAP_SMALL_MAX", 1_000_000)
MCAP_MID_MAX = _get_int("MCAP_MID_MAX", 10_000_000)

# 24h Volume thresholds (USD)
# ADJUSTED: Based on analysis - moonshots had median volume of $63k
# Lowered from 100k/50k/10k to 60k/30k/5k for better signal capture
VOL_VERY_HIGH = _get_int("VOL_VERY_HIGH", 60_000)
VOL_HIGH = _get_int("VOL_HIGH", 30_000)
VOL_MED = _get_int("VOL_MED", 5_000)

# Momentum thresholds (%)
MOMENTUM_1H_STRONG = _get_int("MOMENTUM_1H_STRONG", 5)
DRAW_24H_MAJOR = _get_int("DRAW_24H_MAJOR", -80)

# Holder concentration threshold (%)
TOP10_CONCERN = _get_int("TOP10_CONCERN", 40)

# Detailed fetch decision thresholds
# CRITICAL FIX: Raised from 3 to 5 to prevent wasting credits on tokens that score 5-6 but need 7+
# Analysis showed tokens with prelim 3 get detailed score of 5-6, which are then REJECTED
PRELIM_DETAILED_MIN = _get_int("PRELIM_DETAILED_MIN", 5)
PRELIM_VELOCITY_MIN_SCORE = _get_int("PRELIM_VELOCITY_MIN_SCORE", 3)
VELOCITY_REQUIRED = _get_int("VELOCITY_REQUIRED", 5)

# ==============================================
# STORAGE SETTINGS
# ==============================================
# Keep DB local; if env not set, put under var/ (ignored)
DB_FILE = os.getenv("CALLSBOT_DB_FILE", os.path.join(os.path.dirname(os.path.dirname(__file__)), "var", "alerted_tokens.db"))
DB_RETENTION_HOURS = _get_int("DB_RETENTION_HOURS", 2160)  # default ~90 days

# ==============================================
# FEATURE FLAGS
# ==============================================
CIELO_DISABLE_STATS = os.getenv("CIELO_DISABLE_STATS", "false").lower() == "true"

# Telegram throttling
TELEGRAM_ALERT_MIN_INTERVAL = _get_int("TELEGRAM_ALERT_MIN_INTERVAL", 0)  # seconds

# ==============================================
# TRACKING SETTINGS
# ==============================================
# IMPROVED: Track every 30 seconds instead of 60 to capture pump speed data
# Analysis showed we were missing 86% of timing data - this will help
TRACK_INTERVAL_MIN = _get_int("TRACK_INTERVAL_MIN", 30)
TRACK_BATCH_SIZE = _get_int("TRACK_BATCH_SIZE", 25)

# ==============================================
# TOKEN FILTERS / GATES
# ==============================================
# Comma-separated lists; defaults cover common Solana majors/stables
_stable_mints_env = os.getenv(
    "STABLE_MINTS",
    ",".join([
        # USDC, USDT, wSOL (Solana)
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
        "So11111111111111111111111111111111111111112",  # wSOL
    ])
)
STABLE_MINTS = [m.strip() for m in _stable_mints_env.split(",") if m.strip()]

_block_syms_env = os.getenv(
    "BLOCKLIST_SYMBOLS",
    ",".join(["USDC", "USDT", "SOL", "WSOL", "WBTC", "BTC", "ETH", "WETH"])
)
BLOCKLIST_SYMBOLS = [s.strip().upper() for s in _block_syms_env.split(",") if s.strip()]

# Cap gating: prefer microcaps; gate very large caps unless high momentum or smart-money
MAX_MARKET_CAP_FOR_DEFAULT_ALERT = _get_int("MAX_MARKET_CAP_FOR_DEFAULT_ALERT", 1_500_000)
LARGE_CAP_MOMENTUM_GATE_1H = _get_int("LARGE_CAP_MOMENTUM_GATE_1H", 15)

# ==============================================
# RISK GATES (STRICT MODE)
# ==============================================
# Minimum on-chain liquidity required to alert (USD)
# ADJUSTED: Based on analysis - moonshots had median liquidity of $117k vs losers $30k
# Raised from 8k to 30k to filter out low-liquidity rugs
MIN_LIQUIDITY_USD = _get_int("MIN_LIQUIDITY_USD", 30_000)

# Minimum 24h volume required (USD)
# ADJUSTED: Kept low for new tokens, volume builds over time
VOL_24H_MIN_FOR_ALERT = _get_int("VOL_24H_MIN_FOR_ALERT", 2_000)

# ==============================================
# SIGNAL BALANCE (Smart Money vs General Cycle)
# ==============================================

# Require smart-money cycle for final alert
# If True, drops all non-smart-money tokens no matter how high they score
# Recommendation: Set to FALSE to allow high-quality general cycle tokens
# ADJUSTED: Based on analysis, non-smart money outperforms (3.03x vs 1.12x)
REQUIRE_SMART_MONEY_FOR_ALERT = os.getenv("REQUIRE_SMART_MONEY_FOR_ALERT", "false").lower() == "true"

# Score adjustment for smart money tokens - SET TO 0 (was 2)
# Analysis shows smart money detection doesn't predict success
# Smart money tokens get this bonus to their final score
SMART_MONEY_SCORE_BONUS = _get_int("SMART_MONEY_SCORE_BONUS", 0)

# For general cycle (non-smart money), require higher score
# ADJUSTED: Reduced from 9 to 7 based on analysis showing score 7 has 20% win rate
# Score 7 was the most consistent performer in the data
GENERAL_CYCLE_MIN_SCORE = _get_int("GENERAL_CYCLE_MIN_SCORE", 7)

# Require minimum velocity score for final alert (0 disables)
REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT = _get_int("REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT", 0)

# Security requirements (only enforce when security data is available)
REQUIRE_MINT_REVOKED = os.getenv("REQUIRE_MINT_REVOKED", "false").lower() == "true"
REQUIRE_LP_LOCKED = os.getenv("REQUIRE_LP_LOCKED", "false").lower() == "true"

# If security fields are unknown (e.g., DexScreener fallback), should we allow?
ALLOW_UNKNOWN_SECURITY = os.getenv("ALLOW_UNKNOWN_SECURITY", "true").lower() == "true"

# Maximum acceptable top-10 holders concentration (%). Above this → drop
# CRITICAL: Tightened from 22% to 18% - high concentration = rug risk
MAX_TOP10_CONCENTRATION = _get_int("MAX_TOP10_CONCENTRATION", 18)

# Volume-to-MCap ratio minimum gate (e.g., 0.5 means 24h vol >= 50% of mcap)
# CRITICAL: Kept at 0.60 - this is already good
VOL_TO_MCAP_RATIO_MIN = _get_float("VOL_TO_MCAP_RATIO_MIN", 0.60)  # 0 disables

# Momentum gate for tight mode (require at least this 1h change for alert)
# ADJUSTED: Reduced from 2% to 0% - was blocking all new tokens
REQUIRE_MOMENTUM_1H_MIN_FOR_ALERT = _get_int("REQUIRE_MOMENTUM_1H_MIN_FOR_ALERT", 0)

# Super-high volume threshold to allow momentum leniency in loose mode
VOL_SUPER_HIGH = _get_int("VOL_SUPER_HIGH", 100_000)

# Microcap sweet band bonus
MICROCAP_SWEET_MIN = _get_int("MICROCAP_SWEET_MIN", 10_000)
MICROCAP_SWEET_MAX = _get_int("MICROCAP_SWEET_MAX", 50_000)

# Extra kicker threshold for strong pumpers
MOMENTUM_1H_PUMPER = _get_int("MOMENTUM_1H_PUMPER", 20)

# ==============================================
# RISK GATES (NUANCED MODE FACTORS)
# ==============================================
# Relaxed thresholds for the nuanced evaluation path
NUANCED_SCORE_REDUCTION = _get_int("NUANCED_SCORE_REDUCTION", 1)
NUANCED_LIQUIDITY_FACTOR = _get_float("NUANCED_LIQUIDITY_FACTOR", 0.5)
NUANCED_VOL_TO_MCAP_FACTOR = _get_float("NUANCED_VOL_TO_MCAP_FACTOR", 0.7)
NUANCED_MCAP_FACTOR = _get_float("NUANCED_MCAP_FACTOR", 1.5)
NUANCED_TOP10_CONCENTRATION_BUFFER = _get_int("NUANCED_TOP10_CONCENTRATION_BUFFER", 10)

# Additional holder-composition risk thresholds
# If bundlers/insiders percentages are available from stats, apply strict caps
MAX_BUNDLERS_PERCENT = _get_float("MAX_BUNDLERS_PERCENT", 75.0)
MAX_INSIDERS_PERCENT = _get_float("MAX_INSIDERS_PERCENT", 35.0)
# Nuanced buffers allow slightly higher share than strict
NUANCED_BUNDLERS_BUFFER = _get_float("NUANCED_BUNDLERS_BUFFER", 5.0)
NUANCED_INSIDERS_BUFFER = _get_float("NUANCED_INSIDERS_BUFFER", 5.0)

# Require holder stats for large-cap alerts (avoid blind calls on big tokens)
REQUIRE_HOLDER_STATS_FOR_LARGE_CAP_ALERT = os.getenv(
    "REQUIRE_HOLDER_STATS_FOR_LARGE_CAP_ALERT", "false"
).lower() == "true"
LARGE_CAP_HOLDER_STATS_MCAP_USD = _get_int("LARGE_CAP_HOLDER_STATS_MCAP_USD", 2_000_000)

# ==============================================
# FEED INTELLIGENCE (PHASE 1/2)
# ==============================================
# Multi-signal confirmation before spending expensive stats calls
REQUIRE_MULTI_SIGNAL = os.getenv("REQUIRE_MULTI_SIGNAL", "true").lower() == "true"
MULTI_SIGNAL_WINDOW_SEC = _get_int("MULTI_SIGNAL_WINDOW_SEC", 1800)  # 30 minutes
MULTI_SIGNAL_MIN_COUNT = _get_int("MULTI_SIGNAL_MIN_COUNT", 2)

# Token age preferences using first-seen heuristic
# 0 disables minimum age requirement
MIN_TOKEN_AGE_MINUTES = _get_int("MIN_TOKEN_AGE_MINUTES", 0)
OPTIMAL_TOKEN_AGE_MAX_HOURS = _get_int("OPTIMAL_TOKEN_AGE_MAX_HOURS", 24)

# Smart-money feed wallet quality thresholds
CIELO_MIN_WALLET_PNL = _get_int("CIELO_MIN_WALLET_PNL", 10_000)
CIELO_MIN_TRADES = _get_int("CIELO_MIN_TRADES", 0)  # optional; 0 disables
CIELO_MIN_WIN_RATE = _get_int("CIELO_MIN_WIN_RATE", 0)  # percent; 0 disables

# Optional enforcement switches for holder-composition caps
ENFORCE_BUNDLER_CAP = os.getenv("ENFORCE_BUNDLER_CAP", "false").lower() == "true"
ENFORCE_INSIDER_CAP = os.getenv("ENFORCE_INSIDER_CAP", "false").lower() == "true"

# Rug/outcome heuristics
RUG_DRAWDOWN_PCT = _get_float("RUG_DRAWDOWN_PCT", 90.0)  # price drop from peak (%) to call a rug
RUG_MIN_LIQUIDITY_USD = _get_int("RUG_MIN_LIQUIDITY_USD", 1)  # <= this treated as vanished LP

# ==============================================
# GATE MODE (Tiered defaults via env)
# ==============================================
# ADJUSTED based on analysis: score 7 optimal, liquidity $30k+ critical
# TIER1 (High Confidence): score>=8, liq>=50k, mcap<=1.5M (strictest)
# TIER2 (Balanced Default): score>=7, liq>=30k, mcap<=1.5M (moonshot sweet spot)
# TIER3 (Exploratory/Relax): score>=6, liq>=20k, mcap<=5M (wider net)
GATE_MODE = (os.getenv("GATE_MODE", "DISABLED") or "DISABLED").upper()

GATE_PRESETS = {
    "TIER1": {
        "HIGH_CONFIDENCE_SCORE": 8,
        "MIN_LIQUIDITY_USD": 50_000,
        "VOL_24H_MIN_FOR_ALERT": 30_000,
        "MAX_MARKET_CAP_FOR_DEFAULT_ALERT": 1_500_000,
        "VOL_TO_MCAP_RATIO_MIN": 0.50,
    },
    "TIER2": {
        "HIGH_CONFIDENCE_SCORE": 7,
        "MIN_LIQUIDITY_USD": 30_000,
        "VOL_24H_MIN_FOR_ALERT": 0,
        "MAX_MARKET_CAP_FOR_DEFAULT_ALERT": 1_500_000,
        "VOL_TO_MCAP_RATIO_MIN": 0.40,
    },
    "TIER3": {
        "HIGH_CONFIDENCE_SCORE": 6,
        "MIN_LIQUIDITY_USD": 20_000,
        "VOL_24H_MIN_FOR_ALERT": 0,
        "MAX_MARKET_CAP_FOR_DEFAULT_ALERT": 5_000_000,
        "VOL_TO_MCAP_RATIO_MIN": 0.30,
    },
}


def _apply_gate_mode_overrides() -> None:
    """Apply gate preset only when a value was NOT explicitly provided via env.

    Rule: ENV > PRESET. This prevents unwanted overriding of tuned .env values
    on every startup when GATE_MODE is set.
    """
    global HIGH_CONFIDENCE_SCORE, MIN_LIQUIDITY_USD, VOL_24H_MIN_FOR_ALERT
    global MAX_MARKET_CAP_FOR_DEFAULT_ALERT, VOL_TO_MCAP_RATIO_MIN
    preset = GATE_PRESETS.get(GATE_MODE)
    if not preset:
        return
    # Helper to detect whether user explicitly set a key

    def _has_env(name: str) -> bool:
        return os.getenv(name) is not None and os.getenv(name) != ""

    if not _has_env("HIGH_CONFIDENCE_SCORE"):
        HIGH_CONFIDENCE_SCORE = preset["HIGH_CONFIDENCE_SCORE"]
    if not _has_env("MIN_LIQUIDITY_USD"):
        MIN_LIQUIDITY_USD = preset["MIN_LIQUIDITY_USD"]
    if not _has_env("VOL_24H_MIN_FOR_ALERT"):
        VOL_24H_MIN_FOR_ALERT = preset["VOL_24H_MIN_FOR_ALERT"]
    if not _has_env("MAX_MARKET_CAP_FOR_DEFAULT_ALERT"):
        MAX_MARKET_CAP_FOR_DEFAULT_ALERT = preset["MAX_MARKET_CAP_FOR_DEFAULT_ALERT"]
    if not _has_env("VOL_TO_MCAP_RATIO_MIN"):
        VOL_TO_MCAP_RATIO_MIN = preset["VOL_TO_MCAP_RATIO_MIN"]


_apply_gate_mode_overrides()

# Snapshot for logging/monitoring
CURRENT_GATES = {
    "GATE_MODE": GATE_MODE,
    "HIGH_CONFIDENCE_SCORE": HIGH_CONFIDENCE_SCORE,
    "MIN_LIQUIDITY_USD": MIN_LIQUIDITY_USD,
    "VOL_24H_MIN_FOR_ALERT": VOL_24H_MIN_FOR_ALERT,
    "MAX_MARKET_CAP_FOR_DEFAULT_ALERT": MAX_MARKET_CAP_FOR_DEFAULT_ALERT,
    "VOL_TO_MCAP_RATIO_MIN": VOL_TO_MCAP_RATIO_MIN,
    "REQUIRE_MINT_REVOKED": REQUIRE_MINT_REVOKED,
    "REQUIRE_LP_LOCKED": REQUIRE_LP_LOCKED,
}
