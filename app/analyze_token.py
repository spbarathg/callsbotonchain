# analyze_token.py
import time
from typing import Dict, Tuple, List, Any, Optional
from config import (
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
    TOP10_CONCERN,
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
from config import HTTP_TIMEOUT_STATS
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
                # Prefer marketCap; fall back to fdv; coerce to float
                mc_val = best.get("marketCap")
                if mc_val is None:
                    mc_val = best.get("fdv")
                try:
                    market_cap = float(mc_val or 0)
                except Exception:
                    market_cap = 0.0
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


_deny_cache = {"stats_denied": False}


_stats_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_STATS_TTL_SEC = 120  # increase TTL to reduce API churn

def _cache_get(token_address: str) -> Optional[Dict[str, Any]]:
    import time as _t
    item = _stats_cache.get(token_address)
    if not item:
        return None
    ts, data = item
    if (_t.time() - ts) <= _STATS_TTL_SEC:
        return data
    return None

def _cache_set(token_address: str, data: Dict[str, Any]) -> None:
    import time as _t
    _stats_cache[token_address] = (_t.time(), data)

def get_token_stats(token_address: str) -> Dict[str, Any]:
    if not token_address:
        return {}
    cached = _cache_get(token_address)
    if cached:
        return cached
    # Enforce budget before hitting APIs
    try:
        b = get_budget()
        if not b.can_spend("stats"):
            return {}
    except Exception:
        pass
        
    base_urls = [
        "https://feed-api.cielo.finance/api/v1",
        "https://api.cielo.finance/api/v1",
    ]
    header_variants = [
        {"X-API-Key": CIELO_API_KEY},
        {"Authorization": f"Bearer {CIELO_API_KEY}"},
    ]
    params = {"token_address": token_address, "chain": "solana"}
    
    # Add timeout and retry logic
    max_retries = 3
    
    # Skip Cielo if user disabled or we detected denial previously
    if CIELO_DISABLE_STATS or _deny_cache.get("stats_denied"):
        return _get_token_stats_dexscreener(token_address)

    combos = [(b, h) for b in base_urls for h in header_variants]
    last_status = None
    for idx, (base, hdrs) in enumerate(combos):
        url = f"{base}/token/stats"
        result = request_json("GET", url, params=params, headers=hdrs, timeout=HTTP_TIMEOUT_STATS)
        last_status = result.get("status_code")
        if last_status == 200:
            try:
                get_budget().spend("stats")
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
                                    data.setdefault('volume', {}).setdefault('24h', {})['volume_usd'] = vol24.get('volume_usd')
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
                        norm = _normalize_stats_schema(api_response["data"]) if isinstance(api_response.get("data"), dict) else api_response.get("data")
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
            try:
                log_process({"type": "token_stats_rate_limited", "variant": int(idx + 1)})
            except Exception:
                pass
            time.sleep(1)
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
        _deny_cache["stats_denied"] = True
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
    - Guarantees: market_cap_usd (float), price_usd (float), liquidity_usd (float|None),
      volume.24h.volume_usd (float), change.{1h,24h} (float), security/liquidity/holders dicts present.
    """
    if not isinstance(d, dict):
        return {}
    out: Dict[str, Any] = dict(d)
    # Market cap
    try:
        out["market_cap_usd"] = float(out.get("market_cap_usd") or 0)
    except Exception:
        out["market_cap_usd"] = 0.0
    # Price
    try:
        out["price_usd"] = float(out.get("price_usd") or 0)
    except Exception:
        out["price_usd"] = 0.0
    # Liquidity
    liq_obj = out.get("liquidity") or {}
    try:
        liq_usd = out.get("liquidity_usd")
        if liq_usd is None:
            liq_usd = liq_obj.get("usd")
        out["liquidity_usd"] = float(liq_usd) if liq_usd is not None else None
    except Exception:
        out["liquidity_usd"] = None
    # Volume
    v = (out.get("volume") or {})
    v24 = (v.get("24h") or {})
    try:
        v24_usd = float(v24.get("volume_usd") or 0)
    except Exception:
        v24_usd = 0.0
    out.setdefault("volume", {}).setdefault("24h", {})["volume_usd"] = v24_usd
    # Change
    ch = out.get("change") or {}
    for k in ("1h", "24h"):
        try:
            ch_val = float(ch.get(k) or 0)
        except Exception:
            ch_val = 0.0
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
    
    # Smart money bonus (highest priority)
    if smart_money_detected:
        score += 4  # Higher bonus for preliminary scoring
    
    # USD value indicates serious activity (more sensitive thresholds)
    usd_value = tx_data.get('usd_value', 0) or 0
    if usd_value > PRELIM_USD_HIGH:
        score += 3
    elif usd_value > PRELIM_USD_MID:
        score += 2
    elif usd_value > PRELIM_USD_LOW:
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

    # Smart money bonus is part of raw scoring signal
    if smart_money_detected:
        score += 3
        scoring_details.append("Smart Money: +3 (top wallets active!)")

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

    # Unique trader analysis (indicates community engagement)
    unique_buyers_24h = stats.get('volume', {}).get('24h', {}).get('unique_buyers', 0)
    unique_sellers_24h = stats.get('volume', {}).get('24h', {}).get('unique_sellers', 0)
    total_unique_traders = (unique_buyers_24h or 0) + (unique_sellers_24h or 0)
    if total_unique_traders > 500:
        score += 2
        scoring_details.append(f"Community: +2 ({total_unique_traders} traders - very active)")
    elif total_unique_traders > 200:
        score += 1
        scoring_details.append(f"Community: +1 ({total_unique_traders} traders - active)")

    # Price momentum analysis (positive short-term trend)
    change_1h = stats.get('change', {}).get('1h', 0)
    change_24h = stats.get('change', {}).get('24h', 0)
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

    final_score = max(0, min(score, 10))
    return final_score, scoring_details


def _extract_liquidity_usd(stats: Dict[str, Any]) -> float:
    liq_obj = stats.get('liquidity') or {}
    liq_usd = stats.get('liquidity_usd') or liq_obj.get('usd') or 0
    try:
        return float(liq_usd or 0)
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
    return _check_senior_common(stats, token_address,
                                allow_unknown=False,
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
