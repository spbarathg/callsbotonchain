# fetch_feed.py
from typing import Dict, Any
import os
from typing import Dict, Any
from app.config_unified import HTTP_TIMEOUT_FEED
from app.http_client import request_json
from app.logger_utils import log_process


def fetch_solana_feed(cursor=None, smart_money_only: bool = False) -> Dict[str, Any]:
    # ATM-only mode: disable all external feed fallbacks
    if os.getenv("CALLSBOT_FEED_DISABLED", "false").strip().lower() == "true":
        try:
            log_process({"type": "feed_disabled", "source": "fetch_feed"})
        except Exception:
            pass
        return {"transactions": [], "next_cursor": None, "error": "feed_disabled"}
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
    # Primary source: GeckoTerminal trending (DexScreener trending often 403s on servers)
    primary = _fallback_feed_from_geckoterminal(limit=40)
    if not primary:
        primary = _fallback_feed_from_dexscreener(limit=40, smart_money_only=smart_money_only)
    
    if primary:
        try:
            log_process({"type": "feed_primary", "provider": "dexscreener/gecko", "count": len(primary)})
        except Exception:
            pass
        return {"transactions": primary, "next_cursor": None, "error": None}
    
    return {"transactions": [], "next_cursor": None, "error": "no_feed"}


def _fallback_feed_from_dexscreener(limit: int = 30, smart_money_only: bool = False) -> list:
    """OPTIMIZED: Simplified fallback feed from DexScreener
    
    NOTE: DexScreener trending endpoint may be blocked by Cloudflare.
    This fallback is kept for redundancy but may not work reliably.
    GeckoTerminal is the preferred fallback.
    """
    from app.http_client import request_json as _rq

    if os.getenv("CALLSBOT_DEXSCREENER_TRENDING_ENABLED", "false").strip().lower() != "true":
        return []
    
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
            "source": "dexscreener:trending",
            "channel_name": "Dex Trending",
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
