"""
Enhanced Observability Module

Provides structured logging, metrics collection, and distributed tracing capabilities.
Improves upon existing logger_utils.py with better structure and context management.
"""
import time
import json
from typing import Any, Dict, Optional
from contextlib import contextmanager
from datetime import datetime
from enum import Enum


class LogLevel(Enum):
    """Log severity levels"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class StructuredLogger:
    """
    Enhanced structured logger with context management.
    
    Provides:
    - Structured JSON logging
    - Context propagation
    - Sensitive data masking
    - Performance timing
    """
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self._context: Dict[str, Any] = {}
    
    def add_context(self, **kwargs):
        """Add persistent context to all logs"""
        self._context.update(kwargs)
    
    def clear_context(self):
        """Clear all context"""
        self._context.clear()
    
    def log(
        self,
        level: LogLevel,
        message: str,
        **extra: Any
    ):
        """
        Log a structured message.
        
        Args:
            level: Log severity
            message: Human-readable message
            **extra: Additional structured data
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "service": self.service_name,
            "level": level.value,
            "message": message,
            **self._context,
            **extra
        }
        
        # Mask sensitive data
        log_entry = self._mask_sensitive(log_entry)
        
        # Write to appropriate target
        self._write_log(log_entry)
    
    def debug(self, message: str, **extra):
        """Log debug message"""
        self.log(LogLevel.DEBUG, message, **extra)
    
    def info(self, message: str, **extra):
        """Log info message"""
        self.log(LogLevel.INFO, message, **extra)
    
    def warning(self, message: str, **extra):
        """Log warning message"""
        self.log(LogLevel.WARNING, message, **extra)
    
    def error(self, message: str, **extra):
        """Log error message"""
        self.log(LogLevel.ERROR, message, **extra)
    
    def critical(self, message: str, **extra):
        """Log critical message"""
        self.log(LogLevel.CRITICAL, message, **extra)
    
    @contextmanager
    def operation(self, operation_name: str, **context):
        """
        Context manager for timing operations.
        
        Usage:
            with logger.operation("fetch_token_stats", token="abc123"):
                # do work
                pass
        """
        operation_id = f"{operation_name}_{int(time.time() * 1000)}"
        start_time = time.time()
        
        self.info(
            f"Starting {operation_name}",
            operation_id=operation_id,
            operation=operation_name,
            phase="start",
            **context
        )
        
        try:
            yield
            duration_ms = (time.time() - start_time) * 1000
            self.info(
                f"Completed {operation_name}",
                operation_id=operation_id,
                operation=operation_name,
                phase="complete",
                duration_ms=round(duration_ms, 2),
                **context
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.error(
                f"Failed {operation_name}",
                operation_id=operation_id,
                operation=operation_name,
                phase="error",
                duration_ms=round(duration_ms, 2),
                error=str(e),
                error_type=type(e).__name__,
                **context
            )
            raise
    
    def _mask_sensitive(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mask sensitive fields in log data"""
        from app.logger_utils import _sanitize_obj
        return _sanitize_obj(data)
    
    def _write_log(self, log_entry: Dict[str, Any]):
        """Write log entry to appropriate destination"""
        try:
            # Write to JSONL file
            from app.logger_utils import write_jsonl
            write_jsonl("process.jsonl", log_entry)
        except Exception:
            # Fallback to stdout
            try:
                print(json.dumps(log_entry))
            except Exception:
                pass


class MetricsCollector:
    """
    Collects and aggregates application metrics.
    
    Provides:
    - Counter metrics
    - Gauge metrics
    - Histogram metrics
    - Time-series aggregation
    """
    
    def __init__(self):
        self._metrics: Dict[str, Any] = {}
    
    def increment(self, metric_name: str, value: int = 1, tags: Optional[Dict[str, str]] = None):
        """Increment a counter metric"""
        key = self._make_key(metric_name, tags)
        if key not in self._metrics:
            self._metrics[key] = {"type": "counter", "value": 0, "tags": tags or {}}
        self._metrics[key]["value"] += value
    
    def gauge(self, metric_name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """Set a gauge metric"""
        key = self._make_key(metric_name, tags)
        self._metrics[key] = {"type": "gauge", "value": value, "tags": tags or {}}
    
    def histogram(self, metric_name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """Record a histogram value"""
        key = self._make_key(metric_name, tags)
        if key not in self._metrics:
            self._metrics[key] = {"type": "histogram", "values": [], "tags": tags or {}}
        self._metrics[key]["values"].append(value)
    
    def get_snapshot(self) -> Dict[str, Any]:
        """Get current metrics snapshot"""
        snapshot = {}
        for key, metric in self._metrics.items():
            if metric["type"] == "histogram":
                # Calculate histogram stats
                values = metric["values"]
                if values:
                    snapshot[key] = {
                        "count": len(values),
                        "min": min(values),
                        "max": max(values),
                        "avg": sum(values) / len(values),
                        "tags": metric["tags"],
                    }
            else:
                snapshot[key] = metric
        return snapshot
    
    def reset(self):
        """Reset all metrics"""
        self._metrics.clear()
    
    @staticmethod
    def _make_key(metric_name: str, tags: Optional[Dict[str, str]]) -> str:
        """Create a unique key for a metric with tags"""
        if not tags:
            return metric_name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{metric_name}{{{tag_str}}}"


class TraceContext:
    """
    Distributed tracing context.
    
    Propagates trace IDs across operations for correlation.
    """
    
    def __init__(self, trace_id: Optional[str] = None):
        self.trace_id = trace_id or self._generate_trace_id()
        self.span_stack = []
    
    @staticmethod
    def _generate_trace_id() -> str:
        """Generate a unique trace ID"""
        import uuid
        return str(uuid.uuid4())
    
    @contextmanager
    def span(self, span_name: str):
        """Create a trace span"""
        span_id = f"{span_name}_{len(self.span_stack)}"
        self.span_stack.append(span_id)
        start_time = time.time()
        
        try:
            yield {"trace_id": self.trace_id, "span_id": span_id}
        finally:
            duration = time.time() - start_time
            self.span_stack.pop()
            
            # Log span completion
            try:
                get_logger().info(
                    f"Span completed: {span_name}",
                    trace_id=self.trace_id,
                    span_id=span_id,
                    span_name=span_name,
                    duration_ms=round(duration * 1000, 2)
                )
            except Exception:
                pass


# ============================================================================
# GLOBAL INSTANCES
# ============================================================================

_logger: Optional[StructuredLogger] = None
_metrics: Optional[MetricsCollector] = None


def get_logger(service_name: str = "callsbot") -> StructuredLogger:
    """Get the global structured logger"""
    global _logger
    if _logger is None:
        _logger = StructuredLogger(service_name)
    return _logger


def get_metrics() -> MetricsCollector:
    """Get the global metrics collector"""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def log_alert_event(token: str, score: int, conviction: str, **extra):
    """Log an alert event with standard structure"""
    get_logger().info(
        f"Alert sent for {token}",
        event_type="alert",
        token_address=token,
        final_score=score,
        conviction_type=conviction,
        **extra
    )


def log_api_call(provider: str, endpoint: str, status_code: Optional[int], duration_ms: float):
    """Log an API call with timing"""
    get_logger().info(
        f"API call to {provider}",
        event_type="api_call",
        provider=provider,
        endpoint=endpoint,
        status_code=status_code,
        duration_ms=duration_ms,
        success=status_code is not None and 200 <= status_code < 300
    )
    
    # Also record metrics
    get_metrics().increment(
        "api_calls_total",
        tags={"provider": provider, "status": str(status_code or "error")}
    )
    get_metrics().histogram(
        "api_call_duration_ms",
        duration_ms,
        tags={"provider": provider}
    )


def log_trade_event(
    token: str,
    action: str,  # "open", "close", "rebalance"
    usd_size: float,
    **extra
):
    """Log a trading event"""
    get_logger().info(
        f"Trade {action} for {token}",
        event_type="trade",
        token_address=token,
        action=action,
        usd_size=usd_size,
        **extra
    )
    
    # Record metrics
    get_metrics().increment(
        "trades_total",
        tags={"action": action}
    )


def log_performance_update(
    token: str,
    entry_price: float,
    current_price: float,
    pnl_pct: float,
    **extra
):
    """Log a performance update"""
    get_logger().info(
        f"Performance update for {token}",
        event_type="performance",
        token_address=token,
        entry_price=entry_price,
        current_price=current_price,
        pnl_pct=pnl_pct,
        **extra
    )


# ============================================================================
# HEALTH CHECK
# ============================================================================

def get_observability_health() -> Dict[str, Any]:
    """Get health status of observability systems"""
    return {
        "logger": {
            "initialized": _logger is not None,
            "service": _logger.service_name if _logger else None,
        },
        "metrics": {
            "initialized": _metrics is not None,
            "metric_count": len(_metrics._metrics) if _metrics else 0,
        },
    }

