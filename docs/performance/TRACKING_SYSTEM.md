# 🎯 Comprehensive Performance Tracking & Analysis System

## Overview

This document describes the complete performance tracking system that monitors alerted tokens and provides deep insights into **WHY tokens pump or dump**, enabling data-driven filter optimization.

---

## 🏗️ System Architecture

### 1. **Enhanced Database Schema** (`app/storage.py`)

**New Tables:**
- `price_snapshots`: Time-series price data for alerted tokens
- Enhanced `alerted_token_stats`: Comprehensive metadata including:
  - **Alert Reasoning**: What features caused the token to pass filters
  - **Performance Metrics**: Max gain, max drawdown, rug detection
  - **Token Features**: LP locked, mint revoked, concentration, age, etc.
  - **Market Context**: SOL price, DEX, feed source at alert time

**Key Functions:**
- `record_alert_with_metadata()`: Captures WHY a token was alerted
- `record_price_snapshot()`: Tracks price over time
- `update_token_performance()`: Updates performance metrics
- `get_performance_summary()`: Aggregates performance data

---

## 📊 Data Captured for Each Alert

### Alert Features (WHY it passed)
- ✅ **Preliminary Score** (before detailed analysis)
- ✅ **Final Score** (after all bonuses)
- ✅ **Smart Money Involved** (yes/no + wallet address)
- ✅ **Velocity Score** & Bonus
- ✅ **Gates Passed**: Junior Strict, Senior Strict, Debate
- ✅ **Security**: LP Locked, Mint Revoked
- ✅ **Concentration**: Top 10%, Bundlers%, Insiders%
- ✅ **Age**: Token age in minutes
- ✅ **Activity**: Unique traders (15m window)
- ✅ **Context**: DEX name, feed source, SOL price

### Performance Tracking (OUTCOME)
- 📈 **Price Snapshots**: Every 60 seconds
- 📈 **Max Gain %**: Peak performance vs entry
- 📉 **Max Drawdown %**: Worst drop from entry
- ⏱️ **Time-based Returns**: 1h, 6h, 24h changes
- 💀 **Rug Detection**: >80% drop or liquidity removed
- 🏆 **Peak Tracking**: Highest price & market cap reached

---

## 🔧 Components

### 1. **Price Tracker** (`scripts/track_performance.py`)

**What it does:**
- Runs continuously in Docker container (`callsbot-tracker`)
- Fetches current stats for all alerted tokens (last 48 hours)
- Records price snapshots every 60 seconds
- Updates performance metrics (gains, losses, rugs)
- Prints alerts for significant movements (>20% in 1h)
- Generates performance summary every 10 minutes

**Usage:**
```bash
# Run locally
python scripts/track_performance.py

# Run in Docker
docker-compose up -d tracker
docker logs callsbot-tracker -f
```

---

### 2. **Performance Analyzer** (`scripts/analyze_performance.py`)

**What it does:**
- Deep analysis of which features correlate with pumps vs rugs
- Compares performance: Smart Money vs General Cycle
- Identifies best/worst performing tokens
- Generates configuration recommendations

**Analysis Output:**

```
🔬 FEATURE CORRELATION WITH PUMPS
================================================================================

Smart Money Involved:
  With Feature (45 tokens):
    Pump Rate: 42.2%
    Rug Rate: 8.9%
    Avg Gain: +67.3%
  Without Feature (12 tokens):
    Pump Rate: 25.0%
    Rug Rate: 16.7%
    Avg Gain: +12.5%
  ✅ POSITIVE SIGNAL (increases pumps, reduces rugs)

LP Locked:
  With Feature (50 tokens):
    Pump Rate: 40.0%
    Rug Rate: 6.0%
    Avg Gain: +58.1%
  Without Feature (7 tokens):
    Pump Rate: 14.3%
    Rug Rate: 42.9%
    Avg Gain: -22.8%
  ✅ POSITIVE SIGNAL (increases pumps, reduces rugs)
```

**Recommendations:**
```
💡 Recommendations:

  1. [HIGH PRIORITY]
     Issue: High rug rate (18.3%)
     Action: Enable REQUIRE_LP_LOCKED and REQUIRE_MINT_REVOKED strictly
     Reason: Too many unsafe tokens passing filters

  2. [MEDIUM PRIORITY]
     Issue: General cycle outperforming smart money (72.3% vs 54.1%)
     Action: Reduce CIELO_MIN_WALLET_PNL or disable smart money requirement
     Reason: Smart money filter may be too strict
```

**Usage:**
```bash
# Run analysis
python scripts/analyze_performance.py

# Output saves to terminal and can be redirected
python scripts/analyze_performance.py > analysis_report.txt
```

---

## 🎮 New Configuration Options

### Signal Balance (`config.py`)

```python
# Allow both smart money AND high-quality general cycle
REQUIRE_SMART_MONEY_FOR_ALERT = False  # Default: false

# Bonus for smart money tokens
SMART_MONEY_SCORE_BONUS = 2  # Default: 2 points

# General cycle requires higher base score
GENERAL_CYCLE_MIN_SCORE = 9  # Default: 9/10
```

**How it works:**
- Smart money tokens: Score 7 + 2 bonus = 9 → ALERT ✅
- General cycle tokens: Need score 9 → ALERT ✅
- This ensures quality from both sources

---

## 📈 Performance Metrics Tracked

| Metric | Description | Use Case |
|--------|-------------|----------|
| **Max Gain %** | Peak profit from entry | Identify best signals |
| **Max Drawdown %** | Worst loss from entry | Risk assessment |
| **Price Change 1h** | Short-term momentum | Early exit signals |
| **Price Change 6h** | Medium-term trend | Hold decisions |
| **Price Change 24h** | Long-term performance | Success rate |
| **Rug Detection** | >80% drop or liq removed | Filter effectiveness |
| **Peak Price At** | When ATH occurred | Timing analysis |

---

## 🔄 Feedback Loop

```
1. Bot alerts token
   ↓
2. Records WHY (features + scores + gates passed)
   ↓
3. Tracker monitors price every 60s for 48h
   ↓
4. Records performance (gains/losses/rugs)
   ↓
5. Analyzer correlates features → outcomes
   ↓
6. Generates recommendations
   ↓
7. Adjust config based on data
   ↓
[REPEAT]
```

---

## 🎯 Use Cases

### 1. **Understand Filter Effectiveness**
```bash
python scripts/analyze_performance.py
```
- See which gates are too strict/loose
- Identify which features reduce rugs
- Find blind spots in filtering

### 2. **Optimize Score Thresholds**
- If pump rate < 15% → Lower `HIGH_CONFIDENCE_SCORE`
- If rug rate > 15% → Tighten security requirements
- Data-driven decision making

### 3. **Compare Signal Types**
- Smart Money vs General Cycle performance
- Which DEXs produce best signals
- Optimal token age range

### 4. **Find Patterns**
- Do newer tokens (<1h) pump harder?
- Does high velocity actually matter?
- Are top 10% concentration warnings accurate?

---

## 📊 Example Analysis Output

```
🌟 BEST PERFORMERS
================================================================================

1. CATFISH ($CAT)
   Max Gain: +287.3%
   Score: 4/10 → 10/10
   Smart Money: ✅
   Velocity: 12
   Top10: 8.2%
   → Pattern: Low prelim + smart money + high velocity = MEGA PUMP

2. MOONDOG ($MOON)
   Max Gain: +156.8%
   Score: 5/10 → 9/10
   Smart Money: ❌
   Velocity: 8
   Top10: 12.4%
   → Pattern: General cycle can pump without smart money!

💀 WORST PERFORMERS (Rugs)
================================================================================

1. SCAMCOIN ($SCAM)
   Max Loss: -98.2%
   Score: 3/10 → 8/10
   Smart Money: ❌
   LP Locked: ❌
   Mint Revoked: ❌
   → Pattern: Both security checks failed → immediate rug
```

---

## 🚀 Deployment

### Server Setup

```bash
# 1. Push changes to server
git add .
git commit -m "feat: Add comprehensive performance tracking system"
git push origin main

# 2. Pull on server
ssh root@your-server
cd /opt/callsbotonchain
git pull origin main

# 3. Rebuild and start tracker
docker-compose build tracker
docker-compose up -d tracker

# 4. Verify tracking
docker logs callsbot-tracker -f
```

### Monitor Performance

```bash
# Check tracker logs
docker logs callsbot-tracker --tail 100

# Run analysis (after 24h of data)
docker exec callsbot-worker python scripts/analyze_performance.py

# Export database for local analysis
scp root@your-server:/opt/callsbotonchain/var/alerted_tokens.db ./var/
python scripts/analyze_performance.py
```

---

## 💡 Benefits

### Before This System
- ❌ No visibility into why tokens pump/dump
- ❌ Filter tuning based on gut feeling
- ❌ Can't identify which features matter
- ❌ No feedback loop for improvement

### After This System
- ✅ **Pinpoint causation** → "Tokens with LP locked + smart money have 42% pump rate"
- ✅ **Data-driven tuning** → "Rug rate is 18%, enable REQUIRE_LP_LOCKED"
- ✅ **Feature validation** → "High velocity is correlated with +67% avg gain"
- ✅ **Continuous improvement** → Analyze → Adjust → Repeat

---

## 📝 Summary

This system provides **complete visibility** into:
1. ✅ **WHAT** was alerted (token details)
2. ✅ **WHY** it was alerted (which features/gates/scores)
3. ✅ **HOW** it performed (price tracking over time)
4. ✅ **CORRELATION** (which features → pumps vs rugs)
5. ✅ **RECOMMENDATIONS** (auto-generated config tuning)

**Result:** You can now say with data: _"Tokens with smart money + LP locked + velocity >8 have 67% pump rate and 4% rug rate"_ instead of guessing!
