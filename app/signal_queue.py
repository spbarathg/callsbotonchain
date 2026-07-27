"""
Priority Signal Queue - Redis-backed intelligent signal processing

Implements:
- Priority-based signal queuing (not immediate execution)
- Scoring on ingestion, ranking by score
- Top-N processing per time window
- Token deduplication across channels
- Burst protection and API rate limit awareness

Design Philosophy:
- Quality over quantity
- API calls are scarce resources
- Most memecoin signals are trash - filter aggressively
"""
import os
import time
import json
import threading
import hashlib
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field, asdict
from collections import deque
import heapq

# Try Redis, fallback to in-memory
_USE_REDIS = os.getenv("USE_REDIS", "true").strip().lower() == "true"
_REDIS_URL = os.getenv("REDIS_URL", "").strip() if _USE_REDIS else ""
_redis_client = None

if _REDIS_URL:
    try:
        import redis
        _redis_client = redis.from_url(_REDIS_URL, decode_responses=True)
    except Exception:
        _redis_client = None


@dataclass
class QueuedSignal:
    """Represents a signal in the priority queue"""
    token_address: str
    raw_score: float  # Initial ATM-derived score (higher = better)
    timestamp: float
    source: str  # ATM channel ID
    message_id: Optional[int] = None
    atm_meta: Dict[str, Any] = field(default_factory=dict)
    tx_data: Dict[str, Any] = field(default_factory=dict)
    dedup_key: str = ""
    
    def __post_init__(self):
        if not self.dedup_key:
            self.dedup_key = self._generate_dedup_key()
    
    def _generate_dedup_key(self) -> str:
        """Generate unique key for deduplication"""
        # Dedup by token address only (same token from different channels = one signal)
        return f"sig:{self.token_address}"
    
    def __lt__(self, other):
        """For heap ordering - higher score = higher priority (negative for min-heap)"""
        return self.raw_score > other.raw_score


class SignalPriorityQueue:
    """
    Thread-safe priority queue for trading signals.
    
    Features:
    - Score-based ranking (highest score processed first)
    - Time-window batching (process top-N every X seconds)
    - Token deduplication (same token from multiple channels = 1 signal)
    - Burst protection (max signals per time window)
    - Redis-backed persistence (survives restarts)
    """
    
    # Configuration
    QUEUE_KEY = "callsbot:signal_queue"
    SEEN_SET_KEY = "callsbot:seen_tokens"
    METRICS_KEY = "callsbot:queue_metrics"
    
    def __init__(self):
        # In-memory queue (heap-based priority queue)
        self._queue: List[QueuedSignal] = []
        self._lock = threading.Lock()
        
        # Deduplication tracking
        self._seen_tokens: Dict[str, float] = {}  # token -> timestamp
        self._seen_ttl_sec = int(os.getenv("SIGNAL_DEDUP_TTL_SEC", "300"))  # 5 min default
        
        # Rate limiting for queue processing
        self._process_times: deque = deque()
        self._max_process_per_min = int(os.getenv("SIGNAL_MAX_PROCESS_PER_MIN", "30"))
        
        # Burst protection
        self._burst_window_sec = int(os.getenv("SIGNAL_BURST_WINDOW_SEC", "10"))
        self._max_per_burst = int(os.getenv("SIGNAL_MAX_PER_BURST", "5"))
        
        # Queue limits
        self._max_queue_size = int(os.getenv("SIGNAL_MAX_QUEUE_SIZE", "100"))
        
        # Metrics
        self._metrics = {
            "total_enqueued": 0,
            "total_processed": 0,
            "total_deduplicated": 0,
            "total_dropped_burst": 0,
            "total_dropped_queue_full": 0,
            "total_dropped_low_score": 0,
            "last_metrics_log": time.time(),
        }
        self._metrics_log_interval = int(os.getenv("SIGNAL_METRICS_LOG_SEC", "60"))
        
        # Score threshold for queue admission
        self._min_queue_score = float(os.getenv("SIGNAL_MIN_QUEUE_SCORE", "3.0"))
        
        # Load from Redis if available
        self._load_from_redis()
    
    def _load_from_redis(self):
        """Load queue state from Redis on startup"""
        if not _redis_client:
            return
        
        try:
            # Load queued signals
            raw_queue = _redis_client.lrange(self.QUEUE_KEY, 0, -1)
            for raw in raw_queue:
                try:
                    data = json.loads(raw)
                    signal = QueuedSignal(**data)
                    heapq.heappush(self._queue, signal)
                except Exception:
                    continue
            
            # Load seen tokens
            seen_raw = _redis_client.hgetall(self.SEEN_SET_KEY)
            for token, ts_str in seen_raw.items():
                try:
                    self._seen_tokens[token] = float(ts_str)
                except Exception:
                    continue
            
            print(f"[SIGNAL_QUEUE] Loaded {len(self._queue)} signals from Redis", flush=True)
        except Exception as e:
            print(f"[SIGNAL_QUEUE] Redis load failed: {e}", flush=True)
    
    def _persist_to_redis(self, signal: QueuedSignal):
        """Persist signal to Redis"""
        if not _redis_client:
            return
        
        try:
            # Convert to JSON-serializable dict
            data = {
                "token_address": signal.token_address,
                "raw_score": signal.raw_score,
                "timestamp": signal.timestamp,
                "source": signal.source,
                "message_id": signal.message_id,
                "atm_meta": signal.atm_meta,
                "tx_data": signal.tx_data,
                "dedup_key": signal.dedup_key,
            }
            _redis_client.lpush(self.QUEUE_KEY, json.dumps(data))
            _redis_client.ltrim(self.QUEUE_KEY, 0, self._max_queue_size - 1)
        except Exception:
            pass
    
    def _mark_seen_redis(self, token: str, ts: float):
        """Mark token as seen in Redis"""
        if not _redis_client:
            return
        
        try:
            _redis_client.hset(self.SEEN_SET_KEY, token, str(ts))
            _redis_client.expire(self.SEEN_SET_KEY, self._seen_ttl_sec * 2)
        except Exception:
            pass
    
    def _remove_from_redis(self, signal: QueuedSignal):
        """Remove processed signal from Redis"""
        if not _redis_client:
            return
        
        try:
            data = {
                "token_address": signal.token_address,
                "raw_score": signal.raw_score,
                "timestamp": signal.timestamp,
                "source": signal.source,
                "message_id": signal.message_id,
                "atm_meta": signal.atm_meta,
                "tx_data": signal.tx_data,
                "dedup_key": signal.dedup_key,
            }
            _redis_client.lrem(self.QUEUE_KEY, 1, json.dumps(data))
        except Exception:
            pass
    
    def enqueue(self, signal: QueuedSignal) -> Tuple[bool, str]:
        """
        Add signal to priority queue.
        
        Returns:
            (success, reason) - True if enqueued, False with rejection reason
        """
        now = time.time()
        
        with self._lock:
            # 1. Score threshold check (fast rejection)
            if signal.raw_score < self._min_queue_score:
                self._metrics["total_dropped_low_score"] += 1
                return False, f"score {signal.raw_score:.1f} below threshold {self._min_queue_score}"
            
            # 2. Deduplication check
            last_seen = self._seen_tokens.get(signal.token_address, 0)
            if (now - last_seen) < self._seen_ttl_sec:
                self._metrics["total_deduplicated"] += 1
                return False, f"duplicate (seen {now - last_seen:.0f}s ago)"
            
            # 3. Queue capacity check
            if len(self._queue) >= self._max_queue_size:
                # Check if new signal beats lowest in queue
                if self._queue and signal.raw_score > self._queue[-1].raw_score:
                    # Pop lowest, add new (maintain priority)
                    dropped = heapq.heapreplace(self._queue, signal)
                    self._remove_from_redis(dropped)
                else:
                    self._metrics["total_dropped_queue_full"] += 1
                    return False, f"queue full ({len(self._queue)}/{self._max_queue_size})"
            else:
                heapq.heappush(self._queue, signal)
            
            # 4. Burst protection (check recent enqueues)
            recent_burst = sum(
                1 for s in self._queue 
                if (now - s.timestamp) < self._burst_window_sec
            )
            if recent_burst > self._max_per_burst:
                self._metrics["total_dropped_burst"] += 1
                # Still enqueued, but log warning
                print(f"[SIGNAL_QUEUE] ⚠️ Burst detected: {recent_burst} signals in {self._burst_window_sec}s", flush=True)
            
            # 5. Mark as seen
            self._seen_tokens[signal.token_address] = now
            self._mark_seen_redis(signal.token_address, now)
            
            # 6. Persist to Redis
            self._persist_to_redis(signal)
            
            # 7. Update metrics
            self._metrics["total_enqueued"] += 1
            
            # 8. Cleanup old seen entries
            self._cleanup_seen()
            
            # 9. Log metrics periodically
            self._log_metrics()
            
            return True, f"enqueued (score: {signal.raw_score:.1f}, queue: {len(self._queue)})"
    
    def dequeue(self) -> Optional[QueuedSignal]:
        """
        Get highest-priority signal from queue.
        
        Respects rate limiting - returns None if rate limited.
        """
        now = time.time()
        
        with self._lock:
            # Rate limiting check
            self._process_times = deque(
                t for t in self._process_times if (now - t) < 60
            )
            
            if len(self._process_times) >= self._max_process_per_min:
                return None  # Rate limited
            
            if not self._queue:
                return None
            
            # Pop highest priority (min-heap with negative scores)
            signal = heapq.heappop(self._queue)
            
            # Record processing time
            self._process_times.append(now)
            
            # Remove from Redis
            self._remove_from_redis(signal)
            
            # Update metrics
            self._metrics["total_processed"] += 1
            
            return signal
    
    def peek(self, n: int = 5) -> List[QueuedSignal]:
        """Peek at top N signals without removing"""
        with self._lock:
            # Sort by score (descending) and return top N
            sorted_queue = sorted(self._queue, key=lambda s: s.raw_score, reverse=True)
            return sorted_queue[:n]
    
    def size(self) -> int:
        """Get current queue size"""
        with self._lock:
            return len(self._queue)
    
    def clear(self):
        """Clear the queue"""
        with self._lock:
            self._queue.clear()
            self._seen_tokens.clear()
            if _redis_client:
                try:
                    _redis_client.delete(self.QUEUE_KEY)
                    _redis_client.delete(self.SEEN_SET_KEY)
                except Exception:
                    pass
    
    def _cleanup_seen(self):
        """Remove expired entries from seen set"""
        now = time.time()
        expired = [
            token for token, ts in self._seen_tokens.items()
            if (now - ts) > self._seen_ttl_sec
        ]
        for token in expired:
            self._seen_tokens.pop(token, None)
    
    def _log_metrics(self):
        """Log metrics periodically"""
        now = time.time()
        if (now - self._metrics["last_metrics_log"]) < self._metrics_log_interval:
            return
        
        self._metrics["last_metrics_log"] = now
        print(
            f"[SIGNAL_QUEUE] Metrics: "
            f"queue={len(self._queue)} "
            f"enqueued={self._metrics['total_enqueued']} "
            f"processed={self._metrics['total_processed']} "
            f"dedup={self._metrics['total_deduplicated']} "
            f"dropped_score={self._metrics['total_dropped_low_score']} "
            f"dropped_burst={self._metrics['total_dropped_burst']} "
            f"dropped_full={self._metrics['total_dropped_queue_full']}",
            flush=True
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get queue metrics"""
        with self._lock:
            return {
                **self._metrics,
                "current_queue_size": len(self._queue),
                "seen_tokens_count": len(self._seen_tokens),
                "rate_limit_used": len(self._process_times),
                "rate_limit_max": self._max_process_per_min,
            }


# Global instance
_signal_queue: Optional[SignalPriorityQueue] = None


def get_signal_queue() -> SignalPriorityQueue:
    """Get or create global signal queue instance"""
    global _signal_queue
    if _signal_queue is None:
        _signal_queue = SignalPriorityQueue()
    return _signal_queue


def calculate_atm_signal_score(atm_meta: Dict[str, Any]) -> float:
    """
    Calculate raw score from ATM metadata for queue prioritization.
    
    This is DIFFERENT from the full token scoring - it uses only ATM data
    and is designed for fast, pre-API filtering.
    
    Scoring Components:
    1. Pro-Trader Net Flow (+/- points based on in - out)
    2. Buy/Sell Volume Ratio (positive = more buying)
    3. Holder Distribution (lower top10 = better)
    4. Short-term Momentum (5m, 1h price changes)
    5. Audit Safety Flags (not_freezable, not_mintable)
    
    Returns:
        Score 0-10 (higher = better priority)
    """
    if not atm_meta:
        return 0.0
    
    score = 0.0
    score_breakdown: List[str] = []
    
    # ===== 1. PRO-TRADER NET FLOW (0-3 points) =====
    pro_traders = atm_meta.get("pro_traders") or {}
    wallets_in = pro_traders.get("wallets_in", 0) or 0
    wallets_out = pro_traders.get("wallets_out", 0) or 0
    net_flow = wallets_in - wallets_out
    
    if net_flow >= 3:
        score += 3.0
        score_breakdown.append(f"pro_flow:+3 ({wallets_in}in/{wallets_out}out)")
    elif net_flow >= 1:
        score += 2.0
        score_breakdown.append(f"pro_flow:+2 ({wallets_in}in/{wallets_out}out)")
    elif net_flow == 0 and wallets_in > 0:
        score += 1.0
        score_breakdown.append(f"pro_flow:+1 (neutral)")
    elif net_flow < 0:
        score -= 1.0
        score_breakdown.append(f"pro_flow:-1 (EXITING)")
    
    # ===== 2. BUY/SELL VOLUME RATIO (0-2 points) =====
    buy_vol = atm_meta.get("volume_buy") or {}
    sell_vol = atm_meta.get("volume_sell") or {}
    
    # Use 1h volumes for ratio
    buy_1h = buy_vol.get("1h", 0) or buy_vol.get("5m", 0) * 12 or 0
    sell_1h = sell_vol.get("1h", 0) or sell_vol.get("5m", 0) * 12 or 0
    
    if sell_1h > 0:
        ratio = buy_1h / sell_1h
        if ratio >= 1.5:
            score += 2.0
            score_breakdown.append(f"buy_ratio:+2 ({ratio:.1f}x)")
        elif ratio >= 1.1:
            score += 1.0
            score_breakdown.append(f"buy_ratio:+1 ({ratio:.1f}x)")
        elif ratio < 0.7:
            score -= 1.0
            score_breakdown.append(f"buy_ratio:-1 (heavy selling)")
    
    # ===== 3. HOLDER DISTRIBUTION (0-2 points) =====
    holders_analytics = atm_meta.get("holders_analytics") or {}
    top10 = (
        holders_analytics.get("top10_percent") or 
        atm_meta.get("top10_percent") or 0
    )
    top50 = holders_analytics.get("top50_percent", 0) or 0
    
    if top10 > 0:
        if top10 <= 20:
            score += 2.0
            score_breakdown.append(f"distrib:+2 (top10={top10:.0f}%)")
        elif top10 <= 35:
            score += 1.0
            score_breakdown.append(f"distrib:+1 (top10={top10:.0f}%)")
        elif top10 > 50:
            score -= 1.0
            score_breakdown.append(f"distrib:-1 (top10={top10:.0f}% - whale risk)")
    
    # ===== 4. SHORT-TERM MOMENTUM (0-2 points) =====
    price_change = atm_meta.get("price_change") or {}
    change_5m = price_change.get("5m", 0) or 0
    change_1h = price_change.get("1h", 0) or 0
    
    # Reward early momentum, penalize late entry
    if 5 <= change_5m <= 50:
        score += 1.0
        score_breakdown.append(f"momentum:+1 (5m={change_5m:.0f}%)")
    elif change_5m > 100:
        score -= 0.5
        score_breakdown.append(f"momentum:-0.5 (5m={change_5m:.0f}% - late)")
    
    if 10 <= change_1h <= 100:
        score += 1.0
        score_breakdown.append(f"1h_momentum:+1 ({change_1h:.0f}%)")
    elif change_1h > 200:
        score -= 0.5
        score_breakdown.append(f"1h_momentum:-0.5 ({change_1h:.0f}% - FOMO)")
    
    # ===== 5. AUDIT SAFETY FLAGS (0-1 points) =====
    audit = atm_meta.get("audit") or {}
    if audit.get("not_mintable") and audit.get("not_freezable"):
        score += 1.0
        score_breakdown.append("audit:+1 (safe)")
    elif audit.get("not_freezable"):
        score += 0.5
        score_breakdown.append("audit:+0.5 (not freezable)")
    
    # ===== 6. HOLDER COUNT BONUS (0-1 points) =====
    holder_count = atm_meta.get("holder_count", 0) or 0
    if holder_count >= 500:
        score += 1.0
        score_breakdown.append(f"holders:+1 ({holder_count})")
    elif holder_count >= 200:
        score += 0.5
        score_breakdown.append(f"holders:+0.5 ({holder_count})")
    elif holder_count < 50 and holder_count > 0:
        score -= 0.5
        score_breakdown.append(f"holders:-0.5 ({holder_count} - early/risky)")
    
    # ===== 7. MARKET CAP SWEET SPOT (0-1 points) =====
    market_cap = atm_meta.get("market_cap_usd", 0) or 0
    if 50000 <= market_cap <= 200000:
        score += 1.0
        score_breakdown.append(f"mcap:+1 (${market_cap/1000:.0f}k sweet spot)")
    elif market_cap > 500000:
        score -= 0.5
        score_breakdown.append(f"mcap:-0.5 (${market_cap/1000:.0f}k - large)")
    elif market_cap < 20000 and market_cap > 0:
        score -= 0.5
        score_breakdown.append(f"mcap:-0.5 (${market_cap/1000:.0f}k - micro)")
    
    # Cap score to 0-10 range
    final_score = max(0.0, min(10.0, score))
    
    # Log breakdown for debugging
    if os.getenv("SIGNAL_SCORE_DEBUG", "false").lower() == "true":
        print(f"[SIGNAL_SCORE] {final_score:.1f}/10 | {' | '.join(score_breakdown)}", flush=True)
    
    return final_score
