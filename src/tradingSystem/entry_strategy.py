"""
Entry Strategy System - Pluggable entry timing for memecoin trading.

PROBLEM: Instant buy on ATM signal buys at local top -> stop-loss kills in 90s.
SOLUTION: Configurable entry strategies that accommodate entry noise.

Forensic data:
- Trades held >5min break even
- Trades held >15min are profitable
- Score 3-5 (early stage) outperform Score 9-10 (late stage)
"""

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict


@dataclass
class EntryDecision:
    """Result of an entry strategy evaluation."""
    should_enter: bool
    delay_seconds: float = 0.0
    target_price: float = 0.0
    reason: str = ""
    adjusted_size_usd: float = 0.0


class EntryStrategy(ABC):
    """Base class for all entry strategies."""

    @abstractmethod
    def evaluate(
        self,
        token: str,
        signal_price: float,
        current_price: float,
        score: int,
        stats: Dict,
    ) -> EntryDecision:
        """Evaluate whether to enter a position now.

        Args:
            token: Token mint address.
            signal_price: Price when ATM signal fired.
            current_price: Current market price.
            score: ATM signal score (0-10).
            stats: Token statistics dict.

        Returns:
            EntryDecision with should_enter flag and metadata.
        """
        ...

    def cleanup(self, token: str) -> None:
        """Remove any pending state for a token (called on rejection/timeout)."""
        pass


class InstantEntry(EntryStrategy):
    """Buy immediately on signal. Original (legacy) behavior.

    Kept for backtesting comparison. This is what produced -$0.55/trade
    expectancy -- use as the control baseline, not in production.
    """

    def evaluate(self, token, signal_price, current_price, score, stats):
        return EntryDecision(should_enter=True, reason="instant_entry")


class DelayedEntry(EntryStrategy):
    """Wait N seconds after signal, then buy at market.

    Rationale: Forensic data shows trades surviving >5min are profitable.
    A 60-90s delay lets the initial volatility spike settle before entry.
    """

    def __init__(self, delay_sec: int = 90):
        self.delay_sec = delay_sec
        self._pending: Dict[str, tuple] = {}  # token -> (signal_time, signal_price)

    def evaluate(self, token, signal_price, current_price, score, stats):
        now = time.time()

        if token not in self._pending:
            self._pending[token] = (now, signal_price)
            return EntryDecision(
                should_enter=False,
                delay_seconds=self.delay_sec,
                reason=f"delaying {self.delay_sec}s before entry",
            )

        signal_time, orig_price = self._pending[token]
        elapsed = now - signal_time

        if elapsed < self.delay_sec:
            remaining = self.delay_sec - elapsed
            return EntryDecision(
                should_enter=False,
                delay_seconds=remaining,
                reason=f"waiting {remaining:.0f}s more",
            )

        # Delay complete -- validate price hasn't moved too far
        if orig_price > 0:
            price_change_pct = ((current_price - orig_price) / orig_price) * 100
        else:
            price_change_pct = 0.0

        del self._pending[token]

        if price_change_pct < -30:
            return EntryDecision(
                should_enter=False,
                reason=f"dumped {price_change_pct:.1f}% during delay - skip",
            )
        if price_change_pct > 100:
            return EntryDecision(
                should_enter=False,
                reason=f"already +{price_change_pct:.1f}% - too late",
            )

        return EntryDecision(
            should_enter=True,
            reason=f"delayed_entry after {elapsed:.0f}s (drift: {price_change_pct:+.1f}%)",
        )

    def cleanup(self, token: str) -> None:
        self._pending.pop(token, None)


class DipEntry(EntryStrategy):
    """Wait for price to dip X% from signal price, then buy.

    Rationale: Memecoins swing -15% to -25% in first 2-3 minutes after
    a signal fires. Buying the dip captures a better entry price.
    """

    def __init__(self, dip_pct: float = 10.0, max_wait_sec: int = 300):
        self.dip_pct = dip_pct
        self.max_wait_sec = max_wait_sec
        # token -> (signal_time, signal_price, lowest_price_seen)
        self._watching: Dict[str, tuple] = {}

    def evaluate(self, token, signal_price, current_price, score, stats):
        now = time.time()

        if token not in self._watching:
            self._watching[token] = (now, signal_price, current_price)
            return EntryDecision(
                should_enter=False,
                reason=f"watching for -{self.dip_pct}% dip",
            )

        signal_time, orig_price, lowest = self._watching[token]
        elapsed = now - signal_time

        # Track lowest seen
        if current_price < lowest:
            self._watching[token] = (signal_time, orig_price, current_price)
            lowest = current_price

        if orig_price > 0:
            dip_from_signal = ((current_price - orig_price) / orig_price) * 100
        else:
            dip_from_signal = 0.0

        # Dip target hit
        if dip_from_signal <= -self.dip_pct:
            del self._watching[token]
            return EntryDecision(
                should_enter=True,
                reason=f"dip_entry at {dip_from_signal:.1f}% from signal",
            )

        # Timeout -- buy at market if price held (not dumped)
        if elapsed > self.max_wait_sec:
            del self._watching[token]
            if orig_price > 0 and current_price > orig_price * 0.70:
                return EntryDecision(
                    should_enter=True,
                    reason=f"timeout_entry after {elapsed:.0f}s (no {self.dip_pct}% dip, price held)",
                )
            return EntryDecision(
                should_enter=False,
                reason=f"dumped {dip_from_signal:.1f}% during watch - skip",
            )

        return EntryDecision(
            should_enter=False,
            reason=f"waiting for -{self.dip_pct}% dip (currently {dip_from_signal:+.1f}%)",
        )

    def cleanup(self, token: str) -> None:
        self._watching.pop(token, None)


class HybridEntry(EntryStrategy):
    """Score-based routing derived from forensic analysis.

    Version 1 Logic Restriction (2026-06-17):
    - Score 3, 4, 5 -> InstantEntry
    - Score > 5 -> Rejected (negative expectancy)
    """

    def __init__(self):
        self._instant = InstantEntry()
        self.allow_scores = [3, 4, 5]

    def evaluate(self, token, signal_price, current_price, score, stats):
        if score in self.allow_scores:
            decision = self._instant.evaluate(
                token, signal_price, current_price, score, stats
            )
            decision.reason = f"[early_stage/instant] {decision.reason}"
            return decision
        else:
            return EntryDecision(
                should_enter=False,
                reason=f"[score_rejected] Score {score} not in allowed {self.allow_scores}"
            )

    def cleanup(self, token: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_entry_strategy(name: Optional[str] = None) -> EntryStrategy:
    """Create an entry strategy by name (reads from env if not provided).

    Env var: TS_ENTRY_STRATEGY (default: "hybrid")
    """
    if name is None:
        name = os.getenv("TS_ENTRY_STRATEGY", "hybrid").strip().lower()

    factories = {
        "instant": InstantEntry,
        "delayed": lambda: DelayedEntry(
            delay_sec=int(os.getenv("ENTRY_DELAY_SEC", "90"))
        ),
        "dip": lambda: DipEntry(
            dip_pct=float(os.getenv("ENTRY_DIP_PCT", "10")),
            max_wait_sec=int(os.getenv("ENTRY_DIP_MAX_WAIT_SEC", "300")),
        ),
        "hybrid": HybridEntry,
    }

    factory = factories.get(name)
    if factory is None:
        print(
            f"[ENTRY] Unknown strategy '{name}', falling back to hybrid",
            flush=True,
        )
        factory = HybridEntry

    return factory() if callable(factory) else factory


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_entry_strategy: Optional[EntryStrategy] = None


def get_entry_strategy() -> EntryStrategy:
    """Get or create the global entry strategy instance."""
    global _entry_strategy
    if _entry_strategy is None:
        _entry_strategy = create_entry_strategy()
        print(
            f"[ENTRY] Strategy initialized: {type(_entry_strategy).__name__}",
            flush=True,
        )
    return _entry_strategy
