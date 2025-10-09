# notify.py
import time
import json
import os
from config.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED
from config.config import HTTP_TIMEOUT_TELEGRAM
from app.http_client import request_json


# Redis client for signal passing (optional, graceful fallback if not available)
_REDIS_URL = os.getenv("REDIS_URL") or os.getenv("CALLSBOT_REDIS_URL") or ""
_redis_client = None
if _REDIS_URL:
    try:
        import redis  # type: ignore
        _redis_client = redis.from_url(_REDIS_URL, decode_responses=True)
        # Test connection
        _redis_client.ping()
    except Exception as e:
        print(f"⚠️ Redis not available for signal passing: {e}")
        _redis_client = None


def push_signal_to_redis(signal_data: dict) -> bool:
    """Push trading signal to Redis for real-time consumption by trader.
    
    Args:
        signal_data: Dict containing token, score, conviction, price, liquidity, etc.
    
    Returns:
        True if pushed successfully, False otherwise
    """
    if _redis_client is None:
        return False
    
    try:
        # Push to Redis list with 1 hour expiration
        payload = json.dumps(signal_data)
        _redis_client.lpush("trading_signals", payload)
        # Trim list to last 1000 signals to prevent unbounded growth
        _redis_client.ltrim("trading_signals", 0, 999)
        return True
    except Exception as e:
        print(f"⚠️ Failed to push signal to Redis: {e}")
        return False


def send_telegram_alert(message: str) -> bool:
    if not message or not message.strip():
        print("Error: Empty message provided")
        return False

    # If Telegram is not configured, no-op so the rest of the pipeline continues
    if not TELEGRAM_ENABLED:
        return True

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",  # Allow HTML formatting
    }

    max_retries = 3
    for attempt in range(max_retries):
        result = request_json("POST", url, json=data, timeout=HTTP_TIMEOUT_TELEGRAM)
        status = result.get("status_code")
        if status == 200:
            print("✅ Telegram message sent successfully")
            return True
        elif status == 429:
            print(f"Telegram rate limited, waiting... (attempt {attempt + 1})")
            time.sleep(2 ** attempt)
            continue
        elif status is None:
            print(f"Request exception on Telegram attempt {attempt + 1}: {result.get('error')}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
        else:
            txt = result.get("text") if result.get("json") is None else None
            print(f"Error sending Telegram message: {status}, {txt}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
    print(f"Failed to send Telegram message after {max_retries} attempts")
    return False
