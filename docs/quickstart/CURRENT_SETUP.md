# Current Bot Setup - October 13, 2025

**Status:** 🟢 DEPLOYED & ACTIVE
**Server:** `64.227.157.221`
**Commit:** `1c186c1`
**Analysis Basis:** 673 signals with full performance tracking (55.29% win rate)

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

## 📊 Context: What Changed & Why

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

**Last Updated:** October 6, 2025  
**Next Review:** October 20, 2025 (2 weeks after deployment)  
**Maintained By:** AI Assistant + User
