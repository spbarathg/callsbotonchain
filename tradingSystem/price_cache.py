"""
Price caching system to reduce API calls and avoid rate limiting

This module provides aggressive caching of token prices to minimize
external API calls while ensuring fresh enough data for trading decisions.
"""
import time
import threading
from typing import Dict, Optional, Tuple

class PriceCache:
    """Thread-safe price cache with TTL"""
    
    def __init__(self, ttl_seconds: int = 5):
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Tuple[float, float]] = {}  # token -> (price, timestamp)
        self._lock = threading.Lock()
    
    def get(self, token: str) -> Optional[float]:
        """Get cached price if still valid"""
        with self._lock:
            if token in self._cache:
                price, ts = self._cache[token]
                age = time.time() - ts
                if age < self.ttl_seconds:
                    return price
        return None
    
    def set(self, token: str, price: float):
        """Cache a price"""
        with self._lock:
            self._cache[token] = (price, time.time())
    
    def invalidate(self, token: str):
        """Remove a token from cache"""
        with self._lock:
            self._cache.pop(token, None)
    
    def clear(self):
        """Clear entire cache"""
        with self._lock:
            self._cache.clear()
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        with self._lock:
            now = time.time()
            valid = sum(1 for _, ts in self._cache.values() if (now - ts) < self.ttl_seconds)
            return {
                "total_entries": len(self._cache),
                "valid_entries": valid,
                "stale_entries": len(self._cache) - valid,
                "ttl_seconds": self.ttl_seconds,
            }


# Global price cache instance
# Increased to 10 seconds to ensure we stay well within Jupiter's 60 RPM limit
# With 4 positions × 6 fetches/min = 24 API calls/min (40% of limit)
_price_cache = PriceCache(ttl_seconds=10)  # 10 second cache for exit monitoring

def get_price_cache() -> PriceCache:
    """Get global price cache instance"""
    return _price_cache

