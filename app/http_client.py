from typing import Any, Dict, Optional, Tuple
from datetime import datetime, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config.config import HTTP_MAX_RETRIES, HTTP_BACKOFF_FACTOR
from config.config import HTTP_ALLOW_HOSTS
from app.metrics import inc_api_call
from app.http_headers import merge_headers


_session: Optional[requests.Session] = None


# ============================================================================
# CIRCUIT BREAKER IMPLEMENTATION
# ============================================================================

class CircuitBreaker:
    """
    Circuit breaker pattern for HTTP requests.
    
    States:
    - CLOSED: Normal operation
    - OPEN: Failing, reject requests immediately
    - HALF_OPEN: Testing if service recovered
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def before_request(self) -> None:
        """Check circuit state before making request"""
        if self.state == "OPEN":
            if self._should_attempt_reset():
                self.state = "HALF_OPEN"
            else:
                raise Exception(f"Circuit breaker OPEN - service temporarily unavailable")
    
    def on_success(self) -> None:
        """Reset on successful call"""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def on_failure(self) -> None:
        """Increment failure count and open circuit if threshold exceeded"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery"""
        if self.last_failure_time is None:
            return True
        return datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout)
    
    def reset(self):
        """Manually reset the circuit breaker"""
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"


# Circuit breakers for different API endpoints
_circuit_breakers: Dict[str, CircuitBreaker] = {}


def _get_circuit_breaker(domain: str) -> CircuitBreaker:
    """Get or create circuit breaker for a domain"""
    if domain not in _circuit_breakers:
        _circuit_breakers[domain] = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60
        )
    return _circuit_breakers[domain]


def _build_retry(total: int, backoff_factor: float, status_forcelist: Optional[list] = None) -> Retry:
    return Retry(
        total=total,
        read=total,
        connect=total,
        status=total,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist or [429, 500, 502, 503, 504],
        allowed_methods=(
            frozenset(["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])  # type: ignore[arg-type]
        ),
        raise_on_status=False,
        respect_retry_after_header=True,
    )


def get_session(max_retries: int = HTTP_MAX_RETRIES, backoff_factor: float = HTTP_BACKOFF_FACTOR) -> requests.Session:
    global _session
    if _session is not None:
        return _session
    sess = requests.Session()
    retry = _build_retry(max_retries, backoff_factor)
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    _session = sess
    return sess


def _is_safe_url(url: str, allow_hosts: set) -> Tuple[bool, str]:
    try:
        from urllib.parse import urlparse
        import ipaddress
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, f"Invalid scheme: {parsed.scheme}"
        if not parsed.hostname:
            return False, "Missing hostname"
        try:
            ip = ipaddress.ip_address(parsed.hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False, f"Private IP not allowed: {parsed.hostname}"
        except ValueError:
            pass
        if parsed.hostname not in allow_hosts:
            return False, f"Host not allowed: {parsed.hostname}"
        if parsed.port and parsed.port not in (80, 443):
            return False, f"Non-standard port not allowed: {parsed.port}"
        return True, ""
    except Exception as e:
        return False, f"URL parsing error: {str(e)}"


def request_json(method: str, url: str, *, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None,
                 json: Optional[Dict[str, Any]] = None, timeout: float = 10.0, use_circuit_breaker: bool = True) -> Dict[str, Any]:
    # Domain allowlist with strong SSRF protections (configurable)
    is_safe, err = _is_safe_url(url, HTTP_ALLOW_HOSTS)
    if not is_safe:
        return {"status_code": None, "error": err}
    
    # Get circuit breaker for this domain
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    circuit_breaker = _get_circuit_breaker(domain) if use_circuit_breaker else None
    
    # Check circuit breaker state
    if circuit_breaker:
        try:
            circuit_breaker.before_request()
        except Exception as e:
            return {"status_code": None, "error": str(e), "circuit_breaker": circuit_breaker.state}
    
    sess = get_session()
    
    # Apply conservative default headers to avoid upstream blocks (CF/proxies)
    default_headers = {
        "accept": "application/json, text/plain, */*",
        "user-agent": "callsbotonchain/1.0 (+https://github.com/spbarathg/callsbotonchain)",
    }
    
    # Merge with host-specific and custom headers
    merged_headers = merge_headers(default_headers, headers or {}, url)
    
    # Drop headers with None or obviously invalid values to avoid sending bad auth
    try:
        merged_headers = {
            k: v for k, v in merged_headers.items()
            if (v is not None) and (str(v).strip() != "") and (str(v).strip().lower() != "none") and (str(v).strip() != "Bearer None")
        }
    except Exception:
        pass
    try:
        resp = sess.request(method.upper(), url, params=params, headers=merged_headers, json=json, timeout=timeout)
        result: Dict[str, Any] = {"status_code": resp.status_code}
        try:
            result["json"] = resp.json()
        except Exception:
            result["json"] = None
            result["text"] = resp.text
        result["headers"] = dict(resp.headers)
        
        # Mark success in circuit breaker
        if circuit_breaker and resp.status_code < 500:
            circuit_breaker.on_success()
        
        try:
            provider = "dexscreener" if "dexscreener" in url else ("cielo" if "cielo" in url else None)
            if provider:
                inc_api_call(provider, resp.status_code)
        except Exception:
            pass
        return result
    except requests.RequestException as e:
        # Mark failure in circuit breaker
        if circuit_breaker:
            circuit_breaker.on_failure()
        
        try:
            provider = "dexscreener" if "dexscreener" in url else ("cielo" if "cielo" in url else None)
            if provider:
                inc_api_call(provider, None)
        except Exception:
            pass
        return {"status_code": None, "error": str(e)}


def get_circuit_breaker_status() -> Dict[str, Any]:
    """Get status of all circuit breakers"""
    return {
        domain: {
            "state": cb.state,
            "failure_count": cb.failure_count,
            "last_failure": cb.last_failure_time.isoformat() if cb.last_failure_time else None,
        }
        for domain, cb in _circuit_breakers.items()
    }


def reset_circuit_breakers():
    """Reset all circuit breakers (for testing/recovery)"""
    for cb in _circuit_breakers.values():
        cb.reset()
