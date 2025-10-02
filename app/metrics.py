from __future__ import annotations

import os
from typing import Optional

try:
    from prometheus_client import Counter, Gauge  # type: ignore
except Exception:  # pragma: no cover - metrics optional
    Counter = None  # type: ignore
    Gauge = None  # type: ignore


_enabled = bool(Counter and Gauge)


def enabled() -> bool:
    return _enabled


_counters = {}
_gauges = {}


def _counter(name: str, doc: str, labelnames: Optional[list[str]] = None):
    if not _enabled:
        return None
    key = (name, tuple(labelnames or []))
    c = _counters.get(key)
    if c is not None:
        return c
    c = Counter(name, doc, labelnames=labelnames or [])
    _counters[key] = c
    return c


def _gauge(name: str, doc: str, labelnames: Optional[list[str]] = None):
    if not _enabled:
        return None
    key = (name, tuple(labelnames or []))
    g = _gauges.get(key)
    if g is not None:
        return g
    g = Gauge(name, doc, labelnames=labelnames or [])
    _gauges[key] = g
    return g


# Predefine metrics
_counter_api = _counter("cielo_api_calls_total", "Cielo API calls total", ["status"])  # reused for cielo
_counter_ds = _counter("dexscreener_api_calls_total", "DexScreener API calls total", ["status"])  # dexscreener
_counter_cache_hits = _counter("cache_hits_total", "Cache hits total")
_counter_cache_misses = _counter("cache_misses_total", "Cache misses total")
_counter_alerts_sent = _counter("alerts_sent_total", "Alerts sent total")
_counter_alerts_suppressed = _counter("alerts_suppressed_total", "Alerts suppressed total", ["reason"])
_counter_stats_budget_used = _counter("stats_budget_used", "Stats credits spent total")
_counter_deny = _counter("deny_count", "Number of times stats deny was triggered")
_gauge_queue = _gauge("pending_feed_items", "Pending feed items in last cycle")


def inc_api_call(provider: str, status: Optional[int]) -> None:
    if not _enabled:
        return
    s = str(status if status is not None else "none")
    if provider == "cielo" and _counter_api is not None:
        _counter_api.labels(status=s).inc()  # type: ignore
    elif provider == "dexscreener" and _counter_ds is not None:
        _counter_ds.labels(status=s).inc()  # type: ignore


def cache_hit() -> None:
    if _enabled and _counter_cache_hits is not None:
        _counter_cache_hits.inc()  # type: ignore


def cache_miss() -> None:
    if _enabled and _counter_cache_misses is not None:
        _counter_cache_misses.inc()  # type: ignore


def alert_sent() -> None:
    if _enabled and _counter_alerts_sent is not None:
        _counter_alerts_sent.inc()  # type: ignore


def alert_suppressed(reason: str) -> None:
    if _enabled and _counter_alerts_suppressed is not None:
        _counter_alerts_suppressed.labels(reason=str(reason)).inc()  # type: ignore


def add_stats_budget_used(n: int = 1) -> None:
    if _enabled and _counter_stats_budget_used is not None:
        _counter_stats_budget_used.inc(n)  # type: ignore


def inc_deny() -> None:
    if _enabled and _counter_deny is not None:
        _counter_deny.inc()  # type: ignore


def set_queue_len(n: int) -> None:
    if _enabled and _gauge_queue is not None:
        _gauge_queue.set(n)  # type: ignore


