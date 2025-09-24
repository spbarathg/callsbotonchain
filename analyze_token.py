# analyze_token.py
import requests
import time
from config import CIELO_API_KEY

def get_token_stats(token_address):
    if not token_address:
        return {}
        
    url = f"https://feed-api.cielo.finance/api/v1/token/stats"
    params = {"token_address": token_address, "chain": "solana"}
    headers = {"X-API-Key": CIELO_API_KEY}
    
    # Add timeout and retry logic
    max_retries = 3
    timeout = 10
    
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                api_response = resp.json()
                # Extract data from Cielo API format
                if api_response.get("status") == "ok" and "data" in api_response:
                    return api_response["data"]
                return api_response
            elif resp.status_code == 429:  # Rate limited
                print(f"Rate limited on token stats, waiting... (attempt {attempt + 1})")
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            elif resp.status_code == 404:
                print(f"Token {token_address} not found")
                return {}
            else:
                print(f"Error fetching token stats: {resp.status_code}, {resp.text}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
        except requests.exceptions.RequestException as e:
            print(f"Request exception on token stats attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
    
    print(f"Failed to fetch token stats for {token_address} after {max_retries} attempts")
    return {}

def calculate_preliminary_score(tx_data, smart_money_detected=False):
    """
    CREDIT-EFFICIENT: Calculate preliminary score from feed data without API calls
    Uses only data available in the transaction feed
    """
    score = 0
    
    # Smart money bonus (highest priority)
    if smart_money_detected:
        score += 4  # Higher bonus for preliminary scoring
    
    # USD value indicates serious activity
    usd_value = tx_data.get('usd_value', 0)
    if usd_value > 10000:
        score += 3
    elif usd_value > 5000:
        score += 2
    elif usd_value > 1000:
        score += 1
    
    # Transaction frequency/urgency
    # Note: This would need to be tracked over time
    # For now, we use USD value as a proxy
    
    return min(score, 10)

def score_token(stats, smart_money_detected=False):
    if not stats:
        return 0
        
    score = 0
    scoring_details = []
    
    # SMART MONEY BONUS (highest priority)
    if smart_money_detected:
        score += 3
        scoring_details.append("Smart Money: +3 (top wallets active!)")
    
    # Market cap analysis (lower market cap = higher potential)
    market_cap = stats.get('market_cap_usd', 0)
    if 0 < market_cap < 100_000:  # Under 100K market cap
        score += 3
        scoring_details.append(f"Market Cap: +3 (${market_cap:,.0f} - micro cap gem)")
    elif market_cap < 1_000_000:  # Under 1M market cap
        score += 2
        scoring_details.append(f"Market Cap: +2 (${market_cap:,.0f} - small cap)")
    elif market_cap < 10_000_000:  # Under 10M market cap
        score += 1
        scoring_details.append(f"Market Cap: +1 (${market_cap:,.0f} - growing)")
    
    # Volume analysis (24h volume indicates activity)
    volume_24h = stats.get('volume', {}).get('24h', {}).get('volume_usd', 0)
    if volume_24h > 100_000:  # High volume
        score += 3
        scoring_details.append(f"Volume: +3 (${volume_24h:,.0f} - very high activity)")
    elif volume_24h > 50_000:  # Good volume
        score += 2
        scoring_details.append(f"Volume: +2 (${volume_24h:,.0f} - high activity)")
    elif volume_24h > 10_000:  # Moderate volume
        score += 1
        scoring_details.append(f"Volume: +1 (${volume_24h:,.0f} - moderate activity)")
    
    # Unique trader analysis (indicates community engagement)
    unique_buyers_24h = stats.get('volume', {}).get('24h', {}).get('unique_buyers', 0)
    unique_sellers_24h = stats.get('volume', {}).get('24h', {}).get('unique_sellers', 0)
    total_unique_traders = unique_buyers_24h + unique_sellers_24h
    
    if total_unique_traders > 500:  # Very active community
        score += 2
        scoring_details.append(f"Community: +2 ({total_unique_traders} traders - very active)")
    elif total_unique_traders > 200:  # Active community
        score += 1
        scoring_details.append(f"Community: +1 ({total_unique_traders} traders - active)")
    
    # Price momentum analysis (positive short-term trend)
    change_1h = stats.get('change', {}).get('1h', 0)
    change_24h = stats.get('change', {}).get('24h', 0)
    
    # Reward recent positive momentum
    if change_1h > 5:  # Strong 1h pump
        score += 2
        scoring_details.append(f"Momentum: +2 ({change_1h:.1f}% - strong pump)")
    elif change_1h > 0:  # Positive 1h
        score += 1
        scoring_details.append(f"Momentum: +1 ({change_1h:.1f}% - positive)")
    
    # But penalize if 24h is extremely negative (might be dump)
    if change_24h < -80:
        score -= 1
        scoring_details.append(f"Risk: -1 ({change_24h:.1f}% - major dump risk)")
    
    final_score = max(0, min(score, 10))
    return final_score, scoring_details
