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
        
        # API rate limiting and caching
        self._api_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl_s: int = int(os.getenv("API_CACHE_TTL_S", "30"))  # 30s cache
        self._max_cache_size: int = int(os.getenv("MAX_CACHE_SIZE", "1000"))  # Prevent unbounded growth
        self._last_dex_call: float = 0.0
        self._last_gecko_call: float = 0.0
        self._dex_delay_s: float = float(os.getenv("DEX_DELAY_S", "0.5"))
        self._gecko_delay_s: float = float(os.getenv("GECKO_DELAY_S", "0.5"))

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
        # Prefer live data from DexScreener; fallback to GeckoTerminal. Do NOT use rough estimates.
        total_supply = float(data.get("total_supply") or 0.0)
        live_pair = await self._fetch_live_pair(mint)
        market_cap = None
        live_lp_sol = None
        mc_source = None
        if live_pair:
            market_cap = self._derive_market_cap_usd(live_pair, total_supply)
            # Liquidity in SOL (if priceUsd known)
            liq_usd = float(((live_pair.get("liquidity") or {}).get("usd") or 0.0))
            price_usd = float(live_pair.get("priceUsd") or 0.0)
            sol_price_env = float(os.getenv("SOL_PRICE_USD", "150"))
            denom = price_usd if price_usd > 0 else sol_price_env
            if denom > 0 and liq_usd > 0:
                live_lp_sol = liq_usd / denom
            if market_cap and market_cap > 0:
                mc_source = "DexScreener"
        if not market_cap:
            gecko = await self._fetch_gecko_token(mint)
            if gecko:
                market_cap = self._derive_mc_from_gecko(gecko, total_supply)
                # Liquidity USD → SOL if possible using priceUsd
                try:
                    liq_usd = float(gecko.get("reserve_in_usd") or 0.0)
                    price_usd = float(gecko.get("price_usd") or 0.0)
                    sol_price_env = float(os.getenv("SOL_PRICE_USD", "150"))
                    denom = price_usd if price_usd > 0 else sol_price_env
                    if denom > 0 and liq_usd > 0:
                        live_lp_sol = liq_usd / denom
                except Exception:
                    pass
                if market_cap and market_cap > 0:
                    mc_source = "GeckoTerminal"
        
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
        # Show full Contract Address (CA) in a copy-friendly code block
        mc_str = self._format_usd_short(market_cap) if market_cap else "N/A"
        ts_str = time.strftime("%H:%M:%S UTC", time.gmtime())
        source_suffix = f" ({mc_source}, {ts_str})" if mc_source else ""

        text = f"""{strength_emoji} <b>{signal_type}</b> {strength_emoji}

🎯 <b>${mint[:6]}...{mint[-4:]}</b>
🧾 CA: <code>{esc(mint)}</code>

💎 MC: {mc_str}{source_suffix}
💧 LP: {(live_lp_sol if live_lp_sol is not None else lp_sol):.1f} SOL  
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

    # ---------- Internals ----------
    async def _fetch_live_pair(self, mint: str) -> Optional[Dict[str, Any]]:
        """Fetch the highest-liquidity DexScreener pair for a mint with caching and rate limiting."""
        try:
            if not self._http:
                return None
            
            # Check cache first
            cache_key = f"dex_{mint}"
            now = time.time()
            if cache_key in self._api_cache:
                cached_data = self._api_cache[cache_key]
                if now - cached_data.get("timestamp", 0) < self._cache_ttl_s:
                    return cached_data.get("data")
            
            # Rate limiting
            if now - self._last_dex_call < self._dex_delay_s:
                await asyncio.sleep(self._dex_delay_s - (now - self._last_dex_call))
            self._last_dex_call = time.time()
            
            timeout = aiohttp.ClientTimeout(total=6)
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
            async with self._http.get(url, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
            pairs = (data or {}).get("pairs") or []
            best_pair: Optional[Dict[str, Any]] = None
            best_liq = 0.0
            for p in pairs:
                try:
                    liq = float(((p.get("liquidity") or {}).get("usd") or 0.0))
                    if liq > best_liq:
                        best_liq = liq
                        best_pair = p
                except Exception:
                    continue
            
            # Cache the result
        if best_pair:
            # Implement LRU cache eviction to prevent unbounded growth
            if len(self._api_cache) >= self._max_cache_size:
                # Remove oldest entries (simple FIFO)
                oldest_key = next(iter(self._api_cache))
                del self._api_cache[oldest_key]
            
            self._api_cache[cache_key] = {
                "data": best_pair,
                "timestamp": now
            }
            
            return best_pair
        except Exception as e:
            logging.debug("DexScreener API fetch failed: %s", e)
            return None

    async def _fetch_gecko_token(self, mint: str) -> Optional[Dict[str, Any]]:
        """Fetch token info from GeckoTerminal (Solana network) with caching and rate limiting."""
        try:
            if not self._http:
                return None
            
            # Check cache first
            cache_key = f"gecko_{mint}"
            now = time.time()
            if cache_key in self._api_cache:
                cached_data = self._api_cache[cache_key]
                if now - cached_data.get("timestamp", 0) < self._cache_ttl_s:
                    return cached_data.get("data")
            
            # Rate limiting
            if now - self._last_gecko_call < self._gecko_delay_s:
                await asyncio.sleep(self._gecko_delay_s - (now - self._last_gecko_call))
            self._last_gecko_call = time.time()
            
            timeout = aiohttp.ClientTimeout(total=6)
            url = f"https://api.geckoterminal.com/api/v2/networks/solana/tokens/{mint}"
            headers = {"accept": "application/json"}
            async with self._http.get(url, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
            # GeckoTerminal wraps data under data->attributes
            d = (data or {}).get("data") or {}
            attrs = d.get("attributes") or {}
            # Normalize fields - check multiple possible field names for liquidity
            out = {
                "price_usd": attrs.get("price_usd"),
                "fdv": attrs.get("fdv_usd") or attrs.get("fdv"),
                "market_cap": attrs.get("market_cap_usd") or attrs.get("market_cap"),
                "reserve_in_usd": (attrs.get("reserve_in_usd") or 
                                 attrs.get("liquidity_usd") or 
                                 attrs.get("liquidity") or
                                 attrs.get("reserve_usd") or
                                 attrs.get("pool_liquidity_usd")),
            }
            
            # Cache the result
            if out.get("price_usd") or out.get("market_cap"):
                self._api_cache[cache_key] = {
                    "data": out,
                    "timestamp": now
                }
            
            return out
        except Exception as e:
            logging.debug("GeckoTerminal API fetch failed: %s", e)
            return None

    def _derive_mc_from_gecko(self, gecko: Dict[str, Any], total_supply: float) -> Optional[float]:
        try:
            mc = gecko.get("market_cap") or gecko.get("fdv")
            if isinstance(mc, (int, float)) and mc > 0:
                return float(mc)
            price_usd = float(gecko.get("price_usd") or 0.0)
            if price_usd > 0 and total_supply > 0:
                return float(price_usd * total_supply)
            return None
        except Exception:
            return None

    def _derive_market_cap_usd(self, pair: Dict[str, Any], total_supply: float) -> Optional[float]:
        try:
            mc = pair.get("marketCap") or pair.get("fdv")
            if isinstance(mc, (int, float)) and mc > 0:
                return float(mc)
            price_usd = float(pair.get("priceUsd") or 0.0)
            if price_usd > 0 and total_supply > 0:
                return float(price_usd * total_supply)
            return None
        except Exception:
            return None

    def _format_usd_short(self, value: float) -> str:
        try:
            v = float(value)
            if v >= 1_000_000_000:
                return f"${v/1_000_000_000:.1f}B"
            if v >= 1_000_000:
                return f"${v/1_000_000:.0f}M"
            if v >= 1_000:
                return f"${v/1_000:.0f}K"
            return f"${v:.0f}"
        except Exception:
            return "$-"


__all__ = ["Publisher"]
