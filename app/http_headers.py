"""
HTTP headers configuration for API clients.

Defines host-specific headers to avoid blocks from Cloudflare,
rate limiters, and other protective measures.
"""
from typing import Dict


# Host-specific header configurations
HOST_HEADERS: Dict[str, Dict[str, str]] = {
    "geckoterminal.com": {
        "referer": "https://www.geckoterminal.com/",
        "origin": "https://www.geckoterminal.com",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
    },
    "dexscreener.com": {
        "referer": "https://dexscreener.com/",
        "origin": "https://dexscreener.com",
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
    },
    "api.dexscreener.com": {
        "referer": "https://dexscreener.com/",
        "origin": "https://dexscreener.com",
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
    },
    "cielo.finance": {
        # Cielo API - use clean headers
        "accept": "application/json",
    },
    "api.cielo.finance": {
        "accept": "application/json",
    },
    "feed-api.cielo.finance": {
        "accept": "application/json",
    },
    "jup.ag": {
        "accept": "application/json",
        "origin": "https://jup.ag",
        "referer": "https://jup.ag/",
    },
    "quote-api.jup.ag": {
        "accept": "application/json",
        "origin": "https://jup.ag",
        "referer": "https://jup.ag/",
    },
    "token.jup.ag": {
        "accept": "application/json",
        "origin": "https://jup.ag",
        "referer": "https://jup.ag/",
    },
}


def get_host_headers(url: str) -> Dict[str, str]:
    """
    Get host-specific headers for a URL.
    
    Args:
        url: The URL to get headers for
        
    Returns:
        Dict of headers, or empty dict if no specific headers needed
    """
    # Extract hostname from URL
    try:
        from urllib.parse import urlparse
        hostname = urlparse(url).hostname or ""
    except Exception:
        hostname = ""
    
    # Check for exact match first
    if hostname in HOST_HEADERS:
        return HOST_HEADERS[hostname].copy()
    
    # Check for domain match (e.g., "api.example.com" matches "example.com")
    for host_pattern, headers in HOST_HEADERS.items():
        if hostname.endswith(host_pattern):
            return headers.copy()
    
    return {}


def merge_headers(base_headers: Dict[str, str], custom_headers: Dict[str, str], url: str) -> Dict[str, str]:
    """
    Merge base, host-specific, and custom headers.
    
    Priority: custom_headers > host_headers > base_headers
    
    Args:
        base_headers: Default headers
        custom_headers: User-provided headers
        url: URL to get host-specific headers for
        
    Returns:
        Merged headers dict
    """
    merged = base_headers.copy()
    
    # Add host-specific headers
    host_headers = get_host_headers(url)
    merged.update(host_headers)
    
    # Override with custom headers
    if custom_headers:
        merged.update(custom_headers)
    
    return merged

