"""
Jupiter Price Oracle for Exit Monitoring
Uses real Jupiter sell quotes to get accurate, sellable prices
"""
import time
import threading
from typing import Optional, Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class JupiterPriceOracle:
    """
    Fetches real sellable prices using Jupiter quotes
    
    Key Features:
    - Uses actual Jupiter sell quotes (what you'd really get)
    - Aggressive caching (10s TTL) to minimize API calls
    - Thread-safe with locks
    - Matches what Axiom/real wallets show
    
    This is ONLY used for exit monitoring (not signal detection)
    Signal detection still uses Cielo+DexScreener (proven 33% WR, 7.9x avg)
    """
    
    def __init__(self, cache_ttl: int = 10):
        """
        Initialize the oracle
        
        Args:
            cache_ttl: Cache time-to-live in seconds (default 10s)
        """
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Tuple[float, float]] = {}  # token -> (price, timestamp)
        self._lock = threading.Lock()
        logger.info(f"JupiterPriceOracle initialized with {cache_ttl}s cache TTL")
    
    def get_price(self, token: str, holdings: float) -> float:
        """
        Get the real sellable price for a token
        
        Args:
            token: Token mint address
            holdings: Amount of tokens held (for accurate quote)
        
        Returns:
            Real sellable price per token in USD (0.0 if unavailable)
        """
        if holdings <= 0:
            return 0.0
        
        # Check cache first
        with self._lock:
            if token in self._cache:
                cached_price, cached_time = self._cache[token]
                age = time.time() - cached_time
                if age < self.cache_ttl:
                    return cached_price
        
        # Get fresh Jupiter quote
        try:
            from app.jupiter_client import get_jupiter_client
            from tradingSystem.config_optimized import SOL_MINT
            import requests
            
            jupiter = get_jupiter_client()
            
            # Get token decimals
            token_decimals = self._get_token_decimals(token)
            if token_decimals is None:
                logger.warning(f"Could not get decimals for {token[:8]}")
                return 0.0
            
            # Convert holdings to smallest unit
            in_amount = int(holdings * (10 ** token_decimals))
            
            # Get Jupiter quote for selling this amount
            result = jupiter.get_quote(
                input_mint=token,
                output_mint=SOL_MINT,
                amount=in_amount,
                slippage_bps=2000,  # 20% slippage for quote
                timeout=5.0,
                only_direct_routes=True  # Faster, more reliable
            )
            
            if result["status_code"] != 200 or not result.get("json"):
                logger.warning(f"Jupiter quote failed for {token[:8]}: {result.get('error')}")
                return 0.0
            
            quote = result["json"]
            out_amount_lamports = float(quote.get("outAmount", 0))
            
            if out_amount_lamports <= 0:
                logger.warning(f"Jupiter returned zero output for {token[:8]}")
                return 0.0
            
            # Convert SOL lamports to SOL
            out_sol = out_amount_lamports / 1e9
            
            # Get SOL price in USD
            sol_price_usd = self._get_sol_price_usd()
            if sol_price_usd <= 0:
                logger.warning("Could not get SOL price")
                return 0.0
            
            # Calculate USD value
            usd_value = out_sol * sol_price_usd
            
            # Calculate price per token
            price_per_token = usd_value / holdings
            
            # Cache the result
            with self._lock:
                self._cache[token] = (price_per_token, time.time())
            
            logger.debug(f"Jupiter price for {token[:8]}: ${price_per_token:.10f} (from {holdings:.0f} tokens)")
            return price_per_token
            
        except Exception as e:
            logger.error(f"Error getting Jupiter price for {token[:8]}: {e}")
            return 0.0
    
    def _get_token_decimals(self, token: str) -> Optional[int]:
        """Get token decimals (cached internally by Jupiter client)"""
        try:
            from app.jupiter_client import get_jupiter_client
            jupiter = get_jupiter_client()
            # Use the broker's _get_decimals if available, or default to 6 for most tokens
            try:
                from tradingSystem.broker_optimized import Broker
                broker = Broker()
                return broker._get_decimals(token)
            except:
                # Fallback: most pump.fun tokens are 6 decimals
                return 6
        except Exception as e:
            logger.error(f"Error getting decimals for {token[:8]}: {e}")
            return None
    
    def _get_sol_price_usd(self) -> float:
        """Get current SOL price in USD (with caching)"""
        cache_key = "SOL_PRICE"
        
        # Check cache (use 30s TTL for SOL price)
        with self._lock:
            if cache_key in self._cache:
                cached_price, cached_time = self._cache[cache_key]
                age = time.time() - cached_time
                if age < 30:  # 30 second cache for SOL price
                    return cached_price
        
        try:
            import requests
            
            # Try CoinGecko first (no API key needed)
            resp = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "solana", "vs_currencies": "usd"},
                timeout=3
            )
            
            if resp.status_code == 200:
                data = resp.json()
                sol_price = float(data.get("solana", {}).get("usd", 0))
                
                if sol_price > 0:
                    # Cache it
                    with self._lock:
                        self._cache[cache_key] = (sol_price, time.time())
                    return sol_price
            
            # Fallback to Jupiter's SOL/USDC quote
            from app.jupiter_client import get_jupiter_client
            from tradingSystem.config_optimized import USDC_MINT, SOL_MINT
            
            jupiter = get_jupiter_client()
            result = jupiter.get_quote(
                input_mint=SOL_MINT,
                output_mint=USDC_MINT,
                amount=1000000000,  # 1 SOL
                slippage_bps=50,
                timeout=3.0
            )
            
            if result["status_code"] == 200 and result.get("json"):
                quote = result["json"]
                usdc_out = float(quote.get("outAmount", 0)) / 1e6  # USDC has 6 decimals
                
                if usdc_out > 0:
                    with self._lock:
                        self._cache[cache_key] = (usdc_out, time.time())
                    return usdc_out
            
            logger.warning("Could not fetch SOL price from any source")
            return 0.0
            
        except Exception as e:
            logger.error(f"Error getting SOL price: {e}")
            return 0.0
    
    def clear_cache(self, token: Optional[str] = None):
        """
        Clear cache for a specific token or all tokens
        
        Args:
            token: Token to clear (None = clear all)
        """
        with self._lock:
            if token:
                self._cache.pop(token, None)
            else:
                self._cache.clear()
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        with self._lock:
            now = time.time()
            valid = sum(1 for _, ts in self._cache.values() if (now - ts) < self.cache_ttl)
            return {
                "total_entries": len(self._cache),
                "valid_entries": valid,
                "stale_entries": len(self._cache) - valid,
                "ttl_seconds": self.cache_ttl,
            }


# Global singleton
_jupiter_oracle: Optional[JupiterPriceOracle] = None


def get_jupiter_oracle(cache_ttl: int = 10) -> JupiterPriceOracle:
    """Get or create the global Jupiter price oracle singleton"""
    global _jupiter_oracle
    if _jupiter_oracle is None:
        _jupiter_oracle = JupiterPriceOracle(cache_ttl=cache_ttl)
    return _jupiter_oracle

