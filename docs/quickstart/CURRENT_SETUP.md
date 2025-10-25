# Current Bot Setup - October 25, 2025

**Status:** 🟢 DEPLOYED & ACTIVE - ULTRA AGGRESSIVE MOONSHOT MODE
**Server:** `64.227.157.221`
**Last Updated:** October 25, 2025 17:24 UTC (22:54 IST)
**Trading Config:** Ultra Aggressive (35-50% trails, -35% stop loss)
**Analysis Basis:** 673 signals with full performance tracking (55.29% win rate)

---

## ⏰ TIMEZONE REFERENCE (IMPORTANT!)

**Server Time:** UTC (Coordinated Universal Time)  
**IST (India Standard Time):** UTC + 5:30 (5 hours 30 minutes ahead)

**Quick Conversion Examples:**
- **00:00 UTC** = **05:30 IST** (12 midnight UTC = 5:30 AM IST)
- **12:00 UTC** = **17:30 IST** (12 noon UTC = 5:30 PM IST)
- **18:00 UTC** = **23:30 IST** (6 PM UTC = 11:30 PM IST)
- **23:30 UTC** = **05:00 IST (next day)** (11:30 PM UTC = 5 AM next day IST)

**⚠️ COMMON MISTAKE:** IST is NOT UTC+5:00, it's UTC+5:30!  
When reading timestamps, always add **5 hours and 30 minutes** to UTC to get IST.

---

## 📍 IMPORTANT: Log & Database Locations

### ✅ Active Locations (Use These)
```bash
# Logs
/opt/callsbotonchain/deployment/data/logs/

# Databases
/opt/callsbotonchain/deployment/var/
```

### ❌ Deprecated Locations (Do Not Use)
```bash
# Old logs (empty, cleaned up)
/opt/callsbotonchain/data/logs/

# Old databases (empty)
/opt/callsbotonchain/var/
```

### 🔍 Quick Verification
```bash
# Run verification script
/opt/callsbotonchain/scripts/verify_logs.sh

# View active logs
tail -f /opt/callsbotonchain/deployment/data/logs/stdout.log

# Check API health
curl http://localhost/api/v2/quick-stats
```

**📖 Full Documentation:** See `/opt/callsbotonchain/LOG_LOCATIONS.md`

---

## 🏗️ SYSTEM ARCHITECTURE (CRITICAL FOR AI ASSISTANTS!)

### **⚠️ TWO SEPARATE SYSTEMS - DO NOT CONFUSE THEM!**

This bot has **TWO INDEPENDENT SYSTEMS** that work together:

#### **1. WORKER (Signal Detection Bot)** 
- **Container:** `callsbot-worker`
- **Purpose:** Monitors Telegram, scores tokens, sends signals to Redis
- **Config:** `app/config_unified.py`, `app/analyze_token.py`
- **Database:** `/opt/callsbotonchain/deployment/var/alerted_tokens.db`
- **Logs:** `/opt/callsbotonchain/deployment/data/logs/stdout.log`
- **Key Files:**
  - `scripts/bot.py` - Main signal detection loop
  - `app/analyze_token.py` - Token scoring logic
  - `app/fetch_feed.py` - Telegram feed monitoring

#### **2. TRADER (Trading Execution System)** 
- **Container:** `callsbot-trader`
- **Purpose:** Receives signals from Redis, executes trades on Solana
- **Config:** `tradingSystem/config_optimized.py`
- **Database:** `/opt/callsbotonchain/deployment/var/trading.db`
- **Logs:** 
  - Docker: `docker logs callsbot-trader`
  - File: `/opt/callsbotonchain/deployment/data/logs/trading.log`
- **Key Files:**
  - `tradingSystem/cli_optimized.py` - Main trading loop
  - `tradingSystem/trader_optimized.py` - Trade execution engine
  - `tradingSystem/broker_optimized.py` - Jupiter DEX integration
  - `tradingSystem/strategy_optimized.py` - Entry/exit strategy
  - `tradingSystem/db.py` - Position management & database
  - `tradingSystem/config_optimized.py` - **TRADING CONFIG (trails, stop loss)**

---

## 🎯 TRADING SYSTEM CONFIGURATION (October 25, 2025)

### **Current Mode: ULTRA AGGRESSIVE MOONSHOT HUNTING**

**Philosophy:** Cut losers fast (-35% from entry), let winners run huge (35-50% trails from peak)

### **🔧 Configuration File Locations**

**⚠️ PRECEDENCE ORDER (CRITICAL!):**
1. **Environment variables in `deployment/.env`** (HIGHEST priority - overrides code!)
2. **Environment variables in `deployment/docker-compose.yml`**
3. **Code defaults in `tradingSystem/config_optimized.py`** (LOWEST priority)

**🚨 COMMON MISTAKE:** If you change `config_optimized.py` but it doesn't work, check `.env` and `docker-compose.yml` for overrides!

---

### **📊 Current Trailing Stop Configuration**

Located in: `tradingSystem/config_optimized.py`

```python
# PROFIT-BASED ADAPTIVE TRAILING STOPS
ADAPTIVE_TRAILING_ENABLED = True  # ✅ MUST BE TRUE!

# Stop loss from entry price
STOP_LOSS_PCT = 35.0  # -35% from entry (was 20%, then 12%, now 35%)

# Trailing stops based on PROFIT percentage (not time!)
TRAIL_TIER_0 = 35.0  # 0-50% profit: 35% trail
TRAIL_TIER_1 = 38.0  # 50-100% profit: 38% trail
TRAIL_TIER_2 = 42.0  # 100-200% profit: 42% trail
TRAIL_TIER_3 = 45.0  # 200-500% profit: 45% trail
TRAIL_TIER_4 = 48.0  # 500-1000% profit: 48% trail
TRAIL_TIER_5 = 50.0  # 1000%+ profit: 50% trail
```

**How it works:**
- Token at +80% profit uses **38% trail** (TRAIL_TIER_1)
- If peak is $1.00, bot won't exit until price drops to **$0.62** (-38% from peak)
- This allows healthy dips and consolidation without early exit
- Old system (8-10% trails) would exit at $0.92, missing huge runs!

---

### **🔍 How to Verify Config is Active**

**Method 1: Check environment variables (fastest)**
```bash
ssh root@64.227.157.221
docker exec callsbot-trader env | grep TS_TRAIL
docker exec callsbot-trader env | grep TS_ADAPTIVE
docker exec callsbot-trader env | grep TS_STOP_LOSS
```

**Expected output:**
- `TS_ADAPTIVE_TRAILING_ENABLED=true`
- **NO** `TS_TRAIL_DEFAULT` or `TS_TRAIL_TIER_X` vars (means code values are used)
- `TS_STOP_LOSS_PCT=35.0` (optional, code default is 35.0)

**If you see `TS_TRAIL_DEFAULT=8.0` or old values:**
1. Edit `/opt/callsbotonchain/deployment/.env` and remove those lines
2. Restart: `cd /opt/callsbotonchain/deployment && docker compose restart trader`

---

**Method 2: Watch live position monitoring**
```bash
ssh root@64.227.157.221
docker logs -f callsbot-trader 2>&1 | grep "new peak"
```

**Expected output:**
```
[TRADER] 🚀 5GhEvCMy new peak! Profit: +95.0% | Trail: 38% | Price: $0.00007780
```

The `Trail: 38%` confirms the new config is active!

---

**Method 3: Check config inside container**
```bash
ssh root@64.227.157.221
cat /opt/callsbotonchain/tradingSystem/config_optimized.py | grep "TRAIL_TIER_0"
```

Should show: `TRAIL_TIER_0 = _get_float("TS_TRAIL_TIER_0", 35.0)`

---

### **🐛 Common Configuration Issues**

#### **Issue 1: Changes to `config_optimized.py` Not Taking Effect**

**Symptoms:**
- You change TRAIL_TIER_0 to 35.0 in code
- Bot still uses 8% trails
- Database shows trail_pct=8.0 for new positions

**Root Cause:** Environment variables in `.env` or `docker-compose.yml` are overriding code values

**Fix:**
```bash
# 1. Check for overrides
ssh root@64.227.157.221
cd /opt/callsbotonchain/deployment
grep -E "TS_TRAIL|TS_ADAPTIVE|TS_STOP_LOSS" .env docker-compose.yml

# 2. Remove bad env vars from .env
sed -i '/^TS_TRAIL_/d' .env

# 3. Edit docker-compose.yml and remove these lines under trader environment:
#    - TS_TRAIL_DEFAULT=...
#    - TS_TRAIL_AGGRESSIVE=...
#    - TS_TRAIL_CONSERVATIVE=...
#    - TS_ADAPTIVE_TRAILING_ENABLED=false  (or change to true)

# 4. Rebuild and restart
docker compose down trader
docker compose up -d --build trader

# 5. Verify
docker exec callsbot-trader env | grep TS_TRAIL
# Should show NOTHING or only TS_TRAIL_TIER_X vars
```

---

#### **Issue 2: Bot Using Old Trails for Existing Positions**

**Symptoms:**
- New config deployed
- Old positions in database still have trail_pct=8.0 or 10.0
- Positions not exiting as expected

**Explanation:** 
- Database stores the trail% from when position was OPENED
- With `ADAPTIVE_TRAILING_ENABLED=true`, this is **IGNORED**
- Bot calculates trail% dynamically based on current profit
- Function: `tradingSystem/db.py::update_peak_and_trail()`

**How to verify it's working:**
```bash
# Watch for "new peak" messages showing current trail
docker logs -f callsbot-trader | grep "new peak"

# Example output:
# [TRADER] 🚀 5GhEvCMy new peak! Profit: +95.0% | Trail: 38% | Price: $0.00007780
# This shows bot IS using 38% trail despite database showing 10%
```

**The database trail_pct is ONLY used if:**
- `ADAPTIVE_TRAILING_ENABLED=false` (not recommended)
- OR as a fallback if peak_price or entry_price is missing

---

### **📁 Trading System Database Schema**

**Database:** `/opt/callsbotonchain/deployment/var/trading.db`

#### **Table: `positions`**
```sql
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_address TEXT NOT NULL,
    strategy TEXT,                  -- 'smart_money_premium', 'smart_money_good', etc.
    entry_time REAL,                -- Unix timestamp
    entry_price REAL,               -- Price in USD when bought
    quantity REAL,                  -- Number of tokens
    usd_value REAL,                 -- USD invested
    peak_price REAL,                -- Highest price reached
    trail_pct REAL,                 -- Initial trail % (IGNORED if adaptive=true!)
    status TEXT,                    -- 'open', 'closed'
    exit_time REAL,                 -- Unix timestamp
    exit_price REAL,                -- Price when sold
    pnl_usd REAL,                   -- Profit/loss in USD
    pnl_pct REAL,                   -- Profit/loss percentage
    exit_reason TEXT,               -- 'trail', 'stop_loss', 'time_exit', etc.
    tx_hash TEXT,                   -- Solana transaction hash
    current_price REAL,             -- Last known price
    last_check_time REAL            -- Last time price was checked
);
```

**Key Fields for Analysis:**
- `entry_price` and `peak_price` - Used to calculate profit%
- `trail_pct` - Stored value (ignored if ADAPTIVE_TRAILING_ENABLED=true)
- `pnl_pct` - Final performance when closed
- `exit_reason` - Why position was closed

---

### **🔍 How to Check Trading Performance**

**Method 1: Open Positions**
```bash
ssh root@64.227.157.221
cd /opt/callsbotonchain/deployment
sqlite3 var/trading.db "
SELECT 
    id, 
    substr(token_address, 1, 12) as token,
    ROUND(entry_price, 8) as entry,
    ROUND(peak_price, 8) as peak,
    ROUND(((peak_price - entry_price) / entry_price * 100), 1) as peak_gain_pct,
    trail_pct
FROM positions 
WHERE status='open'
ORDER BY id DESC;
"
```

---

**Method 2: Recently Closed Positions**
```bash
sqlite3 var/trading.db "
SELECT 
    id,
    substr(token_address, 1, 12) as token,
    ROUND(pnl_pct, 1) as pnl_pct,
    exit_reason,
    datetime(exit_time, 'unixepoch') as exit_time
FROM positions 
WHERE status='closed'
ORDER BY exit_time DESC
LIMIT 20;
"
```

---

**Method 3: Performance Summary**
```bash
sqlite3 var/trading.db "
SELECT 
    COUNT(*) as total_trades,
    SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) as winners,
    ROUND(AVG(pnl_pct), 2) as avg_pnl_pct,
    ROUND(MAX(pnl_pct), 2) as best_trade_pct,
    ROUND(MIN(pnl_pct), 2) as worst_trade_pct,
    ROUND(SUM(pnl_usd), 2) as total_pnl_usd
FROM positions 
WHERE status='closed';
"
```

---

### **📊 How to Monitor Live Trading**

**Watch Position Monitoring (Every 5 seconds):**
```bash
docker logs -f callsbot-trader 2>&1 | grep EXIT_LOOP
```

**Watch Buy Signals:**
```bash
docker logs -f callsbot-trader 2>&1 | grep "open_position"
```

**Watch Sell Attempts:**
```bash
docker logs -f callsbot-trader 2>&1 | grep -E "exit_trail|exit_stop|SELL"
```

**Watch Errors:**
```bash
docker logs -f callsbot-trader 2>&1 | grep -E "ERROR|FAILED|6024"
```

---

### **🔧 How to Change Trading Config**

**Step 1: Edit the config file**
```bash
# Local machine
cd /path/to/callsbotonchain
nano tradingSystem/config_optimized.py

# Make changes to TRAIL_TIER_X values
```

**Step 2: Upload to server**
```bash
scp tradingSystem/config_optimized.py root@64.227.157.221:/opt/callsbotonchain/tradingSystem/
```

**Step 3: Check for env var conflicts**
```bash
ssh root@64.227.157.221
cd /opt/callsbotonchain/deployment
grep -E "TS_TRAIL|TS_ADAPTIVE" .env docker-compose.yml
# Remove any conflicting variables
```

**Step 4: Restart trader**
```bash
docker compose down trader
docker compose up -d --build trader
```

**Step 5: Verify new config**
```bash
# Wait for a position to update
docker logs -f callsbot-trader | grep "new peak"
# Should show new trail percentages
```

---

## 📊 Signal Detection System (Worker)

### **Context: What Changed & Why

### **Problem Identified**

After analyzing 2,189 tracked signals, we discovered critical flaws in the bot's scoring and filtering system:

1. **Inverted Scoring System** 🚨
   - Score 4 signals: **8.57x** average (caught the 896x moonshot!)
   - Score 7 signals: **20% win rate** (highest consistency)
   - Score 10 signals: **1.20x** average (underperforming!)
   - **Root Cause:** High scores were assigned to late entries (already pumping). Low scores caught tokens early.

2. **Smart Money Detection Was Anti-Predictive** 🚨
   - With smart money: 1.12x average
   - WITHOUT smart money: **3.03x average** (2.7x better!)
   - Both biggest winners (896x, 143x) had NO smart money
   - **Root Cause:** Detection was too late or false positives

3. **Filters Blocking Winners** ⚠️
   - Volume thresholds ($50k/$100k) unrealistic for new tokens
   - Liquidity filter ($8k) too low - losers had $30k median
   - **Moonshots had $117k median liquidity vs losers $30k**

4. **Missing Timing Data** ⚠️
   - Only 14% of signals had pump speed classification
   - Tracking interval (60s) too slow to capture patterns
   - Couldn't analyze FAST vs SLOW pumps effectively

---

## 🔧 Changes Implemented

### **1. Scoring System Recalibration**

| Parameter | Before | After | Reason |
|-----------|--------|-------|--------|
| `HIGH_CONFIDENCE_SCORE` | 6 | **7** | Score 7 had 20% win rate |
| `GENERAL_CYCLE_MIN_SCORE` | 9 | **7** | Lower scores caught moonshots |
| Smart Money Bonus | +4 total | **0** | Anti-predictive (removed) |

**Impact:** Bot now values score 4-7 signals equally, catching more early-stage winners.

### **2. Entry Filters Optimized**

| Filter | Before | After | Reason |
|--------|--------|-------|--------|
| `MIN_LIQUIDITY_USD` | $8,000 | **$30,000** | Filters low-liquidity rugs |
| `VOL_VERY_HIGH` | $100,000 | **$60,000** | Moonshots had $63k median |
| `VOL_HIGH` | $50,000 | **$30,000** | More realistic for new tokens |
| `VOL_MED` | $10,000 | **$5,000** | Captures early volume |

**Impact:** 
- Eliminates most rugs (moonshots had 3.9x higher liquidity)
- Allows good signals with realistic volume levels
- Better alignment with actual market conditions

### **3. Tracking Frequency Doubled**

| Setting | Before | After | Reason |
|---------|--------|-------|--------|
| `TRACK_INTERVAL_MIN` | 60s | **30s** | Capture more timing data |
| Timing Data Coverage | 14% | **Target: 80%+** | Better pattern analysis |

**Impact:** 2x more price snapshots for better pump speed classification.

### **4. Smart Money Bonus Removed**

**Files Modified:**
- `app/analyze_token.py`: Removed +2 bonus from `score_token()`
- `app/analyze_token.py`: Removed +3 bonus from `calculate_preliminary_score()`
- `scripts/bot.py`: Commented out +2 additional bonus
- `config/config.py`: Set `SMART_MONEY_SCORE_BONUS = 0`

**Rationale:** Data showed non-smart money signals outperformed 2.7x. Smart money detection doesn't predict success.

---

## 📁 Database Structure

### **Tables**

#### 1. `alerted_tokens`
Stores all signals the bot has alerted on.

**Key Fields:**
```sql
- token_address (TEXT PRIMARY KEY)
- alerted_at (REAL) -- Unix timestamp
- final_score (INTEGER) -- 1-10
- prelim_score (INTEGER) -- Preliminary score
- conviction_type (TEXT) -- 'High Confidence', 'Smart Money Runner', etc.
- smart_money_detected (INTEGER) -- 0 or 1
- entry_price (REAL)
- entry_market_cap (REAL)
- entry_liquidity (REAL)
- entry_volume_24h (REAL)
```

#### 2. `alerted_token_stats`
Performance tracking for alerted tokens.

**Key Fields:**
```sql
- token_address (TEXT PRIMARY KEY)
- first_price_usd (REAL) -- Entry price
- peak_price_usd (REAL) -- Highest price reached
- peak_price_at (REAL) -- When peak occurred (timestamp)
- last_price_usd (REAL) -- Most recent price
- max_gain_percent (REAL) -- Max gain from entry
- max_drawdown_percent (REAL) -- Max loss from entry
- time_to_peak_minutes (REAL) -- Time from entry to peak
- is_rug (INTEGER) -- 0 or 1
- updated_at (REAL) -- Last update timestamp
```

#### 3. `price_snapshots`
Historical price data (captured every 30 seconds).

**Key Fields:**
```sql
- token_address (TEXT)
- snapshot_at (REAL) -- Unix timestamp
- price_usd (REAL)
- market_cap_usd (REAL)
- liquidity_usd (REAL)
- volume_24h_usd (REAL)
- change_1h (REAL)
- change_6h (REAL)
- change_24h (REAL)
```

**Index:** `CREATE INDEX idx_snapshots_token_time ON price_snapshots(token_address, snapshot_at)`

---

## 🔍 How to Analyze Performance

### **Method 1: Quick Win Rate Check**

```bash
ssh root@64.227.157.221
cd /opt/callsbotonchain
sqlite3 var/alerted_tokens.db
```

```sql
-- Overall win rate
SELECT 
    COUNT(*) as total_signals,
    SUM(CASE WHEN max_gain_percent > 0 THEN 1 ELSE 0 END) as profitable,
    ROUND(SUM(CASE WHEN max_gain_percent > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as win_rate_pct
FROM alerted_token_stats;
```

**Expected After Fixes:**
- Total signals: Growing (was 2,189)
- Win rate: **15-20%** (was 11.3%)

---

### **Method 2: Score Performance Breakdown**

```sql
-- Performance by score
SELECT 
    a.final_score,
    COUNT(*) as count,
    ROUND(AVG(s.max_gain_percent), 2) as avg_gain_pct,
    ROUND(MAX(s.max_gain_percent), 2) as max_gain_pct,
    SUM(CASE WHEN s.max_gain_percent >= 100 THEN 1 ELSE 0 END) as moonshots_2x,
    SUM(CASE WHEN s.max_gain_percent >= 900 THEN 1 ELSE 0 END) as moonshots_10x
FROM alerted_tokens a
LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
GROUP BY a.final_score
ORDER BY a.final_score DESC;
```

**What to Look For:**
- Score 7 should have highest win rate (~20%)
- Scores 4-6 should catch moonshots (10x+)
- No single score should dominate (if >40% are score 10, recalibrate)

---

### **Method 3: Liquidity Filter Effectiveness**

```sql
-- Rug rate by entry liquidity
SELECT 
    CASE 
        WHEN a.entry_liquidity < 20000 THEN '<$20k'
        WHEN a.entry_liquidity < 30000 THEN '$20k-$30k'
        WHEN a.entry_liquidity < 50000 THEN '$30k-$50k'
        WHEN a.entry_liquidity < 100000 THEN '$50k-$100k'
        ELSE '$100k+'
    END as liquidity_bucket,
    COUNT(*) as count,
    SUM(CASE WHEN s.is_rug = 1 THEN 1 ELSE 0 END) as rugs,
    ROUND(SUM(CASE WHEN s.is_rug = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as rug_rate_pct,
    ROUND(AVG(s.max_gain_percent), 2) as avg_gain_pct
FROM alerted_tokens a
LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
GROUP BY liquidity_bucket
ORDER BY a.entry_liquidity;
```

**Expected:**
- $30k+ liquidity should have <10% rug rate
- <$20k should have very few signals (filter working)

---

### **Method 4: Smart Money vs Non-Smart Money**

```sql
-- Compare smart money performance
SELECT 
    CASE WHEN a.smart_money_detected = 1 THEN 'Smart Money' ELSE 'No Smart Money' END as category,
    COUNT(*) as count,
    ROUND(AVG(s.max_gain_percent), 2) as avg_gain_pct,
    SUM(CASE WHEN s.max_gain_percent > 0 THEN 1 ELSE 0 END) as profitable,
    ROUND(SUM(CASE WHEN s.max_gain_percent > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as win_rate_pct,
    SUM(CASE WHEN s.max_gain_percent >= 900 THEN 1 ELSE 0 END) as moonshots_10x
FROM alerted_tokens a
LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
GROUP BY category;
```

**Expected:**
- Both categories should perform similarly now (no bonus)
- Non-smart money may still slightly outperform

---

### **Method 5: Timing Data Coverage**

```sql
-- Check how many signals have timing data
SELECT 
    COUNT(DISTINCT token_address) as signals_with_snapshots,
    COUNT(*) as total_snapshots,
    ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT token_address), 2) as avg_snapshots_per_token
FROM price_snapshots;

-- Compare to total signals
SELECT COUNT(*) as total_alerted FROM alerted_tokens;
```

**Expected:**
- Coverage: **80%+** of signals should have snapshots (was 14%)
- Avg snapshots per token: **120+** (2 per minute × 60 minutes)

---

### **Method 6: Pump Speed Analysis**

```sql
-- Classify tokens by time to peak
SELECT 
    CASE 
        WHEN time_to_peak_minutes < 5 THEN 'INSTANT (<5min)'
        WHEN time_to_peak_minutes < 30 THEN 'FAST (5-30min)'
        WHEN time_to_peak_minutes < 120 THEN 'MODERATE (30min-2hr)'
        ELSE 'SLOW (>2hr)'
    END as pump_speed,
    COUNT(*) as count,
    ROUND(AVG(max_gain_percent), 2) as avg_gain_pct,
    ROUND(MAX(max_gain_percent), 2) as max_gain_pct
FROM alerted_token_stats
WHERE time_to_peak_minutes IS NOT NULL
GROUP BY pump_speed
ORDER BY 
    CASE 
        WHEN time_to_peak_minutes < 5 THEN 1
        WHEN time_to_peak_minutes < 30 THEN 2
        WHEN time_to_peak_minutes < 120 THEN 3
        ELSE 4
    END;
```

**Expected Pattern (from previous analysis):**
- SLOW pumps (>2hr): Highest avg gain (8.34x) and win rate (90.8%)
- FAST pumps: Moderate performance
- Better data quality with 30s tracking

---

### **Method 7: Top Performers**

```sql
-- Top 20 signals by performance
SELECT 
    a.token_address,
    a.final_score,
    a.smart_money_detected,
    a.entry_liquidity,
    s.max_gain_percent,
    ROUND((s.max_gain_percent / 100.0) + 1, 2) as peak_multiplier,
    ROUND(s.time_to_peak_minutes, 1) as time_to_peak_min,
    s.is_rug
FROM alerted_tokens a
LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
ORDER BY s.max_gain_percent DESC
LIMIT 20;
```

**What to Look For:**
- Mix of scores (not all score 10)
- Majority should have entry_liquidity > $30k
- Low rug rate in top performers

---

### **Method 8: Compare Before/After Changes**

```sql
-- Signals before change (before Oct 6, 2025 18:00 UTC)
SELECT 
    'BEFORE CHANGES' as period,
    COUNT(*) as total,
    ROUND(AVG(max_gain_percent), 2) as avg_gain,
    SUM(CASE WHEN max_gain_percent > 0 THEN 1 ELSE 0 END) as profitable,
    ROUND(SUM(CASE WHEN max_gain_percent > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as win_rate
FROM alerted_tokens a
LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
WHERE a.alerted_at < 1728234000

UNION ALL

-- Signals after change
SELECT 
    'AFTER CHANGES' as period,
    COUNT(*) as total,
    ROUND(AVG(max_gain_percent), 2) as avg_gain,
    SUM(CASE WHEN max_gain_percent > 0 THEN 1 ELSE 0 END) as profitable,
    ROUND(SUM(CASE WHEN max_gain_percent > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as win_rate
FROM alerted_tokens a
LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
WHERE a.alerted_at >= 1728234000;
```

**Target Improvements:**
- Win rate: 11.3% → **15-20%**
- Avg gain: 60% → **150-250%**

---

### **Method 9: Export to CSV for Analysis**

```bash
# Export all data
sqlite3 var/alerted_tokens.db <<EOF
.headers on
.mode csv
.output /tmp/performance_export.csv
SELECT 
    a.token_address,
    a.alerted_at,
    a.final_score,
    a.prelim_score,
    a.conviction_type,
    a.smart_money_detected,
    a.entry_price,
    a.entry_market_cap,
    a.entry_liquidity,
    a.entry_volume_24h,
    s.peak_price_usd,
    s.last_price_usd,
    s.max_gain_percent,
    s.time_to_peak_minutes,
    s.is_rug,
    ROUND((s.max_gain_percent / 100.0) + 1, 2) as peak_multiplier
FROM alerted_tokens a
LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
ORDER BY a.alerted_at DESC;
.output stdout
EOF

# Copy to local machine
scp root@64.227.157.221:/tmp/performance_export.csv .
```

Then analyze in Python/Excel/Google Sheets for deeper insights.

---

## 📈 Success Metrics to Track

### **Weekly Review (Every Monday)**

1. **Signal Quality**
   ```sql
   -- Signals from last 7 days
   SELECT 
       COUNT(*) as signals_this_week,
       ROUND(AVG(final_score), 2) as avg_score,
       ROUND(AVG(entry_liquidity), 0) as avg_liquidity
   FROM alerted_tokens 
   WHERE alerted_at > (strftime('%s', 'now') - 604800);
   ```

2. **Win Rate Trend**
   ```sql
   -- Win rate last 7 days
   SELECT 
       ROUND(SUM(CASE WHEN max_gain_percent > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as win_rate_7d
   FROM alerted_tokens a
   LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
   WHERE a.alerted_at > (strftime('%s', 'now') - 604800);
   ```

3. **Moonshot Detection**
   ```sql
   -- 10x+ winners this week
   SELECT COUNT(*) as moonshots_this_week
   FROM alerted_tokens a
   LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
   WHERE a.alerted_at > (strftime('%s', 'now') - 604800)
   AND s.max_gain_percent >= 900;
   ```

### **Target KPIs (After Changes)**

| Metric | Before | Target | Timeframe |
|--------|--------|--------|-----------|
| Win Rate | 11.3% | **15-20%** | 2-4 weeks |
| Avg Return | 1.60x | **2.5-3.5x** | 2-4 weeks |
| 10x+ Rate | 0.4% | **0.8-1.2%** | 4-8 weeks |
| Rug Rate | Unknown | **<5%** | Immediate |
| Timing Data | 14% | **80%+** | Immediate |

---

## 🚨 Red Flags to Watch For

### **1. Too Many Signals**
If >500 signals per day:
- Filters may be too loose
- Consider raising liquidity to $40k

```sql
SELECT DATE(alerted_at, 'unixepoch') as date, COUNT(*) as signals
FROM alerted_tokens
GROUP BY date
ORDER BY date DESC
LIMIT 7;
```

### **2. High Rug Rate**
If rug rate >10%:
- Liquidity filter needs raising
- Check for honeypots

```sql
SELECT 
    SUM(is_rug) * 100.0 / COUNT(*) as rug_rate_pct
FROM alerted_token_stats;
```

### **3. Score Distribution Skewed**
If >40% signals are score 10:
- Scoring needs recalibration
- Too many signals hitting max score

```sql
SELECT final_score, COUNT(*) as count, 
       ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM alerted_tokens), 2) as pct
FROM alerted_tokens
GROUP BY final_score
ORDER BY final_score DESC;
```

### **4. Win Rate Declining**
If win rate drops below 10%:
- Market conditions changed
- OR filters too loose
- Review recent poor performers

---

## 🔄 Continuous Improvement Loop

### **Every 2 Weeks:**

1. **Run full analysis** (Methods 1-7 above)
2. **Compare to targets**
3. **Identify patterns** in winners vs losers
4. **Adjust one parameter** at a time
5. **Monitor for 2 weeks** before next change

### **Don't Change Multiple Things at Once**
- Only adjust 1-2 parameters per cycle
- Wait 2 weeks for data
- Document changes in this file

---

## 📝 Change Log

### **October 6, 2025 - Initial Optimization**
**Commit:** `d798595`

**Changes:**
- HIGH_CONFIDENCE_SCORE: 6 → 7
- GENERAL_CYCLE_MIN_SCORE: 9 → 7
- MIN_LIQUIDITY_USD: $8k → $30k
- VOL_VERY_HIGH: $100k → $60k
- VOL_HIGH: $50k → $30k
- VOL_MED: $10k → $5k
- SMART_MONEY_SCORE_BONUS: 2 → 0
- TRACK_INTERVAL_MIN: 60s → 30s

**Reason:** Analysis of 2,189 signals revealed inverted scoring and anti-predictive smart money detection.

**Expected Impact:** Win rate 11.3% → 15-20%, Avg return 1.6x → 2.5-3.5x

---

### **October 13, 2025 22:11 UTC / 03:41 IST - Critical Bug Fix**
**Commit:** `0dc9229`

**Changes:**
- Removed conflicting "dump-after-pump" filter in `bot.py` (lines 497-502)

**Reason:** 
The dump-after-pump rejection logic was contradicting the data-driven changes in `analyze_token.py`. It was blocking tokens with the pattern: positive 24h momentum (+30%) but negative 1h momentum (-5%). This pattern is NORMAL consolidation for 45% of winners. Mega winners averaged -7.1% 1h momentum.

**Technical Details:**
```python
# REMOVED (was blocking winners):
if change_24h > 30 and change_1h < -5:
    return "skipped"  # This was rejecting 45% of potential winners!
```

**Expected Impact:**
- Catch 45% more winners (those with negative 1h momentum)
- Aligns with Change 3.1 (dip buying bonus)
- Better entry points during healthy consolidation

**Deployment Time:** October 13, 2025 22:11 UTC (03:41 IST)  
**Bot Restarted:** Process ID 3589815

---

### **October 25, 2025 17:24 UTC / 22:54 IST - ULTRA AGGRESSIVE MOONSHOT MODE**

**Changes:**
- **Trading System Config:** Widened trailing stops from 8-30% to 35-50%
- **Stop Loss:** Widened from -20% to -35% from entry
- **Philosophy Shift:** Allow 35% drawdowns to survive dip-and-rip patterns
- **Adaptive Trailing:** ENABLED (profit-based trails, not time-based)
- **Configuration Management:** Removed all env var overrides in `.env` and `docker-compose.yml`

**Technical Details:**
```python
# Before (Conservative):
TRAIL_TIER_0 = 8.0%   # 0-50% profit
TRAIL_TIER_1 = 12.0%  # 50-100% profit
STOP_LOSS_PCT = 20.0% # -20% from entry

# After (Ultra Aggressive):
TRAIL_TIER_0 = 35.0%  # 0-50% profit
TRAIL_TIER_1 = 38.0%  # 50-100% profit
TRAIL_TIER_2 = 42.0%  # 100-200% profit
TRAIL_TIER_3 = 45.0%  # 200-500% profit
TRAIL_TIER_4 = 48.0%  # 500-1000% profit
TRAIL_TIER_5 = 50.0%  # 1000%+ profit
STOP_LOSS_PCT = 35.0% # -35% from entry
```

**Reason:** 
Signal provider has 45% hit rate for 2x+ moonshots, but bot was exiting winning trades too early due to conservative 8% trailing stops. Analysis showed:
- Position #187: Peaked at +83.1%, sold at +61.7% (missed 21.4%)
- Position #203: Peaked at +78.7%, sold at +55.7% (missed 23.0%)
- Memecoins exhibit dip-and-rip patterns: can dip 20-30% from entry before going 10x
- Old 8% trails were exiting during healthy consolidation, missing moonshot potential

**Root Cause of Config Issues:**
Environment variables in `deployment/.env` and `deployment/docker-compose.yml` were overriding code values:
- `TS_TRAIL_DEFAULT=8.0` in .env (removed)
- `TS_TRAIL_AGGRESSIVE=5.0`, `TS_TRAIL_CONSERVATIVE=10.0` in docker-compose.yml (removed)
- `TS_ADAPTIVE_TRAILING_ENABLED=false` in docker-compose.yml (changed to true)

**Expected Impact:**
- Capture 85-90% of moonshot gains (vs 72% with old trails)
- Allow positions to survive healthy -20-30% dips
- Position at +80% can now dip to +52% before exit (vs +72% with old 8% trail)
- Enable asymmetric risk/reward: Small losses (-35% max), huge wins (10x+ possible)

**Actual Impact (First Hour):**
- ✅ Position #215 (5GhEvCMy): Rode from +28% to +95% using 38% trail
- ✅ Position #214 (Gwf6QBR2): Held until -34% before exit (old 8% would've exited at -19%)
- ✅ Verified in logs: `[TRADER] 🚀 5GhEvCMy new peak! Profit: +95.0% | Trail: 38%`

**Deployment Steps:**
1. Updated `tradingSystem/config_optimized.py` with new TRAIL_TIER values
2. Updated `tradingSystem/db.py` docstrings to reflect new philosophy
3. Edited `deployment/docker-compose.yml` to remove old env vars and enable adaptive trailing
4. Removed `TS_TRAIL_*` variables from `deployment/.env`
5. Rebuilt and restarted trader container: `docker compose down trader && docker compose up -d --build trader`
6. Verified config: `docker exec callsbot-trader env | grep TS_TRAIL` (no overrides)
7. Confirmed in logs: Position updates showing 35-38% trails in use

**Files Modified:**
- `tradingSystem/config_optimized.py` - Changed TRAIL_TIER_0 through TRAIL_TIER_5, STOP_LOSS_PCT
- `tradingSystem/db.py` - Updated `update_peak_and_trail()` docstring
- `deployment/docker-compose.yml` - Removed old trail env vars, enabled adaptive trailing
- `deployment/.env` - Removed `TS_TRAIL_AGGRESSIVE`, `TS_TRAIL_DEFAULT`, `TS_TRAIL_CONSERVATIVE`
- `docs/quickstart/CURRENT_SETUP.md` - Added comprehensive trading system documentation

**Deployment Time:** October 25, 2025 17:24 UTC (22:54 IST)  
**Container:** callsbot-trader (rebuilt with clean config)

---

### **[Future Changes - Template]**

**Date:** YYYY-MM-DD  
**Commit:** [hash]

**Changes:**
- [Parameter]: [before] → [after]

**Reason:** [Data-driven justification]

**Actual Impact After 2 Weeks:**
- Win rate: [%]
- Avg return: [x]
- Notes: [observations]

---

## 🛠️ Quick Reference Commands

### **Connect to Database**
```bash
ssh root@64.227.157.221
cd /opt/callsbotonchain
sqlite3 var/alerted_tokens.db
```

### **Check Latest Signals**
```sql
.headers on
.mode column
SELECT 
    substr(token_address, 1, 8) || '...' as token,
    datetime(alerted_at, 'unixepoch') as alerted,
    final_score as score,
    ROUND(entry_liquidity/1000, 1) || 'k' as liq,
    conviction_type as type
FROM alerted_tokens 
ORDER BY alerted_at DESC 
LIMIT 10;
```

### **Performance Summary**
```sql
SELECT 
    COUNT(*) as total,
    ROUND(AVG(final_score), 2) as avg_score,
    SUM(CASE WHEN max_gain_percent > 0 THEN 1 ELSE 0 END) as winners,
    ROUND(SUM(CASE WHEN max_gain_percent > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) || '%' as win_rate,
    ROUND(AVG(max_gain_percent), 2) || '%' as avg_gain,
    MAX(max_gain_percent) || '%' as max_gain
FROM alerted_tokens a
LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address;
```

### **Export for Python Analysis**
```bash
# Generate JSONL for analysis
sqlite3 var/alerted_tokens.db <<EOF
SELECT json_object(
    'token_address', a.token_address,
    'final_score', a.final_score,
    'entry_liquidity', a.entry_liquidity,
    'max_gain_percent', s.max_gain_percent,
    'peak_multiplier', ROUND((s.max_gain_percent / 100.0) + 1, 2),
    'time_to_peak_minutes', s.time_to_peak_minutes,
    'is_rug', s.is_rug
)
FROM alerted_tokens a
LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address;
EOF
```

---

## 📚 Related Documentation

- **FIXES_CHANGELOG.md** - Complete technical details of all changes
- **docs/guides/OPTIMAL_TRADING_STRATEGY.md** - How to trade these signals
- **docs/guides/goals.md** - Performance targets and expectations
- **docs/COMPREHENSIVE_VERIFICATION_REPORT.md** - Initial analysis report

---

**Last Updated:** October 25, 2025 17:24 UTC (22:54 IST)  
**Next Review:** November 8, 2025 (2 weeks after ultra aggressive deployment)  
**Maintained By:** AI Assistant + User

---

## 📋 Quick Reference Card for AI Assistants

**When asked about trading performance:**
1. Check `deployment/var/trading.db` (NOT `var/trading.db`)
2. Use queries from "How to Check Trading Performance" section

**When asked to change trailing stops:**
1. Edit `tradingSystem/config_optimized.py`
2. Check for env var overrides: `grep -E "TS_TRAIL" deployment/.env deployment/docker-compose.yml`
3. Remove overrides if found
4. Rebuild trader: `docker compose down trader && docker compose up -d --build trader`
5. Verify: `docker logs -f callsbot-trader | grep "new peak"`

**When asked about signal detection:**
1. Check `deployment/var/alerted_tokens.db` (NOT `var/alerted_tokens.db`)
2. Container: `callsbot-worker` (NOT `callsbot-trader`)
3. Config: `app/config_unified.py` (NOT `tradingSystem/config_optimized.py`)

**Remember:** WORKER = Signals, TRADER = Execution. Two separate systems!
