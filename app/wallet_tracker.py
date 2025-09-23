import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional, List

import aiohttp
import random


# -----------------------------
# Cielo Pro Configuration
# -----------------------------
CIELO_API_KEY = os.getenv("CIELO_API_KEY")
CIELO_BASE_URL = os.getenv("CIELO_BASE_URL", "https://feed-api.cielo.finance/api/v1")
CIELO_WS_URL = os.getenv("CIELO_WS_URL", "wss://feed-api.cielo.finance/ws")
CIELO_TIMEOUT_S = float(os.getenv("CIELO_TIMEOUT_S", "8"))
CIELO_RETRIES = int(os.getenv("CIELO_RETRIES", "2"))
CIELO_ENABLE = os.getenv("CIELO_ENABLE", "true").strip().lower() in ("1", "true", "yes", "y")

# Budget Controls
CIELO_MAX_CALLS_PER_HOUR = int(os.getenv("CIELO_MAX_CALLS_PER_HOUR", "200"))
CIELO_MAX_CALLS_PER_DAY = int(os.getenv("CIELO_MAX_CALLS_PER_DAY", "4000"))
CIELO_SAMPLING_PROB = max(0.0, min(1.0, float(os.getenv("CIELO_SAMPLING_PROB", "1.0"))))

# Rate Limiting
CIELO_RATE_LIMIT_S = float(os.getenv("CIELO_RATE_LIMIT_S", "0.1"))  # 10 calls/second
_last_cielo_call = 0.0
_cielo_hourly_calls = 0
_cielo_hourly_reset = time.time() + 3600
_cielo_daily_calls = 0
_cielo_daily_reset = time.time() + 86400
_cielo_lock = asyncio.Lock()
_cielo_call_lock = asyncio.Lock()  # Separate lock for call timing


# -----------------------------
# Internal Budget + Request Layer
# -----------------------------
async def _cielo_budget_allow() -> bool:
    """Atomically check hourly/daily budgets and sampling before calling Cielo."""
    global _cielo_hourly_calls, _cielo_hourly_reset, _cielo_daily_calls, _cielo_daily_reset

    if not CIELO_ENABLE:
        return False
    if CIELO_SAMPLING_PROB < 1.0 and random.random() > CIELO_SAMPLING_PROB:
        return False

    now = time.time()
    async with _cielo_lock:
        if now > _cielo_hourly_reset:
            _cielo_hourly_calls = 0
            _cielo_hourly_reset = now + 3600
        if now > _cielo_daily_reset:
            _cielo_daily_calls = 0
            _cielo_daily_reset = now + 86400
        if _cielo_hourly_calls >= CIELO_MAX_CALLS_PER_HOUR:
            return False
        if _cielo_daily_calls >= CIELO_MAX_CALLS_PER_DAY:
            return False

        _cielo_hourly_calls += 1
        _cielo_daily_calls += 1
        return True


async def _cielo_request(
    session: aiohttp.ClientSession,
    endpoint: str,
    params: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """Make rate-limited request to Cielo Pro API with retries."""
    global _last_cielo_call

    if not CIELO_API_KEY:
        logging.warning("CIELO_API_KEY not configured - smart wallet detection disabled")
        return None

    allowed = await _cielo_budget_allow()
    if not allowed:
        logging.debug("Cielo API call skipped due to budget limits")
        return None

    url = f"{CIELO_BASE_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {CIELO_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "MemecoinBot/1.0"
    }

    for attempt in range(CIELO_RETRIES + 1):
        try:
            # Thread-safe rate limiting
            async with _cielo_call_lock:
                now = time.time()
                if now - _last_cielo_call < CIELO_RATE_LIMIT_S:
                    await asyncio.sleep(CIELO_RATE_LIMIT_S - (now - _last_cielo_call))
                _last_cielo_call = time.time()

            timeout = aiohttp.ClientTimeout(total=CIELO_TIMEOUT_S)
            async with session.get(url, headers=headers, params=params, timeout=timeout) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 429:  # Rate limited
                    if attempt < CIELO_RETRIES:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    logging.warning("Cielo rate limit exceeded")
                    return None
                elif resp.status == 401:
                    logging.error("Cielo API key invalid or expired")
                    return None
                else:
                    logging.debug("Cielo API error %s: %s", resp.status, await resp.text())
                    return None

        except asyncio.TimeoutError:
            if attempt < CIELO_RETRIES:
                await asyncio.sleep(1)
                continue
            logging.warning("Cielo API timeout after %d attempts", CIELO_RETRIES + 1)
            return None
        except Exception as e:
            if attempt < CIELO_RETRIES:
                await asyncio.sleep(1)
                continue
            logging.warning("Cielo API error: %s", e)
            return None

    return None


# -----------------------------
# Token Endpoints
# -----------------------------
async def get_token_metadata(session: aiohttp.ClientSession, mint_address: str) -> Optional[Dict[str, Any]]:
    """Get token metadata from Cielo API."""
    return await _cielo_request(session, f"/token/metadata/{mint_address}")


async def get_token_stats(session: aiohttp.ClientSession, mint_address: str) -> Optional[Dict[str, Any]]:
    """Get token stats from Cielo API."""
    return await _cielo_request(session, f"/token/stats/{mint_address}")


async def get_token_price(session: aiohttp.ClientSession, mint_address: str) -> Optional[Dict[str, Any]]:
    """Get token price from Cielo API."""
    return await _cielo_request(session, f"/token/price/{mint_address}")


# -----------------------------
# Wallet Endpoints
# -----------------------------
async def get_wallet_portfolio(session: aiohttp.ClientSession, wallet_address: str) -> Optional[Dict[str, Any]]:
    """Get wallet portfolio."""
    return await _cielo_request(session, f"/wallet/{wallet_address}/portfolio")


async def get_wallet_pnl(session: aiohttp.ClientSession, wallet_address: str) -> Optional[Dict[str, Any]]:
    """Get wallet total PnL stats."""
    return await _cielo_request(session, f"/wallet/{wallet_address}/pnl/total-stats")


async def get_wallet_tokens_pnl(session: aiohttp.ClientSession, wallet_address: str) -> Optional[Dict[str, Any]]:
    """Get wallet token-specific PnL."""
    return await _cielo_request(session, f"/wallet/{wallet_address}/pnl/tokens")


async def get_related_wallets(session: aiohttp.ClientSession, wallet_address: str) -> Optional[Dict[str, Any]]:
    """Get related wallets for a given address."""
    return await _cielo_request(session, f"/wallet/{wallet_address}/related-wallets")


async def get_wallets_by_tag(session: aiohttp.ClientSession, tag: str) -> Optional[List[Dict[str, Any]]]:
    """Get wallets by tag (e.g., whale, smartmoney, market_maker)."""
    return await _cielo_request(session, f"/wallets-by-tag/{tag}")


# -----------------------------
# Smart Money Analysis
# -----------------------------
async def score_smart_money_involvement(
    session: aiohttp.ClientSession,
    mint_address: str,
    involved_wallets: List[str]
) -> Dict[str, Any]:
    """
    Analyze smart money involvement using Cielo documented endpoints.
    Returns a combined score 0–6.
    """
    if not CIELO_ENABLE or not involved_wallets:
        return {"smart_wallet_score": 0, "pnl_score": 0, "related_score": 0, "total_score": 0}

    smart_wallet_score, pnl_score, related_score = 0, 0, 0

    try:
        for wallet in involved_wallets[:5]:
            pnl_data = await get_wallet_pnl(session, wallet)
            if pnl_data:
                total_pnl = pnl_data.get("total_pnl", 0)
                win_rate = pnl_data.get("win_rate", 0)
                if total_pnl > 0 and win_rate > 0.6:
                    pnl_score += 1

                tags = pnl_data.get("tags", [])
                if any(tag in ["whale", "smartmoney", "market_maker"] for tag in tags):
                    smart_wallet_score += 1

        if len(involved_wallets) > 1:
            related_data = await get_related_wallets(session, involved_wallets[0])
            if related_data:
                related_wallets = related_data.get("related_wallets", [])
                overlap = len(set(involved_wallets) & set(related_wallets))
                if overlap > 0:
                    related_score = min(1, overlap / len(involved_wallets))

        total_score = smart_wallet_score + pnl_score + related_score

        return {
            "smart_wallet_score": min(3, smart_wallet_score),
            "pnl_score": min(2, pnl_score),
            "related_score": related_score,
            "total_score": min(6, total_score)
        }

    except Exception as e:
        logging.warning("Smart money analysis failed: %s", e)
        return {"smart_wallet_score": 0, "pnl_score": 0, "related_score": 0, "total_score": 0}


__all__ = [
    "get_token_metadata",
    "get_token_stats",
    "get_token_price",
    "get_wallet_portfolio",
    "get_wallet_pnl",
    "get_wallet_tokens_pnl",
    "get_wallets_by_tag",
    "get_related_wallets",
    "score_smart_money_involvement"
]