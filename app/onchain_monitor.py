import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Set

import aiohttp
from aiohttp import web

try:
    import base58
except ImportError:
    base58 = None

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
        
        # Rate limiting (configurable)
        self._request_times: List[float] = []
        try:
            self.max_requests_per_minute = int(os.getenv("WEBHOOK_MAX_RPM", "5000"))
        except Exception:
            self.max_requests_per_minute = 5000
        
        # Launches-only filtering toggle
        self.launches_only: bool = os.getenv("LAUNCHES_ONLY", "false").lower() == "true"
        # Dedup window for launches (seconds)
        try:
            self.launch_dedup_s: int = int(os.getenv("LAUNCH_DEDUP_S", "600"))
        except Exception:
            self.launch_dedup_s = 600

        # Deduplication TTL (24 hours)
        self._dedup_ttl_hours = 24
        # Max payload size to prevent DoS
        self._max_payload_size = int(os.getenv("MAX_PAYLOAD_SIZE", "1048576"))  # 1MB default
        
        # Target programs for new token launches
        self._target_programs = {
            "675kPX9MHTjS2zt1qfr1NYHuzeLXf3w7T8vQ1F8VxEZ",  # Raydium V4
            "6EF8rrecthR5DkVKMzskHPBxdLHMpWFqcFvXVvLCADx",  # Pump.fun
            "7xKXGhFZKS1tZa6kFmf1zz55KjKnb5qTgzoBDLmqLwzw"  # Meteora DLMM
        }
        
        # Program-specific instruction filters (lowercase names)
        # Empty list means "accept any instruction for this program"
        self._program_instructions = {
            # Raydium V4
            "675kPX9MHTjS2zt1qfr1NYHuzeLXf3w7T8vQ1F8VxEZ": ["initialize2"],
            # Pump.fun - for launches prefer create; first buy sometimes signals activation
            "6EF8rrecthR5DkVKMzskHPBxdLHMpWFqcFvXVvLCADx": ["create", "buy"],
            # Meteora DLMM
            "7xKXGhFZKS1tZa6kFmf1zz55KjKnb5qTgzoBDLmqLwzw": ["initialize_pool"],
        }
        # Additional launch-related programs (SPL Token + Token Metadata)
        self._launch_aux_programs = {
            # SPL Token Program (initialize mint)
            "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": [
                "initializemint",
                "initialize_mint",
            ],
            # Token Metadata create
            "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s": [
                "create",
                "create_metadata_account",
                "create_metadata_account_v3",
            ],
        }
        
        # Statistics for monitoring
        self._stats = {
            "total_events": 0,
            "filtered_events": 0,
            "program_matches": 0,
            "pump_fun_creations": 0,
            "raydium_initializations": 0,
            "meteora_initializations": 0,
            "duplicate_skips": 0,
            "error_transactions": 0,
            "invalid_mints": 0,
            "missing_creation_logs": 0,
            "instruction_position_issues": 0,
            "cleanup_runs": 0
        }
        
        # Time-based cleanup tracking
        self._last_cleanup_time = time.time()
        self._cleanup_interval = 3600  # 1 hour cleanup interval

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
        
        # If <=0, disable rate limiting
        if self.max_requests_per_minute > 0 and len(self._request_times) >= self.max_requests_per_minute:
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
            
        self._stats["cleanup_runs"] += 1
        if expired_mints:
            logging.info("Cleaned up %d expired mints from cache", len(expired_mints))
        
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
            
            # Count every webhook request (even if no events extracted)
            try:
                await metrics_collector.record_webhook_request()
            except Exception:
                pass
                
            # Time-based cleanup (every hour)
            now = time.time()
            if now - self._last_cleanup_time > self._cleanup_interval:
                self._cleanup_old_mints()
                self._last_cleanup_time = now
                
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
                        await asyncio.wait_for(self.queue.put(event), timeout=0.5)  # Increased timeout
                        processed_count += 1
                        await metrics_collector.record_webhook_request()
                    except asyncio.TimeoutError:
                        await metrics_collector.record_error("queue_full", "Queue overflow")
                        logging.warning("Queue full, dropping event after 0.5s timeout")
                    
            return web.Response(status=200, text=f"Processed {processed_count} events")
            
        except Exception as e:
            await metrics_collector.record_error("webhook_error", str(e))
            logging.error("Webhook error: %s", e)
            return web.Response(status=500, text="Internal server error")
            
    def _extract_events(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract events. If LAUNCHES_ONLY is true, only queue new-launch transactions."""
        events: List[Dict[str, Any]] = []

        # Handle batch events
        if isinstance(payload, list):
            for item in payload:
                events.extend(self._extract_events(item))
            return events

        # Count event
        self._stats["total_events"] += 1

        # Extract all instructions/programIds
        instructions = payload.get("instructions") or []
        first_instr = instructions[0] if instructions else {}
        matching_program = first_instr.get("programId") or ""
        matching_instruction = str((first_instr.get("instruction") or {}).get("name", "")).lower()

        # If launches-only, ensure at least one instruction matches our launch maps
        if self.launches_only:
            matched = False
            # Check primary launch programs
            for instr in instructions:
                pid = instr.get("programId") or ""
                name = str((instr.get("instruction") or {}).get("name", "")).lower()
                allowed = self._program_instructions.get(pid)
                if allowed is not None:
                    if not allowed or name in allowed:
                        matched = True
                        matching_program = pid
                        matching_instruction = name
                        break
                # Check auxiliary programs
                allowed_aux = self._launch_aux_programs.get(pid)
                if allowed_aux is not None and (not allowed_aux or name in allowed_aux):
                    matched = True
                    matching_program = pid
                    matching_instruction = name
                    break
            if not matched:
                # Not a launch-related transaction
                return events

        # Try to extract a mint (best-effort). If none, mark as "unknown" to avoid drops
        mint = self._extract_mint_address(payload) or str(payload.get("tokenMint") or payload.get("mint") or "unknown")

        # Dedup launches by mint within TTL when launches_only
        now_ts = time.time()
        last_ts = self._seen_mints.get(mint)
        if self.launches_only and last_ts and (now_ts - last_ts) < self.launch_dedup_s:
            return events
        self._seen_mints[mint] = now_ts

        # Program counters (best-effort)
        if matching_program:
            self._stats["program_matches"] += 1
            if matching_program == "6EF8rrecthR5DkVKMzskHPBxdLHMpWFqcFvXVvLCADx":
                self._stats["pump_fun_creations"] += 1
            elif matching_program == "675kPX9MHTjS2zt1qfr1NYHuzeLXf3w7T8vQ1F8VxEZ":
                self._stats["raydium_initializations"] += 1
            elif matching_program == "7xKXGhFZKS1tZa6kFmf1zz55KjKnb5qTgzoBDLmqLwzw":
                self._stats["meteora_initializations"] += 1

        # Build event
        event = {
            "mint": mint,
            "event_type": "webhook",
            "tx_signature": payload.get("signature"),
            "slot": payload.get("slot"),
            "block_time": payload.get("blockTime"),
            "program_id": matching_program,
            "instruction": matching_instruction,
            "ts": time.time(),
        }

        self._stats["filtered_events"] += 1
        logging.info("📥 Event accepted: mint=%s prog=%s instr=%s", str(mint)[:8], matching_program[:8], matching_instruction)
        events.append(event)
        return events
        
    def _validate_program_specific_rules(self, payload: Dict[str, Any], program_id: str, instruction: str) -> bool:
        """Validate program-specific rules for new token launches."""
        
        if program_id == "6EF8rrecthR5DkVKMzskHPBxdLHMpWFqcFvXVvLCADx":  # Pump.fun
            # Relaxed Pump.fun validation: accept any buy instruction
            # Remove strict creation log requirement
            logs = payload.get("logs", [])
            creation_log_found = False
            
            for log in logs:
                if "creating bonding curve" in log.lower():
                    creation_log_found = True
                    break
            
            # Accept even if no creation log found (relaxed filtering)
            if not creation_log_found:
                self._stats["missing_creation_logs"] += 1
                logging.debug("Pump.fun transaction missing creation log - accepting anyway")
                # Don't return False - accept the transaction
                
            # Remove strict first-buy check (relaxed filtering)
            # Allow processing even if mint was seen before
            return True
            
        elif program_id == "675kPX9MHTjS2zt1qfr1NYHuzeLXf3w7T8vQ1F8VxEZ":  # Raydium V4
            # Accept if initialize2 appears anywhere
            instructions = payload.get("instructions", [])
            if not instructions:
                return False
            for instr in instructions:
                if str(instr.get("instruction", {}).get("name", "")).lower() == "initialize2":
                    return True
            logging.debug("Raydium transaction missing initialize2 instruction")
            return False
                
        elif program_id == "7xKXGhFZKS1tZa6kFmf1zz55KjKnb5qTgzoBDLmqLwzw":  # Meteora DLMM
            # Accept if initialize_pool appears anywhere
            instructions = payload.get("instructions", [])
            if not instructions:
                return False
            for instr in instructions:
                if str(instr.get("instruction", {}).get("name", "")).lower() == "initialize_pool":
                    return True
            logging.debug("Meteora transaction missing initialize_pool instruction")
            return False
                
        return False
        
    def _extract_mint_address(self, payload: Dict[str, Any]) -> Optional[str]:
        """Extract mint address from transaction payload with validation."""
        # Try tokenTransfers first (most reliable)
        if payload.get("tokenTransfers"):
            for transfer in payload["tokenTransfers"]:
                mint = transfer.get("mint")
                if mint and self._is_valid_mint_address(mint):
                    return mint
                    
        # Try tokenMint field
        if payload.get("tokenMint"):
            mint = payload["tokenMint"]
            if self._is_valid_mint_address(mint):
                return mint
            
        # Try accountKeys for newly created accounts (fallback)
        account_keys = payload.get("accountKeys", [])
        if account_keys:
            # Look for mint accounts (typically the first few accounts)
            for account in account_keys[:5]:  # Check first 5 accounts
                if isinstance(account, str) and self._is_valid_mint_address(account):
                    return account
                    
        return None
        
    def _is_valid_mint_address(self, address: str) -> bool:
        """Validate if address is a proper Solana mint address."""
        if not isinstance(address, str):
            return False
            
        # Relaxed validation: accept any string that looks like a Solana address
        # Check minimum length (Solana addresses are at least 32 bytes = 44 base58 chars)
        if len(address) < 32:
            return False
            
        # Accept any reasonable length address (relaxed filtering)
        if len(address) > 100:  # Reasonable upper bound
            return False
            
        # If base58 is available, do basic validation
        if base58 is not None:
            try:
                decoded = base58.b58decode(address)
                # Accept any reasonable decoded length (relaxed)
                return 20 <= len(decoded) <= 50
            except Exception:
                # If base58 decode fails, still accept if it looks reasonable
                return len(address) >= 32
        else:
            # Fallback: just check reasonable length
            return 32 <= len(address) <= 50
        
    async def _handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            "status": "healthy",
            "timestamp": int(time.time()),
            "queue_size": self.queue.qsize(),
            "seen_mints": len(self._seen_mints),
            "uptime_seconds": int(time.time() - getattr(self, '_start_time', time.time())),
            "filtering_stats": self._stats
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