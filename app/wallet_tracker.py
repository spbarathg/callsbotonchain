import logging
import os
from typing import Any, Dict, Optional

import aiohttp


SOLANASPY_API_KEY = os.getenv("SOLANASPY_API_KEY")
SOLANASPY_BASE_URL = os.getenv("SOLANASPY_BASE_URL", "https://api.solanaspy.io/v1")

SOLANATRACKER_API_KEY = os.getenv("SOLANATRACKER_API_KEY")
SOLANATRACKER_BASE_URL = os.getenv(
    "SOLANATRACKER_BASE_URL", "https://api.solanatracker.io/public"
)


def _pick_provider() -> str:
    if SOLANASPY_API_KEY:
        return "solanaspy"
    if SOLANATRACKER_API_KEY:
        return "solanatracker"
    return "none"


async def _http_get(
    session: aiohttp.ClientSession, url: str, headers: Optional[Dict[str, str]] = None
) -> Optional[Dict[str, Any]]:
    try:
        async with session.get(url, headers=headers, timeout=8) as resp:
            if resp.status != 200:
                logging.debug("wallet provider http %s for %s", resp.status, url)
                return None
            return await resp.json()
    except Exception as e:
        logging.debug("wallet provider request failed: %s", e)
        return None


def _score_from_count(count: int) -> int:
    # Map number of smart wallets to 0-3 score
    if count >= 10:
        return 3
    if count >= 5:
        return 2
    if count >= 2:
        return 1
    return 0


async def fetch_smart_wallet_score(
    session: aiohttp.ClientSession, token_mint: str
) -> int:
    """Return 0-3 based on presence of known smart/whale wallets entering the token.

    This is a best-effort call. If provider or API is unavailable, returns 0.
    """
    provider = _pick_provider()
    if provider == "solanaspy":
        url = f"{SOLANASPY_BASE_URL}/token/{token_mint}/smart-wallets"
        headers = {"Authorization": f"Bearer {SOLANASPY_API_KEY}"}
        data = await _http_get(session, url, headers)
        if data and isinstance(data.get("count"), int):
            return _score_from_count(int(data["count"]))
        # Fallback: derive from list length
        wallets = data.get("wallets") if data else None
        if isinstance(wallets, list):
            return _score_from_count(len(wallets))
        return 0

    if provider == "solanatracker":
        url = f"{SOLANATRACKER_BASE_URL}/token/{token_mint}/smart-wallets"
        headers = {"X-API-KEY": SOLANATRACKER_API_KEY}
        data = await _http_get(session, url, headers)
        if data and isinstance(data.get("count"), int):
            return _score_from_count(int(data["count"]))
        wallets = data.get("wallets") if data else None
        if isinstance(wallets, list):
            return _score_from_count(len(wallets))
        return 0

    return 0


async def fetch_creator_history_score(
    session: aiohttp.ClientSession, creator_address: str
) -> int:
    """Return 0-1 based on historical creator quality.

    Heuristic: if provider reports >0 past tokens with sustained liquidity, return 1.
    """
    provider = _pick_provider()
    try:
        if provider == "solanaspy":
            url = f"{SOLANASPY_BASE_URL}/creator/{creator_address}/history"
            headers = {"Authorization": f"Bearer {SOLANASPY_API_KEY}"}
            data = await _http_get(session, url, headers)
        elif provider == "solanatracker":
            url = f"{SOLANATRACKER_BASE_URL}/creator/{creator_address}/history"
            headers = {"X-API-KEY": SOLANATRACKER_API_KEY}
            data = await _http_get(session, url, headers)
        else:
            data = None
        if not data:
            return 0
        success = int(data.get("successful_tokens") or 0)
        return 1 if success > 0 else 0
    except Exception as e:
        logging.debug("creator history failed: %s", e)
        return 0


__all__ = ["fetch_smart_wallet_score", "fetch_creator_history_score"]


