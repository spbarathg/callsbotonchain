# analyze_token.py
import time
import os
import json
import threading
from typing import Dict, Tuple, List, Any, Optional
from app.file_lock import file_lock
from config.config import (
    CIELO_API_KEY,
    CIELO_DISABLE_STATS,
    PRELIM_USD_HIGH,
    PRELIM_USD_MID,
    PRELIM_USD_LOW,
    MCAP_MICRO_MAX,
    MCAP_SMALL_MAX,
    MCAP_MID_MAX,
    VOL_VERY_HIGH,
    VOL_HIGH,
    VOL_MED,
    MOMENTUM_1H_STRONG,
    DRAW_24H_MAJOR,
    STABLE_MINTS,
    BLOCKLIST_SYMBOLS,
    MAX_MARKET_CAP_FOR_DEFAULT_ALERT,
    LARGE_CAP_MOMENTUM_GATE_1H,
    MIN_LIQUIDITY_USD,
    VOL_24H_MIN_FOR_ALERT,
    VOL_TO_MCAP_RATIO_MIN,
    MICROCAP_SWEET_MIN,
    MICROCAP_SWEET_MAX,
    MOMENTUM_1H_PUMPER,
    REQUIRE_MINT_REVOKED,
    REQUIRE_LP_LOCKED,
    ALLOW_UNKNOWN_SECURITY,
    MAX_TOP10_CONCENTRATION,
    HIGH_CONFIDENCE_SCORE,
    # Nuanced factors
    NUANCED_SCORE_REDUCTION,
    NUANCED_LIQUIDITY_FACTOR,
    NUANCED_VOL_TO_MCAP_FACTOR,
    NUANCED_MCAP_FACTOR,
    NUANCED_TOP10_CONCENTRATION_BUFFER,
    # Holder-composition caps
    MAX_BUNDLERS_PERCENT,
    MAX_INSIDERS_PERCENT,
    NUANCED_BUNDLERS_BUFFER,
    NUANCED_INSIDERS_BUFFER,
    REQUIRE_HOLDER_STATS_FOR_LARGE_CAP_ALERT,
    LARGE_CAP_HOLDER_STATS_MCAP_USD,
    ENFORCE_BUNDLER_CAP,
    ENFORCE_INSIDER_CAP,
)
from config.config import HTTP_TIMEOUT_STATS
from app.http_client import request_json
from app.budget import get_budget
from app.logger_utils import log_process


def _dexscreener_best_pair(pairs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not pairs:
        return None
    # Prefer Solana pairs with highest 24h volume, then liquidity
    sol_pairs = [p for p in pairs if (p.get("chainId") == "solana")]
    candidates = sol_pairs or pairs

    def score(p: Dict[str, Any]) -> float:
        vol = (p.get("volume") or {}).get("h24") or 0
        liq = (p.get("liquidity") or {}).get("usd") or 0
        return float(vol) * 1.0 + float(liq) * 0.1
    return max(candidates, key=score)


def _get_token_stats_dexscreener(token_address: str) -> Dict[str, Any]:
    url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
    max_retries = 3
    for attempt in range(max_retries):
        result = request_json("GET", url, timeout=HTTP_TIMEOUT_STATS)
        status = result.get("status_code")
        if status == 200:
            data = result.get("json") or {}
            try:
                pairs = data.get("pairs") or []
                best = _dexscreener_best_pair(pairs)
                if not best:
                    return {}
                base = best.get("baseToken") or {}
                price_change = best.get("priceChange") or {}
                volume = best.get("volume") or {}
                liquidity = best.get("liquidity") or {}
                # Prefer marketCap; do NOT substitute FDV to avoid misclassification
                mc_val = best.get("marketCap")
                market_cap: Any = None
                try:
                    if mc_val is not None:
                        market_cap = float(mc_val)
                except Exception:
                    market_cap = None
                price_usd = best.get("priceUsd")
                try:
                    price_usd = float(price_usd) if price_usd is not None else 0.0
                except Exception:
                    price_usd = 0.0
                stats: Dict[str, Any] = {
                    "market_cap_usd": market_cap,
                    "price_usd": price_usd,
                    "liquidity_usd": (liquidity.get("usd") or 0),
                    "name": base.get("name") or None,
                    "symbol": base.get("symbol") or None,
                    "volume": {
                        "24h": {
                            "volume_usd": volume.get("h24") or 0,
                            "unique_buyers": 0,
                            "unique_sellers": 0,
                        }
                    },
                    "change": {
                        "1h": (price_change.get("h1") or 0),
                        "24h": (price_change.get("h24") or 0),
                    },
                    # Unknown from DexScreener; leave empty so we don't penalize
                    "security": {},
                    "liquidity": {},
                    "holders": {},
                }
                stats["_source"] = "dexscreener"
                return stats
            except Exception:
                return {}
        elif status == 429:
            time.sleep(2 ** attempt)
            continue
        else:
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
    return {}


_DENY_STATE_FILE = os.getenv("CALLSBOT_DENY_FILE", os.path.join("var", "stats_deny.json"))
# Updated: Use time-boxed denial with TTL instead of permanent flag
_deny_cache = {"stats_denied_until": 0}  # Unix timestamp
_deny_lock = threading.Lock()
# Default TTL: 15 minutes (configurable via env)
_DENY_TTL_SECONDS = int(os.getenv("CALLSBOT_DENY_TTL_SEC", "900"))  # 15 min default


def _deny_load_unlocked() -> None:
    try:
        if not _DENY_STATE_FILE:
            return
        if not os.path.exists(os.path.dirname(_DENY_STATE_FILE) or "."):
            os.makedirs(os.path.dirname(_DENY_STATE_FILE) or ".", exist_ok=True)
        with file_lock(_DENY_STATE_FILE):
            if os.path.exists(_DENY_STATE_FILE):
                with open(_DENY_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        # Support legacy bool format for migration
                        if isinstance(data.get("stats_denied"), bool):
                            if data["stats_denied"]:
                                # Convert legacy permanent deny to TTL
                                _deny_cache["stats_denied_until"] = time.time() + _DENY_TTL_SECONDS
                            else:
                                _deny_cache["stats_denied_until"] = 0
                        # New TTL format
                        elif "stats_denied_until" in data:
                            _deny_cache["stats_denied_until"] = float(data["stats_denied_until"])
    except Exception as e:
        try:
            log_process({"type": "deny_state_load_error", "error": str(e)})
        except Exception:
            pass


def _deny_save_unlocked() -> None:
    try:
        if not _DENY_STATE_FILE:
            return
        os.makedirs(os.path.dirname(_DENY_STATE_FILE) or ".", exist_ok=True)
        with file_lock(_DENY_STATE_FILE):
            tmp = _DENY_STATE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(_deny_cache, f, ensure_ascii=False)
            os.replace(tmp, _DENY_STATE_FILE)
    except Exception as e:
        try:
            log_process({"type": "deny_state_save_error", "error": str(e)})
        except Exception:
            pass


def deny_is_denied() -> bool:
    """Check if stats API is currently denied (with TTL expiry)"""
    with _deny_lock:
        _deny_load_unlocked()
        denied_until = float(_deny_cache.get("stats_denied_until", 0))
        now = time.time()
        
        # Auto-clear expired denials
        if denied_until > 0 and now >= denied_until:
            try:
                log_process({
                    "type": "deny_expired",
                    "denied_until": denied_until,
                    "now": now,
                })
            except Exception:
                pass
            _deny_cache["stats_denied_until"] = 0
            _deny_save_unlocked()
            return False
        
        return denied_until > now


def deny_mark_denied(duration_sec: Optional[int] = None) -> None:
    """
    Mark stats API as denied for a time-boxed duration.
    
    Args:
        duration_sec: Duration in seconds (default: 15 minutes from env)
    """
    duration = duration_sec if duration_sec is not None else _DENY_TTL_SECONDS
    with _deny_lock:
        denied_until = time.time() + duration
        _deny_cache["stats_denied_until"] = denied_until
        _deny_save_unlocked()
        try:
            log_process({
                "type": "deny_marked",
                "duration_sec": duration,
                "denied_until": denied_until,
            })
        except Exception:
            pass


def deny_clear() -> None:
    """Manually clear the deny state"""
    with _deny_lock:
        _deny_cache["stats_denied_until"] = 0
        _deny_save_unlocked()


def deny_get_remaining_sec() -> int:
    """Get remaining deny duration in seconds"""
    with _deny_lock:
        _deny_load_unlocked()
        denied_until = float(_deny_cache.get("stats_denied_until", 0))
        now = time.time()
        if denied_until <= now:
            return 0
        return int(denied_until - now)


_stats_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_stats_lock = threading.Lock()
_STATS_TTL_SEC = int(os.getenv("STATS_TTL_SEC", os.getenv("CALLSBOT_STATS_TTL", "900")))  # default 15 minutes

_REDIS_URL = os.getenv("REDIS_URL") or os.getenv("CALLSBOT_REDIS_URL") or ""
_redis_client = None
if _REDIS_URL:
    try:
        import redis  # type: ignore
        _redis_client = redis.from_url(_REDIS_URL, decode_responses=False)
    except Exception:
        _redis_client = None


def _cache_get(token_address: str) -> Optional[Dict[str, Any]]:
    import time as _t
    key = f"stats:{token_address}"
    # Prefer Redis when available
    if _redis_client is not None:
        try:
            raw = _redis_client.get(key)
            if raw:
                return json.loads(raw.decode("utf-8"))
        except Exception as e:
            try:
                log_process({"type": "stats_cache_redis_get_error", "error": str(e)})
            except Exception:
                pass
    # Fallback in-memory
    with _stats_lock:
        item = _stats_cache.get(token_address)
        if not item:
            return None
        ts, data = item
        if (_t.time() - ts) <= _STATS_TTL_SEC:
            return data
        try:
            _stats_cache.pop(token_address, None)
        except Exception as e:
            try:
                log_process({"type": "stats_cache_pop_error", "error": str(e)})
            except Exception:
                pass
        return None


def _cache_set(token_address: str, data: Dict[str, Any]) -> None:
    import time as _t
    key = f"stats:{token_address}"
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    if _redis_client is not None:
        try:
            _redis_client.setex(key, _STATS_TTL_SEC, payload)
            return
        except Exception as e:
            try:
                log_process({"type": "stats_cache_redis_set_error", "error": str(e)})
            except Exception:
                pass
    with _stats_lock:
        _stats_cache[token_address] = (_t.time(), data)


def get_token_stats(token_address: str, force_refresh: bool = False) -> Dict[str, Any]:
    if not token_address:
        return {}
    cached = _cache_get(token_address) if not force_refresh else None
    if cached:
        try:
            from app.metrics import cache_hit
            cache_hit()
        except Exception:
            pass
        try:
            # Emit lightweight process log so the web can compute cache hit% without Prometheus
            log_process({"type": "stats_cache_hit", "token": token_address})
        except Exception:
            pass
        return cached
    else:
        try:
            from app.metrics import cache_miss
            cache_miss()
        except Exception:
            pass
        try:
            log_process({"type": "stats_cache_miss", "token": token_address})
        except Exception:
            pass
    # Enforce budget before hitting paid APIs; fall back to DexScreener if blocked
    try:
        b = get_budget()
        if b and (not b.can_spend("stats")):
            try:
                log_process({"type": "token_stats_budget_block", "provider": "cielo", "fallback": "dexscreener"})
            except Exception:
                pass
            ds = _get_token_stats_dexscreener(token_address)
            return _normalize_stats_schema(ds) if ds else {}
    except Exception:
        # If budget subsystem errors, proceed normally (will try Cielo then DexScreener)
        pass

    base_urls = [
        "https://feed-api.cielo.finance/api/v1",
        "https://api.cielo.finance/api/v1",
    ]
    # Guard headers so we don't send None/"Bearer None"; if no key, prefer DexScreener
    header_variants = []
    if CIELO_API_KEY:
        header_variants.append({"X-API-Key": CIELO_API_KEY})
        header_variants.append({"Authorization": f"Bearer {CIELO_API_KEY}"})
    params = {"token_address": token_address, "chain": "solana"}

    # Add timeout and retry logic (handled in http_client)

    # Skip Cielo if user disabled or we detected denial previously
    if CIELO_DISABLE_STATS or deny_is_denied():
        return _get_token_stats_dexscreener(token_address)

    # If no API key configured, avoid calling Cielo with invalid headers
    if not (CIELO_API_KEY and str(CIELO_API_KEY).strip()):
        try:
            log_process({"type": "token_stats_no_api_key", "provider": "cielo", "fallback": "dexscreener"})
        except Exception:
            pass
        return _normalize_stats_schema(_get_token_stats_dexscreener(token_address) or {})

    combos = [(b, h) for b in base_urls for h in header_variants]
    last_status = None
    import random as _rand
    for idx, (base, hdrs) in enumerate(combos):
        url = f"{base}/token/stats"
        result = request_json("GET", url, params=params, headers=hdrs, timeout=HTTP_TIMEOUT_STATS)
        last_status = result.get("status_code")
        if last_status == 200:
            try:
                budget = get_budget()
                if not budget.spend("stats"):
                    try:
                        log_process({
                            "type": "budget_spend_failed",
                            "token": token_address,
                            "reason": "budget_exhausted",
                        })
                    except Exception:
                        pass
                try:
                    from app.metrics import add_stats_budget_used
                    add_stats_budget_used(1)
                except Exception:
                    pass
            except Exception:
                pass
            api_response = result.get("json") or {}
            try:
                if api_response.get("status") == "ok" and "data" in api_response:
                    api_response["data"]["_source"] = "cielo"
                    # Augment with DexScreener when critical fields are missing
                    try:
                        data = api_response["data"]
                        # Normalize schema keys for downstream consumers
                        data = _normalize_stats_schema(data)

                        def _missing_liq(d: Dict[str, Any]) -> bool:
                            liq_obj = d.get('liquidity') or {}
                            return not bool(d.get('liquidity_usd') or liq_obj.get('usd'))

                        def _missing_vol(d: Dict[str, Any]) -> bool:
                            return not bool(((d.get('volume') or {}).get('24h') or {}).get('volume_usd'))

                        def _missing_mcap(d: Dict[str, Any]) -> bool:
                            try:
                                return float(d.get('market_cap_usd') or 0) <= 0
                            except Exception:
                                return True

                        if _missing_liq(data) or _missing_vol(data) or _missing_mcap(data) or not data.get('symbol') or not data.get('name'):
                            ds = _get_token_stats_dexscreener(token_address)
                            if ds:
                                # Liquidity
                                if _missing_liq(data) and (ds.get('liquidity_usd') or (ds.get('liquidity') or {}).get('usd')):
                                    if ds.get('liquidity_usd') is not None:
                                        data['liquidity_usd'] = ds.get('liquidity_usd')
                                    if ds.get('liquidity'):
                                        data['liquidity'] = ds.get('liquidity')
                                # Volume (24h)
                                if _missing_vol(data) and (((ds.get('volume') or {}).get('24h') or {}).get('volume_usd') is not None):
                                    vol24 = ((ds.get('volume') or {}).get('24h') or {})
                                    data.setdefault('volume', {}).setdefault('24h', {})[
                                        'volume_usd'] = vol24.get('volume_usd')
                                # Market cap
                                if _missing_mcap(data) and (ds.get('market_cap_usd') is not None):
                                    data['market_cap_usd'] = ds.get('market_cap_usd')
                                # Symbol/name enrichment for UI/alerts
                                if (not data.get('symbol')) and ds.get('symbol'):
                                    data['symbol'] = ds.get('symbol')
                                if (not data.get('name')) and ds.get('name'):
                                    data['name'] = ds.get('name')
                                # Mark composite source
                                try:
                                    data['_source'] = f"{data.get('_source') or 'cielo'}+ds"
                                except Exception:
                                    data['_source'] = 'cielo+ds'
                        _cache_set(token_address, data)
                        return data
                    except Exception:
                        # If augmentation fails for any reason, still return Cielo data
                        norm = _normalize_stats_schema(api_response["data"]) if isinstance(
                            api_response.get("data"), dict) else api_response.get("data")
                        _cache_set(token_address, norm)
                        return norm
                if isinstance(api_response, dict):
                    api_response["_source"] = "cielo"
                norm = _normalize_stats_schema(api_response) if isinstance(api_response, dict) else api_response
                _cache_set(token_address, norm)
                return norm
            except Exception:
                return {}
        elif last_status == 429:
            # Respect Retry-After header and backoff with jitter; mark denied on persistent blocks
            try:
                log_process({"type": "token_stats_rate_limited", "variant": int(idx + 1)})
                try:
                    from app.metrics import inc_deny
                    inc_deny()
                except Exception:
                    pass
            except Exception:
                pass
            headers = result.get("headers") or {}
            retry_after = 0
            try:
                ra = headers.get("Retry-After")
                if ra:
                    retry_after = int(float(ra))
            except Exception:
                retry_after = 0
            if retry_after <= 0:
                # Exponential backoff with jitter based on idx
                base_delay = 2 ** max(0, idx)
                jitter = _rand.uniform(0, 0.5)
                retry_after = base_delay + jitter
            time.sleep(min(30, retry_after))
            if idx >= len(combos) - 1:
                # Use default TTL to avoid accidental 1s deny due to bool->int cast
                deny_mark_denied()
            continue
        elif last_status == 404:
            try:
                log_process({"type": "token_stats_not_found", "token": token_address})
            except Exception:
                pass
            return {}
        elif last_status in (401, 403):
            # Try next variant
            continue
        else:
            txt = None
            if result.get("json") is None:
                txt = result.get("text")
            try:
                log_process({"type": "token_stats_error", "status": last_status, "text": (txt or "")[:200]})
            except Exception:
                pass
            continue

    if last_status in (401, 403):
        # Use default TTL to avoid accidental short deny
        deny_mark_denied()
        try:
            log_process({"type": "token_stats_denied_variants", "provider": "cielo", "fallback": "dexscreener"})
        except Exception:
            pass
    else:
        try:
            log_process({"type": "token_stats_unavailable", "last_status": last_status, "fallback": "dexscreener"})
        except Exception:
            pass
    return _normalize_stats_schema(_get_token_stats_dexscreener(token_address) or {})


def _normalize_stats_schema(d: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure consistent keys and types across Cielo and DexScreener shapes.
    - Guarantees numeric normalization and unknown flags.
    - Fields: market_cap_usd, price_usd, liquidity_usd, volume.24h.volume_usd, change.{1h,24h}.
    """
    if not isinstance(d, dict):
        return {}
    out: Dict[str, Any] = dict(d)
    # Market cap
    try:
        out["market_cap_usd"] = float(out.get("market_cap_usd"))
        out["market_cap_unknown"] = False
    except Exception:
        out["market_cap_usd"] = float("nan")
        out["market_cap_unknown"] = True
    # Price
    try:
        out["price_usd"] = float(out.get("price_usd"))
        out["price_unknown"] = False
    except Exception:
        out["price_usd"] = float("nan")
        out["price_unknown"] = True
    # Liquidity
    liq_obj = out.get("liquidity") or {}
    try:
        liq_usd = out.get("liquidity_usd")
        if liq_usd is None:
            liq_usd = liq_obj.get("usd")
        if liq_usd is None:
            # CRITICAL FIX: Use 0.0 instead of NaN (NaN comparisons always False!)
            out["liquidity_usd"] = 0.0
            out["liquidity_unknown"] = True
        else:
            value = float(liq_usd)
            # Handle NaN/inf from API responses
            if not (value == value) or value == float('inf') or value == float('-inf'):
                out["liquidity_usd"] = 0.0
                out["liquidity_unknown"] = True
            else:
                out["liquidity_usd"] = value
                out["liquidity_unknown"] = False
    except Exception:
        out["liquidity_usd"] = 0.0
        out["liquidity_unknown"] = True
    # Volume
    v = (out.get("volume") or {})
    v24 = (v.get("24h") or {})
    try:
        v24_usd = float(v24.get("volume_usd"))
        out.setdefault("volume", {}).setdefault("24h", {})["volume_usd_unknown"] = False
    except Exception:
        v24_usd = float("nan")
        out.setdefault("volume", {}).setdefault("24h", {})["volume_usd_unknown"] = True
    out.setdefault("volume", {}).setdefault("24h", {})["volume_usd"] = v24_usd
    # Change
    ch = out.get("change") or {}
    for k in ("1h", "24h"):
        try:
            ch_val = float(ch.get(k))
            unknown_key = f"change_{k}_unknown"
            out[unknown_key] = False
        except Exception:
            ch_val = float("nan")
            unknown_key = f"change_{k}_unknown"
            out[unknown_key] = True
        out.setdefault("change", {})[k] = ch_val
    # Containers
    for k in ("security", "liquidity", "holders"):
        if not isinstance(out.get(k), dict):
            out[k] = {}
    return out


def calculate_preliminary_score(tx_data: Dict[str, Any], smart_money_detected: bool = False) -> int:
    """
    CREDIT-EFFICIENT: Calculate preliminary score from feed data without API calls
    Uses only data available in the transaction feed
    """
    score = 0

    # Smart money bonus REMOVED - analysis showed it's anti-predictive
    # if smart_money_detected:
    #     score += 3  # Baseline bonus

    # USD value indicates serious activity; downweight synthetic fallback items
    usd_value = tx_data.get('usd_value', 0) or 0
    is_synthetic = bool(tx_data.get('is_synthetic')) or str(tx_data.get('tx_type') or '').endswith('_fallback')
    high = PRELIM_USD_HIGH * (1.5 if is_synthetic else 1.0)
    mid = PRELIM_USD_MID * (1.5 if is_synthetic else 1.0)
    low = PRELIM_USD_LOW * (1.5 if is_synthetic else 1.0)
    if usd_value > high:
        score += 3
    elif usd_value > mid:
        score += 2
    elif usd_value > low:
        score += 1

    # Transaction frequency/urgency
    # Note: This would need to be tracked over time
    # For now, we use USD value as a proxy

    return min(score, 10)


def score_token(stats: Dict[str, Any], smart_money_detected: bool = False, token_address: Optional[str] = None) -> Tuple[int, List[str]]:
    """
    Compute a raw score based on token metrics only. This function no longer
    performs any filtering or gating. All gatekeeping is handled by moiety
    checkers (senior/junior strict/nuanced).
    """
    if not stats:
        return 0, []

    score = 0
    scoring_details: List[str] = []

    # Smart money bonus - REDUCED from +2 to 0 based on analysis
    # Data shows non-smart money signals outperformed (3.03x vs 1.12x avg)
    # Smart money detection may be too late or false positives
    # if smart_money_detected:
    #     score += 2
    #     scoring_details.append("Smart Money: +2 (top wallets active!)")
    if smart_money_detected:
        scoring_details.append("Smart Money: detected (no bonus)")

    # Market cap analysis (lower market cap = higher potential)
    market_cap = stats.get('market_cap_usd', 0)
    if 0 < (market_cap or 0) < MCAP_MICRO_MAX:
        score += 3
        scoring_details.append(f"Market Cap: +3 (${market_cap:,.0f} - micro cap gem)")
    elif (market_cap or 0) < MCAP_SMALL_MAX:
        score += 2
        scoring_details.append(f"Market Cap: +2 (${market_cap:,.0f} - small cap)")
    elif (market_cap or 0) < MCAP_MID_MAX:
        score += 1
        scoring_details.append(f"Market Cap: +1 (${market_cap:,.0f} - growing)")
    # Microcap sweet band bonus
    if market_cap and MICROCAP_SWEET_MIN <= market_cap <= MICROCAP_SWEET_MAX:
        score = min(score + 1, 10)
        scoring_details.append(f"Microcap Sweet Spot: +1 (${market_cap:,.0f})")

    # === LIQUIDITY ANALYSIS (ANALYST FINDING: #1 PREDICTOR OF WINNERS!) ===
    # Winner median liquidity: $17,811 | Loser median: $0
    # This is THE most important factor - weight it MORE heavily
    # INCREASED WEIGHTS: +4/+3/+2 (was +3/+2/+1) to match its importance
    liquidity_usd = (
        stats.get('liquidity_usd') or 
        (stats.get('liquidity', {}) or {}).get('usd') or 
        (stats.get('liquidity', {}) or {}).get('liquidity_usd') or 
        0
    )
    
    # Liquidity scoring tiers (INCREASED WEIGHTS - liquidity is #1 predictor!)
    if liquidity_usd >= 50_000:  # 90th percentile - EXCELLENT
        score += 4  # Was +3, now +4 (CRITICAL FACTOR)
        scoring_details.append(f"✅ Liquidity: +4 (${liquidity_usd:,.0f} - EXCELLENT)")
    elif liquidity_usd >= 15_000:  # 75th percentile - GOOD (minimum threshold)
        score += 3  # Was +2, now +3
        scoring_details.append(f"✅ Liquidity: +3 (${liquidity_usd:,.0f} - GOOD)")
    elif liquidity_usd >= 5_000:  # Below threshold but not terrible
        score += 2  # Was +1, now +2
        scoring_details.append(f"⚠️ Liquidity: +2 (${liquidity_usd:,.0f} - FAIR)")
    elif liquidity_usd > 0:  # Has some liquidity but very risky
        score += 1  # Was +0, now +1 (give some credit)
        scoring_details.append(f"⚠️ Liquidity: +1 (${liquidity_usd:,.0f} - LOW)")
    else:  # Zero liquidity - will be filtered out by pre-filter
        score -= 2
        scoring_details.append(f"❌ Liquidity: -2 (${liquidity_usd:,.0f} - ZERO/RUG RISK)")
    # === END LIQUIDITY ANALYSIS ===

    # Volume analysis (24h volume indicates activity)
    volume_24h = stats.get('volume', {}).get('24h', {}).get('volume_usd', 0)
    if (volume_24h or 0) > VOL_VERY_HIGH:
        score += 3
        scoring_details.append(f"Volume: +3 (${volume_24h:,.0f} - very high activity)")
    elif (volume_24h or 0) > VOL_HIGH:
        score += 2
        scoring_details.append(f"Volume: +2 (${volume_24h:,.0f} - high activity)")
    elif (volume_24h or 0) > VOL_MED:
        score += 1
        scoring_details.append(f"Volume: +1 (${volume_24h:,.0f} - moderate activity)")
    
    # === VOLUME-TO-LIQUIDITY RATIO (ANALYST FINDING: Top 3 Predictor) ===
    # High ratio = good trading activity relative to liquidity
    if liquidity_usd > 0 and volume_24h > 0:
        vol_to_liq_ratio = volume_24h / liquidity_usd
        if vol_to_liq_ratio >= 48:  # High precision rule from analyst
            score += 1
            scoring_details.append(f"⚡ Vol/Liq Ratio: +1 ({vol_to_liq_ratio:.1f} - EXCELLENT)")
        elif vol_to_liq_ratio >= 10:  # Good threshold
            scoring_details.append(f"✅ Vol/Liq Ratio: ({vol_to_liq_ratio:.1f} - GOOD)")
        else:
            scoring_details.append(f"Vol/Liq Ratio: ({vol_to_liq_ratio:.1f})")
    # === END VOLUME-TO-LIQUIDITY RATIO ===

    # Unique trader analysis (indicates community engagement)
    unique_buyers_24h = stats.get('volume', {}).get('24h', {}).get('unique_buyers', 0)
    unique_sellers_24h = stats.get('volume', {}).get('24h', {}).get('unique_sellers', 0)
    total_unique_traders = (unique_buyers_24h or 0) + (unique_sellers_24h or 0)
    community_bonus = 0
    if total_unique_traders > 500:
        community_bonus = 2
    elif total_unique_traders > 200:
        community_bonus = 1
    if community_bonus > 0:
        score += community_bonus
        scoring_details.append(f"Community: +{community_bonus} ({total_unique_traders} traders)")

    # Price momentum analysis (positive short-term trend)
    change_1h = stats.get('change', {}).get('1h', 0)
    change_24h = stats.get('change', {}).get('24h', 0)
    
    # === EARLY MOMENTUM BONUS (IDEAL ENTRY ZONE: 5-30% in 24h) ===
    # Reward tokens in the sweet spot - not flat, not pumped, just starting to move
    # This is THE optimal entry point for maximum gains
    if 5 <= (change_24h or 0) <= 30:
        score += 2  # Big bonus for ideal entry zone
        scoring_details.append(f"🎯 Early Entry: +2 ({(change_24h or 0):.1f}% - IDEAL MOMENTUM ZONE!)")
    # === END EARLY MOMENTUM BONUS ===
    
    # Short-term momentum (1h)
    if (change_1h or 0) > max(MOMENTUM_1H_STRONG, MOMENTUM_1H_PUMPER):
        score += 2
        scoring_details.append(f"Momentum: +2 ({(change_1h or 0):.1f}% - strong pump)")
    elif (change_1h or 0) > 0:
        score += 1
        scoring_details.append(f"Momentum: +1 ({(change_1h or 0):.1f}% - positive)")

    # Penalize if 24h is extremely negative (might be dump)
    if (change_24h or 0) < DRAW_24H_MAJOR:
        score -= 1
        scoring_details.append(f"Risk: -1 ({(change_24h or 0):.1f}% - major dump risk)")
    
    # ANTI-FOMO PENALTY: Penalize tokens that already pumped too much (late entry!)
    # This ensures we catch tokens EARLY, not after they've mooned
    # Note: Final rejection happens in gating (bot.py FOMO filter), this just reduces score
    
    # CRITICAL: Dump-after-pump detection (already peaked, now declining)
    if (change_24h or 0) > 30 and (change_1h or 0) < -5:
        score -= 3
        scoring_details.append(f"🚨 DUMP AFTER PUMP: +{(change_24h or 0):.1f}% (24h) but {(change_1h or 0):.1f}% (1h) - Already peaked! -3 pts")
    elif (change_24h or 0) > 50:  # Already pumped >50% in 24h
        score -= 2
        scoring_details.append(f"⚠️ Late Entry Risk: -2 ({(change_24h or 0):.1f}% already pumped in 24h)")

    # Diminishing returns: if smart money but community is low, cap total bonus
    if smart_money_detected and community_bonus == 0:
        score = min(score, 8)

    # Rug/honeypot resilience: if LP unlock < 24h, require stricter thresholds
    liq_obj = stats.get('liquidity') or {}
    lock_status = liq_obj.get('lock_status')
    lock_hours = liq_obj.get('lock_hours') or liq_obj.get('lock_duration_hours')
    try:
        lock_hours = float(lock_hours) if lock_hours is not None else None
    except Exception:
        lock_hours = None
    if lock_status in ("unlocked",) or (lock_hours is not None and lock_hours < 24):
        score -= 1
        scoring_details.append("Risk: -1 (LP lock <24h)")

    # Weighted penalty combining concentration and mint status
    holders = stats.get('holders') or {}
    top10 = holders.get('top_10_concentration_percent') or holders.get('top10_percent') or 0
    mint_revoked = (stats.get('security') or {}).get('is_mint_revoked')
    try:
        top10 = float(top10)
    except Exception:
        top10 = 0
    if top10 > 60 and mint_revoked is not True:
        score -= 2
        scoring_details.append("Risk: -2 (High concentration + mint active)")

    final_score = max(0, min(score, 10))
    return final_score, scoring_details


def _extract_liquidity_usd(stats: Dict[str, Any]) -> float:
    liq_obj = stats.get('liquidity') or {}
    liq_usd = stats.get('liquidity_usd') or liq_obj.get('usd') or 0
    try:
        value = float(liq_usd or 0)
        # CRITICAL FIX: NaN comparisons always return False, allowing bad tokens through!
        # If liquidity is NaN or infinite, treat as 0 to properly fail the liquidity check
        if not (value == value):  # NaN check (NaN != NaN in Python)
            return 0.0
        if value == float('inf') or value == float('-inf'):
            return 0.0
        return value
    except Exception:
        return 0.0


def _extract_top10_concentration(stats: Dict[str, Any]) -> Optional[float]:
    holders = stats.get('holders') or {}
    top10 = holders.get('top_10_concentration_percent') or holders.get('top10_percent')
    try:
        return float(top10) if top10 is not None else None
    except Exception:
        return None


def _extract_holder_risk(stats: Dict[str, Any]) -> Dict[str, Optional[float]]:
    holders = stats.get('holders') or {}

    def to_float(x):
        try:
            return float(x) if x is not None else None
        except Exception:
            return None
    return {
        "bundlers": to_float(holders.get('bundlers_percent') or holders.get('bundlers') or holders.get('bundlers_pct')),
        "insiders": to_float(holders.get('insiders_percent') or holders.get('insiders') or holders.get('insiders_pct')),
    }


def _check_senior_common(stats: Dict[str, Any], token_address: Optional[str], *, allow_unknown: bool,
                         top10_buffer: float, bundlers_buffer: float, insiders_buffer: float) -> bool:
    if not stats:
        return False

    security = stats.get('security') or {}
    if security.get('is_honeypot') is True:
        return False

    sym = (stats.get('symbol') or '').upper()
    if sym and sym in BLOCKLIST_SYMBOLS:
        return False
    if token_address and token_address in STABLE_MINTS:
        return False

    if REQUIRE_MINT_REVOKED:
        mint_revoked = security.get('is_mint_revoked')
        if mint_revoked is True:
            pass
        elif mint_revoked is None:
            if not allow_unknown:
                return False
        else:
            return False

    if REQUIRE_LP_LOCKED:
        liq = stats.get('liquidity') or {}
        lp_locked = (
            liq.get('is_lp_locked')
            or liq.get('lock_status') in ("locked", "burned")
            or liq.get('is_lp_burned')
        )
        if lp_locked is True:
            pass
        elif lp_locked is None:
            if not allow_unknown:
                return False
        else:
            return False

    try:
        mcap_val = float(stats.get('market_cap_usd') or 0)
    except Exception:
        mcap_val = 0.0
    if REQUIRE_HOLDER_STATS_FOR_LARGE_CAP_ALERT and mcap_val >= float(LARGE_CAP_HOLDER_STATS_MCAP_USD or 0):
        holders = stats.get('holders') or {}
        if not holders:
            return False

    top10 = _extract_top10_concentration(stats)
    cap = float(MAX_TOP10_CONCENTRATION or 0) + float(top10_buffer or 0)
    if cap and (top10 is not None) and (top10 > cap):
        return False

    hr = _extract_holder_risk(stats)
    bundlers_cap = float(MAX_BUNDLERS_PERCENT or 0) + float(bundlers_buffer or 0)
    if ENFORCE_BUNDLER_CAP and (hr.get("bundlers") is not None) and bundlers_cap and (hr["bundlers"] > bundlers_cap):
        return False
    insiders_cap = float(MAX_INSIDERS_PERCENT or 0) + float(insiders_buffer or 0)
    if ENFORCE_INSIDER_CAP and (hr.get("insiders") is not None) and insiders_cap and (hr["insiders"] > insiders_cap):
        return False

    return True


def check_senior_strict(stats: Dict[str, Any], token_address: Optional[str] = None) -> bool:
    from config.config import ALLOW_UNKNOWN_SECURITY
    return _check_senior_common(stats, token_address,
                                allow_unknown=ALLOW_UNKNOWN_SECURITY,
                                top10_buffer=0.0,
                                bundlers_buffer=0.0,
                                insiders_buffer=0.0)


def _check_junior_common(stats: Dict[str, Any], final_score: int, *,
                         liquidity_factor: float, mcap_factor: float, vol_to_mcap_factor: float, score_reduction: int) -> bool:
    if not stats:
        return False

    liq_usd = _extract_liquidity_usd(stats)
    min_liq = float(MIN_LIQUIDITY_USD or 0) * float(liquidity_factor or 1.0)
    if liq_usd < min_liq:
        return False

    volume_24h = stats.get('volume', {}).get('24h', {}).get('volume_usd', 0) or 0
    try:
        volume_24h = float(volume_24h)
    except Exception:
        volume_24h = 0.0
    vol_min = float(VOL_24H_MIN_FOR_ALERT or 0)
    if vol_min and volume_24h < vol_min:
        return False

    market_cap = stats.get('market_cap_usd', 0) or 0
    try:
        market_cap = float(market_cap)
    except Exception:
        market_cap = 0.0
    change_1h = stats.get('change', {}).get('1h', 0) or 0
    try:
        change_1h = float(change_1h)
    except Exception:
        change_1h = 0.0
    mcap_cap = float(MAX_MARKET_CAP_FOR_DEFAULT_ALERT or 0) * float(mcap_factor or 1.0)
    mcap_ok = (market_cap or 0) <= mcap_cap
    if not mcap_ok:
        if not (change_1h >= float(LARGE_CAP_MOMENTUM_GATE_1H or 0)):
            return False

    ratio = 0.0
    try:
        ratio = (volume_24h or 0.0) / (market_cap or 1.0)
    except Exception:
        ratio = 0.0
    ratio_req = float(VOL_TO_MCAP_RATIO_MIN or 0) * float(vol_to_mcap_factor or 1.0)
    if (ratio_req or 0) and ratio < ratio_req:
        return False

    min_score = int(HIGH_CONFIDENCE_SCORE or 0) - int(score_reduction or 0)
    if final_score < max(0, min_score):
        return False

    return True


def check_junior_strict(stats: Dict[str, Any], final_score: int) -> bool:
    return _check_junior_common(stats, final_score,
                                liquidity_factor=1.0,
                                mcap_factor=1.0,
                                vol_to_mcap_factor=1.0,
                                score_reduction=0)


def check_senior_nuanced(stats: Dict[str, Any], token_address: Optional[str] = None) -> bool:
    return _check_senior_common(stats, token_address,
                                allow_unknown=ALLOW_UNKNOWN_SECURITY,
                                top10_buffer=float(NUANCED_TOP10_CONCENTRATION_BUFFER or 0),
                                bundlers_buffer=float(NUANCED_BUNDLERS_BUFFER or 0),
                                insiders_buffer=float(NUANCED_INSIDERS_BUFFER or 0))


def check_junior_nuanced(stats: Dict[str, Any], final_score: int) -> bool:
    return _check_junior_common(stats, final_score,
                                liquidity_factor=float(NUANCED_LIQUIDITY_FACTOR or 1.0),
                                mcap_factor=float(NUANCED_MCAP_FACTOR or 1.0),
                                vol_to_mcap_factor=float(NUANCED_VOL_TO_MCAP_FACTOR or 1.0),
                                score_reduction=int(NUANCED_SCORE_REDUCTION or 0))
