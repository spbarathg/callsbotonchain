import asyncio
import json
import logging
import os
import hmac
import hashlib
import time
from typing import Any, Dict, List, Optional

from aiohttp import web
from base58 import b58decode  # type: ignore

from .metrics import metrics_collector


# .env is already loaded by app/__init__.py during module import

DEFAULT_MIN_LP_SOL: float = float(os.getenv("MIN_LP_SOL", "5"))
WEBHOOK_SECRET: Optional[str] = os.getenv("WEBHOOK_SECRET")
WEBHOOK_HMAC_SECRET: Optional[str] = os.getenv("WEBHOOK_HMAC_SECRET")
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
        host: str = os.getenv("WEBHOOK_HOST", "0.0.0.0"),
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
                web.get("/health/detailed", self._health_detailed),
                web.get("/metrics", self._metrics),
                web.get("/stats", self._stats),
                web.get("/signals", self._recent_signals),
                web.get("/tokens", self._recent_tokens),
                web.get("/test/{mint}", self._test_live_data),
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
        logging.info("🎯 Bot listening on %s:%s", self.host, self.port)

    async def stop(self) -> None:
        if self._site is not None:
            await self._site.stop()
        if self._runner is not None:
            await self._runner.cleanup()
        logging.info("🛑 Bot stopped")

    async def _health(self, _: web.Request) -> web.Response:
        """Basic health check endpoint."""
        return web.json_response({
            "status": "healthy",
            "timestamp": int(time.time()),
            "service": "callsbotonchain",
            "version": "1.0.0"
        })
    
    async def _health_detailed(self, _: web.Request) -> web.Response:
        """Detailed health check with system metrics."""
        try:
            health_data = await metrics_collector.get_health_status()
            return web.json_response(health_data)
        except Exception as e:
            logging.error("Health check failed: %s", e)
            return web.json_response({
                "status": "error",
                "error": str(e)
            }, status=500)
    
    async def _metrics(self, _: web.Request) -> web.Response:
        """Prometheus-style metrics endpoint."""
        try:
            health_data = await metrics_collector.get_health_status()
            
            # Format as Prometheus metrics
            metrics_text = []
            
            # Counters
            counters = health_data["counters"]
            metrics_text.extend([
                f"# HELP tokens_seen_total Total number of tokens seen",
                f"# TYPE tokens_seen_total counter",
                f"tokens_seen_total {counters['tokens_seen']}",
                "",
                f"# HELP tokens_processed_total Total number of tokens processed",
                f"# TYPE tokens_processed_total counter", 
                f"tokens_processed_total {counters['tokens_processed']}",
                "",
                f"# HELP signals_generated_total Total number of signals generated",
                f"# TYPE signals_generated_total counter",
                f"signals_generated_total {counters['signals_generated']}",
                "",
                f"# HELP errors_total Total number of errors",
                f"# TYPE errors_total counter",
                f"errors_total {counters['errors_count']}",
                ""
            ])
            
            # Gauges
            performance = health_data["performance"]
            rates = health_data["rates"]
            metrics_text.extend([
                f"# HELP processing_time_avg_ms Average processing time in milliseconds",
                f"# TYPE processing_time_avg_ms gauge",
                f"processing_time_avg_ms {performance['avg_processing_time_ms']}",
                "",
                f"# HELP queue_size_current Current queue size",
                f"# TYPE queue_size_current gauge",
                f"queue_size_current {performance['queue_size_current']}",
                "",
                f"# HELP signal_rate_percent Signal generation rate percentage",
                f"# TYPE signal_rate_percent gauge",
                f"signal_rate_percent {rates['signal_rate_percent']}",
                "",
                f"# HELP tokens_per_hour Current tokens processed per hour",
                f"# TYPE tokens_per_hour gauge",
                f"tokens_per_hour {rates['tokens_per_hour']}",
                ""
            ])
            
            return web.Response(text="\n".join(metrics_text), content_type="text/plain")
            
        except Exception as e:
            logging.error("Metrics endpoint failed: %s", e)
            return web.json_response({"error": str(e)}, status=500)
    
    async def _stats(self, request: web.Request) -> web.Response:
        """Statistics endpoint with query parameters."""
        try:
            # Get query parameters
            hours = int(request.query.get("hours", "24"))
            hours = min(max(hours, 1), 168)  # Limit to 1-168 hours (1 week)
            
            health_data = await metrics_collector.get_health_status()
            hourly_stats = await metrics_collector.get_hourly_stats(hours)
            
            return web.json_response({
                "summary": health_data,
                "hourly_breakdown": hourly_stats,
                "query_params": {"hours": hours}
            })
            
        except Exception as e:
            logging.error("Stats endpoint failed: %s", e)
            return web.json_response({"error": str(e)}, status=500)
    
    async def _recent_signals(self, request: web.Request) -> web.Response:
        """Recent signals endpoint."""
        try:
            limit = int(request.query.get("limit", "20"))
            limit = min(max(limit, 1), 100)  # Limit to 1-100
            
            signals = await metrics_collector.get_recent_signals(limit)
            
            return web.json_response({
                "signals": signals,
                "count": len(signals),
                "limit": limit
            })
            
        except Exception as e:
            logging.error("Recent signals endpoint failed: %s", e)
            return web.json_response({"error": str(e)}, status=500)
    
    async def _recent_tokens(self, request: web.Request) -> web.Response:
        """Recent processed tokens endpoint."""
        try:
            limit = int(request.query.get("limit", "50"))
            limit = min(max(limit, 1), 200)  # Limit to 1-200
            
            tokens = await metrics_collector.get_recent_tokens(limit)
            
            return web.json_response({
                "tokens": tokens,
                "count": len(tokens),
                "limit": limit
            })
            
        except Exception as e:
            logging.error("Recent tokens endpoint failed: %s", e)
            return web.json_response({"error": str(e)}, status=500)

    async def _test_live_data(self, request: web.Request) -> web.Response:
        """Test endpoint to verify live data fetching for a given mint."""
        try:
            mint = request.match_info["mint"]
            
            # Basic validation
            if not mint or len(mint) < 32:
                return web.json_response({"error": "Invalid mint address"}, status=400)
            
            # Import here to avoid circular imports
            from .publisher import Publisher
            
            # Create a temporary publisher instance for testing
            publisher = Publisher()
            await publisher.start()
            
            try:
                # Test DexScreener
                dex_pair = await publisher._fetch_live_pair(mint)
                dex_data = {}
                if dex_pair:
                    dex_data = {
                        "price_usd": dex_pair.get("priceUsd"),
                        "market_cap": dex_pair.get("marketCap"),
                        "fdv": dex_pair.get("fdv"),
                        "liquidity_usd": dex_pair.get("liquidity", {}).get("usd"),
                        "source": "DexScreener"
                    }
                
                # Test GeckoTerminal
                gecko_data = await publisher._fetch_gecko_token(mint)
                gecko_result = {}
                if gecko_data:
                    gecko_result = {
                        "price_usd": gecko_data.get("price_usd"),
                        "market_cap": gecko_data.get("market_cap"),
                        "fdv": gecko_data.get("fdv"),
                        "liquidity_usd": gecko_data.get("reserve_in_usd"),
                        "source": "GeckoTerminal"
                    }
                
                return web.json_response({
                    "mint": mint,
                    "timestamp": int(time.time()),
                    "dex_data": dex_data,
                    "gecko_data": gecko_result,
                    "status": "success"
                })
                
            finally:
                await publisher.stop()
                
        except Exception as e:
            logging.error("Test live data endpoint failed: %s", e)
            return web.json_response({"error": str(e)}, status=500)

    async def _webhook(self, request: web.Request) -> web.Response:
        # Enhanced webhook processing for Helius Pro
        user_agent = request.headers.get("User-Agent", "")
        content_type = request.headers.get("Content-Type", "")
        content_length = request.headers.get("Content-Length", "0")
        helius_signature = request.headers.get("Helius-Signature", "")
        
        # Verify this is from Helius Pro service
        if "helius" not in user_agent.lower():
            logging.warning("⚠️  Non-Helius webhook from: %s", user_agent)
        
        # Optional HMAC or shared-secret authentication
        if WEBHOOK_HMAC_SECRET:
            raw_body = await request.read()
            sig = request.headers.get("X-Signature", "")
            try:
                digest = hmac.new(WEBHOOK_HMAC_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
                expected = f"sha256={digest}"
                if sig != expected:
                    return web.json_response({"error": "unauthorized"}, status=401)
            except Exception:
                return web.json_response({"error": "unauthorized"}, status=401)
            # parse JSON from the raw body we already read
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except Exception:
                return web.json_response({"error": "invalid json"}, status=400)
        else:
            # Fallback: shared secret header
            if WEBHOOK_SECRET:
                provided = request.headers.get("X-Webhook-Secret")
                if not provided or provided != WEBHOOK_SECRET:
                    return web.json_response({"error": "unauthorized"}, status=401)
            try:
                payload = await request.json()
            except json.JSONDecodeError:
                return web.json_response({"error": "invalid json"}, status=400)

        # Handle Helius Pro enhanced payloads (batch events)
        events_to_process = []
        if isinstance(payload, list):
            # Helius Pro batch: array of enhanced events
            events_to_process = payload
            logging.debug("📦 Helius Pro batch: %d events", len(payload))
        elif isinstance(payload, dict):
            # Single enhanced event
            events_to_process = [payload]
            logging.debug("📦 Helius Pro single event")
        else:
            return web.json_response({"error": "payload must be dict or list"}, status=400)

        candidates: List[Dict[str, Any]] = []
        
        for event in events_to_process:
            event_type = (str(event.get("event_type")) or "").lower()
            token_mint = event.get("token_mint")
            lp_sol = event.get("lp_sol")
            
            # If direct fields are present, use them
            if token_mint:
                candidates.append({
                    "token_mint": token_mint,
                    "lp_sol": lp_sol,
                    "creator": event.get("creator")
                })
                continue
            
            # If event looks like a Helius Enhanced event, try to extract candidates
            if event.get("type") or event.get("events"):
                # Helius Enhanced: try common places
                try:
                    # Token transfers explicitly include mint pubkeys
                    for b in (event.get("tokenTransfers") or []):
                        m = b.get("mint")
                        if m:
                            candidates.append({"token_mint": m})
                    # Program-specific events may expose mint fields
                    for b in (event.get("events") or []):
                        if isinstance(b, dict):
                            for k in ("mint", "token", "tokenAccount"):
                                if k in b and b[k]:
                                    candidates.append({"token_mint": b[k]})
                                    break
                except Exception as e:
                    logging.warning("Helius extractor failed: %s", e)

        # Candidates are now collected from all events

        # De-duplicate mints in this request
        seen: set = set()
        out_contexts: List[Dict[str, Any]] = []
        for cand in candidates:
            m = cand.get("token_mint")
            if not m or not isinstance(m, str):
                continue
            if m in seen:
                continue
            # Basic base58/length validation
            try:
                raw = b58decode(m)
                if len(raw) != 32:
                    continue
            except Exception:
                continue
            seen.add(m)
            out_contexts.append({
                "event_type": "helius",
                "mint": m,
                "lp_sol": (float(cand.get("lp_sol")) if cand.get("lp_sol") is not None else None),
                "pool_address": cand.get("pool_address"),
                "dex": cand.get("dex"),
                "creator": cand.get("creator"),
                "ts": cand.get("ts") or int(time.time()),
            })

        # If no candidates after extraction, enforce original requirements
        if not out_contexts:
            return web.json_response({"error": "token_mint required"}, status=400)

        # Enqueue each candidate (unknown LP allowed)
        queued = 0
        for ctx in out_contexts:
            lp = ctx.get("lp_sol")
            # Only skip when explicit lp is provided and below threshold; unknown allowed
            if lp is not None:
                try:
                    if float(lp) < self.min_lp_sol:
                        logging.debug("Discarding %s due to LP %.2f < threshold", ctx.get("mint"), float(lp))
                        continue
                except Exception:
                    pass
            try:
                self.queue.put_nowait(ctx)
                queued += 1
                # Record metrics for each token seen
                await metrics_collector.record_token_seen("webhook")
            except asyncio.QueueFull:
                logging.warning("Queue full, dropping token %s", ctx.get("mint"))
                await metrics_collector.record_error("queue_full", f"Queue full for token {ctx.get('mint')}")

        # Update queue size metrics
        await metrics_collector.record_queue_size(self.queue.qsize())

        return web.json_response({"queued": bool(queued), "count": queued})


__all__ = ["OnchainMonitor", "DEFAULT_MIN_LP_SOL"]


