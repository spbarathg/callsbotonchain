import json
import logging
import os
import time
from typing import Any, Dict, Optional
import html

import aiohttp

import aiosqlite

try:
    from redis import asyncio as aioredis  # type: ignore
except Exception:  # pragma: no cover
    aioredis = None  # type: ignore

from .metrics import metrics_collector


class Publisher:
    """Publishes high-confidence signals to Redis and/or SQLite."""

    def __init__(
        self,
        redis_url: Optional[str] = os.getenv("REDIS_URL"),
        sqlite_path: Optional[str] = os.getenv("SQLITE_PATH", "signals.db"),
    ) -> None:
        self.redis_url = redis_url
        self.sqlite_path = sqlite_path
        self._redis: Optional[Any] = None
        self._sqlite: Optional[aiosqlite.Connection] = None
        # Telegram
        self._tg_token: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
        self._tg_chat_id: Optional[str] = os.getenv("TELEGRAM_CHAT_ID")
        self._http: Optional[aiohttp.ClientSession] = None
        # In-process publish dedup (TTL seconds)
        self._dedup_ttl_s: int = int(os.getenv("PUBLISH_DEDUP_TTL_S", "600"))
        self._recent: Dict[str, int] = {}

    async def start(self) -> None:
        # HTTP session for Telegram if configured
        if self._tg_token and self._tg_chat_id:
            try:
                timeout = aiohttp.ClientTimeout(total=6)
                self._http = aiohttp.ClientSession(timeout=timeout)
            except Exception as e:
                logging.warning("HTTP session init failed: %s", e)
                self._http = None

        if aioredis and self.redis_url:
            try:
                self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
                await self._redis.ping()
                await metrics_collector.record_api_health("redis", "healthy")
                logging.info("Connected to Redis")
            except Exception as e:
                logging.warning("Redis unavailable: %s", e)
                await metrics_collector.record_api_health("redis", "error", error=True)
                self._redis = None

        if self.sqlite_path:
            self._sqlite = await aiosqlite.connect(self.sqlite_path)
            await self._sqlite.execute(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    mint TEXT NOT NULL,
                    score REAL NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            await self._sqlite.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_signals_mint_ts ON signals(mint, ts);
                """
            )
            await self._sqlite.commit()
            logging.info("SQLite ready at %s", self.sqlite_path)

    async def stop(self) -> None:
        if self._http is not None:
            try:
                await self._http.close()
            except Exception:
                pass
        if self._redis is not None:
            try:
                await self._redis.close()
                # Some redis.asyncio versions benefit from explicit pool disconnect
                pool = getattr(self._redis, "connection_pool", None)
                if pool is not None:
                    try:
                        await pool.disconnect()
                    except Exception:
                        pass
            except Exception:
                pass
        if self._sqlite is not None:
            try:
                await self._sqlite.close()
            except Exception:
                pass

    async def publish(self, data: Dict[str, Any]) -> None:
        """Publish a signal to configured sinks."""
        ts = int(time.time())
        data_with_ts = {**data, "published_ts": ts}
        payload_str = json.dumps(data_with_ts, separators=(",", ":"))

        # Dedup by mint within TTL window
        mint_key = str(data.get("mint"))
        # cleanup
        try:
            expired = [m for m, until in self._recent.items() if until <= ts]
            for m in expired:
                del self._recent[m]
        except Exception:
            self._recent = {}
        if mint_key in self._recent:
            logging.info("SKIP publish %s: recent duplicate", mint_key)
            return
        self._recent[mint_key] = ts + self._dedup_ttl_s

        # Redis
        if self._redis is not None:
            try:
                await self._redis.rpush("signals:memecoins", payload_str)
                await metrics_collector.record_api_health("redis", "healthy")
            except Exception as e:
                logging.debug("Redis publish failed: %s", e)
                await metrics_collector.record_api_health("redis", "error", error=True)

        # SQLite
        if self._sqlite is not None:
            try:
                await self._sqlite.execute(
                    "INSERT INTO signals (ts, mint, score, payload) VALUES (?, ?, ?, ?)",
                    (ts, str(data.get("mint")), float(data.get("score") or 0.0), payload_str),
                )
                await self._sqlite.commit()
            except Exception as e:
                logging.debug("SQLite publish failed: %s", e)

        # Console
        logging.info("SIGNAL %s score=%.2f", data.get("mint"), float(data.get("score") or 0.0))

        # Telegram (best-effort)
        try:
            await self.publish_telegram(data_with_ts)
        except Exception as e:
            logging.debug("Telegram publish failed: %s", e)

    async def publish_telegram(self, data: Dict[str, Any]) -> None:
        """Publish a formatted message to Telegram if configured."""
        if not (self._tg_token and self._tg_chat_id and self._http):
            return

        mint = str(data.get("mint"))
        score = float(data.get("score") or 0.0)
        lp_sol = float(data.get("lp_sol") or 0.0)
        top1 = float(data.get("top1_pct") or 0.0)
        momentum = int(data.get("momentum_score") or 0)
        market_cap = lp_sol * 2 * 150  # Rough MC estimate (2x LP * SOL price)
        
        # Determine signal strength emoji
        if score >= 9:
            strength_emoji = "🔥🔥🔥"  # Ultra strong
            signal_type = "MEGA PLAY"
        elif score >= 8:
            strength_emoji = "🔥🔥"    # Very strong  
            signal_type = "STRONG"
        elif score >= 7.5:
            strength_emoji = "🔥"      # Strong
            signal_type = "SOLID"
        elif score >= 6.5:
            strength_emoji = "⚡"      # Good
            signal_type = "GOOD"
        else:
            strength_emoji = "💎"      # Decent
            signal_type = "PLAY"

        esc = html.escape
        
        # Minimalistic format inspired by reference
        text = f"""{strength_emoji} <b>{signal_type}</b> {strength_emoji}

🎯 <b>${mint[:6]}...{mint[-4:]}</b>

💎 MC: ${market_cap/1000:.0f}K
💧 LP: {lp_sol:.1f} SOL  
📊 Score: <b>{score:.1f}/10</b>
⚡ Mom: {momentum}  •  🏛️ Top1: {top1*100:.0f}%

🔗 <a href="https://dexscreener.com/solana/{esc(mint)}">Chart</a> | <a href="https://solscan.io/token/{esc(mint)}">Scan</a>"""
        url = f"https://api.telegram.org/bot{self._tg_token}/sendMessage"
        payload = {
            "chat_id": self._tg_chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            async with self._http.post(url, json=payload) as resp:
                if resp.status != 200:
                    logging.debug("Telegram http %s", resp.status)
                    await metrics_collector.record_api_health("telegram", "error", error=True)
                else:
                    await metrics_collector.record_api_health("telegram", "healthy")
        except Exception as e:
            logging.debug("Telegram request error: %s", e)
            await metrics_collector.record_api_health("telegram", "error", error=True)


__all__ = ["Publisher"]


