import asyncio
import logging
import os
import signal
import platform
from typing import Any, Dict, List, Optional

import aiohttp

from .analyzer import analyze_token
from .onchain_monitor import OnchainMonitor
from .publisher import Publisher
from .scorer import score_token


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
QUEUE_SIZE = int(os.getenv("QUEUE_SIZE", "1024"))
WORKERS = int(os.getenv("WORKERS", "4"))


async def worker(
    name: str,
    queue: "asyncio.Queue[Dict[str, Any]]",
    publisher: Publisher,
    session: aiohttp.ClientSession,
) -> None:
    while True:
        item: Dict[str, Any] = await queue.get()
        try:
            mint = str(item.get("mint"))
            lp_sol = float(item.get("lp_sol") or 0.0)
            if lp_sol < float(os.getenv("MIN_LP_SOL", "5")):
                logging.debug("[%s] Skipping %s: LP %.2f < threshold", name, mint, lp_sol)
                continue

            base_context = {
                "lp_sol": lp_sol,
                "dex": item.get("dex"),
                "pool_address": item.get("pool_address"),
                "creator": item.get("creator"),
                "ts": item.get("ts"),
            }

            data = await analyze_token(mint, base_context, session=session)
            scored = score_token(data)
            result: Dict[str, Any] = {**data, **scored}
            if result.get("signal"):
                await publisher.publish(result)
            else:
                logging.debug(
                    "[%s] Dropped %s score=%.2f", name, mint, float(result.get("score") or 0.0)
                )
        except Exception as e:
            logging.exception("[%s] Processing error: %s", name, e)
        finally:
            queue.task_done()


async def main() -> None:
    logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
    queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue(maxsize=QUEUE_SIZE)
    monitor = OnchainMonitor(queue)
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


