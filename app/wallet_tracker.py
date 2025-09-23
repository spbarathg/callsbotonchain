import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional

import aiohttp


# Cielo Pro - Primary smart wallet tracking service
CIELO_API_KEY = os.getenv("CIELO_API_KEY")
CIELO_BASE_URL = os.getenv("CIELO_BASE_URL", "https://api.cielo.finance")
CIELO_TIMEOUT_S = float(os.getenv("CIELO_TIMEOUT_S", "8"))
CIELO_RETRIES = int(os.getenv("CIELO_RETRIES", "2"))

# Rate limiting for Cielo Pro
CIELO_RATE_LIMIT_S = float(os.getenv("CIELO_RATE_LIMIT_S", "0.1"))  # 10 calls/second max
_last_cielo_call = 0.0


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
    
    url = f"{CIELO_BASE_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {CIELO_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "MemecoinBot/1.0"
    }
    
    for attempt in range(CIELO_RETRIES + 1):
        try:
            # Rate limiting
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
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
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


def _score_from_smart_wallets(smart_wallets: list) -> int:
    """Enhanced scoring based on Cielo Pro smart wallet data."""
    if not smart_wallets:
        return 0
    
    # Enhanced scoring considering wallet quality and activity
    high_quality_count = 0
    total_count = len(smart_wallets)
    
    for wallet in smart_wallets:
        # Cielo Pro provides quality metrics
        confidence = wallet.get("confidence", 0)
        profit_rate = wallet.get("profit_rate", 0)
        activity_level = wallet.get("activity_level", "low")
        
        # High-quality wallet criteria
        if (confidence >= 0.8 or profit_rate >= 0.7 or activity_level in ["high", "very_high"]):
            high_quality_count += 1
    
    # Scoring: prioritize quality over quantity
    if high_quality_count >= 5:
        return 3  # Excellent
    elif high_quality_count >= 2 or total_count >= 8:
        return 2  # Good
    elif high_quality_count >= 1 or total_count >= 3:
        return 1  # Fair
    else:
        return 0  # Poor


async def fetch_smart_wallet_score(
    session: aiohttp.ClientSession, token_mint: str
) -> int:
    """Fetch smart wallet score using Cielo Pro API.
    
    Returns 0-3 based on quality and quantity of smart wallets holding the token.
    """
    try:
        # Cielo Pro endpoint for smart wallet analysis
        # NOTE: Verify this endpoint exists in Cielo API documentation
        data = await _cielo_request(session, f"/v1/tokens/{token_mint}/smart-wallets")
        
        if not data:
            return 0
        
        # Handle different response formats
        smart_wallets = data.get("smart_wallets", [])
        if isinstance(smart_wallets, list):
            return _score_from_smart_wallets(smart_wallets)
        
        # Fallback to simple count if detailed data unavailable
        count = data.get("count", 0)
        if isinstance(count, int):
            if count >= 10:
                return 3
            elif count >= 5:
                return 2
            elif count >= 2:
                return 1
        
        return 0
        
    except Exception as e:
        logging.warning("Smart wallet detection failed: %s", e)
        return 0


async def fetch_creator_history_score(
    session: aiohttp.ClientSession, creator_address: str
) -> int:
    """Fetch creator history score using Cielo Pro API.
    
    Returns 0-1 based on creator's historical token performance.
    """
    try:
        # Cielo Pro endpoint for creator analysis
        # NOTE: Verify this endpoint exists in Cielo API documentation
        data = await _cielo_request(session, f"/v1/creators/{creator_address}/history")
        
        if not data:
            return 0
        
        # Cielo Pro provides detailed creator metrics
        successful_tokens = data.get("successful_tokens", 0)
        total_tokens = data.get("total_tokens", 0)
        avg_performance = data.get("avg_performance", 0)
        reputation_score = data.get("reputation_score", 0)
        
        # Enhanced scoring based on multiple factors
        if (successful_tokens >= 3 or 
            (total_tokens > 0 and successful_tokens / total_tokens >= 0.6) or
            avg_performance >= 2.0 or  # 2x average
            reputation_score >= 0.8):
            return 1
        
        return 0
        
    except Exception as e:
        logging.warning("Creator history analysis failed: %s", e)
        return 0


__all__ = ["fetch_smart_wallet_score", "fetch_creator_history_score"]


