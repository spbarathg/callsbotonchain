from __future__ import annotations

from typing import Optional, Dict, Any
import time
import threading

try:
    from prometheus_client import Counter, Gauge, Histogram  # type: ignore
except Exception:  # pragma: no cover - metrics optional
    Counter = None  # type: ignore
    Gauge = None  # type: ignore
    Histogram = None  # type: ignore


_enabled = bool(Counter and Gauge)


def enabled() -> bool:
    return _enabled


# Thread-safe metric registry caches
# Note: Prometheus client Counter/Gauge/Histogram objects are thread-safe by design.
# The lock is only needed for the cache dictionary operations during metric creation.
_counters = {}
_gauges = {}
_histograms = {}
_MAX_METRIC_CACHE_SIZE = 1000
_lock = threading.Lock()  # Protects _counters, _gauges, _histograms dictionaries


def _counter(name: str, doc: str, labelnames: Optional[list[str]] = None):
    if not _enabled:
        return None
    key = (name, tuple(labelnames or []))
    with _lock:
        c = _counters.get(key)
        if c is not None:
            return c
        if len(_counters) >= _MAX_METRIC_CACHE_SIZE:
            try:
                oldest_key = next(iter(_counters))
                del _counters[oldest_key]
            except Exception:
                _counters.clear()
        c = Counter(name, doc, labelnames=labelnames or [])
        _counters[key] = c
        return c


def _gauge(name: str, doc: str, labelnames: Optional[list[str]] = None):
    if not _enabled:
        return None
    key = (name, tuple(labelnames or []))
    with _lock:
        g = _gauges.get(key)
        if g is not None:
            return g
        if len(_gauges) >= _MAX_METRIC_CACHE_SIZE:
            try:
                oldest_key = next(iter(_gauges))
                del _gauges[oldest_key]
            except Exception:
                _gauges.clear()
        g = Gauge(name, doc, labelnames=labelnames or [])
        _gauges[key] = g
        return g


def _histogram(name: str, doc: str, labelnames: Optional[list[str]] = None, buckets=None):
    if not _enabled or not Histogram:
        return None
    key = (name, tuple(labelnames or []))
    with _lock:
        h = _histograms.get(key)
        if h is not None:
            return h
        if len(_histograms) >= _MAX_METRIC_CACHE_SIZE:
            try:
                oldest_key = next(iter(_histograms))
                del _histograms[oldest_key]
            except Exception:
                _histograms.clear()
        h = Histogram(name, doc, labelnames=labelnames or [], buckets=buckets)
        _histograms[key] = h
        return h


# ============ EXPANDED METRICS ============

# API Calls (existing)
_counter_api = _counter("cielo_api_calls_total", "Cielo API calls total", ["status", "endpoint"])
_counter_ds = _counter("dexscreener_api_calls_total", "DexScreener API calls total", ["status"])
_counter_gecko = _counter("geckoterminal_api_calls_total", "GeckoTerminal API calls total", ["status"])

# Retry & Circuit Breaker Metrics
_counter_retries = _counter("api_retries_total", "Total API retry attempts", ["provider", "reason"])
_gauge_circuit_state = _gauge("circuit_breaker_state", "Circuit breaker state (0=closed, 1=open, 2=half_open)", ["provider"])
_counter_circuit_opens = _counter("circuit_breaker_opens_total", "Total circuit breaker opens", ["provider"])

# Signal Metrics
_counter_signals_emitted = _counter("signals_emitted_total", "Total signals emitted")
_counter_signals_skipped = _counter("signals_skipped_total", "Signals skipped by reason", ["reason"])
_counter_signals_deduplicated = _counter("signals_deduplicated_total", "Duplicate signals filtered")
_gauge_last_signal_time = _gauge("last_signal_timestamp", "Unix timestamp of last signal")

# Cache Metrics (existing + expanded)
_counter_cache_hits = _counter("cache_hits_total", "Cache hits total", ["cache_type"])
_counter_cache_misses = _counter("cache_misses_total", "Cache misses total", ["cache_type"])
_gauge_cache_size = _gauge("cache_size", "Current cache size", ["cache_type"])

# Alert Metrics (existing)
_counter_alerts_sent = _counter("alerts_sent_total", "Alerts sent total")
_counter_alerts_suppressed = _counter("alerts_suppressed_total", "Alerts suppressed total", ["reason"])

# Budget Metrics
_counter_stats_budget_used = _counter("stats_budget_used_total", "Stats credits spent total")
_gauge_budget_remaining = _gauge("budget_remaining", "Budget remaining", ["window"])

# Deny State Metrics
_counter_deny = _counter("deny_triggered_total", "Number of times stats deny was triggered")
_gauge_deny_remaining = _gauge("deny_remaining_sec", "Seconds remaining in deny state")

# Feed Metrics
_gauge_queue = _gauge("pending_feed_items", "Pending feed items in last cycle")
_counter_feed_errors = _counter("feed_errors_total", "Feed fetch errors", ["error_type"])
_histogram_feed_latency = _histogram("feed_fetch_latency_seconds", "Feed fetch latency", buckets=[0.5, 1, 2, 5, 10, 30, 60])

# Processing Metrics
_histogram_token_analysis_duration = _histogram("token_analysis_duration_seconds", "Token analysis duration", buckets=[0.1, 0.5, 1, 2, 5, 10])
_counter_tokens_processed = _counter("tokens_processed_total", "Tokens processed", ["outcome"])


# ============ METRIC FUNCTIONS ============

def inc_api_call(provider: str, status: Optional[int], endpoint: str = "unknown") -> None:
    if not _enabled:
        return
    s = str(status if status is not None else "none")
    
    if provider == "cielo" and _counter_api is not None:
        _counter_api.labels(status=s, endpoint=endpoint).inc()  # type: ignore
    elif provider == "dexscreener" and _counter_ds is not None:
        _counter_ds.labels(status=s).inc()  # type: ignore
    elif provider == "geckoterminal" and _counter_gecko is not None:
        _counter_gecko.labels(status=s).inc()  # type: ignore


def inc_retry(provider: str, reason: str) -> None:
    if _enabled and _counter_retries is not None:
        _counter_retries.labels(provider=provider, reason=reason).inc()  # type: ignore


def set_circuit_state(provider: str, state: str) -> None:
    """Set circuit breaker state: closed=0, open=1, half_open=2"""
    if _enabled and _gauge_circuit_state is not None:
        state_map = {"closed": 0, "open": 1, "half_open": 2}
        _gauge_circuit_state.labels(provider=provider).set(state_map.get(state, 0))  # type: ignore


def inc_circuit_open(provider: str) -> None:
    if _enabled and _counter_circuit_opens is not None:
        _counter_circuit_opens.labels(provider=provider).inc()  # type: ignore


def inc_signal_emitted() -> None:
    if _enabled and _counter_signals_emitted is not None:
        _counter_signals_emitted.inc()  # type: ignore
    if _enabled and _gauge_last_signal_time is not None:
        _gauge_last_signal_time.set(time.time())  # type: ignore


def inc_signal_skipped(reason: str) -> None:
    if _enabled and _counter_signals_skipped is not None:
        _counter_signals_skipped.labels(reason=reason).inc()  # type: ignore


def inc_signal_deduplicated() -> None:
    if _enabled and _counter_signals_deduplicated is not None:
        _counter_signals_deduplicated.inc()  # type: ignore


def cache_hit(cache_type: str = "stats") -> None:
    if _enabled and _counter_cache_hits is not None:
        _counter_cache_hits.labels(cache_type=cache_type).inc()  # type: ignore


def cache_miss(cache_type: str = "stats") -> None:
    if _enabled and _counter_cache_misses is not None:
        _counter_cache_misses.labels(cache_type=cache_type).inc()  # type: ignore


def set_cache_size(cache_type: str, size: int) -> None:
    if _enabled and _gauge_cache_size is not None:
        _gauge_cache_size.labels(cache_type=cache_type).set(size)  # type: ignore


def alert_sent() -> None:
    if _enabled and _counter_alerts_sent is not None:
        _counter_alerts_sent.inc()  # type: ignore


def alert_suppressed(reason: str) -> None:
    if _enabled and _counter_alerts_suppressed is not None:
        _counter_alerts_suppressed.labels(reason=str(reason)).inc()  # type: ignore


def add_stats_budget_used(n: int = 1) -> None:
    if _enabled and _counter_stats_budget_used is not None:
        _counter_stats_budget_used.inc(n)  # type: ignore


def set_budget_remaining(window: str, amount: int) -> None:
    if _enabled and _gauge_budget_remaining is not None:
        _gauge_budget_remaining.labels(window=window).set(amount)  # type: ignore


def inc_deny() -> None:
    if _enabled and _counter_deny is not None:
        _counter_deny.inc()  # type: ignore


def set_deny_remaining(seconds: int) -> None:
    if _enabled and _gauge_deny_remaining is not None:
        _gauge_deny_remaining.set(seconds)  # type: ignore


def set_queue_len(n: int) -> None:
    if _enabled and _gauge_queue is not None:
        _gauge_queue.set(n)  # type: ignore


def inc_feed_error(error_type: str) -> None:
    if _enabled and _counter_feed_errors is not None:
        _counter_feed_errors.labels(error_type=error_type).inc()  # type: ignore


def observe_feed_latency(seconds: float) -> None:
    if _enabled and _histogram_feed_latency is not None:
        _histogram_feed_latency.observe(seconds)  # type: ignore


def observe_token_analysis_duration(seconds: float) -> None:
    if _enabled and _histogram_token_analysis_duration is not None:
        _histogram_token_analysis_duration.observe(seconds)  # type: ignore


def inc_token_processed(outcome: str) -> None:
    """Track token processing outcomes: alert_sent, skipped, error"""
    if _enabled and _counter_tokens_processed is not None:
        _counter_tokens_processed.labels(outcome=outcome).inc()  # type: ignore


def get_all_metrics_summary() -> Dict[str, Any]:
    """
    Get summary of all metrics (for health endpoint when Prometheus not available).
    Returns dict with metric values.
    """
    # This is a simplified version that returns counter values
    # In production, you'd query Prometheus or store values separately
    return {
        "enabled": _enabled,
        "counters": len(_counters),
        "gauges": len(_gauges),
        "histograms": len(_histograms),
    }
