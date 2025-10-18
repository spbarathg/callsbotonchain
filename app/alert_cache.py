"""
Alert lookup cache for performance optimization.

Caches recent alert lookups to avoid repeated database queries
in the hot path of transaction processing.
"""
import time
import threading
from typing import Dict, Optional, Any


class AlertCache:
    """
    Thread-safe LRU cache for alert lookups.
    
    Stores token addresses that have been alerted with timestamps.
    Automatically expires entries after TTL.
    """
    
    def __init__(self, ttl_seconds: int = 3600, max_size: int = 10000):
        """
        Args:
            ttl_seconds: Time-to-live for cache entries (default 1 hour)
            max_size: Maximum number of entries before eviction
        """
        self._cache: Dict[str, float] = {}  # token -> timestamp
        self._lock = threading.RLock()  # Re-entrant lock
        self._ttl = ttl_seconds
        self._max_size = max_size
        
        # Stats
        self._hits = 0
        self._misses = 0
    
    def add(self, token_address: str) -> None:
        """
        Add a token to the cache.
        
        Args:
            token_address: Token address to cache
        """
        with self._lock:
            # Evict oldest if at capacity
            if len(self._cache) >= self._max_size:
                self._evict_oldest()
            
            self._cache[token_address] = time.time()
    
    def contains(self, token_address: str) -> bool:
        """
        Check if token is in cache and not expired.
        
        Args:
            token_address: Token address to check
            
        Returns:
            True if cached and not expired, False otherwise
        """
        with self._lock:
            timestamp = self._cache.get(token_address)
            
            if timestamp is None:
                self._misses += 1
                return False
            
            # Check expiry
            age = time.time() - timestamp
            if age > self._ttl:
                # Expired - remove it
                del self._cache[token_address]
                self._misses += 1
                return False
            
            # Valid hit
            self._hits += 1
            return True
    
    def remove(self, token_address: str) -> None:
        """
        Remove a token from the cache.
        
        Args:
            token_address: Token address to remove
        """
        with self._lock:
            self._cache.pop(token_address, None)
    
    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    def _evict_oldest(self) -> None:
        """Evict the oldest entry (internal, assumes lock held)."""
        if not self._cache:
            return
        
        # Find and remove oldest
        oldest_token = min(self._cache.items(), key=lambda x: x[1])[0]
        del self._cache[oldest_token]
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired entries.
        
        Returns:
            Number of entries removed
        """
        with self._lock:
            now = time.time()
            expired = [
                token for token, timestamp in self._cache.items()
                if (now - timestamp) > self._ttl
            ]
            
            for token in expired:
                del self._cache[token]
            
            return len(expired)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dict with cache stats
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "ttl_seconds": self._ttl,
            }
    
    def reset_stats(self) -> None:
        """Reset hit/miss statistics."""
        with self._lock:
            self._hits = 0
            self._misses = 0


# Global singleton
_alert_cache: Optional[AlertCache] = None
_cache_lock = threading.Lock()


def get_alert_cache() -> AlertCache:
    """
    Get or create the global alert cache instance.
    
    Returns:
        Global AlertCache singleton
    """
    global _alert_cache
    
    if _alert_cache is None:
        with _cache_lock:
            # Double-check after acquiring lock
            if _alert_cache is None:
                import os
                
                # Configurable via environment
                ttl = int(os.getenv("ALERT_CACHE_TTL_SEC", "3600"))  # 1 hour
                max_size = int(os.getenv("ALERT_CACHE_MAX_SIZE", "10000"))
                
                _alert_cache = AlertCache(ttl_seconds=ttl, max_size=max_size)
    
    return _alert_cache

