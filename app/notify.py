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
_redis_status = "not_configured"

def _create_redis_client():
    try:
        import socket
        import redis  # type: ignore
        from redis.retry import Retry  # type: ignore
        from redis.backoff import ExponentialBackoff  # type: ignore
        from redis.connection import ConnectionPool  # type: ignore
        retry = Retry(ExponentialBackoff(), 3)
        pool = ConnectionPool.from_url(
            _REDIS_URL,
            decode_responses=True,
            max_connections=10,
            socket_keepalive=True,
            socket_keepalive_options={
                getattr(socket, 'TCP_KEEPIDLE', 3): 60,
                getattr(socket, 'TCP_KEEPINTVL', 4): 10,
                getattr(socket, 'TCP_KEEPCNT', 6): 3,
            },
            retry=retry,
        )
        return redis.Redis(connection_pool=pool)
    except Exception as e:
        print(f"⚠️ Redis client creation failed: {e}")
        return None

if _REDIS_URL:
    _redis_client = _create_redis_client()
    if _redis_client is not None:
        try:
            _redis_client.ping()
            _redis_status = "connected"
            # Avoid logging full URL which may include credentials
            try:
                from urllib.parse import urlparse
                _host = urlparse(_REDIS_URL).hostname or "redis"
                print(f"✅ Redis client connected successfully (host={_host})")
            except Exception:
                print("✅ Redis client connected successfully")
        except Exception as e:
            print(f"⚠️ Redis not available for signal passing: {e}")
            _redis_client = None
            _redis_status = f"failed"
else:
    print("⚠️ REDIS_URL not configured, signal passing to paper trader disabled")

def get_redis_status() -> str:
    """Return current Redis connection status."""
    return _redis_status


def push_signal_to_redis(signal_data: dict) -> bool:
    """Push trading signal to Redis for real-time consumption by trader.
    
    Args:
        signal_data: Dict containing token, score, conviction, price, liquidity, etc.
    
    Returns:
        True if pushed successfully, False otherwise
    """
    if _redis_client is None:
        print(f"⚠️ Cannot push signal to Redis: client not connected (status: {_redis_status})")
        return False
    
    try:
        # Push to Redis list with bounded size
        payload = json.dumps(signal_data)
        _redis_client.lpush("trading_signals", payload)
        _redis_client.ltrim("trading_signals", 0, 999)
        return True
    except Exception as e:
        # Retry basic reconnect once
        try:
            print(f"⚠️ Redis push failed, attempting reconnect: {e}")
            client = _create_redis_client()
            if client is not None:
                globals()["_redis_client"] = client
                client.ping()
                payload = json.dumps(signal_data)
                client.lpush("trading_signals", payload)
                client.ltrim("trading_signals", 0, 999)
                return True
        except Exception as e2:
            print(f"⚠️ Failed to push signal to Redis after reconnect: {e2}")
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
