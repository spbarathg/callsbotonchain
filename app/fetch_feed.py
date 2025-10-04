# fetch_feed.py
from typing import Dict, Any
import requests
import time
from datetime import datetime, timezone
from typing import Optional
import os
from config import CIELO_API_KEY, MIN_USD_VALUE, CIELO_LIST_ID, CIELO_NEW_TRADE_ONLY
from config import CIELO_MIN_WALLET_PNL, CIELO_MIN_TRADES, CIELO_MIN_WIN_RATE
from config import HTTP_TIMEOUT_FEED
from app.http_client import request_json
from app.logger_utils import log_process
from app.budget import get_budget
try:
    from config import CIELO_LIST_IDS  # optional multi-list support
except Exception:
    CIELO_LIST_IDS = []


def _parse_retry_after_seconds(resp: requests.Response) -> Optional[int]:
    """
    Try to determine how long to wait from rate limit headers.
    Supports standard Retry-After seconds and epoch reset headers.
    Returns None if not determinable.
    """
    # Standard header with seconds or HTTP-date
    ra = resp.headers.get("Retry-After")
    if ra:
        try:
            # Prefer integer seconds if provided
            return int(float(ra))
        except Exception:
            # If it's a date format, try to parse to epoch seconds
            try:
                reset_dt = datetime.strptime(ra, "%a, %d %b %Y %H:%M:%S %Z")
                now = datetime.now(timezone.utc)
                return max(0, int((reset_dt - now).total_seconds()))
            except Exception:
                pass

    # Common vendor-specific headers with epoch seconds
    for key in ("X-RateLimit-Reset", "X-RateLimit-Reset-At", "X-Ratelimit-Reset", "RateLimit-Reset"):
        val = resp.headers.get(key)
        if not val:
            continue
        try:
            reset_epoch = int(float(val))
            now_epoch = int(time.time())
            return max(0, reset_epoch - now_epoch)
        except Exception:
            continue
    return None


def fetch_solana_feed(cursor=None, smart_money_only: bool = False) -> Dict[str, Any]:
    # Emergency switch: force fallback feed for resilience/testing
    if os.getenv("CALLSBOT_FORCE_FALLBACK", "false").strip().lower() == "true":
        try:
            items = _fallback_feed_from_geckoterminal(limit=40)
            if not items:
                items = _fallback_feed_from_dexscreener(limit=40, smart_money_only=smart_money_only)
            if items:
                try:
                    log_process({"type": "feed_fallback_forced", "count": len(items)})
                except Exception:
                    pass
                return {"transactions": items, "next_cursor": None, "error": None}
        except Exception:
            return {"transactions": [], "next_cursor": None, "error": "forced_fallback_failed"}
    url = "https://feed-api.cielo.finance/api/v1/feed"

    # Base parameters (keep minimal to maximize visibility). We will try
    # multiple variants because upstream APIs sometimes toggle between
    # "chain" and "chains", and occasionally accept no chain filter.
    base_params = {
        "limit": 100,
        "cursor": cursor,
    }
    # Multi-list support: if CIELO_LIST_IDS present, prefer it; else fallback to single CIELO_LIST_ID
    if CIELO_LIST_IDS:
        base_params["list_id"] = ",".join(str(x) for x in CIELO_LIST_IDS)
    elif CIELO_LIST_ID is not None:
        base_params["list_id"] = CIELO_LIST_ID
    if CIELO_NEW_TRADE_ONLY:
        base_params["new_trade"] = "true"

    # Add smart money filters for enhanced detection
    if smart_money_only:
        base_params.update({
            "smart_money": "true",
            # Raise wallet quality bar significantly to avoid bots/noise
            "min_wallet_pnl": str(int(CIELO_MIN_WALLET_PNL)),
            "top_wallets": "true"
        })
        # Optional quality parameters if upstream supports them
        if int(CIELO_MIN_TRADES or 0) > 0:
            base_params["min_trades"] = str(int(CIELO_MIN_TRADES))
        if int(CIELO_MIN_WIN_RATE or 0) > 0:
            base_params["min_win_rate"] = str(int(CIELO_MIN_WIN_RATE))
        # CRITICAL FIX: Smart money trades are often smaller but highly strategic
        # Use a much lower USD filter for smart money to catch early entries
        if MIN_USD_VALUE and MIN_USD_VALUE > 0:
            base_params["minimum_usd_value"] = max(50, MIN_USD_VALUE // 4)
        try:
            log_process({
                "type": "feed_mode",
                "mode": "smart_money",
            })
        except Exception:
            pass
    else:
        # Only include minimum_usd_value for general feed
        if MIN_USD_VALUE and MIN_USD_VALUE > 0:
            base_params["minimum_usd_value"] = MIN_USD_VALUE
        try:
            log_process({
                "type": "feed_mode",
                "mode": "general",
            })
        except Exception:
            pass

    # Respect configured MIN_USD_VALUE as-is to maximize visibility
    # Header name should be case-insensitive, keep canonical spelling
    # Cielo is case-insensitive, but align with other modules using X-API-Key
    header_variants = [
        {"X-API-Key": CIELO_API_KEY},
        {"Authorization": f"Bearer {CIELO_API_KEY}"},
    ]

    last_retry_after: Optional[int] = None
    quota_exceeded = False
    max_retries = 3
    # Budget check (treat feed as low-cost but enforce cap)
    try:
        b = get_budget()
        if not b.can_spend("feed"):
            return {"transactions": [], "next_cursor": None, "error": "budget_exceeded"}
    except Exception:
        pass
    # Build a small set of parameter variants to maximize compatibility
    # with upstream API quirks.

    def _param_variants() -> list:
        variants = []
        # Preferred modern form
        v1 = dict(base_params)
        v1["chains"] = "solana"
        variants.append(v1)
        # Single chain key variant
        v2 = dict(base_params)
        v2["chain"] = "solana"
        variants.append(v2)
        # Last resort: no chain filter
        v3 = dict(base_params)
        v3.pop("cursor", None) if v3.get("cursor") is None else None
        variants.append(v3)
        return variants

    def _parse_items(api_response: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Shape A: {status:"ok", data:{items:[...], paging:{next_cursor}}}
            if api_response.get("status") == "ok" and isinstance(api_response.get("data"), dict):
                data = api_response["data"]
                items = data.get("items") or []
                next_cursor = (data.get("paging", {}) or {}).get("next_cursor")
                return {"items": items or [], "next_cursor": next_cursor}
            # Shape B: {status:"ok", data:[...]}
            if api_response.get("status") == "ok" and isinstance(api_response.get("data"), list):
                return {"items": api_response.get("data") or [], "next_cursor": None}
            # Shape C: {items:[...], next_cursor:...}
            if isinstance(api_response.get("items"), list):
                return {"items": api_response.get("items") or [], "next_cursor": api_response.get("next_cursor")}
            # Shape D: top-level list
            if isinstance(api_response, list):
                return {"items": api_response, "next_cursor": None}
        except Exception:
            pass
        return {"items": [], "next_cursor": None}

    # track if we saw 200 with no items (for debug/logging only)
    def _valid_item(item: Dict[str, Any]) -> bool:
        """Lenient validation to keep the pipeline flowing even when upstream schema varies.
        Accept any item that has a token address and a positive USD estimate derived from common fields.
        If timestamp is missing, synthesize a current timestamp.
        """
        try:
            tok = item.get("token0_address") or item.get("token1_address") or item.get("token")
            if not tok:
                return False
            # Try multiple fields for USD value
            candidates = [
                item.get("usd_value"),
                item.get("token1_amount_usd"),
                item.get("token0_amount_usd"),
                item.get("amount_usd"),
                item.get("value_usd"),
            ]
            usd_val: float = 0.0
            for c in candidates:
                try:
                    v = float(c if c is not None else 0)
                    if v > usd_val:
                        usd_val = v
                except Exception:
                    continue
            if usd_val <= 0:
                return False
            # Ensure timestamp exists; synthesize if missing
            ts = item.get("ts") or item.get("timestamp") or item.get("time")
            if ts is None:
                try:
                    item["ts"] = int(time.time())
                except Exception:
                    pass
            return True
        except Exception:
            return False

    for attempt in range(max_retries):
        # Try both header and parameter variants within the attempt
        made_progress = False
        rate_limited_encountered = False
        for headers in header_variants:
            for params in _param_variants():
                result = request_json("GET", url, params=params, headers=headers, timeout=HTTP_TIMEOUT_FEED)
                status = result.get("status_code")
                if status == 200:
                    try:
                        get_budget().spend("feed")
                    except Exception:
                        pass
                    api_response = result.get("json") or {}
                    parsed = _parse_items(api_response)
                    if parsed["items"]:
                        # Lenient validation with coercion: keep valid items; coerce partials when possible
                        valid = []
                        for it in parsed["items"]:
                            if _valid_item(it):
                                valid.append(it)
                            else:
                                # Attempt to coerce partials by inferring usd_value from available fields
                                try:
                                    if isinstance(it, dict):
                                        if it.get("token0_address") or it.get("token1_address") or it.get("token"):
                                            # try derive usd from amounts
                                            for k in ("token1_amount_usd", "token0_amount_usd", "amount_usd", "value_usd"):
                                                try:
                                                    v = float(it.get(k) or 0)
                                                    if v > 0:
                                                        it.setdefault("usd_value", v)
                                                        break
                                                except Exception:
                                                    continue
                                            if _valid_item(it):
                                                valid.append(it)
                                                continue
                                except Exception:
                                    pass
                                try:
                                    log_process({"type": "feed_item_invalid", "reason": "missing_required_fields"})
                                except Exception:
                                    pass
                        return {"transactions": valid, "next_cursor": parsed.get("next_cursor"), "error": None}
                    # If 200 but empty, continue trying next param variant (could be filter mismatch)
                    try:
                        log_process({
                            "type": "feed_debug",
                            "status": int(status),
                            "params": {k: v for k, v in (params or {}).items() if k in ("limit", "chains", "chain", "new_trade", "smart_money")},
                            "message": (api_response.get("message") or "")[:160],
                            "shape_keys": list(api_response.keys())[:8],
                            "items_len": 0,
                        })
                    except Exception:
                        pass
                    made_progress = True
                    continue
                elif status == 429:
                    body = result.get("json") or {}
                    msg = (body.get("message") or "").lower()
                    if "maximum api credit" in msg or "quota" in msg:
                        quota_exceeded = True

                    class _R:
                        def __init__(self, headers):
                            self.headers = headers
                    retry_after = _parse_retry_after_seconds(_R(result.get("headers") or {}))
                    if retry_after is not None:
                        last_retry_after = max(last_retry_after or 0, retry_after)
                    # Add small jitter to reduce thundering herd
                    try:
                        import random as _rand
                        if last_retry_after is not None:
                            last_retry_after = int(last_retry_after + _rand.uniform(0, 0.5))
                    except Exception:
                        pass
                    try:
                        log_process({
                            "type": "rate_limited",
                            "attempt": int(attempt + 1),
                            "retry_after_sec": int(retry_after or 0),
                        })
                    except Exception:
                        pass
                    time.sleep(retry_after if retry_after is not None else (2 ** attempt))
                    # Move to next attempt after backoff
                    made_progress = True
                    rate_limited_encountered = True
                    break
                elif status in (401, 403):
                    # try next header variant within the same attempt
                    continue
                elif status is None:
                    try:
                        log_process({
                            "type": "network_exception",
                            "attempt": int(attempt + 1),
                            "error": str(result.get("error") or "")[:200],
                        })
                    except Exception:
                        pass
                    # try next param/header variant
                    continue
                else:
                    text = None
                    if result.get("json") is None:
                        text = (result.get("text") or "")
                    print(f"Error fetching feed: {status}, {text}")
                    try:
                        log_process({
                            "type": "feed_error",
                            "status": status,
                            "text": (text or "")[:200],
                        })
                    except Exception:
                        pass
                    # try next param/header variant
                    continue
            # if we hit rate-limit we already broke param loop; break header loop as well to proceed to next attempt
            if rate_limited_encountered:
                break
        # No header/param variant produced items this attempt
        if attempt < max_retries - 1:
            # Only sleep a bit between attempts if we made a request but got empty/other errors
            if made_progress and not quota_exceeded and (last_retry_after is None):
                time.sleep(1)
            continue
        # Allow fallback logic below to engage (avoid returning http_200 on empty)
        break

    # All retries failed
    try:
        log_process({
            "type": "feed_failed",
            "max_retries": int(max_retries),
            "quota_exceeded": bool(quota_exceeded),
            "retry_after_sec": int(last_retry_after or 0),
        })
    except Exception:
        pass
    if last_retry_after is not None or quota_exceeded:
        # Provide a hint to caller for adaptive cooldown
        return {
            "transactions": [],
            "next_cursor": None,
            "error": "quota_exceeded" if quota_exceeded else "rate_limited",
            "retry_after_sec": max(last_retry_after or 0, 0),
        }
    # As a last resort, build a fallback feed from DexScreener trending pairs
    try:
        # Try DexScreener first; if blocked by Cloudflare, try GeckoTerminal
        fallback = _fallback_feed_from_dexscreener(limit=30, smart_money_only=smart_money_only)
        if not fallback:
            fallback = _fallback_feed_from_geckoterminal(limit=30)
        if fallback and len(fallback) > 0:
            try:
                log_process({
                    "type": "feed_fallback",
                    "provider": "dexscreener_or_gecko",
                    "count": len(fallback),
                })
            except Exception:
                pass
            return {"transactions": fallback, "next_cursor": None, "error": None}
    except Exception:
        pass
    return {"transactions": [], "next_cursor": None, "error": "retries_exhausted"}


def _fallback_feed_from_dexscreener(limit: int = 30, smart_money_only: bool = False) -> list:
    """
    Build a synthetic feed using DexScreener trending/pairs endpoints.
    Returns a list of tx-like dicts that downstream code can consume.
    """
    from app.http_client import request_json as _rq
    urls = [
        "https://api.dexscreener.com/latest/dex/trending",
        "https://api.dexscreener.com/latest/dex/pairs/solana",
    ]
    pairs = []
    for u in urls:
        r = _rq("GET", u, timeout=HTTP_TIMEOUT_FEED)
        if r.get("status_code") == 200:
            j = r.get("json") or {}
            if isinstance(j, dict):
                ps = j.get("pairs") or []
            elif isinstance(j, list):
                ps = j
            else:
                ps = []
            if ps:
                pairs = ps
                break
    if not pairs:
        return []
    sol_mint = "So11111111111111111111111111111111111111112"
    txs = []
    for p in pairs:
        if p.get("chainId") and str(p.get("chainId")).lower() != "solana":
            continue
        base = (p.get("baseToken") or {})
        token = base.get("address") or base.get("address0") or base.get("id")
        if not token:
            continue
        liq = (p.get("liquidity") or {}).get("usd") or 0
        vol24 = (p.get("volume") or {}).get("h24") or 0
        # Synthesize a plausible USD trade size to drive prelim scoring
        try:
            liq = float(liq or 0)
        except Exception:
            liq = 0.0
        try:
            vol24 = float(vol24 or 0)
        except Exception:
            vol24 = 0.0
        # Encourage detailed analysis by ensuring prelim score crosses threshold
        min_usd = 1200.0 if smart_money_only else 800.0
        usd_val = max(min_usd, min(max(float(liq or 0) * 0.02, float(vol24 or 0) * 0.03), 5000.0))
        tx = {
            # Structure mimics a Cielo feed item for downstream parsing
            "token0_address": sol_mint,
            "token1_address": token,
            "token0_amount_usd": 0,
            "token1_amount_usd": usd_val,
            # Helpful extras (ignored by parser but useful for future)
            "dex": (p.get("dexId") or "dexscreener"),
            "tx_type": "trending_fallback",
        }
        tx["is_synthetic"] = True
        txs.append(tx)
        if len(txs) >= int(limit or 30):
            break
    return txs


def _fallback_feed_from_geckoterminal(limit: int = 30) -> list:
    """
    Build a synthetic feed using GeckoTerminal trending pools for Solana.
    This endpoint is generally accessible without Cloudflare challenges.
    """
    from app.http_client import request_json as _rq
    url = "https://api.geckoterminal.com/api/v2/networks/solana/trending_pools"
    r = _rq("GET", url, timeout=HTTP_TIMEOUT_FEED)
    if r.get("status_code") != 200:
        return []
    j = r.get("json") or {}
    data = j.get("data") or []
    # We don't require 'included'. Extract token addresses directly from relationship ids

    sol_mint = "So11111111111111111111111111111111111111112"
    txs = []
    for item in data:
        try:
            rel = item.get("relationships") or {}
            base_rel = ((rel.get("base_token") or {}).get("data") or {}).get("id")
            q_rel = ((rel.get("quote_token") or {}).get("data") or {}).get("id")

            def _addr_from_rel(rel_id: str) -> str:
                if not rel_id or not isinstance(rel_id, str):
                    return ""
                if rel_id.startswith("solana_"):
                    return rel_id.split("_", 1)[1]
                return rel_id
            base_addr = _addr_from_rel(base_rel)
            quote_addr = _addr_from_rel(q_rel)
            token_addr = base_addr or quote_addr
            if not token_addr:
                continue
            # Synthesize usd_value from pool liquidity/volume where available
            attrs = item.get("attributes") or {}
            # Prefer FDV/MCAP to approximate activity if liquidity not present in this endpoint
            fdv = 0.0
            try:
                fdv = float(attrs.get("fdv_usd") or attrs.get("market_cap_usd") or 0)
            except Exception:
                fdv = 0.0
            base_price = 0.0
            try:
                base_price = float(attrs.get("base_token_price_usd") or 0)
            except Exception:
                base_price = 0.0
            # Heuristic USD trade size: 1% of FDV capped, or synthetic from price
            min_usd = 1000.0
            est_from_fdv = (fdv * 0.01) if fdv > 0 else 0.0
            est_from_price = (base_price * 120000.0) if base_price > 0 else 0.0
            usd_val = max(min_usd, min(max(est_from_fdv, est_from_price), 7500.0))
            txs.append({
                "token0_address": sol_mint,
                "token1_address": token_addr,
                "token0_amount_usd": 0,
                "token1_amount_usd": usd_val,
                "tx_type": "gecko_trending_fallback",
                "dex": "geckoterminal",
                "is_synthetic": True,
            })
            if len(txs) >= int(limit or 30):
                break
        except Exception:
            continue
    return txs
