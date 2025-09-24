import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from collections import defaultdict, deque


@dataclass
class TokenStats:
    """Statistics for a processed token."""
    mint: str
    timestamp: float
    score: float
    lp_sol: float
    is_signal: bool
    processing_time_ms: float
    source: str  # "webhook", "userbot"
    

@dataclass
class SystemMetrics:
    """System-wide performance metrics."""
    start_time: float = field(default_factory=time.time)
    
    # Counters
    tokens_seen: int = 0
    tokens_processed: int = 0
    signals_generated: int = 0
    errors_count: int = 0
    webhook_requests: int = 0
    
    # Processing stats
    avg_processing_time_ms: float = 0.0
    max_processing_time_ms: float = 0.0
    queue_size_current: int = 0
    queue_size_max: int = 0
    
    # Score distribution
    score_distribution: Dict[str, int] = field(default_factory=lambda: {
        "0-2": 0, "2-4": 0, "4-6": 0, "6-8": 0, "8-10": 0
    })
    
    # Recent activity (last hour)
    recent_tokens: deque = field(default_factory=lambda: deque(maxlen=100))
    recent_signals: deque = field(default_factory=lambda: deque(maxlen=50))
    recent_errors: deque = field(default_factory=lambda: deque(maxlen=20))
    
    # API health
    api_health: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        "quicknode": {"status": "unknown", "last_check": 0, "response_time_ms": 0, "error_count": 0},
        "dexscreener": {"status": "unknown", "last_check": 0, "response_time_ms": 0, "error_count": 0},
        "cielo": {"status": "unknown", "last_check": 0, "response_time_ms": 0, "error_count": 0},
        "redis": {"status": "unknown", "last_check": 0, "error_count": 0},
        "telegram": {"status": "unknown", "last_check": 0, "error_count": 0}
    })
    
    # Processing times by component  
    processing_times: Dict[str, List[float]] = field(default_factory=dict)


class MetricsCollector:
    """Centralized metrics collection for the memecoin bot."""
    
    def __init__(self, max_history: int = 1000):
        self.metrics = SystemMetrics()
        self.max_history = max_history
        self._lock = asyncio.Lock()
        
        # Track hourly stats
        self.hourly_stats: Dict[int, Dict[str, int]] = defaultdict(lambda: {
            "tokens": 0, "signals": 0, "errors": 0
        })
        
    async def record_webhook_request(self) -> None:
        """Record a received webhook request/event."""
        async with self._lock:
            self.metrics.webhook_requests += 1

    async def record_token_seen(self, source: str = "unknown") -> None:
        """Record that a token was seen."""
        async with self._lock:
            self.metrics.tokens_seen += 1
            if source == "webhook":
                self.metrics.webhook_requests += 1
                
            # Update hourly stats
            hour = int(time.time() // 3600)
            self.hourly_stats[hour]["tokens"] += 1
    
    async def record_token_processed(self, token_stats: TokenStats) -> None:
        """Record that a token was fully processed."""
        async with self._lock:
            self.metrics.tokens_processed += 1
            
            # Update processing time stats
            proc_time = token_stats.processing_time_ms
            self.metrics.max_processing_time_ms = max(self.metrics.max_processing_time_ms, proc_time)
            
            # Calculate rolling average
            if self.metrics.tokens_processed == 1:
                self.metrics.avg_processing_time_ms = proc_time
            else:
                # Exponential moving average
                alpha = 0.1
                self.metrics.avg_processing_time_ms = (
                    alpha * proc_time + (1 - alpha) * self.metrics.avg_processing_time_ms
                )
            
            # Update score distribution
            score = token_stats.score
            if score < 2:
                self.metrics.score_distribution["0-2"] += 1
            elif score < 4:
                self.metrics.score_distribution["2-4"] += 1
            elif score < 6:
                self.metrics.score_distribution["4-6"] += 1
            elif score < 8:
                self.metrics.score_distribution["6-8"] += 1
            else:
                self.metrics.score_distribution["8-10"] += 1
            
            # Track signals
            if token_stats.is_signal:
                self.metrics.signals_generated += 1
                self.metrics.recent_signals.append({
                    "mint": token_stats.mint,
                    "score": token_stats.score,
                    "lp_sol": token_stats.lp_sol,
                    "timestamp": token_stats.timestamp,
                    "source": token_stats.source
                })
                
                # Update hourly stats
                hour = int(time.time() // 3600)
                self.hourly_stats[hour]["signals"] += 1
            
            # Add to recent tokens
            self.metrics.recent_tokens.append({
                "mint": token_stats.mint[:8] + "...",  # Truncated for privacy
                "score": token_stats.score,
                "lp_sol": token_stats.lp_sol,
                "timestamp": token_stats.timestamp,
                "is_signal": token_stats.is_signal,
                "source": token_stats.source
            })
    
    async def record_error(self, error_type: str, details: str = "") -> None:
        """Record an error occurrence."""
        async with self._lock:
            self.metrics.errors_count += 1
            
            self.metrics.recent_errors.append({
                "type": error_type,
                "details": details[:100],  # Truncate long error messages
                "timestamp": time.time()
            })
            
            # Update hourly stats
            hour = int(time.time() // 3600)
            self.hourly_stats[hour]["errors"] += 1
    
    async def record_queue_size(self, current_size: int) -> None:
        """Record current queue size."""
        async with self._lock:
            self.metrics.queue_size_current = current_size
            self.metrics.queue_size_max = max(self.metrics.queue_size_max, current_size)
    
    async def record_api_health(self, api_name: str, status: str, response_time_ms: float = 0, error: bool = False) -> None:
        """Record API health status."""
        async with self._lock:
            if api_name in self.metrics.api_health:
                api_stats = self.metrics.api_health[api_name]
                api_stats["status"] = status
                api_stats["last_check"] = time.time()
                if response_time_ms > 0:
                    api_stats["response_time_ms"] = response_time_ms
                if error:
                    api_stats["error_count"] = api_stats.get("error_count", 0) + 1
    
    async def record_processing_time(self, component: str, time_ms: float) -> None:
        """Record processing time for a specific component."""
        async with self._lock:
            if component not in self.metrics.processing_times:
                self.metrics.processing_times[component] = []
            times = self.metrics.processing_times[component]
            times.append(time_ms)
            
            # Keep only recent times
            if len(times) > 100:
                times.pop(0)
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status."""
        async with self._lock:
            now = time.time()
            uptime_seconds = now - self.metrics.start_time
            
            # Calculate rates (per hour)
            tokens_per_hour = (self.metrics.tokens_processed / uptime_seconds * 3600) if uptime_seconds > 0 else 0
            signals_per_hour = (self.metrics.signals_generated / uptime_seconds * 3600) if uptime_seconds > 0 else 0
            error_rate = (self.metrics.errors_count / max(self.metrics.tokens_processed, 1)) * 100
            
            # Signal rate
            signal_rate = (self.metrics.signals_generated / max(self.metrics.tokens_processed, 1)) * 100
            
            # Recent activity (last hour)
            recent_hour = now - 3600
            recent_activity = {
                "tokens_last_hour": len([t for t in self.metrics.recent_tokens if t["timestamp"] > recent_hour]),
                "signals_last_hour": len([s for s in self.metrics.recent_signals if s["timestamp"] > recent_hour]),
                "errors_last_hour": len([e for e in self.metrics.recent_errors if e["timestamp"] > recent_hour])
            }
            
            return {
                "status": "healthy" if error_rate < 10 and self.metrics.tokens_processed > 0 else "degraded",
                "uptime_seconds": uptime_seconds,
                "uptime_human": self._format_uptime(uptime_seconds),
            "counters": {
                "tokens_seen": self.metrics.tokens_seen,
                "tokens_processed": self.metrics.tokens_processed,
                "signals_generated": self.metrics.signals_generated,
                "errors_count": self.metrics.errors_count,
                "webhook_requests": self.metrics.webhook_requests
            },
                "rates": {
                    "tokens_per_hour": round(tokens_per_hour, 1),
                    "signals_per_hour": round(signals_per_hour, 1),
                    "signal_rate_percent": round(signal_rate, 2),
                    "error_rate_percent": round(error_rate, 2)
                },
                "performance": {
                    "avg_processing_time_ms": round(self.metrics.avg_processing_time_ms, 1),
                    "max_processing_time_ms": round(self.metrics.max_processing_time_ms, 1),
                    "queue_size_current": self.metrics.queue_size_current,
                    "queue_size_max": self.metrics.queue_size_max
                },
                "recent_activity": recent_activity,
                "score_distribution": self.metrics.score_distribution,
                "api_health": self.metrics.api_health
            }
    
    async def get_recent_signals(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent signals for monitoring."""
        async with self._lock:
            return list(self.metrics.recent_signals)[-limit:]
    
    async def get_recent_tokens(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent processed tokens."""
        async with self._lock:
            return list(self.metrics.recent_tokens)[-limit:]
    
    async def get_hourly_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get hourly statistics."""
        async with self._lock:
            current_hour = int(time.time() // 3600)
            stats = {}
            
            for i in range(hours):
                hour = current_hour - i
                hour_data = self.hourly_stats.get(hour, {"tokens": 0, "signals": 0, "errors": 0})
                # Convert hour back to readable format
                hour_str = time.strftime("%Y-%m-%d %H:00", time.gmtime(hour * 3600))
                stats[hour_str] = hour_data
            
            return stats
    
    def _format_uptime(self, seconds: float) -> str:
        """Format uptime in human readable format."""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"

    async def get_metrics(self) -> Dict[str, Any]:
        """Return raw metrics snapshot suitable for /metrics endpoint."""
        async with self._lock:
            # Shallow copies to avoid mutation while serializing
            return {
                "start_time": self.metrics.start_time,
                "counters": {
                    "tokens_seen": self.metrics.tokens_seen,
                    "tokens_processed": self.metrics.tokens_processed,
                    "signals_generated": self.metrics.signals_generated,
                    "errors_count": self.metrics.errors_count,
                    "webhook_requests": self.metrics.webhook_requests,
                },
                "performance": {
                    "avg_processing_time_ms": self.metrics.avg_processing_time_ms,
                    "max_processing_time_ms": self.metrics.max_processing_time_ms,
                    "queue_size_current": self.metrics.queue_size_current,
                    "queue_size_max": self.metrics.queue_size_max,
                },
                "score_distribution": dict(self.metrics.score_distribution),
                "api_health": dict(self.metrics.api_health),
                "recent": {
                    "tokens": list(self.metrics.recent_tokens),
                    "signals": list(self.metrics.recent_signals),
                    "errors": list(self.metrics.recent_errors),
                },
                "hourly": self.hourly_stats.copy(),
            }


# Global metrics collector instance
metrics_collector = MetricsCollector()


__all__ = ["TokenStats", "MetricsCollector", "metrics_collector"]
