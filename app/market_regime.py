import time
import urllib.request
import json

_CACHE = {
    "data": {
        "sol_price": 0.0,
        "sol_trend": "neutral",
        "btc_trend": "neutral",
        "market_regime": "ranging"
    },
    "last_updated": 0
}
CACHE_TTL = 300  # 5 minutes

def get_market_regime() -> dict:
    """Fetch macro market conditions (SOL/BTC trends) with caching."""
    now = time.time()
    if now - _CACHE["last_updated"] < CACHE_TTL:
        return _CACHE["data"]
        
    try:
        # Simplistic implementation using CoinGecko or Jupiter for SOL price
        url = "https://api.jup.ag/price/v2?ids=So11111111111111111111111111111111111111112"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read())
            sol_price = float(data.get("data", {}).get("So11111111111111111111111111111111111111112", {}).get("price", 0.0))
            
        # In a full implementation, you would compare current price to 1h/24h SMAs to determine trend
        # For now, we stub the trends.
        _CACHE["data"] = {
            "sol_price": sol_price,
            "sol_trend": "neutral", # placeholder
            "btc_trend": "neutral", # placeholder
            "market_regime": "ranging" # placeholder
        }
        _CACHE["last_updated"] = now
        
    except Exception as e:
        print(f"[MARKET] Error fetching regime: {e}")
        
    return _CACHE["data"]
