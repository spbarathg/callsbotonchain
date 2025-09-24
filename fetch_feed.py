# fetch_feed.py
import requests
import time
from config import CIELO_API_KEY, MIN_USD_VALUE

def fetch_solana_feed(cursor=None, smart_money_only=False):
    url = "https://feed-api.cielo.finance/api/v1/feed"
    
    # Base parameters
    params = {
        "limit": 100,
        "chains": "solana",
        "transaction_types": "mint,swap,transfer",
        "minimum_usd_value": MIN_USD_VALUE,
        "cursor": cursor
    }
    
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
        
    # Always try to get high-value transactions
    params["minimum_usd_value"] = max(MIN_USD_VALUE, 500)  # Minimum $500 for quality
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
                    return {
                        "transactions": data.get("items", []),
                        "next_cursor": data.get("paging", {}).get("next_cursor")
                    }
                return api_response
            elif resp.status_code == 429:  # Rate limited
                print(f"Rate limited, waiting before retry... (attempt {attempt + 1})")
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            else:
                print(f"Error fetching feed: {resp.status_code}, {resp.text}")
                if attempt < max_retries - 1:
                    time.sleep(1)  # Brief pause before retry
                    continue
        except requests.exceptions.RequestException as e:
            print(f"Request exception on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
    
    # All retries failed
    print(f"Failed to fetch feed after {max_retries} attempts")
    return {"transactions": [], "next_cursor": None}
