# notify.py
import requests
import time
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

def send_telegram_alert(message):
    if not message or not message.strip():
        print("Error: Empty message provided")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",  # Allow HTML formatting
    }
    
    # Add timeout and retry logic
    max_retries = 3
    timeout = 10
    
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, json=data, timeout=timeout)
            if resp.status_code == 200:
                print("✅ Telegram message sent successfully")
                return True
            elif resp.status_code == 429:  # Rate limited
                print(f"Telegram rate limited, waiting... (attempt {attempt + 1})")
                time.sleep(2 ** attempt)
                continue
            else:
                print(f"Error sending Telegram message: {resp.status_code}, {resp.text}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
        except requests.exceptions.RequestException as e:
            print(f"Request exception on Telegram attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
    
    print(f"Failed to send Telegram message after {max_retries} attempts")
    return False
