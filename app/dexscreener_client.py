"""
DexScreener API Client for price monitoring
Used for frequent price checks to avoid Jupiter API rate limits
"""
import requests
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class DexScreenerClient:
    """
    DexScreener API client for Solana token price monitoring
    
    Features:
    - High rate limits (~300 RPM vs Jupiter's 40-60 RPM)
    - Real-time market data aggregation
    - No authentication required
    - Simple REST API
    
    Used for: Exit monitoring (frequent price checks)
    NOT used for: Swap execution (use Jupiter for that)
    """
    
    def __init__(self):
        self.base_url = "https://api.dexscreener.com"
        self.session = requests.Session()
        
        # Configure session for connection pooling
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=0
        )
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)
        
        # Simple cache to reduce duplicate requests within short window
        self._cache: Dict[str, tuple[float, float]] = {}  # token -> (price, timestamp)
        self._cache_ttl = 3.0  # 3 second cache
        
        logger.info("DexScreener client initialized for price monitoring")
    
    def get_token_price(self, token_address: str) -> Optional[float]:
        """
        Get current market price for a Solana token
        
        Args:
            token_address: Solana token mint address
            
        Returns:
            Price in USD or None if unavailable
        """
        # Check cache first
        if token_address in self._cache:
            cached_price, cached_time = self._cache[token_address]
            if time.time() - cached_time < self._cache_ttl:
                return cached_price
        
        try:
            # DexScreener API endpoint for Solana tokens
            # Use full chain:address format for better compatibility
            url = f"{self.base_url}/latest/dex/tokens/{token_address}"
            
            response = self.session.get(url, timeout=5.0)
            
            if response.status_code != 200:
                logger.warning(f"DexScreener returned {response.status_code} for {token_address[:8]}")
                return None
            
            data = response.json()
            
            # DexScreener returns pairs array
            pairs = data.get("pairs", [])
            if not pairs:
                logger.warning(f"No pairs found for {token_address[:8]}")
                return None
            
            # Get the most liquid pair (first one is usually best)
            best_pair = pairs[0]
            price_usd = best_pair.get("priceUsd")
            
            if price_usd:
                price = float(price_usd)
                # Cache the result
                self._cache[token_address] = (price, time.time())
                return price
            
            return None
            
        except requests.exceptions.Timeout:
            logger.warning(f"DexScreener timeout for {token_address[:8]}")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"DexScreener request error for {token_address[:8]}: {e}")
            return None
        except Exception as e:
            logger.error(f"DexScreener unexpected error for {token_address[:8]}: {e}")
            return None
    
    def get_token_info(self, token_address: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed token information including price, liquidity, volume
        
        Args:
            token_address: Solana token mint address
            
        Returns:
            Dict with price, liquidity, volume, etc. or None if unavailable
        """
        try:
            url = f"{self.base_url}/latest/dex/tokens/solana/{token_address}"
            
            response = self.session.get(url, timeout=5.0)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            pairs = data.get("pairs", [])
            
            if not pairs:
                return None
            
            best_pair = pairs[0]
            
            return {
                "price_usd": float(best_pair.get("priceUsd", 0)),
                "liquidity_usd": float(best_pair.get("liquidity", {}).get("usd", 0)),
                "volume_24h": float(best_pair.get("volume", {}).get("h24", 0)),
                "price_change_5m": float(best_pair.get("priceChange", {}).get("m5", 0)),
                "price_change_1h": float(best_pair.get("priceChange", {}).get("h1", 0)),
                "price_change_24h": float(best_pair.get("priceChange", {}).get("h24", 0)),
                "dex": best_pair.get("dexId", ""),
                "pair_address": best_pair.get("pairAddress", "")
            }
            
        except Exception as e:
            logger.error(f"DexScreener info error for {token_address[:8]}: {e}")
            return None
    
    def clear_cache(self):
        """Clear the price cache"""
        self._cache.clear()


# Global singleton
_dexscreener_client: Optional[DexScreenerClient] = None


def get_dexscreener_client() -> DexScreenerClient:
    """Get or create the global DexScreener client singleton"""
    global _dexscreener_client
    if _dexscreener_client is None:
        _dexscreener_client = DexScreenerClient()
    return _dexscreener_client

