import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from . import wallet_tracker
from .metrics import metrics_collector


QUICKNODE_URL: Optional[str] = os.getenv("QUICKNODE_URL")
RPC_TIMEOUT_S: float = float(os.getenv("RPC_TIMEOUT_S", "12"))
RPC_RETRIES: int = int(os.getenv("RPC_RETRIES", "2"))
MOMENTUM_WINDOW_S: float = float(os.getenv("MOMENTUM_WINDOW_S", "600"))
MOMENTUM_LIMIT: int = int(os.getenv("MOMENTUM_LIMIT", "25"))
RPC_MAX_CONCURRENCY: int = int(os.getenv("RPC_MAX_CONCURRENCY", "5"))  # Optimized for Pro services
RPC_DELAY_S: float = float(os.getenv("RPC_DELAY_S", "0.1"))  # Faster with Pro reliability
_rpc_sem = asyncio.Semaphore(RPC_MAX_CONCURRENCY)


async def _rpc_request(
    session: aiohttp.ClientSession,
    url: str,
    method: str,
    params: List[Any],
    *,
    timeout_s: float = RPC_TIMEOUT_S,
) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    attempt = 0
    last_error: Optional[Exception] = None
    start_time = time.time()
    
    # attempt ranges from 1..RPC_RETRIES inclusive to match configured attempts
    while attempt < RPC_RETRIES:
        attempt += 1
        try:
            # Rate limiting delay for RPC calls
            if RPC_DELAY_S > 0:
                await asyncio.sleep(RPC_DELAY_S)
                
            timeout = aiohttp.ClientTimeout(total=timeout_s)
            async with _rpc_sem:
                async with session.post(url, json=payload, timeout=timeout) as resp:
                    response_time = (time.time() - start_time) * 1000
                    
                    if resp.status != 200:
                        text = await resp.text()
                        await metrics_collector.record_api_health("quicknode", "error", response_time, error=True)
                        raise RuntimeError(f"RPC {method} HTTP {resp.status}: {text}")
                    
                    data = await resp.json()
                    if data.get("error"):
                        await metrics_collector.record_api_health("quicknode", "error", response_time, error=True)
                        raise RuntimeError(f"RPC {method} error: {data['error']}")
                    
                    # Record successful API call
                    await metrics_collector.record_api_health("quicknode", "healthy", response_time)
                    return data.get("result")
                    
        except (asyncio.TimeoutError, aiohttp.ClientError, RuntimeError) as e:
            last_error = e
            response_time = (time.time() - start_time) * 1000
            
            if isinstance(e, asyncio.TimeoutError):
                await metrics_collector.record_api_health("quicknode", "timeout", response_time, error=True)
            else:
                await metrics_collector.record_api_health("quicknode", "error", response_time, error=True)
            
            is_timeout = isinstance(e, asyncio.TimeoutError) or (
                isinstance(e, RuntimeError) and "timeout" in str(e).lower()
            )
            if attempt <= RPC_RETRIES and (
                is_timeout or isinstance(e, aiohttp.ClientError) or "HTTP 5" in str(e) or "HTTP 429" in str(e)
            ):
                backoff_s = min(0.5 * (2 ** (attempt - 1)), 4.0)
                logging.debug("RPC retry %s/%s for %s after error: %s", attempt, RPC_RETRIES, method, e)
                await asyncio.sleep(backoff_s)
                continue
            break
    
    raise RuntimeError(f"RPC {method} failed after {attempt} attempts: {last_error}")


async def get_token_supply(
    session: aiohttp.ClientSession, quicknode_url: str, mint: str
) -> Tuple[float, int]:
    """Return (total_supply_tokens, decimals)."""
    result = await _rpc_request(session, quicknode_url, "getTokenSupply", [mint])
    value = result.get("value") or {}
    amount_raw = int(value.get("amount") or 0)
    decimals = int(value.get("decimals") or 0)
    divisor = 10 ** decimals if decimals >= 0 else 1
    total_supply = amount_raw / divisor
    return total_supply, decimals


async def get_token_largest_accounts(
    session: aiohttp.ClientSession, quicknode_url: str, mint: str
) -> List[float]:
    """Return top holder balances in token units (decimals adjusted)."""
    result = await _rpc_request(
        session,
        quicknode_url,
        "getTokenLargestAccounts",
        [mint, {"commitment": "confirmed"}],
    )
    value = result.get("value") or []
    balances: List[float] = []
    for entry in value:
        try:
            amount_raw = int(entry.get("amount") or 0)
            decimals = int(entry.get("decimals") or 0)
            divisor = 10 ** decimals if decimals >= 0 else 1
            balances.append(amount_raw / divisor)
        except Exception:
            continue
    return balances


async def get_mint_info(
    session: aiohttp.ClientSession, quicknode_url: str, mint: str
) -> Dict[str, Any]:
    """Return parsed mint info with safety-related fields.

    Attempts to parse SPL Token 2022 extensions (e.g., transferFeeConfig) when present.
    """
    try:
        result = await _rpc_request(
            session,
            quicknode_url,
            "getAccountInfo",
            [mint, {"encoding": "jsonParsed", "commitment": "confirmed"}],
        )
        value = (result or {}).get("value") or {}
        parsed = ((value.get("data") or {}).get("parsed") or {}).get("info") or {}
        # Transfer fee config may exist under extensions
        extensions = parsed.get("extensions") or []
        transfer_fee_bps = 0
        for ext in extensions:
            try:
                if (ext.get("state") or {}).get("transferFeeConfig"):
                    cfg = ext["state"]["transferFeeConfig"]
                    transfer_fee_bps = int(cfg.get("transferFeeBasisPoints") or 0)
                    break
            except Exception:
                continue
        return {
            "mint_authority_null": parsed.get("mintAuthority") in (None, ""),
            "freeze_authority_null": parsed.get("freezeAuthority") in (None, ""),
            "decimals": int(parsed.get("decimals") or 0),
            "supply_raw": int(parsed.get("supply") or 0),
            "transfer_fee_bps": transfer_fee_bps,
        }
    except Exception as e:
        logging.debug("mint info fetch failed: %s", e)
        return {
            "mint_authority_null": False,
            "freeze_authority_null": False,
            "decimals": 0,
            "supply_raw": 0,
            "transfer_fee_bps": 0,
        }


async def get_recent_signatures(
    session: aiohttp.ClientSession, quicknode_url: str, address: str, *, limit: int = MOMENTUM_LIMIT
) -> List[Dict[str, Any]]:
    try:
        result = await _rpc_request(
            session,
            quicknode_url,
            "getSignaturesForAddress",
            [address, {"limit": int(limit)}],
        )
        return result or []
    except Exception as e:
        logging.debug("signatures fetch failed: %s", e)
        return []


def _compute_concentration(total_supply: float, top_balances: List[float]) -> Dict[str, float]:
    sorted_balances = sorted(top_balances, reverse=True)
    supply = max(total_supply, 1e-9)

    # Heuristic: exclude a likely LP/program vault that dwarfs others
    # If the largest balance is >3x the next largest or >35% of supply, drop it
    filtered = list(sorted_balances)
    if len(filtered) >= 2:
        largest = filtered[0]
        second = filtered[1]
        if largest >= 3.0 * second or (largest / supply) > 0.35:
            filtered = filtered[1:]

    top1 = filtered[0] if filtered else 0.0
    top10 = sum(filtered[:10]) if filtered else 0.0
    top1_pct = min(max(top1 / supply, 0.0), 1.0)
    top10_pct = min(max(top10 / supply, 0.0), 1.0)
    return {"top1_pct": top1_pct, "top10_pct": top10_pct}


def _compute_momentum(signatures: List[Dict[str, Any]]) -> Dict[str, Any]:
    now = int(time.time())
    cutoff = now - MOMENTUM_WINDOW_S
    in_window = [s for s in signatures if isinstance(s.get("blockTime"), int) and s["blockTime"] >= cutoff]
    count = len(in_window) if in_window else len(signatures)
    
    # Enhanced scoring for 50%+ pump detection
    if count >= 20:
        score = 4  # Viral momentum
    elif count >= 12:
        score = 3  # Strong momentum  
    elif count >= 6:
        score = 2  # Good momentum
    elif count >= 2:
        score = 1  # Some momentum
    else:
        score = 0  # No momentum
        
    return {"tx_count": count, "score": score}


async def analyze_token(
    mint: str,
    base_context: Dict[str, Any],
    *,
    quicknode_url: Optional[str] = None,
    session: Optional[aiohttp.ClientSession] = None,
) -> Dict[str, Any]:
    """Fetch on-chain data and optional enrichment for scoring.

    base_context should provide: lp_sol (float), dex, pool_address, creator, ts
    """
    qn_url = quicknode_url or QUICKNODE_URL
    if not qn_url:
        raise RuntimeError("QUICKNODE_URL not configured")

    owns_session = False
    if session is None:
        session = aiohttp.ClientSession()
        owns_session = True

    try:
        # Supply and holders concurrently; tolerate holder failures
        supply_task = asyncio.create_task(get_token_supply(session, qn_url, mint))
        holders_task = asyncio.create_task(get_token_largest_accounts(session, qn_url, mint))
        mint_info_task = asyncio.create_task(get_mint_info(session, qn_url, mint))
        # Momentum: prefer pool address when available, fallback to mint address
        momentum_address = str(base_context.get("pool_address") or mint)
        sigs_task = asyncio.create_task(get_recent_signatures(session, qn_url, momentum_address))

        total_supply, decimals = await supply_task
        try:
            top_balances = await holders_task
        except Exception as e:
            logging.warning("holders fetch failed for %s: %s", mint, e)
            top_balances = []

        mint_info = await mint_info_task
        sigs = await sigs_task
        momentum = _compute_momentum(sigs)

        conc = _compute_concentration(total_supply, top_balances)

        result: Dict[str, Any] = {
            "mint": mint,
            "ts": base_context.get("ts") or int(time.time()),
            "dex": base_context.get("dex"),
            "pool_address": base_context.get("pool_address"),
            "creator": base_context.get("creator"),
            "lp_sol": float(base_context.get("lp_sol") or 0.0),
            "total_supply": total_supply,
            "decimals": decimals,
            "top1_pct": conc["top1_pct"],
            "top10_pct": conc["top10_pct"],
            # Mint safety
            "freeze_authority_null": bool(mint_info.get("freeze_authority_null")),
            "mint_authority_null": bool(mint_info.get("mint_authority_null")),
            "transfer_fee_bps": int(mint_info.get("transfer_fee_bps") or 0),
            # Momentum
            "momentum_tx_count": int(momentum["tx_count"]),
            "momentum_score": int(momentum["score"]),
        }

        # Only enrich with wallet data after base risk check
        enrichment_score = 0
        creator_score = 0
        if result["lp_sol"] >= float(os.getenv("MIN_LP_SOL", "5")):
            try:
                enrichment_score = await wallet_tracker.fetch_smart_wallet_score(
                    session, mint
                )
            except Exception as e:
                logging.debug("wallet enrichment failed: %s", e)

            creator_addr = base_context.get("creator")
            if creator_addr:
                try:
                    creator_score = await wallet_tracker.fetch_creator_history_score(
                        session, creator_addr
                    )
                except Exception as e:
                    logging.debug("creator history failed: %s", e)

        result["enrichment_score"] = int(enrichment_score)
        result["creator_score"] = int(creator_score)
        return result
    finally:
        if owns_session and session:
            await session.close()


__all__ = [
    "analyze_token",
    "get_token_supply",
    "get_token_largest_accounts",
]


