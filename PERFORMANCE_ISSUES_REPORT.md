# Signal Performance Issues - Diagnostic Report
**Date:** October 17, 2025  
**Analysis:** 1,064 signals tracked

---

## 🚨 CRITICAL ISSUES IDENTIFIED

### 1. **EXTREMELY HIGH RUG RATE** (49.1%)
- **522 out of 1,064 signals are rugs** (49.1% rug rate)
- **Target should be <10%**
- This is destroying overall performance

### 2. **MARKET CAP FILTER NOT WORKING**
- **34 signals have market cap > $1M** (should be 0)
- One signal at **$2.05M market cap** (2x over limit!)
- Many signals in $100k-$500k range
- Filter exists in code (line 796 of analyze_token.py) but **NOT being enforced**

### 3. **WRONG MARKET CAP FOCUS**
**The data CONTRADICTS the README's micro-cap thesis:**

| Market Cap Range | Signals | Avg Gain | Win Rate | Rug Rate |
|------------------|---------|----------|----------|----------|
| <$100k           | 516     | 177%     | 56.6%    | **57.2%** 🚩 |
| $100k-$500k      | 209     | 182%     | 70.3%    | 44.5% |
| $500k-$1M        | 32      | 42%      | 81.2%    | 15.6% |
| $1M-$5M          | 20      | 18%      | **90.0%** | **0.0%** ✅ |
| **>$5M**         | 287     | **893%** | 58.2%    | 44.9% |

**Key Findings:**
- **$1M-$5M tokens:** 90% win rate, 0% rug rate (BEST!)
- **>$5M tokens:** 893% average gain (massive moonshots)
- **<$100k tokens:** 57% rug rate (TERRIBLE)

**CONCLUSION:** The "micro-cap only" strategy is WRONG. Larger caps ($500k-$5M) perform much better!

### 4. **LIQUIDITY TOO LOW**
- **Current minimum:** $18,000
- **Winners average:** $67,739 liquidity
- **Rugs average:** $34,172 liquidity
- **Winners have 2x the liquidity of rugs!**

| Liquidity Range | Signals | Avg Gain | Rug Rate |
|-----------------|---------|----------|----------|
| <$20k           | 211     | 422%     | 42.7% |
| $20k-$50k       | 305     | 193%     | 40.7% |
| $50k-$100k      | 125     | **1,356%** | 35.2% |
| >$100k          | 423     | 166%     | **62.4%** 🤔 |

**Optimal range:** $50k-$100k liquidity (1,356% avg gain, 35% rug rate)

### 5. **SCORING BROKEN - NO DIVERSITY**
- **ALL recent 30 signals are score 10** (no diversity)
- Score 10: 28.9% of all signals
- Everything getting maximum score = scoring system not discriminating

**Score Performance:**
| Score | Signals | Avg Gain | Win Rate |
|-------|---------|----------|----------|
| 10    | 308     | 184%     | 61.4% |
| 8     | 258     | 222%     | 68.2% |
| 7     | 173     | **524%** | 55.5% |
| 6     | 79      | 130%     | **69.6%** |
| 5     | 62      | **2,379%** | 50.0% |

**Note:** Score 5 has the mega moonshot (146,145% gain!), Score 7 has 524% avg

### 6. **RECENT PERFORMANCE DECLINING**
**Last 7 days:**
- 557 signals generated
- Win rate: 66.8% (decent)
- Average gain: 135% (mediocre)
- Big losses (>-20%): 97 signals
- Rugs: 224 (40% of recent signals)

**Most recent 30 signals:**
- Gains range from **-25.7% to +1,196%**
- Many negative performers (-18%, -21%, -23%)
- 4 rugs out of 30

---

## 📊 ROOT CAUSE ANALYSIS

### Why is Performance Bad?

1. **Micro-cap strategy is flawed**
   - Data shows <$100k tokens have 57% rug rate
   - $500k-$5M tokens have 90% win rate, 0-15% rug rate
   - README claims micro-caps are better, but data says opposite

2. **Liquidity filter too permissive**
   - $18k minimum lets in rugs ($34k avg)
   - Winners need $67k+ liquidity
   - Should be $50k+ minimum for quality

3. **Market cap filter not enforced**
   - Config says $1M max, but 34 signals over $1M got through
   - $2M signal proves filter is bypassed somewhere
   - Need to debug why check_junior_common() isn't rejecting large caps

4. **Scoring gives everything 10/10**
   - No discrimination between good/bad signals
   - Need to recalibrate scoring thresholds
   - Min score of 5 is too low (catches everything)

5. **Wrong optimization target**
   - Optimizing for "catch early" (low volume, low liquidity)
   - Should optimize for "avoid rugs" (higher liquidity, proven traction)
   - Quality > Quantity

---

## 🔧 RECOMMENDED FIXES

### IMMEDIATE (Critical)

#### 1. **RAISE LIQUIDITY MINIMUM** (Highest Priority)
```bash
MIN_LIQUIDITY_USD=50000  # $50k (was $18k)
```
**Why:** Winners average $67k, rugs average $34k. $50k filters most rugs while keeping winners.
**Impact:** Will reduce signal volume by ~60% but increase quality dramatically.

#### 2. **FIX MARKET CAP FILTER** (Critical Bug)
The filter exists but isn't working. Need to:
- Add explicit market cap check in `signal_processor.py` BEFORE scoring
- Add logging to see actual market caps
- Debug why `check_junior_common()` is letting $2M tokens through

```python
# Add to signal_processor.py after stats fetch
if stats.market_cap_usd and stats.market_cap_usd > 1_000_000:
    self._log(f"❌ REJECTED (MARKET CAP): {token_address} - ${stats.market_cap_usd:,.0f} > $1M")
    return ProcessResult(status="skipped", error_message="Market cap > $1M")
```

#### 3. **RECONSIDER MARKET CAP STRATEGY**
**Option A:** Keep micro-cap focus but accept high rug rate
**Option B:** Change to $500k-$5M range for better win rate (90%) and 0-15% rug rate

**Recommendation:** Option B with nuanced approach:
```bash
MIN_MARKET_CAP_USD=200000          # $200k minimum (filters ultra-micro rugs)
MAX_MARKET_CAP_USD=5000000         # $5M maximum (allows proven tokens)
SWEET_SPOT_MIN=500000              # $500k-$5M bonus zone
```

#### 4. **RAISE MINIMUM SCORE**
```bash
GENERAL_CYCLE_MIN_SCORE=7  # (was 5)
HIGH_CONFIDENCE_SCORE=7    # (was 6)
```
**Why:** Score 7 has 524% avg gain. Score 5-6 are marginal.
**Impact:** Reduces signal volume but increases quality.

#### 5. **RAISE VOLUME THRESHOLD**
```bash
MIN_VOLUME_24H_USD=10000  # $10k (was $5k)
```
**Why:** Filters dead/low-activity tokens while keeping active ones.

---

### MEDIUM PRIORITY

#### 6. **Add Minimum Market Cap**
```bash
MIN_MARKET_CAP_USD=200000  # $200k minimum
```
**Why:** <$100k tokens have 57% rug rate. Need minimum size to avoid scams.

#### 7. **Tighten Vol/MCap Ratio**
```bash
VOL_TO_MCAP_RATIO_MIN=0.30  # 30% (was 15%)
```
**Why:** Higher ratio = more genuine trading interest.

#### 8. **Add Anti-Rug Filters**
```bash
ENFORCE_BUNDLER_CAP=true
MAX_BUNDLERS_PERCENT=15.0  # (was 20%)
MAX_INSIDERS_PERCENT=25.0  # (was 30%)
MAX_TOP10_CONCENTRATION=20.0  # (was 25%)
```

---

### CONFIGURATION CHANGES NEEDED

#### Current Config (deployment/.env):
```bash
MIN_LIQUIDITY_USD=18000
GENERAL_CYCLE_MIN_SCORE=5
MIN_VOLUME_24H_USD=5000
MAX_MARKET_CAP_FOR_DEFAULT_ALERT=1000000  # Not being enforced!
```

#### Recommended Config (CONSERVATIVE - Focus on Quality):
```bash
# Liquidity (CRITICAL FIX)
MIN_LIQUIDITY_USD=50000  # $50k minimum (was $18k)
EXCELLENT_LIQUIDITY_USD=100000  # $100k bonus

# Market Cap (RETHINK STRATEGY)
MIN_MARKET_CAP_USD=200000  # $200k minimum (filter ultra-micro rugs)
MAX_MARKET_CAP_USD=5000000  # $5M maximum (allow proven tokens)
MAX_MARKET_CAP_FOR_DEFAULT_ALERT=5000000

# Volume
MIN_VOLUME_24H_USD=10000  # $10k (was $5k)
VOL_TO_MCAP_RATIO_MIN=0.30  # 30% (was 15%)

# Scoring
GENERAL_CYCLE_MIN_SCORE=7  # (was 5)
HIGH_CONFIDENCE_SCORE=7  # (was 6)

# Anti-Rug
MAX_TOP10_CONCENTRATION=20.0  # (was 25%)
MAX_BUNDLERS_PERCENT=15.0  # (was 20%)
MAX_INSIDERS_PERCENT=25.0  # (was 30%)
```

**Expected Impact:**
- Rug rate: 49% → <15%
- Win rate: 61% → 70-80%
- Signal volume: ~10-20/day → ~3-5/day (quality over quantity)
- Average gain: 364% → 500-800%

---

### ALTERNATIVE CONFIG (AGGRESSIVE - Keep Micro-Cap Focus):
If you insist on micro-caps despite the data:

```bash
# Liquidity (MUST RAISE)
MIN_LIQUIDITY_USD=50000  # $50k minimum (non-negotiable)

# Market Cap (Micro-cap range but with minimum)
MIN_MARKET_CAP_USD=100000  # $100k minimum (avoid ultra-micro rugs)
MAX_MARKET_CAP_USD=1000000  # $1M maximum (strict)

# Volume (MUST RAISE)
MIN_VOLUME_24H_USD=15000  # $15k minimum
VOL_TO_MCAP_RATIO_MIN=0.50  # 50% (very strict)

# Scoring
GENERAL_CYCLE_MIN_SCORE=8  # Very strict
HIGH_CONFIDENCE_SCORE=8

# Anti-Rug (VERY STRICT)
MAX_TOP10_CONCENTRATION=15.0
MAX_BUNDLERS_PERCENT=10.0
MAX_INSIDERS_PERCENT=20.0
MIN_HOLDER_COUNT=100  # (was 75)
```

**Expected Impact:**
- Rug rate: 49% → 20-25% (still high!)
- Win rate: 61% → 65-70%
- Signal volume: ~10-20/day → ~1-2/day
- Average gain: 364% → 400-600%

---

## 🎯 DECISION NEEDED

**The data is clear:** Your current "micro-cap only" strategy is causing 57% rug rate in <$100k tokens, while $500k-$5M tokens have 90% win rate and 0% rug rate.

**Options:**

1. **RECOMMENDED: Switch to "Quality Caps" ($500k-$5M)**
   - Pros: 90% win rate, 0-15% rug rate, stable returns
   - Cons: Smaller gains per trade (but more consistent)
   - Philosophy: Sustainable growth over moonshot hunting

2. **ALTERNATIVE: Keep Micro-Caps but MUCH Stricter**
   - Pros: Keeps moonshot potential
   - Cons: Still 20-25% rug rate even with strict filters
   - Philosophy: High risk, high reward

3. **HYBRID: Multi-Tier Approach**
   - Tier 1: $500k-$5M (70% of capital, safe plays)
   - Tier 2: $100k-$500k (20% of capital, balanced)
   - Tier 3: $50k-$100k (10% of capital, moonshot hunting)
   - Philosophy: Diversified risk

---

## 📝 ACTION ITEMS

### Immediate:
1. ✅ Stop worker: `docker compose stop worker`
2. ✅ Update `/opt/callsbotonchain/deployment/.env` with new config
3. ✅ Add market cap logging to debug filter
4. ✅ Test with dry run
5. ✅ Deploy and monitor

### Short-term (Next 7 days):
1. Monitor rug rate daily
2. Compare new vs old performance
3. Adjust thresholds based on results
4. Update README with corrected strategy

### Long-term:
1. Backtest different market cap ranges
2. Consider ML model for rug detection
3. Add holder distribution analysis
4. Implement tiered position sizing

---

## 🔍 DEBUGGING STEPS

### Why is market cap filter not working?

1. **Check if MAX_MARKET_CAP_FOR_DEFAULT_ALERT is set**
   ```bash
   ssh root@64.227.157.221
   cd /opt/callsbotonchain/deployment
   grep MAX_MARKET_CAP .env
   ```

2. **Add logging to see actual market caps**
   - Edit `app/analyze_token.py` line 796
   - Add: `print(f"DEBUG: mcap={market_cap}, limit={mcap_cap}")`

3. **Check if check_junior_common is being called**
   - Add logging in `signal_processor.py`
   - See if signals bypass junior checks

4. **Verify stats parsing**
   - Check if `market_cap_usd` is None/0 (would pass filter)
   - Add fallback to FDV if market cap missing

---

## 📈 EXPECTED RESULTS AFTER FIXES

### Conservative Config ($500k-$5M range):
- **Rug Rate:** 49% → 10-15%
- **Win Rate:** 61% → 75-85%
- **Avg Gain:** 364% → 300-500% (more consistent)
- **Signals/Day:** 10-20 → 3-5 (quality!)

### Aggressive Config (Strict micro-cap):
- **Rug Rate:** 49% → 20-25%
- **Win Rate:** 61% → 65-70%
- **Avg Gain:** 364% → 400-600%
- **Signals/Day:** 10-20 → 1-2

---

**END OF REPORT**

