import asyncio
import json
import logging
import os
import re
import time
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from base58 import b58decode  # type: ignore
from telethon import TelegramClient, events
from telethon.tl.types import MessageEntityCode, MessageEntityPre, MessageEntityTextUrl


# --- Config ---
API_ID: int = int(os.getenv("API_ID", "0"))
API_HASH: str = os.getenv("API_HASH", "")
SESSION_NAME: str = os.getenv("TELEGRAM_SESSION", "memecoin_session")

# Comma-separated list or defaults below
MONITORED_GROUPS_ENV = os.getenv("MONITORED_GROUPS")
if MONITORED_GROUPS_ENV:
    MONITORED_GROUPS: List[str] = [g.strip() for g in MONITORED_GROUPS_ENV.split(",") if g.strip()]
else:
    MONITORED_GROUPS = [
        "@MooDengPresidentCallers",
        "@Bot_NovaX",
        "@Ranma_Calls_Solana",
        "@MarksGems",
        "@Alphakollswithins",
        "@mattprintalphacalls",
        "@ReVoX_Academy",
        "@pfultimate",
        "@pumpfunvolumeby4AM",
        "@SouthParkCall",
        "@batman_gem",
        "@wifechangingcallss",
        "@SAVANNAHCALLS",
    ]

TARGET_GROUP: Optional[str] = os.getenv("TARGET_GROUP", "@callbotmemecoin")

# Optional webhook to feed the analyzer service
WEBHOOK_URL: Optional[str] = os.getenv("WEBHOOK_URL", None)
WEBHOOK_SECRET: Optional[str] = os.getenv("WEBHOOK_SECRET", None)
MIN_LP_SOL: float = float(os.getenv("MIN_LP_SOL", "5"))
SOL_PRICE_USD: float = float(os.getenv("SOL_PRICE_USD", "150"))


BASE58_BOUNDED_RE: re.Pattern[str] = re.compile(r"(?<![A-Za-z0-9])[1-9A-HJ-NP-Za-km-z]{32,44}(?![A-Za-z0-9])")
BASE58_FULL_RE: re.Pattern[str] = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
PREFIX_RE: re.Pattern[str] = re.compile(r"(?i)(?:\b(?:ca|mint|contract|token|token mint|address)\b)[:\s]*([1-9A-HJ-NP-Za-km-z]{32,44})")
SOLSCAN_RE: re.Pattern[str] = re.compile(r"solscan\.io\/token\/([1-9A-HJ-NP-Za-km-z]{32,44})", re.I)
EXPLORER_RE: re.Pattern[str] = re.compile(r"explorer\.solana\.com\/address\/([1-9A-HJ-NP-Za-km-z]{32,44})", re.I)
WSOL_MINT = "So11111111111111111111111111111111111111112"


async def _dexscreener_pairs(session: aiohttp.ClientSession, mint: str) -> Optional[Dict[str, Any]]:
    url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
    try:
        async with session.get(url, timeout=8) as resp:
            if resp.status != 200:
                return None
            return await resp.json()
    except Exception:
        return None


def _estimate_lp_sol_from_pair(pair: Dict[str, Any], sol_price_usd: float) -> Tuple[float, str, str, str]:
    # Returns (lp_sol_est, dex, pair_address, quote_symbol)
    liquidity_usd = float(((pair.get("liquidity") or {}).get("usd") or 0.0))
    dex_id = str(pair.get("dexId") or "")
    pair_addr = str(pair.get("pairAddress") or "")
    quote_symbol = str(((pair.get("quoteToken") or {}).get("symbol")) or "")
    if liquidity_usd <= 0.0:
        return 0.0, dex_id, pair_addr, quote_symbol
    if sol_price_usd <= 0.0:
        return 0.0, dex_id, pair_addr, quote_symbol
    return liquidity_usd / sol_price_usd, dex_id, pair_addr, quote_symbol


async def _approx_pool_info(session: aiohttp.ClientSession, mint: str) -> Tuple[float, Optional[str], Optional[str]]:
    data = await _dexscreener_pairs(session, mint)
    if not data:
        return 0.0, None, None
    pairs = data.get("pairs") or []
    best_lp = 0.0
    best_dex: Optional[str] = None
    best_pair: Optional[str] = None
    for p in pairs:
        lp_sol, dex, pair_addr, quote_symbol = _estimate_lp_sol_from_pair(p, SOL_PRICE_USD)
        # Prefer SOL-quoted pairs
        if lp_sol > best_lp and quote_symbol.upper() == "SOL":
            best_lp = lp_sol
            best_dex = dex
            best_pair = pair_addr
    # Fallback: any pair
    if best_lp <= 0.0:
        for p in pairs:
            lp_sol, dex, pair_addr, _ = _estimate_lp_sol_from_pair(p, SOL_PRICE_USD)
            if lp_sol > best_lp:
                best_lp = lp_sol
                best_dex = dex
                best_pair = pair_addr
    return float(best_lp), best_dex, best_pair


ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\ufeff", "\u2060"}


def _normalize_text(text: str) -> str:
    s = unicodedata.normalize("NFKC", text)
    for zw in ZERO_WIDTH:
        s = s.replace(zw, "")
    s = s.replace("–", "-").replace("—", "-").replace("−", "-")
    s = "".join(ch for ch in s if ch.isprintable())
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _valid_pubkey(candidate: str) -> bool:
    if not BASE58_FULL_RE.match(candidate):
        return False
    try:
        raw = b58decode(candidate)
    except Exception:
        return False
    return len(raw) == 32


def _extract_from_entities(message_text: str, entities: Optional[List[Any]]) -> List[str]:
    if not entities:
        return []
    cands: List[str] = []
    for ent in entities:
        try:
            segment = message_text[ent.offset : ent.offset + ent.length]
        except Exception:
            segment = ""
        if isinstance(ent, (MessageEntityCode, MessageEntityPre)):
            if segment:
                cands.extend(BASE58_BOUNDED_RE.findall(segment))
                cands.extend(PREFIX_RE.findall(segment))
                cands.extend(SOLSCAN_RE.findall(segment))
                cands.extend(EXPLORER_RE.findall(segment))
        elif isinstance(ent, MessageEntityTextUrl):
            url = getattr(ent, "url", "") or segment
            if url:
                cands.extend(SOLSCAN_RE.findall(url))
                cands.extend(EXPLORER_RE.findall(url))
    return cands


def _extract_from_text(text: str) -> List[str]:
    cands: List[str] = []
    cands.extend(BASE58_BOUNDED_RE.findall(text))
    cands.extend(PREFIX_RE.findall(text))
    cands.extend(SOLSCAN_RE.findall(text))
    cands.extend(EXPLORER_RE.findall(text))
    # Reassemble obfuscated sequences like "Abcd Efg1 Hij2 ..."
    for m in re.finditer(r"([1-9A-HJ-NP-Za-km-z]{4,})(?:[ \-]+([1-9A-HJ-NP-Za-km-z]{4,})){1,}", text):
        joined = re.sub(r"[ \-]+", "", m.group(0))
        if BASE58_FULL_RE.match(joined):
            cands.append(joined)
    return cands


class RecentSet:
    def __init__(self, ttl_s: int = 900) -> None:
        self.ttl_s = ttl_s
        self._store: Dict[str, float] = {}

    def add(self, key: str) -> None:
        self._store[key] = time.time() + self.ttl_s

    def seen(self, key: str) -> bool:
        now = time.time()
        # Cleanup
        expired = [k for k, until in self._store.items() if until < now]
        for k in expired:
            del self._store[k]
        return key in self._store


async def run_userbot() -> None:
    logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO))
    if not API_ID or not API_HASH:
        raise RuntimeError("API_ID/API_HASH not configured for userbot")

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    recent = RecentSet(ttl_s=900)

    http_session: Optional[aiohttp.ClientSession] = None

    @client.on(events.NewMessage(chats=MONITORED_GROUPS))
    async def handler(event: events.NewMessage.Event) -> None:  # type: ignore
        try:
            raw = event.message.message or ""
            if not raw:
                return
            text = _normalize_text(raw)

            # Entity-first candidates
            candidates = set(_extract_from_entities(raw, event.message.entities))
            # Fallback to full-text parsing
            if not candidates:
                candidates = set(_extract_from_text(text))
            if not candidates:
                return
            # Basic filter
            candidates = {c for c in candidates if c and c != WSOL_MINT and _valid_pubkey(c)}
            if not candidates:
                return

            if http_session is None:
                # lazy init
                pass

            for mint in list(candidates)[:3]:  # cap per message
                if recent.seen(mint):
                    continue
                recent.add(mint)

                # Optional: approximate LP via DexScreener
                lp_sol = 0.0
                dex: Optional[str] = None
                pair_addr: Optional[str] = None
                if http_session is None:
                    http_session = aiohttp.ClientSession()

                try:
                    lp_sol, dex, pair_addr = await _approx_pool_info(http_session, mint)
                except Exception:
                    lp_sol, dex, pair_addr = 0.0, None, None

                # Forward to target group (brief)
                if TARGET_GROUP:
                    try:
                        msg = f"Candidate mint: {mint}\nLP~ {lp_sol:.2f} SOL | DEX: {dex or '-'}"
                        await client.send_message(TARGET_GROUP, msg)
                    except Exception:
                        pass

                # Post to webhook if configured and LP meets threshold
                if WEBHOOK_URL and lp_sol >= MIN_LP_SOL:
                    try:
                        headers = {"Content-Type": "application/json"}
                        if WEBHOOK_SECRET:
                            headers["X-Webhook-Secret"] = WEBHOOK_SECRET
                        payload = {
                            "event_type": "userbot_candidate",
                            "token_mint": mint,
                            "lp_sol": lp_sol,
                            "pool_address": pair_addr,
                            "dex": dex,
                            "creator": None,
                            "ts": int(time.time()),
                        }
                        async with http_session.post(WEBHOOK_URL, data=json.dumps(payload), headers=headers, timeout=8) as resp:
                            _ = resp.status
                    except Exception:
                        pass
        except Exception:
            logging.exception("userbot handler error")

    async with client:
        logging.info("Userbot monitoring %d groups", len(MONITORED_GROUPS))
        await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(run_userbot())
    except KeyboardInterrupt:
        pass


