import asyncio
import logging
import os
import signal
import platform
import time
from typing import Any, Dict, List, Optional

import aiohttp

# .env is already loaded by app/__init__.py during module import

from .analyzer import analyze_token
from .onchain_monitor import OnchainMonitor
from .publisher import Publisher
from .scorer import score_token
from .metrics import metrics_collector, TokenStats


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
QUEUE_SIZE = int(os.getenv("QUEUE_SIZE", "1024"))
WORKERS = int(os.getenv("WORKERS", "4"))
MIN_LP_SOL = float(os.getenv("MIN_LP_SOL", "5"))
MAX_TOKENS_PER_HOUR = int(os.getenv("MAX_TOKENS_PER_HOUR", "50"))  # Optimized for Cielo Pro + Helius Pro
_hourly_count = 0
_hourly_reset_time = time.time() + 3600

# Dedup of processed mints to avoid repeated analysis within a window
RECENT_TTL_S = int(os.getenv("DEDUP_TTL_S", "900"))
_recent_mints: Dict[str, float] = {}

# Optimized rate limiting for Pro services
DS_MAX_CONCURRENCY = int(os.getenv("DS_MAX_CONCURRENCY", "3"))  # Higher with Pro reliability
DS_DELAY_S = float(os.getenv("DS_DELAY_S", "0.3"))  # Faster with enhanced stability
_ds_sem = asyncio.Semaphore(DS_MAX_CONCURRENCY)
_last_ds_call = 0.0
_hourly_lock = asyncio.Lock()


async def _ds_fetch_best_lp_sol(session: aiohttp.ClientSession, mint: str, sol_price_usd: float = 150.0) -> float:
    global _last_ds_call
    url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
    attempt = 0
    last_lp = 0.0
    start_time = time.time()
    
    while attempt < 2:
        attempt += 1
        try:
            async with _ds_sem:
                # Rate limiting delay
                now = time.time()
                if now - _last_ds_call < DS_DELAY_S:
                    await asyncio.sleep(DS_DELAY_S - (now - _last_ds_call))
                _last_ds_call = time.time()
                
                timeout = aiohttp.ClientTimeout(total=6)
                async with session.get(url, timeout=timeout) as resp:
                    response_time = (time.time() - start_time) * 1000
                    
                    if resp.status != 200:
                        await metrics_collector.record_api_health("dexscreener", "error", response_time, error=True)
                        continue
                    
                    data = await resp.json()
                    await metrics_collector.record_api_health("dexscreener", "healthy", response_time)
                    
            pairs = (data or {}).get("pairs") or []
            best_usd = 0.0
            for p in pairs:
                try:
                    usd = float(((p.get("liquidity") or {}).get("usd") or 0.0))
                    quote_sym = str(((p.get("quoteToken") or {}).get("symbol")) or "").upper()
                    if quote_sym == "SOL" and usd > best_usd:
                        best_usd = usd
                except Exception:
                    continue
            if best_usd > 0 and sol_price_usd > 0:
                last_lp = best_usd / sol_price_usd
            break
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            await metrics_collector.record_api_health("dexscreener", "error", response_time, error=True)
            await asyncio.sleep(0.5 * attempt)
    return float(last_lp)


def _recent_seen(mint: str) -> bool:
    now = time.time()
    # cleanup
    expired = [m for m, until in _recent_mints.items() if until <= now]
    for m in expired:
        _recent_mints.pop(m, None)
    return mint in _recent_mints


def _recent_add(mint: str) -> None:
    now = time.time()
    _recent_mints[mint] = now + RECENT_TTL_S


def _check_hourly_limit() -> bool:
    """Check if we're within hourly token processing limit."""
    global _hourly_count, _hourly_reset_time
    now = time.time()
    if now > _hourly_reset_time:
        _hourly_count = 0
        _hourly_reset_time = now + 3600
    return _hourly_count < MAX_TOKENS_PER_HOUR

def _increment_hourly_count() -> None:
    """Increment hourly token count."""
    global _hourly_count
    _hourly_count += 1


async def _try_acquire_hourly_slot() -> bool:
    """Atomically check and consume one hourly processing slot.

    Prevents concurrent workers from overshooting the hourly cap.
    """
    global _hourly_count, _hourly_reset_time
    async with _hourly_lock:
        now = time.time()
        if now > _hourly_reset_time:
            _hourly_count = 0
            _hourly_reset_time = now + 3600
        if _hourly_count >= MAX_TOKENS_PER_HOUR:
            return False
        _hourly_count += 1
        return True

async def worker(
    name: str,
    queue: "asyncio.Queue[Dict[str, Any]]",
    publisher: Publisher,
    session: aiohttp.ClientSession,
) -> None:
    while True:
        item: Dict[str, Any] = await queue.get()
        start_time = time.time()
        result: Optional[Dict[str, Any]] = None
        processing_successful = False
        
        try:
            mint = str(item.get("mint"))
            source = str(item.get("event_type", "unknown"))
            
            if _recent_seen(mint):
                continue
            
            # Early non-atomic guard to skip work if we're likely over limit
            if not _check_hourly_limit():
                logging.info("⏸️  Hourly limit reached (%d/%d)", _hourly_count, MAX_TOKENS_PER_HOUR)
                continue
                
            lp_sol = float(item.get("lp_sol") or 0.0)
            if lp_sol < MIN_LP_SOL:
                # Second-chance LP check via DexScreener (fast)
                try:
                    lp_sol = max(lp_sol, await _ds_fetch_best_lp_sol(session, mint))
                except Exception:
                    pass
                if lp_sol < MIN_LP_SOL:
                    continue

            base_context = {
                "lp_sol": lp_sol,
                "dex": item.get("dex"),
                "pool_address": item.get("pool_address"),
                "creator": item.get("creator"),
                "ts": item.get("ts"),
            }

            # Acquire hourly slot atomically right before expensive RPC analysis
            if not await _try_acquire_hourly_slot():
                logging.info("⏸️  Hourly limit reached after LP checks, skipping %s", mint[:8])
                continue

            # Track analysis time
            analysis_start = time.time()
            data = await analyze_token(mint, base_context, session=session)
            analysis_time = (time.time() - analysis_start) * 1000
            await metrics_collector.record_processing_time("analysis", analysis_time)
            
            # Track scoring time
            scoring_start = time.time()
            scored = score_token(data)
            scoring_time = (time.time() - scoring_start) * 1000
            await metrics_collector.record_processing_time("scoring", scoring_time)
            
            result = {**data, **scored}
            processing_time_ms = (time.time() - start_time) * 1000
            
            # Create token stats for metrics
            token_stats = TokenStats(
                mint=mint,
                timestamp=time.time(),
                score=float(result.get("score") or 0.0),
                lp_sol=lp_sol,
                is_signal=bool(result.get("signal")),
                processing_time_ms=processing_time_ms,
                source=source
            )
            
            # Record processing metrics
            await metrics_collector.record_token_processed(token_stats)
            processing_successful = True
            
            if result.get("signal"):
                _recent_add(mint)
                score = float(result.get("score") or 0.0)
                logging.info("🚀 SIGNAL: %s (Score: %.1f)", mint[:8], score)
                
                # Track publishing time
                publish_start = time.time()
                await publisher.publish(result)
                publish_time = (time.time() - publish_start) * 1000
                await metrics_collector.record_processing_time("publishing", publish_time)
                
        except Exception as e:
            error_msg = str(e)[:100]
            logging.error("❌ Processing error: %s", error_msg)
            await metrics_collector.record_error("processing_error", error_msg)
            
        finally:
            # Update queue size metrics
            await metrics_collector.record_queue_size(queue.qsize())
            queue.task_done()


async def main() -> None:
    logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
    queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue(maxsize=QUEUE_SIZE)
    # Pass port explicitly to ensure .env is respected
    webhook_port = int(os.getenv("WEBHOOK_PORT", "8080"))
    webhook_host = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    monitor = OnchainMonitor(queue, host=webhook_host, port=webhook_port)
    publisher = Publisher()
    await publisher.start()
    await monitor.start()

    stop_event = asyncio.Event()

    def _handle_signal(sig: int, _frame: Optional[object] = None) -> None:
        logging.info("Received signal %s, shutting down...", sig)
        stop_event.set()

    # Signal handling (Windows supports SIGINT only)
    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, _handle_signal, signal.SIGINT)
    except NotImplementedError:
        pass
    try:
        loop.add_signal_handler(signal.SIGTERM, _handle_signal, signal.SIGTERM)
    except (AttributeError, NotImplementedError):
        pass

    async with aiohttp.ClientSession() as session:
        workers: List[asyncio.Task[None]] = []
        for i in range(WORKERS):
            workers.append(asyncio.create_task(worker(f"w{i+1}", queue, publisher, session)))

        try:
            await stop_event.wait()
        finally:
            for w in workers:
                w.cancel()
            await monitor.stop()
            await publisher.stop()
            await asyncio.gather(*workers, return_exceptions=True)


if __name__ == "__main__":
    # Ensure aiodns works on Windows by using the SelectorEventLoop
    if platform.system() == "Windows":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


