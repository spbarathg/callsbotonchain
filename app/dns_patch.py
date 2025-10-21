"""
DNS Patch for Jupiter API
Monkey-patches socket.getaddrinfo to force IP resolution for quote-api.jup.ag
"""
import socket
import logging

logger = logging.getLogger(__name__)

_original_getaddrinfo = socket.getaddrinfo

# Known working Cloudflare IPs for quote-api.jup.ag
JUPITER_FALLBACK_IPS = ["104.26.11.139", "104.26.10.139", "172.67.133.245"]

def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    """
    Patched getaddrinfo that returns fallback IP for quote-api.jup.ag
    """
    if "quote-api.jup.ag" in host:
        logger.info(f"DNS PATCH: Intercepted resolution for {host}, returning fallback IP {JUPITER_FALLBACK_IPS[0]}")
        # Return result in the same format as getaddrinfo
        # (family, type, proto, canonname, sockaddr)
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', (JUPITER_FALLBACK_IPS[0], port))
        ]
    
    # For all other hosts, use original DNS resolution
    return _original_getaddrinfo(host, port, family, type, proto, flags)

def apply_dns_patch():
    """
    Apply the DNS patch globally
    Call this once at module initialization
    """
    socket.getaddrinfo = patched_getaddrinfo
    logger.info("✅ DNS patch applied - quote-api.jup.ag will resolve to fallback IPs")

def remove_dns_patch():
    """
    Remove the DNS patch (restore original behavior)
    """
    socket.getaddrinfo = _original_getaddrinfo
    logger.info("DNS patch removed - using system DNS resolution")

