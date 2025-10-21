"""
Jupiter API Client with DNS fallback and circuit breaker bypass
Handles quote and swap requests with robust error handling
"""
import socket
import requests
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
import logging

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
        
        # Try DNS resolution - if fails, switch to IP mode
        try:
            socket.gethostbyname(self.hostname)
            logger.info(f"Jupiter client initialized with DNS resolution")
        except socket.gaierror:
            logger.warning(f"DNS resolution failed for {self.hostname}, switching to IP fallback mode")
            self.using_ip_fallback = True
            self._current_ip = self.fallback_ips[0]
            self.base_url = f"https://{self._current_ip}"
            logger.info(f"Using IP fallback: {self._current_ip}")
    
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
        
        # If using IP fallback, we need to set the Host header for SSL/TLS
        headers = {}
        if self.using_ip_fallback:
            headers["Host"] = self.hostname
        
        for attempt in range(retries):
            try:
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
                    return {
                        "status_code": 200,
                        "json": response.json(),
                        "error": None
                    }
                else:
                    return {
                        "status_code": response.status_code,
                        "json": None,
                        "error": f"HTTP {response.status_code}: {response.text[:200]}"
                    }
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"Jupiter API attempt {attempt + 1}/{retries} failed: {e}")
                
                # Try next IP if using fallback
                if self.using_ip_fallback and attempt < len(self.fallback_ips) - 1:
                    self._current_ip = self.fallback_ips[attempt + 1]
                    self.base_url = f"https://{self._current_ip}"
                    url = f"{self.base_url}{path}"
                    logger.info(f"Trying fallback IP: {self._current_ip}")
                
                if attempt == retries - 1:
                    return {
                        "status_code": None,
                        "json": None,
                        "error": str(e)
                    }
                
                # Wait before retry
                import time
                time.sleep(1 * (attempt + 1))
        
        return {
            "status_code": None,
            "json": None,
            "error": "Max retries exceeded"
        }
    
    def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int = 2000,
        timeout: float = 10.0
    ) -> Dict[str, Any]:
        """
        Get swap quote from Jupiter
        
        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Amount in smallest unit (lamports for SOL)
            slippage_bps: Slippage tolerance in basis points (2000 = 20%)
            timeout: Request timeout in seconds
            
        Returns:
            Dict with status_code, json (quote data), and error
        """
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": str(slippage_bps)
        }
        
        logger.debug(f"Getting Jupiter quote: {input_mint[:8]}... → {output_mint[:8]}... ({amount} units, {slippage_bps} BPS slippage)")
        
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

