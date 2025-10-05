# notify.py
import time
from config.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED
from config.config import HTTP_TIMEOUT_TELEGRAM
from app.http_client import request_json


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
