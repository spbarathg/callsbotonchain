import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from . import wallet_tracker
from .metrics import metrics_collector

# Config from environment
QUICKNODE_URL: Optional[str] = os.getenv("QUICKNODE_URL")
RPC_TIMEOUT_S: float = float(os.getenv("RPC_TIMEOUT_S", "12"))
RPC_RETRIES: int = int(os.getenv("RPC_RETRIES", "2"))
MOMENTUM_WINDOW_S: float = float(os.getenv("MOMENTUM_WINDOW_S", "600"))
MOMENTUM_LIMIT: int = int(os.getenv("MOMENTUM_LIMIT", "25"))
RPC_MAX_CONCURRENCY: int = int(os.getenv("RPC_MAX_CONCURRENCY", "5"))
RPC_DELAY_S: float = float(os.getenv("RPC_DELAY_S", "0.1"))

_rpc_sem = asyncio.Semaphore(RPC_MAX_CONCURRENCY)


async def _rpc_request(
    session: aiohttp.ClientSession,
    url: str,
    method: str,
    params: List[Any],
    *,
    timeout_s: float = RPC_TIMEOUT_S,
) -> Any:
    """Safe RPC request with retries, backoff, and metrics recording."""
    # Use unique ID to avoid conflicts in parallel requests
    import random
    payload = {"jsonrpc": "2.0", "id": random.randint(1, 1000000), "method": method, "params": params}
    last_error: Optional[Exception] = None

    for attempt in range(1, RPC_RETRIES + 1):
        try:
            if RPC_DELAY_S > 0:
                await asyncio.sleep(RPC_DELAY_S)

            timeout = aiohttp.ClientTimeout(total=timeout_s)
            async with _rpc_sem:
                async with session.post(url, json=payload, timeout=timeout) as resp:
                    response_time = time.time() * 1000
                    if resp.status != 200:
                        text = await resp.text()
                        await metrics_collector.record_api_health("quicknode", "error", response_time, error=True)
                        raise RuntimeError(f"RPC {method} HTTP {resp.status}: {text}")
                    try:
                        data = await resp.json()
                    except Exception as json_error:
                        await metrics_collector.record_api_health("quicknode", "error", response_time, error=True)
                        raise RuntimeError(f"RPC {method} JSON decode error: {json_error}")
                    
                    if "error" in data:
                        await metrics_collector.record_api_health("quicknode", "error", response_time, error=True)
                        raise RuntimeError(f"RPC {method} error: {data['error']}")
                    await metrics_collector.record_api_health("quicknode", "healthy", response_time)
                    return data.get("result")
        except (asyncio.TimeoutError, aiohttp.ClientError, RuntimeError) as e:
            last_error = e
            if attempt < RPC_RETRIES:
                backoff = min(0.5 * (2 ** (attempt - 1)), 4.0)
                logging.debug("RPC retry %s/%s for %s after error: %s", attempt, RPC_RETRIES, method, e)
                await asyncio.sleep(backoff)
                continue
            break
    raise RuntimeError(f"RPC {method} failed after {RPC_RETRIES} attempts: {last_error}")


async def get_token_supply(session: aiohttp.ClientSession, quicknode_url: str, mint: str) -> Tuple[float, int]:
    """Return total supply (human-readable) and decimals."""
    result = await _rpc_request(session, quicknode_url, "getTokenSupply", [mint])
    value = result.get("value", {})
    amount_raw = int(value.get("amount", 0))
    decimals = int(value.get("decimals", 0))
    total_supply = amount_raw / (10 ** decimals) if decimals >= 0 else amount_raw
    return total_supply, decimals


async def get_token_largest_accounts(session: aiohttp.ClientSession, quicknode_url: str, mint: str) -> List[float]:
    """Return top token holder balances (decimals adjusted)."""
    result = await _rpc_request(session, quicknode_url, "getTokenLargestAccounts", [mint, {"commitment": "confirmed"}])
    value = result.get("value", [])
    balances: List[float] = []
    for entry in value:
        try:
            amount_raw = int(entry.get("amount", 0))
            decimals = int(entry.get("decimals", 0))
            balances.append(amount_raw / (10 ** decimals if decimals >= 0 else 1))
        except Exception:
            continue
    return balances


async def get_mint_info(session: aiohttp.ClientSession, quicknode_url: str, mint: str) -> Dict[str, Any]:
    """Return basic mint info: authority, decimals, supply, transfer fee (if SPL 2022)."""
    try:
        result = await _rpc_request(
            session,
            quicknode_url,
            "getAccountInfo",
            [mint, {"encoding": "jsonParsed", "commitment": "confirmed"}],
        )
        value = result.get("value", {})
        parsed = value.get("data", {}).get("parsed", {}).get("info", {})
        extensions = parsed.get("extensions", [])
        transfer_fee_bps = 0
        for ext in extensions:
            cfg = ext.get("state", {}).get("transferFeeConfig")
            if cfg:
                transfer_fee_bps = int(cfg.get("transferFeeBasisPoints", 0))
                break
        return {
            "mint_authority_null": parsed.get("mintAuthority") in (None, ""),
            "freeze_authority_null": parsed.get("freezeAuthority") in (None, ""),
            "decimals": int(parsed.get("decimals", 0)),
            "supply_raw": int(parsed.get("supply", 0)),
            "transfer_fee_bps": transfer_fee_bps,
        }
    except Exception as e:
        logging.debug("mint info fetch failed: %s", e)
        return {"mint_authority_null": False, "freeze_authority_null": False, "decimals": 0, "supply_raw": 0, "transfer_fee_bps": 0}


async def get_recent_signatures(session: aiohttp.ClientSession, quicknode_url: str, address: str, *, limit: int = MOMENTUM_LIMIT) -> List[Dict[str, Any]]:
    """Fetch recent transactions for momentum analysis."""
    try:
        result = await _rpc_request(session, quicknode_url, "getSignaturesForAddress", [address, {"limit": limit}])
        return result or []
    except Exception as e:
        logging.debug("signatures fetch failed: %s", e)
        return []


def _compute_concentration(total_supply: float, top_balances: List[float]) -> Dict[str, float]:
    """Return top1% and top10% holder concentration with LP heuristics."""
    sorted_balances = sorted(top_balances, reverse=True)
    supply = max(total_supply, 1e-9)
    filtered = sorted_balances
    if len(filtered) >= 2:
        if filtered[0] >= 3 * filtered[1] or filtered[0] / supply > 0.35:
            filtered = filtered[1:]
    top1 = filtered[0] if filtered else 0.0
    top10 = sum(filtered[:10]) if filtered else 0.0
    return {"top1_pct": min(top1 / supply, 1.0), "top10_pct": min(top10 / supply, 1.0)}


def _compute_momentum(signatures: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Heuristic momentum scoring based on transactions within MOMENTUM_WINDOW_S."""
    now = int(time.time())
    cutoff = now - MOMENTUM_WINDOW_S
    in_window = [s for s in signatures if isinstance(s.get("blockTime"), int) and s["blockTime"] >= cutoff]
    count = len(in_window) if in_window else len(signatures)
    if count >= 20: score = 4
    elif count >= 12: score = 3
    elif count >= 6: score = 2
    elif count >= 2: score = 1
    else: score = 0
    return {"tx_count": count, "score": score}


async def analyze_token(mint: str, base_context: Dict[str, Any], *, quicknode_url: Optional[str] = None, session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
    """Fetch and analyze on-chain data for a token, with optional enrichment."""
    qn_url = quicknode_url or QUICKNODE_URL
    if not qn_url:
        raise RuntimeError("QUICKNODE_URL not configured")

    owns_session = False
    if session is None:
        session = aiohttp.ClientSession()
        owns_session = True

    try:
        supply_task = asyncio.create_task(get_token_supply(session, qn_url, mint))
        holders_task = asyncio.create_task(get_token_largest_accounts(session, qn_url, mint))
        mint_info_task = asyncio.create_task(get_mint_info(session, qn_url, mint))
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
            "freeze_authority_null": bool(mint_info.get("freeze_authority_null")),
            "mint_authority_null": bool(mint_info.get("mint_authority_null")),
            "transfer_fee_bps": int(mint_info.get("transfer_fee_bps") or 0),
            "momentum_tx_count": int(momentum["tx_count"]),
            "momentum_score": int(momentum["score"]),
        }

        enrichment_score = 0
        creator_score = 0
        if result["lp_sol"] >= float(os.getenv("MIN_LP_SOL", "5")):
            try:
                # Use the new smart money analysis function
                involved_wallets = base_context.get("involved_wallets", [])
                if involved_wallets:
                    smart_money_data = await wallet_tracker.score_smart_money_involvement(session, mint, involved_wallets)
                    enrichment_score = smart_money_data.get("total_score", 0)
            except Exception as e:
                logging.debug("wallet enrichment failed: %s", e)
            creator_addr = base_context.get("creator")
            if creator_addr:
                try:
                    # Simplified creator scoring - can be enhanced later
                    creator_score = 1 if creator_addr else 0
                except Exception as e:
                    logging.debug("creator history failed: %s", e)

        result["enrichment_score"] = int(enrichment_score)
        result["creator_score"] = int(creator_score)
        return result
    finally:
        if owns_session:
            await session.close()


__all__ = ["analyze_token", "get_token_supply", "get_token_largest_accounts"]