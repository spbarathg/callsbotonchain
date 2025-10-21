# fetch_feed.py
from typing import Dict, Any
import requests
import time
from datetime import datetime, timezone
from typing import Optional
import os
from app.config_unified import CIELO_API_KEY, MIN_USD_VALUE, CIELO_LIST_ID, CIELO_NEW_TRADE_ONLY
from app.config_unified import CIELO_MIN_WALLET_PNL, CIELO_MIN_TRADES, CIELO_MIN_WIN_RATE
from app.config_unified import HTTP_TIMEOUT_FEED
from app.http_client import request_json
from app.logger_utils import log_process
from app.budget import get_budget
try:
    from app.config_unified import CIELO_LIST_IDS  # optional multi-list support
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

    # OPTIMIZED: Single parameter set (removed Tesla valve logic - multiple redundant variants)
    params = {
        "limit": 100,
        "chains": "solana",  # Use modern format only
    }
    if cursor:
        params["cursor"] = cursor
    
    # Multi-list support
    if CIELO_LIST_IDS:
        params["list_id"] = ",".join(str(x) for x in CIELO_LIST_IDS)
    elif CIELO_LIST_ID is not None:
        params["list_id"] = CIELO_LIST_ID
    if CIELO_NEW_TRADE_ONLY:
        params["new_trade"] = "true"

    # Add smart money filters
    if smart_money_only:
        params.update({
            "smart_money": "true",
            "min_wallet_pnl": str(int(CIELO_MIN_WALLET_PNL)),
            "top_wallets": "true"
        })
        if int(CIELO_MIN_TRADES or 0) > 0:
            params["min_trades"] = str(int(CIELO_MIN_TRADES))
        if int(CIELO_MIN_WIN_RATE or 0) > 0:
            params["min_win_rate"] = str(int(CIELO_MIN_WIN_RATE))
        if MIN_USD_VALUE and MIN_USD_VALUE > 0:
            params["minimum_usd_value"] = max(50, MIN_USD_VALUE // 4)
    else:
        if MIN_USD_VALUE and MIN_USD_VALUE > 0:
            params["minimum_usd_value"] = MIN_USD_VALUE

    # OPTIMIZED: Single header format (removed unnecessary variants)
    headers = {"X-API-Key": CIELO_API_KEY}

    # Budget check
    try:
        b = get_budget()
        if not b.can_spend("feed"):
            return {"transactions": [], "next_cursor": None, "error": "budget_exceeded"}
    except Exception:
        pass

    # OPTIMIZED: Simplified parsing and validation (removed excessive coercion logic)
    def _parse_items(api_response: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(api_response, dict):
            return {"items": [], "next_cursor": None}
        
        # Try standard shapes in order
        if api_response.get("status") == "ok":
            data = api_response.get("data")
            if isinstance(data, dict):
                items = data.get("items", [])
                next_cursor = data.get("paging", {}).get("next_cursor") if isinstance(data.get("paging"), dict) else None
                return {"items": items if isinstance(items, list) else [], "next_cursor": next_cursor}
            elif isinstance(data, list):
                return {"items": data, "next_cursor": None}
        
        if isinstance(api_response.get("items"), list):
            return {"items": api_response["items"], "next_cursor": api_response.get("next_cursor")}
        
        return {"items": [], "next_cursor": None}

    # OPTIMIZED: Fast validation - reject invalid items immediately
    def _valid_item(item: Dict[str, Any]) -> bool:
        if not isinstance(item, dict):
            return False
        # Must have token address
        if not (item.get("token0_address") or item.get("token1_address") or item.get("token")):
            return False
        # Must have positive USD value
        usd = item.get("usd_value") or item.get("token1_amount_usd") or item.get("token0_amount_usd") or 0
        try:
            usd_float = float(usd)
            # CRITICAL FIX: Check for NaN and inf (NaN comparisons always return False!)
            if not (usd_float == usd_float):  # NaN check (NaN != NaN)
                return False
            if usd_float == float('inf') or usd_float == float('-inf'):
                return False
            if usd_float <= 0:
                return False
        except (ValueError, TypeError):
            return False
        return True

    # OPTIMIZED: Linear retry (removed nested header/param loops - Tesla valve eliminated)
    last_retry_after: Optional[int] = None
    quota_exceeded = False
    max_retries = 3

    for attempt in range(max_retries):
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
                # Fast validation - no coercion attempts
                valid = [it for it in parsed["items"] if _valid_item(it)]
                if valid:
                    return {"transactions": valid, "next_cursor": parsed.get("next_cursor"), "error": None}
            
            # Empty response - might be no activity, break and try fallback
            break
            
        elif status == 429:
            body = result.get("json") or {}
            if "quota" in (body.get("message") or "").lower():
                quota_exceeded = True
            
            retry_after = _parse_retry_after_seconds(type('R', (), {'headers': result.get("headers", {})}))
            if retry_after:
                last_retry_after = max(last_retry_after or 0, retry_after)
                time.sleep(min(retry_after, 30))
            else:
                time.sleep(min(2 ** attempt, 30))
            continue
            
        elif status in (401, 403):
            # Auth failure - no point retrying
            break
            
        elif attempt < max_retries - 1:
            # Network error or other - retry with backoff
            time.sleep(min(2 ** attempt, 10))
            continue
        else:
            break

    # All retries failed - provide error info for adaptive cooldown
    if last_retry_after is not None or quota_exceeded:
        return {
            "transactions": [],
            "next_cursor": None,
            "error": "quota_exceeded" if quota_exceeded else "rate_limited",
            "retry_after_sec": max(last_retry_after or 0, 0),
        }
    
    # OPTIMIZED: Single fallback path (removed redundant try/catch nesting)
    fallback = _fallback_feed_from_dexscreener(limit=30, smart_money_only=smart_money_only)
    if not fallback:
        fallback = _fallback_feed_from_geckoterminal(limit=30)
    
    if fallback:
        return {"transactions": fallback, "next_cursor": None, "error": None}
    
    return {"transactions": [], "next_cursor": None, "error": "retries_exhausted"}


def _fallback_feed_from_dexscreener(limit: int = 30, smart_money_only: bool = False) -> list:
    """OPTIMIZED: Simplified fallback feed from DexScreener
    
    NOTE: DexScreener trending endpoint may be blocked by Cloudflare.
    This fallback is kept for redundancy but may not work reliably.
    GeckoTerminal is the preferred fallback.
    """
    from app.http_client import request_json as _rq
    
    # Try trending first (may get 403 from Cloudflare)
    r = _rq("GET", "https://api.dexscreener.com/latest/dex/trending", timeout=HTTP_TIMEOUT_FEED)
    if r.get("status_code") not in [200, 201]:
        # Silently fail and let caller try next fallback
        return []
    
    data = r.get("json", {})
    pairs = data.get("pairs", []) if isinstance(data, dict) else data if isinstance(data, list) else []
    
    if not pairs:
        return []
    
    sol_mint = "So11111111111111111111111111111111111111112"
    txs = []
    min_usd = 1200.0 if smart_money_only else 800.0
    
    for p in pairs[:limit]:  # Limit iteration
        if str(p.get("chainId", "")).lower() != "solana":
            continue
        
        base = p.get("baseToken", {})
        token = base.get("address")
        if not token:
            continue
        
        # Quick USD value estimation
        liq = float(p.get("liquidity", {}).get("usd", 0) or 0)
        vol24 = float(p.get("volume", {}).get("h24", 0) or 0)
        usd_val = max(min_usd, min(liq * 0.02 + vol24 * 0.03, 5000.0))
        
        txs.append({
            "token0_address": sol_mint,
            "token1_address": token,
            "token0_amount_usd": 0,
            "token1_amount_usd": usd_val,
            "dex": p.get("dexId", "dexscreener"),
            "tx_type": "trending_fallback",
            "is_synthetic": True,
        })
        
        if len(txs) >= limit:
            break
    
    return txs


def _fallback_feed_from_geckoterminal(limit: int = 30) -> list:
    """OPTIMIZED: Simplified GeckoTerminal fallback"""
    from app.http_client import request_json as _rq
    
    r = _rq("GET", "https://api.geckoterminal.com/api/v2/networks/solana/trending_pools", timeout=HTTP_TIMEOUT_FEED)
    if r.get("status_code") != 200:
        return []
    
    data = r.get("json", {}).get("data", [])
    if not data:
        return []
    
    sol_mint = "So11111111111111111111111111111111111111112"
    txs = []
    
    for item in data[:limit]:
        try:
            # Extract token address from relationships
            rel = item.get("relationships", {})
            base_rel = rel.get("base_token", {}).get("data", {}).get("id", "")
            
            # Parse address from "solana_ADDRESS" format
            token_addr = base_rel.split("_", 1)[1] if base_rel.startswith("solana_") else base_rel
            if not token_addr:
                continue
            
            # Quick USD estimation
            attrs = item.get("attributes", {})
            fdv = float(attrs.get("fdv_usd", 0) or 0)
            price = float(attrs.get("base_token_price_usd", 0) or 0)
            usd_val = max(1000.0, min(fdv * 0.01 if fdv > 0 else price * 120000.0, 7500.0))
            
            txs.append({
                "token0_address": sol_mint,
                "token1_address": token_addr,
                "token0_amount_usd": 0,
                "token1_amount_usd": usd_val,
                "tx_type": "gecko_trending_fallback",
                "dex": "geckoterminal",
                "is_synthetic": True,
            })
            
            if len(txs) >= limit:
                break
        except Exception:
            continue
    
    return txs
