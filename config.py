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
    HIGH_CONFIDENCE_SCORE = int(os.getenv("HIGH_CONFIDENCE_SCORE", "8"))
    MIN_USD_VALUE = int(os.getenv("MIN_USD_VALUE", "100"))
    FETCH_INTERVAL = int(os.getenv("FETCH_INTERVAL", "120"))
except ValueError as e:
    raise ValueError(f"Invalid numeric value in .env file: {e}")

# Validate settings
if HIGH_CONFIDENCE_SCORE < 1 or HIGH_CONFIDENCE_SCORE > 10:
    raise ValueError("HIGH_CONFIDENCE_SCORE must be between 1 and 10")

if MIN_USD_VALUE < 0:
    raise ValueError("MIN_USD_VALUE must be positive")

if FETCH_INTERVAL < 60:
    raise ValueError("FETCH_INTERVAL should be at least 60 seconds to avoid rate limiting")
