# 🎯 Aggressive Optimization Plan: Target 50% Hit Rate for 2x+

**Current Performance:** 17.6% hit rate (2x+), 47.2% rug rate  
**Target Goal:** 50% hit rate (2x+) WITHOUT compromising signal volume  
**Strategy:** Be MUCH better at identifying winners, not just reducing signals

---

## 📊 ANALYSIS: What Makes 2x+ Winners Different?

### Winner Characteristics (From Data)
```
Winner Median Liquidity: $17,811
Loser Median Liquidity: $0

Liquidity is the #1 predictor!
```

### Key Insights

**High-Quality Signals Have:**
1. **Liquidity ≥ $18k** (winner median)
2. **Low concentration** (top10 < 30%)
3. **No bundler manipulation** (bundlers < 40%)
4. **No insider dumping setup** (insiders < 50%)
5. **Good volume/mcap ratio** (> 0.1)
6. **Score ≥ 6** (proven threshold)

**Strategy:**
- Keep signal volume by maintaining PRELIM gate at 1
- Raise QUALITY bar at final gates
- Let more tokens through prelim, filter harder at the end

---

## 🔧 COMPREHENSIVE FIX PLAN

### Phase 1: Critical Gates (Immediate) 🔥

**1. Enable Bundlers/Insiders Enforcement**
```python
ENFORCE_BUNDLER_CAP = true
MAX_BUNDLERS_PERCENT = 35      # Tighter than 40%
ENFORCE_INSIDER_CAP = true
MAX_INSIDERS_PERCENT = 45      # Tighter than 50%
```

**2. Raise Liquidity Threshold to Winner Median**
```python
MIN_LIQUIDITY_USD = 18000      # Match winner median!
```

**3. Tighten Top10 Concentration**
```python
MAX_TOP10_CONCENTRATION = 30   # From 22% - slightly looser for micro-caps
```

**4. Increase Minimum Score**
```python
HIGH_CONFIDENCE_SCORE = 6      # From 5 - higher bar
GENERAL_CYCLE_MIN_SCORE = 5    # From 3 - much higher bar
```

**5. Require Better Vol/Mcap Ratio**
```python
VOL_TO_MCAP_RATIO_MIN = 0.10   # From 0.02 - 5x stricter
```

---

### Phase 2: Scoring Optimization 🎯

**Current Problem:** Scoring doesn't differentiate winners enough

**Solution:** Weight factors that correlate with 2x+ winners MORE heavily

**Changes to `app/analyze_token.py`:**

1. **Increase liquidity bonus weight**
```python
# Current: +4 for ≥$50k, +3 for ≥$15k
# New: +5 for ≥$50k, +4 for ≥$20k, +2 for ≥$15k

if liquidity_usd >= 50_000:
    score += 5  # Was +4
elif liquidity_usd >= 20_000:
    score += 4  # New tier
elif liquidity_usd >= 15_000:
    score += 2  # Was +3
```

2. **Add liquidity stability bonus**
```python
# New: Bonus for liquidity ABOVE winner median
if liquidity_usd >= 18_000:  # Winner median
    score += 1
    scoring_details.append("✅ Liquidity Stability: +1 (above winner median)")
```

3. **Penalize low vol/mcap ratio more**
```python
# New: Penalty for low trading activity
vol_to_mcap = volume_24h / (market_cap or 1)
if vol_to_mcap < 0.05:  # Very low activity
    score -= 1
    scoring_details.append("⚠️  Low Activity: -1 (vol/mcap too low)")
```

---

### Phase 3: Advanced Filtering 🔬

**1. Add Volume Consistency Check**
```python
# In config_unified.py
MIN_VOLUME_24H_USD = 5000  # Require minimum absolute volume

# In analyze_token.py - junior gate
if volume_24h < MIN_VOLUME_24H_USD:
    return False  # Reject low-volume tokens
```

**2. Add Holder Count Minimum**
```python
MIN_HOLDER_COUNT = 50  # Require some distribution

# In senior checks
holder_count = stats.get('holders', {}).get('holder_count', 0)
if holder_count > 0 and holder_count < MIN_HOLDER_COUNT:
    return False
```

**3. Tighten Nuanced Buffers**
```python
# Make nuanced less lenient
NUANCED_TOP10_CONCENTRATION_BUFFER = 3.0  # From 5.0
NUANCED_BUNDLERS_BUFFER = 3.0             # From 5.0
NUANCED_INSIDERS_BUFFER = 3.0             # From 5.0
NUANCED_LIQUIDITY_FACTOR = 0.7            # From 0.5 (less lenient)
```

---

## 📊 PROJECTED IMPACT

### Conservative Estimate

**With All Fixes:**
```
Current:  17.6% hit rate, 47.2% rugs, ~200 signals/day
Target:   30-40% hit rate, 25-30% rugs, ~100-150 signals/day
```

**Reality Check:**
- 50% hit rate is extremely ambitious
- Would likely require reducing to 50-80 signals/day
- Better target: 35-40% hit rate with 100-150 signals/day

### Optimistic Estimate

**If aggressive filtering works perfectly:**
```
Hit Rate: 40-45%
Rug Rate: 20-25%
Signal Volume: 80-120/day
Quality: MUCH higher
```

---

## ⚙️ IMPLEMENTATION

### Step 1: Update config_unified.py (Code Defaults)

```python
# Line 320: Raise liquidity to winner median
MIN_LIQUIDITY_USD = _get_float("MIN_LIQUIDITY_USD", 18000.0)  # Was 15000

# Line 325: Require better vol/mcap
VOL_TO_MCAP_RATIO_MIN = _get_float("VOL_TO_MCAP_RATIO_MIN", 0.10)  # Was 0.02

# Line 333: Allow slightly more concentration for micro-caps
MAX_TOP10_CONCENTRATION = _get_float("MAX_TOP10_CONCENTRATION", 30.0)  # Was 18.0

# Line 334-337: Enable bundlers/insiders with tighter limits
MAX_BUNDLERS_PERCENT = _get_float("MAX_BUNDLERS_PERCENT", 35.0)  # Was 100.0
MAX_INSIDERS_PERCENT = _get_float("MAX_INSIDERS_PERCENT", 45.0)  # Was 100.0
ENFORCE_BUNDLER_CAP = _get_bool("ENFORCE_BUNDLER_CAP", True)    # Was False
ENFORCE_INSIDER_CAP = _get_bool("ENFORCE_INSIDER_CAP", True)    # Was False

# Line 342: Tighten nuanced buffers
NUANCED_SCORE_REDUCTION = _get_int("NUANCED_SCORE_REDUCTION", 2)  # Was 1
NUANCED_LIQUIDITY_FACTOR = _get_float("NUANCED_LIQUIDITY_FACTOR", 0.7)  # Was 0.5
NUANCED_VOL_TO_MCAP_FACTOR = _get_float("NUANCED_VOL_TO_MCAP_FACTOR", 0.5)  # Was 0.3
NUANCED_TOP10_CONCENTRATION_BUFFER = _get_float("NUANCED_TOP10_CONCENTRATION_BUFFER", 3.0)  # Was 5.0
NUANCED_BUNDLERS_BUFFER = _get_float("NUANCED_BUNDLERS_BUFFER", 3.0)  # Was 5.0
NUANCED_INSIDERS_BUFFER = _get_float("NUANCED_INSIDERS_BUFFER", 3.0)  # Was 5.0

# Line 368-369: Raise minimum scores
SMART_CYCLE_MIN_SCORE = _get_int("SMART_CYCLE_MIN_SCORE", 5)  # Was 4
GENERAL_CYCLE_MIN_SCORE = _get_int("GENERAL_CYCLE_MIN_SCORE", 5)  # Was 3

# Add new config vars
MIN_VOLUME_24H_USD = _get_float("MIN_VOLUME_24H_USD", 5000.0)
MIN_HOLDER_COUNT = _get_int("MIN_HOLDER_COUNT", 50)
```

### Step 2: Update analyze_token.py (Scoring)

```python
# Around line 465-480: Increase liquidity weights
if liquidity_usd >= 50_000:
    score += 5  # Was +4
    scoring_details.append(f"✅ Liquidity: +5 (${liquidity_usd:,.0f} - EXCELLENT)")
elif liquidity_usd >= 20_000:
    score += 4  # New tier
    scoring_details.append(f"✅ Liquidity: +4 (${liquidity_usd:,.0f} - VERY GOOD)")
elif liquidity_usd >= 18_000:
    score += 3  # Winner median tier
    scoring_details.append(f"✅ Liquidity: +3 (${liquidity_usd:,.0f} - GOOD)")
elif liquidity_usd >= 15_000:
    score += 2  # Was +3
    scoring_details.append(f"⚠️ Liquidity: +2 (${liquidity_usd:,.0f} - FAIR)")

# After liquidity scoring (~line 481): Add stability bonus
if liquidity_usd >= 18_000:
    score += 1
    scoring_details.append("✅ Winner-Tier Liquidity: +1 (≥$18k median)")

# Around line 520: Add low activity penalty
if market_cap > 0 and volume_24h > 0:
    vol_to_mcap = volume_24h / market_cap
    if vol_to_mcap < 0.05:
        score -= 1
        scoring_details.append(f"⚠️  Low Activity: -1 (vol/mcap: {vol_to_mcap:.2f})")
```

### Step 3: Update analyze_token.py (Gates)

```python
# In check_junior_common (~line 717-724): Add volume check
volume_24h = stats.get('volume', {}).get('24h', {}).get('volume_usd', 0) or 0
try:
    volume_24h = float(volume_24h)
except Exception:
    volume_24h = 0.0

# Add minimum volume check
from app.config_unified import MIN_VOLUME_24H_USD
if MIN_VOLUME_24H_USD and volume_24h < MIN_VOLUME_24H_USD:
    return False

# In check_senior_common (~line 673-695): Add holder count check
from app.config_unified import MIN_HOLDER_COUNT
holders = stats.get('holders') or {}
holder_count = holders.get('holder_count', 0)
if holder_count > 0 and holder_count < MIN_HOLDER_COUNT:
    return False
```

---

## 🎯 EXPECTED RESULTS

### Conservative Projection
```
Hit Rate (2x+): 30-35% (up from 17.6%)
Rug Rate: 30-35% (down from 47.2%)
Signal Volume: 100-150/day (down from ~200/day)
Avg Gain: 400-500% (up from 385%)
User Experience: MUCH BETTER
```

### Stretch Goal
```
Hit Rate (2x+): 40-45%
Rug Rate: 20-25%
Signal Volume: 80-120/day
Avg Gain: 500-600%
User Experience: EXCELLENT
```

### Reality
- 50% hit rate would require ≤50 signals/day (very selective)
- Better to aim for 35-40% with good volume
- Can iterate based on results

---

## ⚠️ IMPORTANT NOTES

### Trade-offs

**More Selective = Better Quality BUT:**
- ✅ Much higher hit rate
- ✅ Much lower rug rate
- ✅ Better avg gains
- ❌ Fewer total signals (maybe 50% reduction)
- ❌ Might miss some ultra-early gems

**The Math:**
```
Current: 200 signals/day × 17.6% = 35 winners/day
Target:  100 signals/day × 35% = 35 winners/day (same winner count!)
         OR 150 signals/day × 23% = 35 winners/day
```

**Key Insight:** We can maintain same WINNER COUNT with half the signals if we double the hit rate!

### Maintaining Signal Volume

**To keep volume high while improving quality:**
1. Keep PRELIM_DETAILED_MIN = 1 (analyze everything)
2. Let more tokens through prelim (low bar)
3. Filter HARD at final gates (high bar)
4. This gives volume + quality

---

## 🚀 DEPLOYMENT PLAN

1. **Update config_unified.py** (code defaults)
2. **Update analyze_token.py** (scoring + gates)
3. **Update environment variables** (override if needed)
4. **Commit and push** to GitHub
5. **Pull on server** and restart containers
6. **Monitor for 24-48 hours**
7. **Iterate based on results**

---

**Ready to implement all changes?**

