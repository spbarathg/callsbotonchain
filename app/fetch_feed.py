# fetch_feed.py
import requests
import time
from config import CIELO_API_KEY, MIN_USD_VALUE, CIELO_LIST_ID, CIELO_NEW_TRADE_ONLY

def fetch_solana_feed(cursor=None, smart_money_only=False):
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
    if CIELO_LIST_ID is not None:
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
    headers = {"X-API-Key": CIELO_API_KEY}
    
    # Add timeout and retry logic
    max_retries = 3
    timeout = 10
    
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                api_response = resp.json()
                # Convert Cielo API format to expected format
                if api_response.get("status") == "ok" and "data" in api_response:
                    data = api_response["data"]
                    # Adapt to both items-based and flat list responses
                    items = data.get("items") if isinstance(data, dict) else None
                    if items is None and isinstance(api_response.get("data"), list):
                        items = api_response["data"]
                    return {
                        "transactions": items or [],
                        "next_cursor": (data.get("paging", {}).get("next_cursor")
                                         if isinstance(data, dict) else None),
                        "error": None,
                    }
                # Unexpected shape but still HTTP 200
                return {
                    "transactions": [],
                    "next_cursor": None,
                    "error": "unexpected_response_shape",
                }
            elif resp.status_code == 429:  # Rate limited
                print(f"Rate limited, waiting before retry... (attempt {attempt + 1})")
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            else:
                print(f"Error fetching feed: {resp.status_code}, {resp.text}")
                if attempt < max_retries - 1:
                    time.sleep(1)  # Brief pause before retry
                    continue
                return {
                    "transactions": [],
                    "next_cursor": None,
                    "error": f"http_{resp.status_code}",
                }
        except requests.exceptions.RequestException as e:
            print(f"Request exception on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            return {
                "transactions": [],
                "next_cursor": None,
                "error": "network_exception",
            }
    
    # All retries failed
    print(f"Failed to fetch feed after {max_retries} attempts")
    return {"transactions": [], "next_cursor": None, "error": "retries_exhausted"}
