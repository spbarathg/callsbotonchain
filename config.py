# config.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ==============================================
# CIELO API INTEGRATION
# ==============================================
CIELO_API_KEY = os.getenv("CIELO_API_KEY")
if not CIELO_API_KEY:
    raise ValueError("CIELO_API_KEY is required in .env file")

# ==============================================
# TELEGRAM PUBLISHER SETTINGS
# ==============================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required in .env file")

# ==============================================
# BOT SETTINGS
# ==============================================
try:
    HIGH_CONFIDENCE_SCORE = int(os.getenv("HIGH_CONFIDENCE_SCORE", "6"))
    MIN_USD_VALUE = int(os.getenv("MIN_USD_VALUE", "100"))
    FETCH_INTERVAL = int(os.getenv("FETCH_INTERVAL", "120"))
    # Optional feed scoping
    _list_id_raw = os.getenv("CIELO_LIST_ID")
    if _list_id_raw is not None and _list_id_raw != "":
        CIELO_LIST_ID = int(_list_id_raw)
    else:
        CIELO_LIST_ID = None
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
# SCORING THRESHOLDS (override via .env)
# ==============================================
def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
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
VOL_VERY_HIGH = _get_int("VOL_VERY_HIGH", 100_000)
VOL_HIGH = _get_int("VOL_HIGH", 50_000)
VOL_MED = _get_int("VOL_MED", 10_000)

# Momentum thresholds (%)
MOMENTUM_1H_STRONG = _get_int("MOMENTUM_1H_STRONG", 5)
DRAW_24H_MAJOR = _get_int("DRAW_24H_MAJOR", -80)

# Holder concentration threshold (%)
TOP10_CONCERN = _get_int("TOP10_CONCERN", 40)

# Detailed fetch decision thresholds
PRELIM_DETAILED_MIN = _get_int("PRELIM_DETAILED_MIN", 6)
PRELIM_VELOCITY_MIN_SCORE = _get_int("PRELIM_VELOCITY_MIN_SCORE", 3)
VELOCITY_REQUIRED = _get_int("VELOCITY_REQUIRED", 5)

# ==============================================
# STORAGE SETTINGS
# ==============================================
DB_FILE = os.getenv("CALLSBOT_DB_FILE", "alerted_tokens.db")
DB_RETENTION_HOURS = _get_int("DB_RETENTION_HOURS", 72)

# ==============================================
# FEATURE FLAGS
# ==============================================
CIELO_DISABLE_STATS = os.getenv("CIELO_DISABLE_STATS", "false").lower() == "true"

# Telegram throttling
TELEGRAM_ALERT_MIN_INTERVAL = _get_int("TELEGRAM_ALERT_MIN_INTERVAL", 0)  # seconds

# ==============================================
# TRACKING SETTINGS
# ==============================================
TRACK_INTERVAL_MIN = _get_int("TRACK_INTERVAL_MIN", 60)
TRACK_BATCH_SIZE = _get_int("TRACK_BATCH_SIZE", 25)