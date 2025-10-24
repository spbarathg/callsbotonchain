"""
Jupiter API Client with DNS fallback and circuit breaker bypass
Handles quote and swap requests with robust error handling
"""
import socket
import requests
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
import logging
import os
import time
import threading
import random

# Apply DNS patch for Jupiter API before any requests are made
from app.dns_patch import apply_dns_patch
apply_dns_patch()

logger = logging.getLogger(__name__)

class JupiterClient:
    """
    Dedicated Jupiter API client with:
    - DNS resolution fallback
    - No circuit breaker interference
    - Connection pooling
    - Retry logic
    """
    
    def __init__(self):
        self.hostname = "quote-api.jup.ag"
        self.fallback_ips = ["104.26.11.139", "104.26.10.139", "172.67.133.245"]  # Cloudflare IPs
        self.base_url = f"https://{self.hostname}"
        self.using_ip_fallback = False
        self._current_ip = None
        
        # Jupiter Pro API Key (optional)
        self.api_key = os.getenv("JUPITER_API_KEY", "")
        if self.api_key:
            logger.info("🚀 Jupiter Pro API key detected - using Pro tier")
        
        self.session = requests.Session()
        self._dns_cache = {}
        self._dns_cache_timeout = timedelta(minutes=5)
        
        # Configure session
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=0  # We handle retries manually
        )
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)
        
        # --- Global rate limiter (token bucket) ---
        # Increased to 45 RPM (75% of Jupiter's 60 RPM limit) for better throughput
        rpm_limit = max(10, int(os.getenv("JUP_RPM_LIMIT", "45")))
        # refill_rate tokens/sec; capacity allows small bursts
        self._bucket_capacity = int(os.getenv("JUP_RATE_BUCKET", "5"))
        self._bucket_refill_rate = rpm_limit / 60.0  # tokens per second
        self._bucket_tokens = float(self._bucket_capacity)
        self._bucket_last_refill = time.time()
        self._bucket_lock = threading.Lock()
        
        # 429 handling state
        self._consecutive_429 = 0
        self._cooldown_until: Optional[float] = None
        # REMOVED: Request lock that was serializing all requests (bottleneck!)
        # We rely on token bucket for rate limiting instead
        
        # CRITICAL FIX: NEVER use IP fallback for HTTPS - SSL cert validation will fail
        # Always use domain name for actual trades
        # DNS resolution in Docker containers works fine - health check failures are cosmetic
        logger.info(f"Jupiter client initialized with DNS resolution (domain: {self.hostname})")
        # Keep base_url as domain for SSL compatibility
        self.base_url = f"https://{self.hostname}"
    
    def is_in_cooldown(self) -> tuple[bool, float]:
        """
        Check if Jupiter API is in cooldown period
        Returns: (is_cooling_down, seconds_remaining)
        """
        if self._cooldown_until:
            now = time.time()
            if now < self._cooldown_until:
                return (True, self._cooldown_until - now)
        return (False, 0.0)
    
    def _resolve_dns(self, domain: str) -> Optional[str]:
        """
        Resolve DNS with caching and fallback
        Returns IP address or None if failed
        """
        # Check cache
        if domain in self._dns_cache:
            cached_ip, cached_time = self._dns_cache[domain]
            if datetime.now() - cached_time < self._dns_cache_timeout:
                return cached_ip
        
        # Try DNS resolution
        try:
            ip = socket.gethostbyname(domain)
            self._dns_cache[domain] = (ip, datetime.now())
            logger.debug(f"DNS resolved: {domain} → {ip}")
            return ip
        except socket.gaierror as e:
            logger.warning(f"DNS resolution failed for {domain}: {e}")
            
            # Fallback to known Cloudflare IPs for quote-api.jup.ag
            if "quote-api.jup.ag" in domain:
                fallback_ips = ["104.26.11.139", "104.26.10.139", "172.67.133.245"]
                logger.info(f"Using fallback IP for {domain}: {fallback_ips[0]}")
                self._dns_cache[domain] = (fallback_ips[0], datetime.now())
                return fallback_ips[0]
            
            return None
    
    def _make_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        json: Optional[Dict] = None,
        timeout: float = 10.0,
        retries: int = 3
    ) -> Dict[str, Any]:
        """
        Make HTTP request with DNS fallback and retry logic
        """
        url = f"{self.base_url}{path}"
        
        # Always use domain name (no IP fallback for HTTPS/SSL compatibility)
        headers = {}
        
        # Add Jupiter Pro API key if available
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        # Respect global cooldown if triggered by excessive 429s
        now = time.time()
        if self._cooldown_until and now < self._cooldown_until:
            delay = max(0.0, self._cooldown_until - now)
            logger.warning(f"Jupiter rate-limit cooldown active for {delay:.1f}s")
            return {"status_code": 429, "json": None, "error": f"Rate limited; cooling down {delay:.1f}s"}
        
        for attempt in range(retries):
            # Acquire rate-limit token (token bucket) - this provides rate limiting
            self._acquire_rate_token()
            try:
                # NO MORE REQUEST LOCK - allows concurrent requests (better throughput!)
                # Token bucket prevents overloading Jupiter API
                if method == "GET":
                    headers["Accept"] = "application/json"
                    response = self.session.get(
                        url,
                        params=params,
                        timeout=timeout,
                        headers=headers,
                        verify=True  # Keep SSL verification
                    )
                elif method == "POST":
                    headers["Content-Type"] = "application/json"
                    response = self.session.post(
                        url,
                        json=json,
                        timeout=timeout,
                        headers=headers,
                        verify=True  # Keep SSL verification
                    )
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                # Success
                if response.status_code == 200:
                    # Success clears 429 counters
                    self._consecutive_429 = 0
                    return {
                        "status_code": 200,
                        "json": response.json(),
                        "error": None
                    }
                else:
                    # Handle explicit 429 with exponential backoff + jitter
                    if response.status_code == 429:
                        self._consecutive_429 += 1
                        backoff = min(8, (2 ** attempt))
                        sleep_for = backoff + random.uniform(0, 0.5)
                        logger.warning(f"Jupiter 429 received. attempt={attempt+1}/{retries} backoff={sleep_for:.2f}s")
                        time.sleep(sleep_for)
                        # Trigger cooldown if persistent (reduced from 5 minutes to 60 seconds)
                        if self._consecutive_429 >= int(os.getenv("JUP_429_COOLDOWN_THRESHOLD", "3")):
                            cooldown_sec = int(os.getenv("JUP_429_COOLDOWN_SEC", "60"))
                            self._cooldown_until = time.time() + cooldown_sec
                            logger.error(f"Entering Jupiter cooldown for {cooldown_sec}s due to repeated 429s")
                        continue
                    return {
                        "status_code": response.status_code,
                        "json": None,
                        "error": f"HTTP {response.status_code}: {response.text[:200]}"
                    }
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"Jupiter API attempt {attempt + 1}/{retries} failed: {e}")
                
                # No IP fallback - always use domain name for HTTPS/SSL compatibility
                # Just retry with backoff
                
                if attempt == retries - 1:
                    return {
                        "status_code": None,
                        "json": None,
                        "error": str(e)
                    }
                
                # Wait before retry with exponential backoff
                time.sleep(1 * (attempt + 1) + random.uniform(0, 0.2))
        
        return {
            "status_code": None,
            "json": None,
            "error": "Max retries exceeded"
        }

    def is_rate_limited(self) -> bool:
        now = time.time()
        return bool(self._cooldown_until and now < self._cooldown_until)

    def _acquire_rate_token(self) -> None:
        """Block until a token is available under the global RPM limit."""
        with self._bucket_lock:
            now = time.time()
            # Refill
            elapsed = max(0.0, now - self._bucket_last_refill)
            self._bucket_last_refill = now
            self._bucket_tokens = min(
                self._bucket_capacity,
                self._bucket_tokens + elapsed * self._bucket_refill_rate,
            )
            if self._bucket_tokens >= 1.0:
                self._bucket_tokens -= 1.0
                return
            # Calculate wait time for next token
            needed = 1.0 - self._bucket_tokens
            wait_sec = needed / max(self._bucket_refill_rate, 0.01)
        # Sleep outside the lock
        time.sleep(wait_sec)
        # After sleeping, ensure we consume a token
        with self._bucket_lock:
            now2 = time.time()
            elapsed2 = max(0.0, now2 - self._bucket_last_refill)
            self._bucket_last_refill = now2
            self._bucket_tokens = min(
                self._bucket_capacity,
                self._bucket_tokens + elapsed2 * self._bucket_refill_rate,
            )
            if self._bucket_tokens >= 1.0:
                self._bucket_tokens -= 1.0
                return
            # Fallback: enforce small sleep to avoid tight loops
            time.sleep(0.2)
    
    def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int = 2000,
        timeout: float = 10.0,
        only_direct_routes: bool = False,
        max_accounts: int = None
    ) -> Dict[str, Any]:
        """
        Get swap quote from Jupiter
        
        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Amount in smallest unit (lamports for SOL)
            slippage_bps: Slippage tolerance in basis points (2000 = 20%)
            timeout: Request timeout in seconds
            only_direct_routes: If True, only return quotes using single-hop routes (more reliable)
            max_accounts: Max accounts/hops to use (lower = simpler routes, e.g. 20 for 2-hop max)
            
        Returns:
            Dict with status_code, json (quote data), and error
        """
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": str(slippage_bps)
        }
        
        if only_direct_routes:
            params["onlyDirectRoutes"] = "true"
        
        if max_accounts is not None:
            params["maxAccounts"] = str(max_accounts)
        
        logger.debug(f"Getting Jupiter quote: {input_mint[:8]}... → {output_mint[:8]}... ({amount} units, {slippage_bps} BPS slippage, direct={only_direct_routes}, maxAccounts={max_accounts})")
        
        result = self._make_request("GET", "/v6/quote", params=params, timeout=timeout)
        
        if result["status_code"] == 200:
            logger.info(f"✅ Jupiter quote received: {result['json'].get('outAmount')} units")
        else:
            logger.error(f"❌ Jupiter quote failed: {result['error']}")
        
        return result
    
    def get_swap_transaction(
        self,
        quote: Dict,
        user_public_key: str,
        wrap_unwrap_sol: bool = True,
        priority_fee: int = 100000,
        timeout: float = 15.0
    ) -> Dict[str, Any]:
        """
        Get swap transaction from Jupiter
        
        Args:
            quote: Quote object from get_quote()
            user_public_key: User's wallet public key
            wrap_unwrap_sol: Auto wrap/unwrap SOL
            priority_fee: Priority fee in microlamports
            timeout: Request timeout in seconds
            
        Returns:
            Dict with status_code, json (swap transaction), and error
        """
        payload = {
            "quoteResponse": quote,
            "userPublicKey": user_public_key,
            "wrapAndUnwrapSol": wrap_unwrap_sol,
            "computeUnitPriceMicroLamports": priority_fee,
            "dynamicComputeUnitLimit": True,
            "asLegacyTransaction": False
        }
        
        logger.debug(f"Getting Jupiter swap transaction for {user_public_key[:8]}...")
        
        result = self._make_request("POST", "/v6/swap", json=payload, timeout=timeout)
        
        if result["status_code"] == 200:
            logger.info("✅ Jupiter swap transaction received")
        else:
            logger.error(f"❌ Jupiter swap failed: {result['error']}")
        
        return result
    
    def health_check(self) -> bool:
        """
        Check if Jupiter API is accessible
        Returns True if healthy, False otherwise
        """
        try:
            result = self.get_quote(
                input_mint="So11111111111111111111111111111111111111112",  # SOL
                output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
                amount=1000000000,  # 1 SOL
                slippage_bps=50,
                timeout=5.0
            )
            
            return result["status_code"] == 200 and result["json"] is not None
            
        except Exception as e:
            logger.error(f"Jupiter health check failed: {e}")
            return False


# Global instance
_jupiter_client = None

def get_jupiter_client() -> JupiterClient:
    """Get or create global Jupiter client instance"""
    global _jupiter_client
    if _jupiter_client is None:
        _jupiter_client = JupiterClient()
    return _jupiter_client

