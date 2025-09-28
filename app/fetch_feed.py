# fetch_feed.py
import time
from datetime import datetime, timezone
from typing import Optional
from config import CIELO_API_KEY, MIN_USD_VALUE, CIELO_LIST_ID, CIELO_NEW_TRADE_ONLY
from config import HTTP_TIMEOUT_FEED
from app.http_client import request_json
from app.budget import get_budget
try:
    from config import CIELO_LIST_IDS  # optional multi-list support
except Exception:
    CIELO_LIST_IDS = []

def _parse_retry_after_seconds(resp: requests.Response) -> Optional[int]:
    """
    Try to determine how long to wait from rate limit headers.
    Supports standard Retry-After seconds and epoch reset headers.
    Returns None if not determinable.
    """
    # Standard header with seconds or HTTP-date
    ra = resp.headers.get("Retry-After")
    if ra:
        try:
            # Prefer integer seconds if provided
            return int(float(ra))
        except Exception:
            # If it's a date format, try to parse to epoch seconds
            try:
                reset_dt = datetime.strptime(ra, "%a, %d %b %Y %H:%M:%S %Z")
                now = datetime.now(timezone.utc)
                return max(0, int((reset_dt - now).total_seconds()))
            except Exception:
                pass

    # Common vendor-specific headers with epoch seconds
    for key in ("X-RateLimit-Reset", "X-RateLimit-Reset-At", "X-Ratelimit-Reset", "RateLimit-Reset"):
        val = resp.headers.get(key)
        if not val:
            continue
        try:
            reset_epoch = int(float(val))
            now_epoch = int(time.time())
            return max(0, reset_epoch - now_epoch)
        except Exception:
            continue
    return None


from typing import Dict, Any


def fetch_solana_feed(cursor=None, smart_money_only: bool = False) -> Dict[str, Any]:
    url = "https://feed-api.cielo.finance/api/v1/feed"
    
    # Base parameters (keep minimal to maximize visibility)
    params = {
        "limit": 100,
        "chains": "solana",
        "cursor": cursor
    }
    # Only include minimum_usd_value if configured > 0
    if MIN_USD_VALUE and MIN_USD_VALUE > 0:
        params["minimum_usd_value"] = MIN_USD_VALUE
    # Multi-list support: if CIELO_LIST_IDS present, prefer it; else fallback to single CIELO_LIST_ID
    if CIELO_LIST_IDS:
        params["list_id"] = ",".join(str(x) for x in CIELO_LIST_IDS)
    elif CIELO_LIST_ID is not None:
        params["list_id"] = CIELO_LIST_ID
    if CIELO_NEW_TRADE_ONLY:
        params["new_trade"] = "true"
    
    # Add smart money filters for enhanced detection
    if smart_money_only:
        params.update({
            "smart_money": "true",
            "min_wallet_pnl": "1000",  # Only profitable wallets
            "top_wallets": "true"
        })
        print("🧠 Fetching SMART MONEY activity...")
    else:
        print("📡 Fetching general feed...")

    # Respect configured MIN_USD_VALUE as-is to maximize visibility
    # Header name should be case-insensitive, keep canonical spelling
    # Cielo is case-insensitive, but align with other modules using X-API-Key
    headers = {"X-API-Key": CIELO_API_KEY}
    
    last_retry_after: Optional[int] = None
    quota_exceeded = False
    max_retries = 3
    # Budget check (treat feed as low-cost but enforce cap)
    try:
        b = get_budget()
        if not b.can_spend("feed"):
            return {"transactions": [], "next_cursor": None, "error": "budget_exceeded"}
    except Exception:
        pass
    for attempt in range(max_retries):
        result = request_json("GET", url, params=params, headers=headers, timeout=HTTP_TIMEOUT_FEED)
        status = result.get("status_code")
        if status == 200:
            try:
                get_budget().spend("feed")
            except Exception:
                pass
            api_response = result.get("json") or {}
            try:
                # Convert Cielo API format to expected format
                if api_response.get("status") == "ok" and "data" in api_response:
                    data = api_response["data"]
                    items = data.get("items") if isinstance(data, dict) else None
                    if items is None and isinstance(api_response.get("data"), list):
                        items = api_response["data"]
                    return {
                        "transactions": items or [],
                        "next_cursor": (data.get("paging", {}).get("next_cursor")
                                         if isinstance(data, dict) else None),
                        "error": None,
                    }
            except Exception:
                pass
            # Unexpected shape but still HTTP 200
            return {
                "transactions": [],
                "next_cursor": None,
                "error": "unexpected_response_shape",
            }
        elif status == 429:
            body = result.get("json") or {}
            msg = (body.get("message") or "").lower()
            if "maximum api credit" in msg or "quota" in msg:
                quota_exceeded = True
            # Build a fake response-like for header parsing compatibility
            class _R:
                def __init__(self, headers):
                    self.headers = headers
            retry_after = _parse_retry_after_seconds(_R(result.get("headers") or {}))
            if retry_after is not None:
                last_retry_after = max(last_retry_after or 0, retry_after)
            print(f"Rate limited, waiting before retry... (attempt {attempt + 1})")
            time.sleep(retry_after if retry_after is not None else (2 ** attempt))
            continue
        elif status is None:
            print(f"Network exception on attempt {attempt + 1}: {result.get('error')}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return {"transactions": [], "next_cursor": None, "error": "network_exception"}
        else:
            text = None
            if result.get("json") is None:
                text = (result.get("text") or "")
            print(f"Error fetching feed: {status}, {text}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            return {"transactions": [], "next_cursor": None, "error": f"http_{status}"}
    
    # All retries failed
    print(f"Failed to fetch feed after {max_retries} attempts")
    if last_retry_after is not None or quota_exceeded:
        # Provide a hint to caller for adaptive cooldown
        return {
            "transactions": [],
            "next_cursor": None,
            "error": "quota_exceeded" if quota_exceeded else "rate_limited",
            "retry_after_sec": max(last_retry_after or 0, 0),
        }
    return {"transactions": [], "next_cursor": None, "error": "retries_exhausted"}
