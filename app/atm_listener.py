"""
ATM Signal Listener

Listens to specified Telegram channels (ATM family) via Telethon, parses
token mint addresses, and feeds them into the existing SignalProcessor.
"""

import asyncio
import os
import re
import time
import shutil
from typing import Any, Dict, List, Set

from app.config_unified import (
    ATM_TELETHON_API_ID,
    ATM_TELETHON_API_HASH,
    ATM_TELETHON_SESSION_FILE,
    ATM_CHANNEL_IDS,
    ATM_INGEST_ENABLED,
    ATM_DEFAULT_USD_VALUE,
    ATM_RATE_LIMIT_PER_MIN,
)
from app.logger_utils import log_process, log_atm_message, log_atm_signal, log_error
from app.toggles import signals_enabled
from app.storage import has_been_alerted

# Telethon import (soft error if missing)
try:
    from telethon import TelegramClient, events  # type: ignore
except Exception as e:  # pragma: no cover - import guard
    raise RuntimeError("Telethon is required for ATM ingestion") from e

# Rough base58 pattern for Solana mints (32-44 chars)
_SOLANA_CA_RE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")
_SOL_MINT = "So11111111111111111111111111111111111111112"

_MONEY_RE = re.compile(r"\$?\s*([0-9]+(?:\.[0-9]+)?)\s*([kKmMbB]?)")
_PCT_RE = re.compile(r"(-?[0-9]+(?:\.[0-9]+)?)%")


def _parse_money(value: str) -> float:
    if not value:
        return 0.0
    match = _MONEY_RE.search(value.replace(",", ""))
    if not match:
        return 0.0
    amount = float(match.group(1))
    suffix = match.group(2).lower()
    if suffix == "k":
        return amount * 1_000
    if suffix == "m":
        return amount * 1_000_000
    if suffix == "b":
        return amount * 1_000_000_000
    return amount


def _parse_pct(value: str) -> float:
    if not value:
        return 0.0
    match = _PCT_RE.search(value.replace(",", ""))
    if not match:
        return 0.0
    return float(match.group(1))


def _parse_atm_advanced_info(text: str) -> Dict[str, Any]:
    """
    Parse structured metrics from ATM advanced info blocks.
    Returns a dict with any extracted fields.
    """
    out: Dict[str, Any] = {}
    if not text:
        return out

    # Basic fields
    price_match = re.search(r"Price:\s*\$?([0-9.,]+[kKmMbB]?)", text)
    mcap_match = re.search(r"Market Cap:\s*\$?([0-9.,]+[kKmMbB]?)", text)
    holders_match = re.search(r"Holders:\s*([0-9,]+)", text)
    top10_match = re.search(r"Top10:\s*([0-9.]+)%", text)

    if price_match:
        out["price_usd"] = _parse_money(price_match.group(1))
    if mcap_match:
        out["market_cap_usd"] = _parse_money(mcap_match.group(1))
    if holders_match:
        try:
            out["holder_count"] = int(holders_match.group(1).replace(",", ""))
        except Exception:
            pass
    if top10_match:
        try:
            out["top10_percent"] = float(top10_match.group(1))
        except Exception:
            pass

    # Volume trends
    vol_section = re.search(r"Volume trends:(.*?)(Price Change Trends:|Holders analytics:|Pro-traders activity|Audit:)", text, re.DOTALL)
    if vol_section:
        vol_text = vol_section.group(1)
        def _extract_block(label: str) -> Dict[str, float]:
            block = {}
            match = re.search(rf"{label}\s*(.*?)(🟢|🔴|Price Change Trends:|Holders analytics:|Pro-traders activity|Audit:|$)", vol_text, re.DOTALL)
            if not match:
                return block
            for line in match.group(1).splitlines():
                if "5m" in line:
                    block["5m"] = _parse_money(line)
                elif "1h" in line:
                    block["1h"] = _parse_money(line)
                elif "6h" in line:
                    block["6h"] = _parse_money(line)
                elif "24h" in line:
                    block["24h"] = _parse_money(line)
            return block
        buy = _extract_block("🟢Buy")
        sell = _extract_block("🔴Sell")
        if buy:
            out["volume_buy"] = buy
        if sell:
            out["volume_sell"] = sell

    # Price change trends
    change_section = re.search(r"Price Change Trends:(.*?)(Holders analytics:|Pro-traders activity|Audit:)", text, re.DOTALL)
    if change_section:
        change_text = change_section.group(1)
        change: Dict[str, float] = {}
        for line in change_text.splitlines():
            if "5m" in line:
                change["5m"] = _parse_pct(line)
            elif "1h" in line:
                change["1h"] = _parse_pct(line)
            elif "6h" in line:
                change["6h"] = _parse_pct(line)
            elif "24h" in line:
                change["24h"] = _parse_pct(line)
        if change:
            out["price_change"] = change

    # Holder analytics
    holders_section = re.search(r"Holders analytics:(.*?)(Pro-traders activity|Audit:)", text, re.DOTALL)
    if holders_section:
        holders_text = holders_section.group(1)
        ha: Dict[str, float] = {}
        for line in holders_text.splitlines():
            if "top10" in line:
                ha["top10_percent"] = _parse_pct(line)
            elif "top50" in line:
                ha["top50_percent"] = _parse_pct(line)
            elif "top100" in line:
                ha["top100_percent"] = _parse_pct(line)
        if ha:
            out["holders_analytics"] = ha

    # Pro-traders activity
    pro_section = re.search(r"Pro-traders activity(.*?)(Audit:|$)", text, re.DOTALL)
    if pro_section:
        pro_text = pro_section.group(1)
        pro: Dict[str, Any] = {}
        wallets = re.search(r"(\d+)\s*/\s*(\d+)\s*wallets", pro_text)
        if wallets:
            pro["wallets_in"] = int(wallets.group(1))
            pro["wallets_out"] = int(wallets.group(2))
        volume = re.search(r"([0-9.,]+)\s*/\s*volume", pro_text)
        if volume:
            pro["volume_in_out"] = _parse_money(volume.group(1))
        avg_price = re.search(r"([0-9.]+)\s*/\s*avg\.\s*buy/sell price", pro_text)
        if avg_price:
            try:
                pro["avg_buy_sell_price"] = float(avg_price.group(1))
            except Exception:
                pass
        if pro:
            out["pro_traders"] = pro

    # Audit flags
    audit_section = re.search(r"Audit:(.*?)(🧠|Trade on|$)", text, re.DOTALL)
    if audit_section:
        audit_text = audit_section.group(1)
        out["audit"] = {
            "not_mintable": "Not Mintable" in audit_text,
            "not_freezable": "Not Freezable" in audit_text,
            "dex_not_paid": "Dex not paid" in audit_text,
        }

    return out


def _extract_contracts(text: str) -> List[str]:
    """Extract candidate Solana contract addresses from text."""
    if not text:
        return []
    candidates = _SOLANA_CA_RE.findall(text)
    # Deduplicate while preserving order
    seen: Set[str] = set()
    ordered = []
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        ordered.append(c)
    return ordered


def _safe_for_console(text: str) -> str:
    """Make text safe for Windows consoles (avoid UnicodeEncodeError)."""
    if not text:
        return ""
    return text.encode("ascii", "backslashreplace").decode("ascii")


class ATMListener:
    def __init__(self, processor):
        self.processor = processor
        self.channel_ids = ATM_CHANNEL_IDS or []
        self.allowed_channel_ids = set()
        for cid in self.channel_ids:
            try:
                self.allowed_channel_ids.add(self._normalize_channel_id(int(str(cid).strip())))
            except Exception:
                continue
        self.enabled = ATM_INGEST_ENABLED
        self.default_usd = max(100, int(ATM_DEFAULT_USD_VALUE or 0))
        self.rate_limit = max(10, int(ATM_RATE_LIMIT_PER_MIN or 0))
        self._per_channel_window: Dict[int, List[float]] = {}
        self._dedup_recent: Set[str] = set()
        self._debug_messages = os.getenv("ATM_DEBUG_MESSAGES", "false").strip().lower() == "true"
        self._listen_all = os.getenv("ATM_LISTEN_ALL", "true").strip().lower() == "true"

        if not self.enabled:
            print("[ATM] Ingestion disabled via ATM_INGEST_ENABLED=false")
        if not self.channel_ids:
            print("[ATM] No ATM_CHANNEL_IDS configured; listener will idle")

    def _normalize_channel_id(self, channel_id: int) -> int:
        """
        Normalize Telegram channel IDs so we match allowed IDs.
        Telegram often emits -100<channel_id> for channels.
        """
        try:
            cid = int(channel_id)
        except Exception:
            return channel_id
        if cid < 0:
            s = str(abs(cid))
            if s.startswith("100"):
                try:
                    return int(s[3:])
                except Exception:
                    return cid
        return cid

    def _prepare_session_file(self) -> str:
        session_path = ATM_TELETHON_SESSION_FILE
        os.makedirs(os.path.dirname(session_path), exist_ok=True)
        if not os.path.exists(session_path):
            return session_path
        if os.getenv("ATM_SESSION_CLONE", "true").strip().lower() != "true":
            return session_path
        base, ext = os.path.splitext(session_path)
        clone_path = f"{base}.clone.{os.getpid()}{ext or '.session'}"
        try:
            shutil.copy2(session_path, clone_path)
        except Exception:
            return session_path
        return clone_path

    async def start(self):
        if not self.enabled:
            return
        if not ATM_TELETHON_API_ID or not ATM_TELETHON_API_HASH:
            raise RuntimeError("ATM Telethon credentials not configured (ATM_TELETHON_API_ID/ATM_TELETHON_API_HASH)")

        session_file = self._prepare_session_file()
        self.client = TelegramClient(session_file, ATM_TELETHON_API_ID, ATM_TELETHON_API_HASH)

        if self._listen_all:
            @self.client.on(events.NewMessage())
            async def handler(event):
                await self._handle_message(event)
        else:
            @self.client.on(events.NewMessage(chats=self.channel_ids or None))
            async def handler(event):
                await self._handle_message(event)

        print(f"[ATM] Starting listener on {len(self.channel_ids)} channel(s)")
        await self.client.start()
        await self.client.run_until_disconnected()

    def _within_rate_limit(self, channel_id: int) -> bool:
        now = time.time()
        window = self._per_channel_window.setdefault(channel_id, [])
        # prune older than 60s
        self._per_channel_window[channel_id] = [t for t in window if now - t < 60]
        if len(self._per_channel_window[channel_id]) >= self.rate_limit:
            return False
        self._per_channel_window[channel_id].append(now)
        return True

    async def _handle_message(self, event):
        if not self.enabled:
            return
        if os.getenv("KILL_SWITCH", "false").strip().lower() == "true":
            return
        if not signals_enabled():
            return

        channel_id = None
        try:
            channel_id = event.chat_id
        except Exception:
            channel_id = None
        if channel_id is None and event.chat:
            channel_id = getattr(event.chat, "id", None)
        if channel_id is None and getattr(event, "message", None):
            peer = getattr(event.message, "peer_id", None)
            if peer is not None:
                if hasattr(peer, "channel_id"):
                    channel_id = int(peer.channel_id)
                elif hasattr(peer, "chat_id"):
                    channel_id = int(peer.chat_id)
        message_id = getattr(event.message, "id", None)
        text = event.raw_text or ""
        snippet = " ".join((text or "").split())[:160]
        if self._debug_messages:
            safe_snippet = _safe_for_console(snippet)
            print(
                f"[ATM] Debug message: channel_id={channel_id} message_id={message_id} text={safe_snippet!r}",
                flush=True,
            )

        if channel_id is None:
            return
        normalized_id = self._normalize_channel_id(int(channel_id))
        if self._debug_messages or (not self.allowed_channel_ids or normalized_id in self.allowed_channel_ids):
            try:
                log_atm_message({
                    "type": "atm_message",
                    "channel_id": channel_id,
                    "normalized_channel_id": normalized_id,
                    "message_id": message_id,
                    "text_snippet": snippet,
                    "text_len": len(text or ""),
                })
            except Exception:
                pass
        if self.allowed_channel_ids and normalized_id not in self.allowed_channel_ids:
            if self._debug_messages:
                print(f"[ATM] Debug skip: channel_id={channel_id} normalized={normalized_id} not in allowed list", flush=True)
            return
        if not self._within_rate_limit(int(channel_id)):
            return

        cas = _extract_contracts(text)
        if not cas:
            return
        atm_meta = _parse_atm_advanced_info(text)

        for ca in cas:
            print(f"[ATM] Signal received: channel_id={channel_id} message_id={message_id} token={ca}", flush=True)
            try:
                log_atm_signal({
                    "type": "atm_signal_detected",
                    "channel_id": channel_id,
                    "normalized_channel_id": normalized_id,
                    "message_id": message_id,
                    "token": ca,
                    "atm_meta": atm_meta or None,
                })
            except Exception:
                pass
            dedup_key = f"{channel_id}:{ca}"
            if dedup_key in self._dedup_recent:
                continue
            self._dedup_recent.add(dedup_key)
            if len(self._dedup_recent) > 5000:
                # keep memory bounded
                self._dedup_recent.pop()

            # Skip already alerted tokens
            try:
                if has_been_alerted(ca):
                    continue
            except Exception:
                pass

            tx = {
                "token0_address": _SOL_MINT,
                "token1_address": ca,
                "token0_amount_usd": 0,
                "token1_amount_usd": self.default_usd,
                "usd_value": self.default_usd,
                "dex": "atm",
                "tx_type": "atm_signal",
                "is_synthetic": True,
                "channel_id": channel_id,
                "message_id": message_id,
                "source": "atm",
                "atm_meta": atm_meta,
            }

            try:
                result = self.processor.process_feed_item(tx, is_smart_cycle=False)
                try:
                    log_process({
                        "type": "atm_signal_processed",
                        "channel_id": channel_id,
                        "message_id": message_id,
                        "token": ca,
                        "status": result.status,
                        "error": result.error_message,
                        "prelim": result.preliminary_score,
                        "final": result.final_score,
                    })
                except Exception:
                    pass
            except Exception as e:
                try:
                    log_process({
                        "type": "atm_signal_error",
                        "channel_id": channel_id,
                        "message_id": message_id,
                        "token": ca,
                        "error": str(e),
                    })
                except Exception:
                    pass
                try:
                    log_error({
                        "type": "atm_signal_error",
                        "channel_id": channel_id,
                        "normalized_channel_id": normalized_id,
                        "message_id": message_id,
                        "token": ca,
                        "error": str(e),
                    })
                except Exception:
                    pass
                continue


async def run_atm_listener():
    from app.signal_processor import SignalProcessor
    from app.storage import init_db

    if not ATM_INGEST_ENABLED:
        print("[ATM] Ingestion disabled; exiting.")
        return

    init_db()
    processor = SignalProcessor({})
    listener = ATMListener(processor)
    await listener.start()


def main():
    asyncio.run(run_atm_listener())


if __name__ == "__main__":
    main()


