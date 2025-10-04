from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import HTTP_MAX_RETRIES, HTTP_BACKOFF_FACTOR
from app.metrics import inc_api_call


_session: Optional[requests.Session] = None


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


def request_json(method: str, url: str, *, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None,
                 json: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
    # Domain allowlist to reduce SSRF / misconfig risks
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        allow_hosts = {"api.dexscreener.com", "dexscreener.com",
                       "feed-api.cielo.finance", "api.cielo.finance", "api.geckoterminal.com",
                       "api.telegram.org"}
        if host and host not in allow_hosts:
            return {"status_code": None, "error": f"host_not_allowed:{host}"}
    except Exception:
        pass
    sess = get_session()
    # Apply conservative default headers to avoid upstream blocks (CF/proxies)
    default_headers = {
        "accept": "application/json, text/plain, */*",
        "user-agent": "callsbotonchain/1.0 (+https://github.com/spbarathg/callsbotonchain)",
    }
    try:
        # Host-specific header hints
        if "geckoterminal.com" in url:
            default_headers.update({
                "referer": "https://www.geckoterminal.com/",
                "origin": "https://www.geckoterminal.com",
                "accept-language": "en-US,en;q=0.9",
                "cache-control": "no-cache",
            })
        if "dexscreener.com" in url:
            default_headers.update({
                "referer": "https://dexscreener.com/",
                "origin": "https://dexscreener.com",
            })
    except Exception:
        pass
    merged_headers = dict(default_headers)
    if headers:
        try:
            merged_headers.update(headers)
        except Exception:
            pass
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
        try:
            provider = "dexscreener" if "dexscreener" in url else ("cielo" if "cielo" in url else None)
            if provider:
                inc_api_call(provider, resp.status_code)
        except Exception:
            pass
        return result
    except requests.RequestException as e:
        try:
            provider = "dexscreener" if "dexscreener" in url else ("cielo" if "cielo" in url else None)
            if provider:
                inc_api_call(provider, None)
        except Exception:
            pass
        return {"status_code": None, "error": str(e)}
