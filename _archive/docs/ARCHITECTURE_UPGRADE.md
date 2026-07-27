# Trading Bot Architecture Upgrade

## Overview

This upgrade transforms the bot from a **reactive signal follower** into a **rate-limit-aware, priority-driven, high-signal extraction engine**.

## Core Changes

### 1. Priority Signal Queue (`app/signal_queue.py`)

**Problem**: Signals were processed immediately as they arrived, causing API overload during burst traffic.

**Solution**: Redis-backed priority queue that:
- Scores signals on ingestion using ATM metadata
- Ranks by score (highest processed first)
- Deduplicates tokens across channels
- Enforces burst limits (max 5 signals per 10s window)
- Drops low-score signals when queue is full

**Key Config**:
```env
ATM_USE_SIGNAL_QUEUE=true
SIGNAL_DEDUP_TTL_SEC=300
SIGNAL_MAX_PROCESS_PER_MIN=30
SIGNAL_MAX_PER_BURST=5
SIGNAL_MIN_QUEUE_SCORE=3.0
```

### 2. ATM-Enhanced Scoring (`app/atm_scoring.py`)

**Problem**: Rich ATM data (pro-traders, buy/sell volumes) was parsed but not used in scoring.

**Solution**: New scoring engine that integrates:
- **Pro-Trader Net Flow**: `wallets_in - wallets_out` (weight: 1.5x)
- **Buy/Sell Pressure**: Volume ratio across 5m/1h/6h (weight: 1.2x)
- **Holder Distribution**: Top10/Top50/Top100 concentration (weight: 1.0x)
- **Short-Term Momentum**: 5m and 1h price changes (weight: 1.0x)
- **Audit Flags**: not_mintable, not_freezable (weight: 0.5x)
- **Volume Activity**: Absolute trading volume (weight: 0.8x)

**Key Thresholds**:
```env
ATM_PRO_NET_FLOW_EXCELLENT=5      # +3 score bonus
ATM_PRO_NET_FLOW_GOOD=2           # +2 score bonus
ATM_BUY_SELL_RATIO_EXCELLENT=2.0  # +2 score bonus
ATM_TOP10_EXCELLENT=15            # +2 score bonus
ATM_TOP10_WARNING=40              # -1.5 score penalty
```

### 3. Queue Processor (`app/queue_processor.py`)

**Purpose**: Consumes signals from priority queue in order of score.

**Features**:
- Respects Jupiter cooldown state
- Rate-limited processing (configurable RPS)
- Batch processing with configurable intervals
- Full metrics and logging

**Key Config**:
```env
QUEUE_MIN_PROCESS_INTERVAL_SEC=2.0
QUEUE_MAX_PROCESS_PER_BATCH=3
QUEUE_BATCH_INTERVAL_SEC=10.0
```

### 4. Dynamic Position Controller (`app/position_controller.py`)

**Problem**: Fixed max concurrent positions regardless of API health.

**Solution**: Dynamic scaling based on:
- **API Health Score**: 429 rate + latency tracking
- **Queue Depth**: Processing backlog awareness
- **Daily Limits**: USD and trade count caps

**Position Scaling Formula**:
- API Health ≥90%: Use max positions (15)
- API Health ≥70%: Use base positions (10)
- API Health ≥50%: Reduce to 70% of base
- API Health <50%: Use minimum positions (3)

**Key Config**:
```env
POSITION_BASE_MAX=10
POSITION_MIN=3
POSITION_MAX=15
POSITION_DAILY_MAX_USD=500.0
POSITION_DAILY_MAX_TRADES=20
```

### 5. Jupiter Client Enhancements

**Changes**:
- Records latency to position controller
- Records 429s to position controller
- Enables adaptive position scaling based on API health

### 6. Observability Dashboard (`app/observability.py`)

**Purpose**: Full visibility into system behavior.

**Tracked Metrics**:
- Signal rejection reasons (with counts)
- Score distributions (queue vs final)
- API call rates per service
- Trade performance by score bucket
- Queue depth over time

**Output**:
- Real-time console dashboard every 60s
- JSONL log file for post-hoc analysis

---

## API Rate Limit Analysis

### Jupiter Pro (~9 RPS effective)

| Operation | Priority | Est. Calls/Trade | Notes |
|-----------|----------|------------------|-------|
| Sell/Exit | HIGH | 2-4 | Quote + Swap + retries |
| Buy/Entry | MEDIUM | 2-3 | Quote + Swap |
| Validation | MEDIUM | 1 | Route check before queue |
| Monitoring | LOW | 0.5/pos/min | Price oracle |

**Safe Concurrent Monitoring**:
- With 9 RPS budget: ~8-10 positions max
- Each position needs ~0.5 calls/min for monitoring
- Exits consume 2-4 calls (prioritized)
- New entries consume 2-3 calls

### Recommended Settings

```env
# Conservative (safe for 10 positions)
JUP_PRO_RPM_LIMIT=540
JUP_MAX_CONCURRENT=8
POSITION_BASE_MAX=10

# Aggressive (15 positions, may hit limits)
JUP_PRO_RPM_LIMIT=540
JUP_MAX_CONCURRENT=12
POSITION_BASE_MAX=15
```

---

## Burst Handling Strategy

**Scenario**: 11 ATM channels fire simultaneously

**Old Behavior**: 11 immediate Jupiter calls → rate limit → failures

**New Behavior**:
1. Signals scored on arrival using ATM metadata
2. Top 5 queued (burst limit)
3. Duplicates deduplicated (same token = 1 signal)
4. Queue processes top 3 every 10 seconds
5. If Jupiter in cooldown → processing pauses

**Result**: Controlled API usage, highest-EV trades processed first

---

## Signal Quality Filtering

### Pre-Queue Filters (Fast Rejection)
1. **Pro-trader outflow**: Reject if `wallets_out > wallets_in + 2`
2. **Heavy sell pressure**: Reject if buy/sell ratio < 0.5
3. **Score threshold**: Reject if ATM score < 3.0

### Post-Queue Filters (Full Validation)
1. Standard liquidity/market cap gates
2. Jupiter route validation
3. Full token scoring with ATM enhancement

---

## Configuration Summary

### Must-Have Settings
```env
# Enable new architecture
ATM_USE_SIGNAL_QUEUE=true
SIGNAL_MIN_QUEUE_SCORE=3.0

# Position limits
POSITION_BASE_MAX=10
POSITION_MAX=15
POSITION_DAILY_MAX_USD=500.0

# Jupiter Pro
JUPITER_API_KEY=your_key_here
JUP_PRO_RPM_LIMIT=540
```

### Tuning Parameters
```env
# More aggressive filtering (fewer, higher-quality trades)
SIGNAL_MIN_QUEUE_SCORE=5.0
ATM_PRO_NET_FLOW_GOOD=3

# Less aggressive (more trades, lower average quality)
SIGNAL_MIN_QUEUE_SCORE=2.0
SIGNAL_MAX_PROCESS_PER_MIN=45
```

---

## Monitoring

### Real-Time Dashboard
The observability module prints a dashboard every 60 seconds:
- Signal flow rates
- Top rejection reasons
- Score distributions
- API health metrics

### Log Files
- `data/logs/observability.jsonl` - All events
- `data/logs/trading.jsonl` - Trade lifecycle

### Key Metrics to Watch
1. **Queue depth**: Should stay < 20 normally
2. **Rejection rate**: High = filters working; too high = might miss opportunities
3. **API error rate**: Should be < 5%
4. **Win rate by score**: Score 8+ should have best performance

---

## Migration Notes

1. **Backward Compatible**: Set `ATM_USE_SIGNAL_QUEUE=false` to use legacy behavior
2. **Redis Required**: Signal queue uses Redis for persistence
3. **No Breaking Changes**: All existing config still works
4. **New Dependencies**: None (uses existing packages)
