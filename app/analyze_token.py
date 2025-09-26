# analyze_token.py
import requests
import time
from typing import Dict, Tuple, List, Any, Optional
from app.logger_utils import log_alert  # if needed later; safe to leave
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
)

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
    timeout = 10
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json() or {}
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
            elif resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            else:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
        except requests.exceptions.RequestException:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
    return {}


_deny_cache = {"stats_denied": False}


def get_token_stats(token_address: str) -> Dict[str, Any]:
    if not token_address:
        return {}
        
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
    timeout = 10
    
    # Skip Cielo if user disabled or we detected denial previously
    if CIELO_DISABLE_STATS or _deny_cache.get("stats_denied"):
        return _get_token_stats_dexscreener(token_address)

    combos = [(b, h) for b in base_urls for h in header_variants]
    last_status = None
    for idx, (base, hdrs) in enumerate(combos):
        try:
            url = f"{base}/token/stats"
            resp = requests.get(url, params=params, headers=hdrs, timeout=timeout)
            last_status = resp.status_code
            if resp.status_code == 200:
                api_response = resp.json()
                if api_response.get("status") == "ok" and "data" in api_response:
                    api_response["data"]["_source"] = "cielo"
                    return api_response["data"]
                if isinstance(api_response, dict):
                    api_response["_source"] = "cielo"
                return api_response
            elif resp.status_code == 429:
                print(f"Rate limited on token stats, waiting... (variant {idx + 1})")
                time.sleep(1)
                continue
            elif resp.status_code == 404:
                print(f"Token {token_address} not found")
                return {}
            elif resp.status_code in (401, 403):
                # Try next variant
                continue
            else:
                print(f"Error fetching token stats: {resp.status_code}, {resp.text}")
                continue
        except requests.exceptions.RequestException as e:
            print(f"Request exception on token stats (variant {idx + 1}): {e}")
            continue

    if last_status in (401, 403):
        _deny_cache["stats_denied"] = True
        print("Cielo token stats denied across variants – using DexScreener fallback")
    else:
        print(f"Cielo token stats unavailable (last status={last_status}); using DexScreener fallback")
    return _get_token_stats_dexscreener(token_address)

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
    if not stats:
        return 0
        
    score = 0
    scoring_details = []

    # Hard filters: stables/majors (by mint or symbol); allow if strong momentum or smart money
    sym = (stats.get('symbol') or '').upper()
    if token_address and token_address in STABLE_MINTS:
        # Only allow if smart money and strong 1h momentum
        ch1 = stats.get('change', {}).get('1h', 0)
        if not (smart_money_detected and ch1 and ch1 >= LARGE_CAP_MOMENTUM_GATE_1H):
            scoring_details.append("Filtered: stable/major mint")
            return 0, scoring_details
    if sym in BLOCKLIST_SYMBOLS:
        ch1 = stats.get('change', {}).get('1h', 0)
        if not (smart_money_detected and ch1 and ch1 >= LARGE_CAP_MOMENTUM_GATE_1H):
            scoring_details.append("Filtered: blocklisted symbol")
            return 0, scoring_details
    
    # SMART MONEY BONUS (highest priority)
    if smart_money_detected:
        score += 3
        scoring_details.append("Smart Money: +3 (top wallets active!)")
    
    # Market cap analysis (lower market cap = higher potential)
    market_cap = stats.get('market_cap_usd', 0)
    if 0 < market_cap < MCAP_MICRO_MAX:  # Micro cap
        score += 3
        scoring_details.append(f"Market Cap: +3 (${market_cap:,.0f} - micro cap gem)")
    elif market_cap < MCAP_SMALL_MAX:  # Small cap
        score += 2
        scoring_details.append(f"Market Cap: +2 (${market_cap:,.0f} - small cap)")
    elif market_cap < MCAP_MID_MAX:  # Mid cap
        score += 1
        scoring_details.append(f"Market Cap: +1 (${market_cap:,.0f} - growing)")
    # Microcap sweet band bonus
    if market_cap and MICROCAP_SWEET_MIN <= market_cap <= MICROCAP_SWEET_MAX:
        score = min(score + 1, 10)
        scoring_details.append(f"Microcap Sweet Spot: +1 (${market_cap:,.0f})")
    # Gate very large caps unless strong momentum or smart money
    if market_cap and market_cap > MAX_MARKET_CAP_FOR_DEFAULT_ALERT:
        ch1 = stats.get('change', {}).get('1h', 0)
        if not (smart_money_detected and ch1 and ch1 >= LARGE_CAP_MOMENTUM_GATE_1H):
            scoring_details.append(f"Filtered: large cap ${market_cap:,.0f} without strong momentum")
            return 0, scoring_details
    
    # Volume analysis (24h volume indicates activity)
    volume_24h = stats.get('volume', {}).get('24h', {}).get('volume_usd', 0)
    if volume_24h > VOL_VERY_HIGH:  # Very high activity
        score += 3
        scoring_details.append(f"Volume: +3 (${volume_24h:,.0f} - very high activity)")
    elif volume_24h > VOL_HIGH:  # High activity
        score += 2
        scoring_details.append(f"Volume: +2 (${volume_24h:,.0f} - high activity)")
    elif volume_24h > VOL_MED:  # Moderate activity
        score += 1
        scoring_details.append(f"Volume: +1 (${volume_24h:,.0f} - moderate activity)")
    # Volume-to-MCap ratio gate (optional)
    if VOL_TO_MCAP_RATIO_MIN:
        try:
            ratio = (volume_24h or 0) / (market_cap or 1)
        except Exception:
            ratio = 0
        if ratio < VOL_TO_MCAP_RATIO_MIN:
            scoring_details.append(f"Filtered: vol/mcap {ratio:.2f} < {VOL_TO_MCAP_RATIO_MIN}")
            return 0, scoring_details
    
    # Unique trader analysis (indicates community engagement)
    unique_buyers_24h = stats.get('volume', {}).get('24h', {}).get('unique_buyers', 0)
    unique_sellers_24h = stats.get('volume', {}).get('24h', {}).get('unique_sellers', 0)
    total_unique_traders = unique_buyers_24h + unique_sellers_24h
    
    if total_unique_traders > 500:  # Very active community
        score += 2
        scoring_details.append(f"Community: +2 ({total_unique_traders} traders - very active)")
    elif total_unique_traders > 200:  # Active community
        score += 1
        scoring_details.append(f"Community: +1 ({total_unique_traders} traders - active)")
    
    # Price momentum analysis (positive short-term trend)
    change_1h = stats.get('change', {}).get('1h', 0)
    change_24h = stats.get('change', {}).get('24h', 0)
    
    # Reward recent positive momentum
    if change_1h > max(MOMENTUM_1H_STRONG, MOMENTUM_1H_PUMPER):  # Strong pump threshold
        score += 2
        scoring_details.append(f"Momentum: +2 ({change_1h:.1f}% - strong pump)")
    elif change_1h > 0:  # Positive 1h
        score += 1
        scoring_details.append(f"Momentum: +1 ({change_1h:.1f}% - positive)")
    
    # But penalize if 24h is extremely negative (might be dump)
    if change_24h < DRAW_24H_MAJOR:
        score -= 1
        scoring_details.append(f"Risk: -1 ({change_24h:.1f}% - major dump risk)")

    # --- Safety checks / Disqualifiers ---
    security = stats.get('security', {}) or {}
    liquidity = stats.get('liquidity', {}) or {}
    holders = stats.get('holders', {}) or {}

    # Disqualifier: honeypot
    if security.get('is_honeypot') is True:
        scoring_details.append("Disqualified: honeypot")
        return 0, scoring_details

    # Strict gates: mint revoked required unless unknown and allowed
    mint_revoked = security.get('is_mint_revoked')
    if REQUIRE_MINT_REVOKED:
        if mint_revoked is False:
            scoring_details.append("Filtered: mint not revoked")
            return 0, scoring_details
        if mint_revoked is None and not ALLOW_UNKNOWN_SECURITY:
            scoring_details.append("Filtered: mint revoke unknown")
            return 0, scoring_details
    else:
        if mint_revoked is False:
            score -= 3
            scoring_details.append("Security: -3 (mint not revoked)")

    # LP locked/burned gate
    lp_locked = (
        liquidity.get('is_lp_locked')
        or liquidity.get('lock_status') in ("locked", "burned")
        or liquidity.get('is_lp_burned')
    )
    if REQUIRE_LP_LOCKED:
        if lp_locked is False:
            scoring_details.append("Filtered: LP not locked/burned")
            return 0, scoring_details
        if lp_locked is None and not ALLOW_UNKNOWN_SECURITY:
            scoring_details.append("Filtered: LP lock unknown")
            return 0, scoring_details
    else:
        if lp_locked is False:
            score -= 2
            scoring_details.append("Liquidity: -2 (LP not locked/burned)")

    # Top 10 holders concentration high → -1
    top10 = holders.get('top_10_concentration_percent') or holders.get('top10_percent') or 0
    try:
        top10 = float(top10)
    except Exception:
        top10 = 0
    if MAX_TOP10_CONCENTRATION and top10 and top10 > MAX_TOP10_CONCENTRATION:
        scoring_details.append(f"Filtered: Top10 {top10:.1f}% > {MAX_TOP10_CONCENTRATION}%")
        return 0, scoring_details
    elif top10 > TOP10_CONCERN:
        score -= 1
        scoring_details.append(f"Holders: -1 (Top10 {top10:.1f}% > {TOP10_CONCERN}%)")

    # Liquidity and minimum volume gates (DexScreener provides liquidity_usd sometimes)
    liq_usd = stats.get('liquidity_usd') or liquidity.get('usd') or 0
    if MIN_LIQUIDITY_USD and (liq_usd or 0) < MIN_LIQUIDITY_USD:
        scoring_details.append(f"Filtered: liquidity ${liq_usd:,.0f} < ${MIN_LIQUIDITY_USD}")
        return 0, scoring_details
    if VOL_24H_MIN_FOR_ALERT and (volume_24h or 0) < VOL_24H_MIN_FOR_ALERT:
        scoring_details.append(f"Filtered: vol24 ${volume_24h:,.0f} < ${VOL_24H_MIN_FOR_ALERT}")
        return 0, scoring_details
    
    final_score = max(0, min(score, 10))
    return final_score, scoring_details
