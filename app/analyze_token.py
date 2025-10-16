# analyze_token.py
import time
import os
import json
import threading
from typing import Dict, Tuple, List, Any, Optional
from app.file_lock import file_lock
from app.config_unified import (
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
from app.config_unified import HTTP_TIMEOUT_STATS
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


# OPTIMIZED: In-memory only deny cache (removed file I/O bottleneck)
_deny_cache = {"stats_denied_until": 0.0}  # Unix timestamp
_deny_lock = threading.Lock()
_DENY_TTL_SECONDS = int(os.getenv("CALLSBOT_DENY_TTL_SEC", "900"))  # 15 min default


def deny_is_denied() -> bool:
    """OPTIMIZED: Check if stats API is denied (in-memory only, no file I/O)"""
    with _deny_lock:
        denied_until = _deny_cache.get("stats_denied_until", 0.0)
        now = time.time()
        
        # Auto-clear expired denials
        if denied_until > 0 and now >= denied_until:
            _deny_cache["stats_denied_until"] = 0.0
            return False
        
        return denied_until > now


def deny_mark_denied(duration_sec: Optional[int] = None) -> None:
    """OPTIMIZED: Mark stats API as denied (in-memory only)"""
    duration = duration_sec if duration_sec is not None else _DENY_TTL_SECONDS
    with _deny_lock:
        _deny_cache["stats_denied_until"] = time.time() + duration


def deny_clear() -> None:
    """Manually clear the deny state"""
    with _deny_lock:
        _deny_cache["stats_denied_until"] = 0.0


def deny_get_remaining_sec() -> int:
    """Get remaining deny duration in seconds"""
    with _deny_lock:
        denied_until = _deny_cache.get("stats_denied_until", 0.0)
        now = time.time()
        return max(0, int(denied_until - now))


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
    """OPTIMIZED: Streamlined stats fetching with simplified retry logic"""
    if not token_address:
        return {}
    
    # Check cache
    cached = _cache_get(token_address) if not force_refresh else None
    if cached:
        try:
            from app.metrics import cache_hit
            cache_hit()
        except Exception:
            pass
        return cached
    
    try:
        from app.metrics import cache_miss
        cache_miss()
    except Exception:
        pass
    
    # Budget check
    try:
        b = get_budget()
        if b and not b.can_spend("stats"):
            ds = _get_token_stats_dexscreener(token_address)
            return _normalize_stats_schema(ds) if ds else {}
    except Exception:
        pass

    # Skip Cielo if disabled or denied
    if CIELO_DISABLE_STATS or deny_is_denied() or not CIELO_API_KEY:
        return _normalize_stats_schema(_get_token_stats_dexscreener(token_address) or {})

    # OPTIMIZED: Single URL and header (removed combinatorial explosion)
    url = "https://feed-api.cielo.finance/api/v1/token/stats"
    params = {"token_address": token_address, "chain": "solana"}
    headers = {"X-API-Key": CIELO_API_KEY}
    
    # Try Cielo API with simple retry
    max_retries = 2
    for attempt in range(max_retries):
        result = request_json("GET", url, params=params, headers=headers, timeout=HTTP_TIMEOUT_STATS)
        status = result.get("status_code")
        
        if status == 200:
            try:
                get_budget().spend("stats")
            except Exception:
                pass
            
            api_response = result.get("json", {})
            if api_response.get("status") == "ok" and "data" in api_response:
                data = _normalize_stats_schema(api_response["data"])
                data["_source"] = "cielo"
                
                # OPTIMIZED: Simplified augmentation logic
                if not data.get("liquidity_usd") or not data.get("market_cap_usd") or not data.get("symbol"):
                    ds = _get_token_stats_dexscreener(token_address)
                    if ds:
                        data["liquidity_usd"] = data.get("liquidity_usd") or ds.get("liquidity_usd")
                        data["market_cap_usd"] = data.get("market_cap_usd") or ds.get("market_cap_usd")
                        data["symbol"] = data.get("symbol") or ds.get("symbol")
                        data["name"] = data.get("name") or ds.get("name")
                        data["_source"] = "cielo+ds"
                
                _cache_set(token_address, data)
                return data
            break
            
        elif status == 429:
            if attempt < max_retries - 1:
                time.sleep(min(2 ** attempt, 10))
                continue
            deny_mark_denied()
            break
            
        elif status in (401, 403):
            deny_mark_denied()
            break
            
        elif status == 404:
            return {}
            
        elif attempt < max_retries - 1:
            time.sleep(1)
            continue
        else:
            break
    
    # Fallback to DexScreener
    return _normalize_stats_schema(_get_token_stats_dexscreener(token_address) or {})


def _normalize_stats_schema(d: Dict[str, Any]) -> Dict[str, Any]:
    """OPTIMIZED: Streamlined normalization with fast validation"""
    if not isinstance(d, dict):
        return {}
    
    out: Dict[str, Any] = dict(d)
    
    # Helper for safe float conversion
    def safe_float(val, default=0.0):
        if val is None:
            return default
        try:
            f = float(val)
            if f != f or f == float('inf') or f == float('-inf'):  # NaN or inf check
                return default
            return f
        except (ValueError, TypeError):
            return default
    
    # Market cap
    out["market_cap_usd"] = safe_float(out.get("market_cap_usd"))
    
    # Price
    out["price_usd"] = safe_float(out.get("price_usd"))
    
    # Liquidity
    liq_usd = out.get("liquidity_usd")
    if liq_usd is None:
        liq_usd = (out.get("liquidity") or {}).get("usd")
    out["liquidity_usd"] = safe_float(liq_usd)
    
    # Volume
    v24 = (out.get("volume", {}) or {}).get("24h", {}) or {}
    out.setdefault("volume", {}).setdefault("24h", {})["volume_usd"] = safe_float(v24.get("volume_usd"))
    
    # Change (can be negative)
    ch = out.get("change", {}) or {}
    for k in ("1h", "24h"):
        out.setdefault("change", {})[k] = safe_float(ch.get(k))
    
    # Ensure containers exist
    for k in ("security", "liquidity", "holders"):
        if not isinstance(out.get(k), dict):
            out[k] = {}
    
    return out


def calculate_preliminary_score(tx_data: Dict[str, Any], smart_money_detected: bool = False) -> int:
    """
    CREDIT-EFFICIENT: Calculate preliminary score from feed data without API calls
    Uses only data available in the transaction feed
    
    OPTIMIZED FOR MICRO-CAPS: More lenient thresholds to catch early transactions
    """
    score = 1  # FIXED: Start at 1 instead of 0 to avoid universal rejection

    # Smart money bonus REMOVED - analysis showed it's anti-predictive
    # if smart_money_detected:
    #     score += 3  # Baseline bonus

    # USD value indicates serious activity; downweight synthetic fallback items
    # OPTIMIZED: Lowered thresholds for micro-cap focus
    usd_value = tx_data.get('usd_value', 0) or 0
    is_synthetic = bool(tx_data.get('is_synthetic')) or str(tx_data.get('tx_type') or '').endswith('_fallback')
    
    # MICRO-CAP MODE: Lower thresholds (was 50k/10k/1k, now 10k/2k/200)
    high = 10000.0 * (1.5 if is_synthetic else 1.0)
    mid = 2000.0 * (1.5 if is_synthetic else 1.0)
    low = 200.0 * (1.5 if is_synthetic else 1.0)
    
    if usd_value > high:
        score += 3
    elif usd_value > mid:
        score += 2
    elif usd_value > low:
        score += 1
    # Even tiny transactions get base score of 1 (from initialization)

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

    # Market cap analysis - DATA-DRIVEN SCORING (7-day performance analysis)
    # < $50k: 63% avg gain, 53.7% win rate (decent)
    # $50k-$100k: 207% avg gain, 68.4% win rate (excellent)
    # $100k-$200k: 267% avg gain, 70.8% win rate, 5 moonshots (BEST!)
    # $200k-$500k: 61% avg gain, 67.2% win rate (good)
    market_cap = stats.get('market_cap_usd', 0)
    if 0 < (market_cap or 0) < 50_000:  # < $50k
        score += 2
        scoring_details.append(f"Market Cap: +2 (${market_cap:,.0f} - ULTRA micro cap, high volatility)")
    elif (market_cap or 0) < MCAP_MICRO_MAX:  # $50k-$100k
        score += 2
        scoring_details.append(f"Market Cap: +2 (${market_cap:,.0f} - micro cap, excellent 2x potential)")
    elif (market_cap or 0) < MCAP_SMALL_MAX:  # $100k-$200k
        score += 3
        scoring_details.append(f"Market Cap: +3 (${market_cap:,.0f} - SWEET SPOT! Best moonshot zone)")
    elif (market_cap or 0) < MCAP_MID_MAX:  # $200k-$1M
        score += 1
        scoring_details.append(f"Market Cap: +1 (${market_cap:,.0f} - small cap, 2-3x potential)")
    
    # === 2X SWEET SPOT BONUS (OPTIMIZED: $20k-$200k) ===
    # Why? Tokens in this range need minimal capital to 2x
    # $50k → $100k = needs $50k | $200k → $400k = needs $200k
    if market_cap and MICROCAP_SWEET_MIN <= market_cap <= MICROCAP_SWEET_MAX:
        score = min(score + 1, 10)
        scoring_details.append(f"🎯 2X Sweet Spot: +1 (${market_cap:,.0f} - optimized for quick 2x!)")
    
    # === ULTRA-MICRO BONUS: $20k-$50k (HIGHEST 2X POTENTIAL) ===
    # Extra bonus for the tiniest tokens with explosive potential
    if market_cap and 20_000 <= market_cap <= 50_000:
        score = min(score + 1, 10)
        scoring_details.append(f"💎 Ultra-Micro Gem: +1 (${market_cap:,.0f} - 10x+ potential!)")

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
    
    # Liquidity scoring tiers (OPTIMIZED FOR 50% HIT RATE TARGET!)
    # Winner median: $17,811 | Loser median: $0
    # Weight liquidity HEAVILY as it's the #1 predictor
    if liquidity_usd >= 50_000:  # Premium tier - EXCELLENT
        score += 5  # RAISED from +4 to +5
        scoring_details.append(f"✅ Liquidity: +5 (${liquidity_usd:,.0f} - EXCELLENT)")
    elif liquidity_usd >= 20_000:  # NEW TIER - Very Good
        score += 4  # NEW: Above winner median
        scoring_details.append(f"✅ Liquidity: +4 (${liquidity_usd:,.0f} - VERY GOOD)")
    elif liquidity_usd >= 18_000:  # Winner median tier - Good
        score += 3  # At winner median
        scoring_details.append(f"✅ Liquidity: +3 (${liquidity_usd:,.0f} - GOOD)")
    elif liquidity_usd >= 15_000:  # Minimum threshold - Fair
        score += 2  # LOWERED from +3 to +2
        scoring_details.append(f"⚠️ Liquidity: +2 (${liquidity_usd:,.0f} - FAIR)")
    elif liquidity_usd >= 5_000:  # Below threshold - Low
        score += 1  # LOWERED from +2 to +1
        scoring_details.append(f"⚠️ Liquidity: +1 (${liquidity_usd:,.0f} - LOW)")
    elif liquidity_usd > 0:  # Very low liquidity
        score += 0  # No bonus
        scoring_details.append(f"❌ Liquidity: +0 (${liquidity_usd:,.0f} - VERY LOW)")
    else:  # Zero liquidity - will be filtered out
        score -= 2
        scoring_details.append(f"❌ Liquidity: -2 (${liquidity_usd:,.0f} - ZERO/RUG RISK)")
    
    # === LIQUIDITY STABILITY BONUS (NEW!) ===
    # Extra bonus for being at or above winner median
    if liquidity_usd >= 18_000:
        score += 1
        scoring_details.append("✨ Winner-Tier Liquidity: +1 (≥$18k median)")
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
    
    # === VOLUME-TO-LIQUIDITY & MCAP RATIOS (Top 3 Predictor) ===
    # High ratio = strong trading interest = better chance of 2x+
    vol_to_liq_ratio = 0.0
    if liquidity_usd > 0 and volume_24h > 0:
        vol_to_liq_ratio = volume_24h / liquidity_usd
        if vol_to_liq_ratio >= 48:  # High precision rule from analyst
            score += 1
            scoring_details.append(f"⚡ Vol/Liq Ratio: +1 ({vol_to_liq_ratio:.1f} - EXCELLENT)")
        elif vol_to_liq_ratio >= 10:  # Good threshold
            scoring_details.append(f"✅ Vol/Liq Ratio: ({vol_to_liq_ratio:.1f} - GOOD)")
    
    # === LOW ACTIVITY PENALTY (NEW!) ===
    # Penalize tokens with very low trading activity
    if market_cap > 0 and volume_24h > 0:
        vol_to_mcap = volume_24h / market_cap
        if vol_to_mcap < 0.05:  # Very low activity
            score -= 1
            scoring_details.append(f"⚠️  Low Activity: -1 (vol/mcap: {vol_to_mcap:.3f})")
        elif vol_to_liq_ratio > 0:  # Only log if we have valid ratio
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
    
    # === EARLY MOMENTUM BONUS (EXPANDED: -20% to +300% in 24h) ===
    # FIXED: Was 5-100%, now -20% to +300% to include dips and ongoing pumps
    # Reward tokens showing momentum OR in dip-buy zone OR in mid-pump
    # DATA: Winners ranged from -21% to +646%, mega winners often in dips
    if -20 <= (change_24h or 0) <= 300:  # EXPANDED from 5-100%
        score += 2  # Big bonus for entry opportunities
        if (change_24h or 0) < 0:
            scoring_details.append(f"🎯 Dip Buy: +2 ({(change_24h or 0):.1f}% - BUY THE DIP!)")
        elif (change_24h or 0) <= 100:
            scoring_details.append(f"🎯 Early Entry: +2 ({(change_24h or 0):.1f}% - MOMENTUM ZONE!)")
        else:
            scoring_details.append(f"🎯 Mid-Pump Entry: +2 ({(change_24h or 0):.1f}% - ONGOING PUMP!)")
    # === END EARLY MOMENTUM BONUS ===
    
    # Short-term momentum (1h) - REVISED TO REWARD DIP BUYING
    # DATA: 45% of winners had negative 1h momentum, mega winners avg -7.1%
    if (change_1h or 0) > max(MOMENTUM_1H_STRONG, MOMENTUM_1H_PUMPER):
        score += 2
        scoring_details.append(f"Momentum: +2 ({(change_1h or 0):.1f}% - strong pump)")
    elif (change_1h or 0) > 0:
        score += 1
        scoring_details.append(f"Momentum: +1 ({(change_1h or 0):.1f}% - positive)")
    # NEW: Reward dip buying (negative 1h but positive 24h trend)
    elif (change_1h or 0) < 0 and (change_24h or 0) > 0:
        score += 1  # Same bonus as positive momentum
        scoring_details.append(f"🎯 Dip Buy: +1 ({(change_1h or 0):.1f}% 1h, {(change_24h or 0):.1f}% 24h - buying the dip!)")

    # Penalize if 24h is extremely negative (might be dump)
    # FIXED: Threshold now -60% (was -30%) to allow more dip buying
    if (change_24h or 0) < DRAW_24H_MAJOR:  # DRAW_24H_MAJOR = -60
        score -= 1
        scoring_details.append(f"Risk: -1 ({(change_24h or 0):.1f}% - major dump risk)")

    # FIXED: Removed ANTI-FOMO scoring penalty (redundant with hard gate)
    # REASON: Hard gate now at 1000%+ (effectively disabled)
    # Winners can pump >200% and continue - don't penalize ongoing pumps
    # DATA: Today's best winner +585% would have been penalized at entry
    # if (change_24h or 0) > 200:
    #     score -= 1  # REMOVED

    # FIXED: Removed smart money score cap
    # REASON: Smart money bonus was already removed (non-smart outperforms)
    # No reason to cap smart money tokens when they don't get a bonus
    # if smart_money_detected and community_bonus == 0:
    #     score = min(score, 8)  # REMOVED

    # FIXED: Removed LP lock time penalty
    # REASON: REQUIRE_LP_LOCKED = False (not required), so don't penalize
    # Many early micro-caps have 1-7 day locks which are acceptable
    # Only actual honeypots/rugs are blocked by senior strict checks
    # liq_obj = stats.get('liquidity') or {}
    # lock_status = liq_obj.get('lock_status')
    # lock_hours = liq_obj.get('lock_hours') or liq_obj.get('lock_duration_hours')
    # if lock_status in ("unlocked",) or (lock_hours < 24):
    #     score -= 1  # REMOVED

    # FIXED: Removed concentration + mint double penalty
    # REASON: REQUIRE_MINT_REVOKED = False (not required), so don't penalize
    # 60% concentration is normal for new micro-caps
    # Senior strict checks handle extreme cases (MAX_TOP10_CONCENTRATION)
    # holders = stats.get('holders') or {}
    # top10 = holders.get('top_10_concentration_percent') or holders.get('top10_percent') or 0
    # mint_revoked = (stats.get('security') or {}).get('is_mint_revoked')
    # if top10 > 60 and mint_revoked is not True:
    #     score -= 2  # REMOVED

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
    
    # NEW: Minimum holder count check for distribution
    from app.config_unified import MIN_HOLDER_COUNT
    if MIN_HOLDER_COUNT:
        holders = stats.get('holders') or {}
        holder_count = holders.get('holder_count', 0)
        if holder_count > 0 and holder_count < MIN_HOLDER_COUNT:
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
    from app.config_unified import ALLOW_UNKNOWN_SECURITY
    return _check_senior_common(stats, token_address,
                                allow_unknown=ALLOW_UNKNOWN_SECURITY,
                                top10_buffer=0.0,
                                bundlers_buffer=0.0,
                                insiders_buffer=0.0)


def _check_junior_common(stats: Dict[str, Any], final_score: int, *,
                         liquidity_factor: float, mcap_factor: float, vol_to_mcap_factor: float, score_reduction: int) -> bool:
    if not stats:
        return False

    # Liquidity check with factor support for nuanced mode
    # NOTE: This is also checked in signal_processor as an EARLY GATE for performance
    # but we need it here too to support nuanced liquidity_factor
    liq_usd = _extract_liquidity_usd(stats)
    min_liq = float(MIN_LIQUIDITY_USD or 0) * float(liquidity_factor or 1.0)
    if liq_usd < min_liq:
        return False

    # OPTIMIZED: Single volume check (removed redundant VOL_24H_MIN_FOR_ALERT check)
    # VOL_24H_MIN_FOR_ALERT is always 0.0 (disabled), so only check MIN_VOLUME_24H_USD
    volume_24h = stats.get('volume', {}).get('24h', {}).get('volume_usd', 0) or 0
    try:
        volume_24h = float(volume_24h)
    except Exception:
        volume_24h = 0.0
    
    # Absolute minimum volume check for quality
    from app.config_unified import MIN_VOLUME_24H_USD
    if MIN_VOLUME_24H_USD and volume_24h < MIN_VOLUME_24H_USD:
        return False

    market_cap = stats.get('market_cap_usd', 0) or 0
    try:
        market_cap = float(market_cap)
    except Exception:
        market_cap = 0.0
    
    # STRICT MARKET CAP FILTER: NO tokens > $1M, regardless of momentum or mode
    # CRITICAL FIX: Removed momentum bypass and mcap_factor to enforce strict $1M limit
    # User requirement: "no token with market cap > 1million gets past through"
    mcap_cap = float(MAX_MARKET_CAP_FOR_DEFAULT_ALERT or 0)  # Always $1M, no multiplier
    if market_cap > mcap_cap:
        return False  # HARD REJECT: No bypass for large caps

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
