import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Set

import aiohttp
from aiohttp import web

from .metrics import metrics_collector


class OnchainMonitor:
    """Webhook server to receive and process on-chain events from Helius."""
    
    def __init__(self, queue: asyncio.Queue, host: str = "0.0.0.0", port: int = 8080):
        self.queue = queue
        self.host = host
        self.port = port
        self.app = None
        self.runner = None
        self.site = None
        self._seen_mints = {}  # Changed to dict for TTL tracking: {mint: timestamp}
        
        # Webhook security
        self.webhook_secret = os.getenv("WEBHOOK_SECRET")
        self.webhook_hmac_secret = os.getenv("WEBHOOK_HMAC_SECRET")
        self.max_payload_bytes = int(os.getenv("WEBHOOK_MAX_BYTES", "32768"))
        
        # Rate limiting
        self._request_times: List[float] = []
        self.max_requests_per_minute = 100
        
        # Deduplication TTL (24 hours)
        self._dedup_ttl_hours = 24
        # Max payload size to prevent DoS
        self._max_payload_size = int(os.getenv("MAX_PAYLOAD_SIZE", "1048576"))  # 1MB default
        
    async def start(self) -> None:
        """Start the webhook server."""
        self.app = web.Application()
        self.app.router.add_post("/webhook", self._handle_webhook)
        self.app.router.add_get("/health", self._handle_health)
        self.app.router.add_get("/metrics", self._handle_metrics)
        self.app.router.add_get("/test/{mint}", self._handle_test)
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        
        # Track start time for uptime calculation
        self._start_time = time.time()
        
        logging.info("🚀 Webhook server started on %s:%d", self.host, self.port)
        
    async def stop(self) -> None:
        """Stop the webhook server."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        logging.info("🛑 Webhook server stopped")
        
    def _verify_webhook_auth(self, request: web.Request) -> bool:
        """Verify webhook authentication if configured."""
        if not self.webhook_secret:
            return True  # No auth required
            
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return False
            
        expected = f"Bearer {self.webhook_secret}"
        return auth_header == expected
        
    def _verify_webhook_signature(self, body: bytes, headers: Dict[str, str]) -> bool:
        """Verify webhook HMAC signature if configured."""
        if not self.webhook_hmac_secret:
            return True  # No signature verification required
            
        signature = headers.get("X-Signature") or headers.get("Helius-Signature")
        if not signature:
            return False
            
        import hmac
        import hashlib
        
        expected = hmac.new(
            self.webhook_hmac_secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected)
        
    def _is_rate_limited(self) -> bool:
        """Check if we're being rate limited."""
        now = time.time()
        # Remove requests older than 1 minute
        self._request_times = [t for t in self._request_times if now - t < 60]
        
        if len(self._request_times) >= self.max_requests_per_minute:
            return True
            
        self._request_times.append(now)
        return False
        
    def _cleanup_old_mints(self) -> None:
        """Remove old mints from deduplication cache to prevent memory growth."""
        now = time.time()
        cutoff = now - (self._dedup_ttl_hours * 3600)
        
        # Remove mints older than TTL
        expired_mints = [mint for mint, timestamp in self._seen_mints.items() if timestamp < cutoff]
        for mint in expired_mints:
            del self._seen_mints[mint]
        
    async def _handle_webhook(self, request: web.Request) -> web.Response:
        """Handle incoming webhook events."""
        try:
            # Rate limiting
            if self._is_rate_limited():
                await metrics_collector.record_error("rate_limit", "Too many requests")
                return web.Response(status=429, text="Rate limited")
                
            # Check payload size
            content_length = request.headers.get("Content-Length", "0")
            if int(content_length) > self._max_payload_size:
                await metrics_collector.record_error("payload_too_large", f"Size: {content_length}")
                return web.Response(status=413, text="Payload too large")
                
            # Read body
            body = await request.read()
            if len(body) > self._max_payload_size:
                await metrics_collector.record_error("payload_too_large", f"Size: {len(body)}")
                return web.Response(status=413, text="Payload too large")
                
            # Verify authentication
            if not self._verify_webhook_auth(request):
                await metrics_collector.record_error("auth_failed", "Invalid auth")
                return web.Response(status=401, text="Unauthorized")
                
            # Verify signature
            if not self._verify_webhook_signature(body, dict(request.headers)):
                await metrics_collector.record_error("signature_failed", "Invalid signature")
                return web.Response(status=401, text="Invalid signature")
                
            # Parse JSON
            try:
                import json
                payload = json.loads(body)
            except json.JSONDecodeError as e:
                await metrics_collector.record_error("json_parse_error", str(e))
                return web.Response(status=400, text="Invalid JSON")
                
            # Cleanup old mints periodically (every 100 requests)
            if len(self._seen_mints) > 0 and len(self._seen_mints) % 100 == 0:
                self._cleanup_old_mints()
                
            # Process events
            events = self._extract_events(payload)
            if not events:
                return web.Response(status=200, text="No events to process")
                
            # Add events to queue with timeout fallback
            processed_count = 0
            for event in events:
                try:
                    self.queue.put_nowait(event)
                    processed_count += 1
                    await metrics_collector.record_webhook_request()
                except asyncio.QueueFull:
                    # Try with timeout as fallback
                    try:
                        await asyncio.wait_for(self.queue.put(event), timeout=0.1)
                        processed_count += 1
                        await metrics_collector.record_webhook_request()
                    except asyncio.TimeoutError:
                        await metrics_collector.record_error("queue_full", "Queue overflow")
                        logging.warning("Queue full, dropping event")
                    
            return web.Response(status=200, text=f"Processed {processed_count} events")
            
        except Exception as e:
            await metrics_collector.record_error("webhook_error", str(e))
            logging.error("Webhook error: %s", e)
            return web.Response(status=500, text="Internal server error")
            
    def _extract_events(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract token mint events from webhook payload."""
        events = []
        
        # Handle batch events
        if isinstance(payload, list):
            for item in payload:
                events.extend(self._extract_events(item))
            return events
            
        # Check if this is a token mint event
        tx_type = payload.get("type") or payload.get("transactionType")
        if tx_type != "TOKEN_MINT":
            return events
            
        # Extract mint address
        mint = None
        
        # Try different locations for mint address
        if payload.get("tokenTransfers"):
            for transfer in payload["tokenTransfers"]:
                if transfer.get("mint"):
                    mint = transfer["mint"]
                    break
                    
        if not mint and payload.get("tokenMint"):
            mint = payload["tokenMint"]
            
        if not mint:
            return events
            
        # Deduplicate with TTL
        now = time.time()
        if mint in self._seen_mints:
            # Check if mint is still within TTL
            if now - self._seen_mints[mint] < (self._dedup_ttl_hours * 3600):
                return events
        self._seen_mints[mint] = now
        
        # Create event
        event = {
            "mint": mint,
            "event_type": "webhook",
            "tx_signature": payload.get("signature"),
            "slot": payload.get("slot"),
            "block_time": payload.get("blockTime"),
            "ts": time.time()
        }
        
        events.append(event)
        return events
        
    async def _handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            "status": "healthy",
            "timestamp": int(time.time()),
            "queue_size": self.queue.qsize(),
            "seen_mints": len(self._seen_mints),
            "uptime_seconds": int(time.time() - getattr(self, '_start_time', time.time()))
        })
        
    async def _handle_metrics(self, request: web.Request) -> web.Response:
        """Metrics endpoint."""
        metrics = await metrics_collector.get_metrics()
        return web.json_response(metrics)
        
    async def _handle_test(self, request: web.Request) -> web.Response:
        """Test endpoint for manual token analysis."""
        mint = request.match_info.get("mint")
        if not mint:
            return web.Response(status=400, text="Missing mint parameter")
            
        # Add test event to queue
        event = {
            "mint": mint,
            "event_type": "test",
            "ts": time.time()
        }
        
        try:
            self.queue.put_nowait(event)
            return web.json_response({"status": "queued", "mint": mint})
        except asyncio.QueueFull:
            return web.Response(status=503, text="Queue full")


__all__ = ["OnchainMonitor"]