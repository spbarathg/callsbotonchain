"""
Signal Source Interface
=======================

Defines the minimal contract that any signal source must satisfy to feed
the SignalPriorityQueue without touching the risk or execution layers.

CONTEXT (2026-05-17)
--------------------
The current signal pipeline looks like this:

    [Telegram ATM]  →  atm_listener.py  →  SignalPriorityQueue  →  cli_optimized.py
                                                    ↑
                           (This is the abstraction boundary)

To add a new signal source — e.g. a Yellowstone gRPC pool-creation stream,
a smart-wallet tracker, or an on-chain DEX event listener — you only need to:

    1. Create a new coroutine / thread that produces `QueuedSignal` objects.
    2. Push them into the queue via `get_signal_queue().enqueue(signal)`.
    3. No changes needed to the entry strategy, risk management, or executor.

The queue already handles:
    - Deduplication (by token address, 5min TTL)
    - Score-threshold admission (SIGNAL_MIN_QUEUE_SCORE env var)
    - Burst protection
    - Redis persistence across restarts

KNOWN LIMITATION
----------------
`signal_queue.py` persists to Redis using `lpush` (stack order), while
`watcher.py` consumes with `brpop` (right-pop = FIFO order). The in-memory
heap's priority ordering is only used for in-process `dequeue()` calls.
If the process restarts mid-queue, signals are replayed in FIFO order (not
score order). This is a known, accepted trade-off for the current scale.

ADDING A NEW SOURCE — CHECKLIST
---------------------------------
1. Import `QueuedSignal` from `app.signal_queue`.
2. Populate QueuedSignal fields:
   - token_address: str         (Solana mint)
   - raw_score: float           (0-10 — your scoring model's output)
   - timestamp: float           (unix epoch, time of detection)
   - source: str                (e.g. "grpc_pool_create", "smart_wallet")
   - atm_meta: dict             (optional; any metadata you want downstream)
   - tx_data: dict              (optional; raw transaction data)
3. Call `get_signal_queue().enqueue(signal)` from your ingestion thread.
4. Register your coroutine / thread in `cli_optimized.py::run()` startup.
5. Done. The rest of the pipeline is unchanged.

EXAMPLE SKELETON (gRPC source)
---------------------------------

    import asyncio
    from app.signal_queue import get_signal_queue, QueuedSignal
    import time

    async def run_grpc_pool_stream(grpc_endpoint: str) -> None:
        \"\"\"
        Connect to Yellowstone gRPC and emit a QueuedSignal for every new
        Pump.fun / Raydium liquidity pool creation detected.
        \"\"\"
        # ... set up grpc channel, subscribe to program account updates ...
        async for event in grpc_channel:
            token_address = _parse_mint_from_event(event)
            if not token_address:
                continue

            score = _score_pool_event(event)   # your scoring logic

            signal = QueuedSignal(
                token_address=token_address,
                raw_score=score,
                timestamp=time.time(),
                source="grpc_pool_create",
                atm_meta={},
                tx_data={"signature": event.signature},
            )

            enqueued, reason = get_signal_queue().enqueue(signal)
            if enqueued:
                print(f"[GRPC] Queued {token_address[:8]} (score={score:.1f})")
            else:
                print(f"[GRPC] Dropped {token_address[:8]}: {reason}")
"""

# ---------------------------------------------------------------------------
# Formal protocol (Python 3.8+ compatible)
# ---------------------------------------------------------------------------
from abc import ABC, abstractmethod
from typing import AsyncIterator

from app.signal_queue import QueuedSignal


class SignalSource(ABC):
    """
    Abstract base class for all signal sources.

    A SignalSource is responsible for discovering trading opportunities and
    yielding `QueuedSignal` objects.  It knows NOTHING about entry strategy,
    risk management, or execution — those are handled downstream.

    Implementors
    ------------
    - `ATMListener`  (app/atm_listener.py) — existing Telegram source
    - Future: `GrpcPoolSource`  — Yellowstone gRPC pool creation stream
    - Future: `SmartWalletSource`  — on-chain wallet copy-trade tracker
    """

    @abstractmethod
    async def stream(self) -> AsyncIterator[QueuedSignal]:
        """
        Yield signals as they are discovered.

        Implementations MUST be long-running coroutines that only return when
        the source is intentionally shut down.  They should handle their own
        reconnect/retry logic internally.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for logging, e.g. 'atm_telegram', 'grpc_pool'."""
        ...
