"""
Birdeye API client with global rate limiting (Lite plan safe defaults).
"""
import time
import threading
from typing import Dict, Any, Optional

from app.config_unified import BIRDEYE_API_KEY, BIRDEYE_RPS
from app.http_client import request_json


_rate_lock = threading.Lock()
_request_times: list[float] = []


def _enforce_rate_limit(rps_limit: int) -> None:
    if rps_limit <= 0:
        return
    with _rate_lock:
        now = time.time()
        cutoff = now - 1.0
        global _request_times
        _request_times = [t for t in _request_times if t > cutoff]
        if len(_request_times) >= rps_limit:
            oldest = _request_times[0]
            wait_time = 1.0 - (now - oldest)
            if wait_time > 0:
                time.sleep(wait_time)
                now = time.time()
                cutoff = now - 1.0
                _request_times = [t for t in _request_times if t > cutoff]
        _request_times.append(time.time())


def birdeye_enabled() -> bool:
    return bool(BIRDEYE_API_KEY)


def get_price(token_address: str) -> Dict[str, Any]:
    """
    Fetch token price from Birdeye.
    Returns dict with price in USD if available.
    """
    if not birdeye_enabled():
        return {}
    _enforce_rate_limit(max(1, int(BIRDEYE_RPS or 0)))
    url = "https://public-api.birdeye.so/defi/price"
    headers = {"X-API-KEY": BIRDEYE_API_KEY}
    result = request_json("GET", url, params={"address": token_address}, headers=headers, timeout=10)
    if result.get("status_code") != 200:
        return {}
    data = result.get("json") or {}
    price = ((data.get("data") or {}).get("value"))
    if not price:
        return {}
    try:
        price_usd = float(price)
    except Exception:
        return {}
    return {
        "price": {
            "price_usd": price_usd,
            "price_change_1h": 0,
            "price_change_6h": 0,
            "price_change_24h": 0,
        },
        "source": "birdeye",
    }
