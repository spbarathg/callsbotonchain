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
except ValueError as e:
    raise ValueError(f"Invalid numeric value in .env file: {e}")

# Validate settings
if HIGH_CONFIDENCE_SCORE < 1 or HIGH_CONFIDENCE_SCORE > 10:
    raise ValueError("HIGH_CONFIDENCE_SCORE must be between 1 and 10")

if MIN_USD_VALUE < 0:
    raise ValueError("MIN_USD_VALUE must be positive")

if FETCH_INTERVAL < 30:
    raise ValueError("FETCH_INTERVAL should be at least 30 seconds to avoid rate limiting")
