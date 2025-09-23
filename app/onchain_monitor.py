import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

from aiohttp import web


DEFAULT_MIN_LP_SOL: float = float(os.getenv("MIN_LP_SOL", "5"))
WEBHOOK_SECRET: Optional[str] = os.getenv("WEBHOOK_SECRET")
WEBHOOK_MAX_BYTES: int = int(os.getenv("WEBHOOK_MAX_BYTES", "32768"))


class OnchainMonitor:
    """Lightweight webhook server for ingesting on-chain event notifications.

    Exposes one POST endpoint `/webhook` that accepts JSON payloads for:
      - event_type: "token_mint" | "raydium_pool_created" | "orca_pool_created" | "lp_created"
      - token_mint: base58 mint address
      - lp_sol: optional float, LP depth in SOL (if present, used for early filtering)
      - pool_address, dex, creator, ts: optional metadata

    Qualified events (LP >= MIN_LP_SOL) are pushed into `queue` for downstream analysis.
    """

    def __init__(
        self,
        queue: "asyncio.Queue[Dict[str, Any]]",
        host: str = "0.0.0.0",
        port: int = int(os.getenv("WEBHOOK_PORT", "8080")),
        min_lp_sol: float = DEFAULT_MIN_LP_SOL,
    ) -> None:
        self.queue = queue
        self.host = host
        self.port = port
        self.min_lp_sol = float(min_lp_sol)
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    def _build_app(self) -> web.Application:
        app = web.Application(client_max_size=WEBHOOK_MAX_BYTES)
        app.add_routes(
            [
                web.get("/health", self._health),
                web.post("/webhook", self._webhook),
            ]
        )
        return app

    async def start(self) -> None:
        app = self._build_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        logging.info("OnchainMonitor listening on %s:%s", self.host, self.port)

    async def stop(self) -> None:
        if self._site is not None:
            await self._site.stop()
        if self._runner is not None:
            await self._runner.cleanup()
        logging.info("OnchainMonitor stopped")

    async def _health(self, _: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def _webhook(self, request: web.Request) -> web.Response:
        # Optional shared-secret authentication
        if WEBHOOK_SECRET:
            provided = request.headers.get("X-Webhook-Secret")
            if not provided or provided != WEBHOOK_SECRET:
                return web.json_response({"error": "unauthorized"}, status=401)

        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid json"}, status=400)

        event_type = (payload.get("event_type") or "").lower()
        token_mint = payload.get("token_mint")
        lp_sol = payload.get("lp_sol")

        if not token_mint:
            return web.json_response({"error": "token_mint required"}, status=400)

        # Early LP filter: only enqueue if LP >= threshold, when available
        qualifies = False
        if lp_sol is None:
            # If LP depth is unknown, we do not enqueue to avoid wasteful RPC calls
            qualifies = False
        else:
            try:
                qualifies = float(lp_sol) >= self.min_lp_sol
            except (TypeError, ValueError):
                qualifies = False

        if not qualifies:
            logging.debug(
                "Discarding event %s for %s due to insufficient or unknown LP: %s",
                event_type,
                token_mint,
                lp_sol,
            )
            return web.json_response({"queued": False, "reason": "lp_below_threshold"})

        context: Dict[str, Any] = {
            "event_type": event_type,
            "mint": token_mint,
            "lp_sol": float(lp_sol),
            "pool_address": payload.get("pool_address"),
            "dex": payload.get("dex"),
            "creator": payload.get("creator"),
            "ts": payload.get("ts"),
        }

        try:
            self.queue.put_nowait(context)
        except asyncio.QueueFull:
            logging.warning("Queue full, dropping token %s", token_mint)
            return web.json_response({"queued": False, "reason": "queue_full"}, status=503)

        logging.info(
            "Enqueued token %s (LP %.2f SOL) from %s",
            token_mint,
            float(lp_sol),
            event_type or "unknown",
        )
        return web.json_response({"queued": True})


__all__ = ["OnchainMonitor", "DEFAULT_MIN_LP_SOL"]


