import os
import random
import time
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import HTTP_MAX_RETRIES, HTTP_BACKOFF_FACTOR


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
    sess = get_session()
    try:
        resp = sess.request(method.upper(), url, params=params, headers=headers, json=json, timeout=timeout)
        result: Dict[str, Any] = {"status_code": resp.status_code}
        try:
            result["json"] = resp.json()
        except Exception:
            result["json"] = None
            result["text"] = resp.text
        result["headers"] = dict(resp.headers)
        return result
    except requests.RequestException as e:
        return {"status_code": None, "error": str(e)}


