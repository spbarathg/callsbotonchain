# Quick Start: Signal Performance Analysis

## What Was Added

Your monitoring system now includes **Signal Performance Analysis** - the most critical piece for tuning your bot. It answers:

1. ✅ **Which tokens pumped or dumped** after your alerts
2. 🔍 **WHY the bot sent each signal**
3. 📊 **Which conditions lead to wins** vs losses  
4. 🎯 **Specific tuning recommendations**

---

## Usage in 3 Steps

### Step 1: Copy Database from Server

```powershell
# Windows PowerShell
scp root@64.227.157.221:/opt/callsbotonchain/var/alerted_tokens.db var/
```

### Step 2: Run Signal Analysis

```powershell
# Analyze last 7 days
python monitoring/analyze_signals.py

# Or analyze last 30 days
python monitoring/analyze_signals.py 30
```

### Step 3: Review and Act

The analyzer shows:
- **Win Rate** - What % of signals actually pumped
- **Outcome Distribution** - How many big wins, losses, rugs
- **Score Correlation** - Do high-score signals perform better?
- **Smart Money Advantage** - How much better are smart money signals?
- **Market Cap Analysis** - Which mcap ranges perform best?
- **Tuning Recommendations** - Specific config changes to try

---

## Example Output

```
================================================================================
SIGNAL PERFORMANCE ANALYZER
================================================================================

📊 Overall Performance:
  Total Signals: 45
  Win Rate: 42.2%                    👈 Your success rate
  Wins: 19
  Losses: 12

📈 Outcome Distribution:
  big_win             :   7 (15.6%) | Avg Gain: +320.5% | Avg Score: 8.4
  win                 :  12 (26.7%) | Avg Gain: +85.3% | Avg Score: 7.8
  small_win           :   8 (17.8%) | Avg Gain: +15.2% | Avg Score: 6.9
  rug                 :   3 ( 6.7%) | Avg Gain: -85.2% | Avg Score: 5.8

🎯 Conviction Performance:
  Smart Money         :  25 signals | Win Rate: 52.0%   👈 Smart money wins more!
  Nuanced             :  12 signals | Win Rate: 33.3%   👈 Nuanced underperforming
  Velocity            :   8 signals | Win Rate: 37.5%

📊 Score Analysis:
  Winners Avg Score: 7.8/10         👈 Winners have higher scores
  Losers Avg Score: 6.0/10
  Difference: +1.8 ✅                 👈 Scoring is working!

💎 Smart Money Analysis:
  Smart Money Win Rate: 52.0%
  No Smart Money Win Rate: 28.6%
  Smart Money Advantage: +23.4% ✅   👈 Smart money detection working

💰 Market Cap Performance:
  micro (<100k)       : Win Rate 55.6% (n=18)   👈 Best performing range!
  small (100k-500k)   : Win Rate 41.7% (n=12)
  mid (500k-2M)       : Win Rate 35.3% (n=8)
  large (>2M)         : Win Rate 28.6% (n=7)

================================================================================
TUNING RECOMMENDATIONS
================================================================================

[MEDIUM] Conviction Type
  Issue: Nuanced conviction underperforming: 33.3% win rate
  Recommendation: Disable or tighten criteria for Nuanced conviction alerts
  Action: Review why Nuanced signals are failing - may need higher thresholds
                   👆 Actionable advice!

[LOW   ] Market Cap
  Issue: micro (<100k) range performs best (55.6% vs 42.2% overall)
  Recommendation: Consider focusing more on micro (<100k) tokens
  Action: Adjust MAX_MARKET_CAP_FOR_DEFAULT_ALERT to favor this range
```

---

## What to Look For

### 🎯 Target Metrics

| Metric | Good | Needs Work |
|--------|------|------------|
| Win Rate | >40% | <35% |
| Score Difference | >1.5 | <1.0 |
| Smart Money Advantage | >15% | <10% |

### 🚨 Red Flags

- **Low win rate (<35%)** → Bot is too aggressive, tighten criteria
- **Score difference <1.0** → Scoring logic isn't working, adjust weights
- **Smart money advantage <10%** → Smart money detection has issues
- **One conviction type <30% win rate** → That conviction type is broken

### ✅ Good Signs

- **Win rate >45%** → Bot is well-tuned
- **Score difference >1.5** → Scoring effectively differentiates quality
- **Smart money advantage >20%** → Smart wallet detection working great
- **All convictions >35% win rate** → All signal types are viable

---

## Quick Tuning Guide

Based on analysis results, here's what to adjust:

### If Win Rate is Low (<35%)

```python
# In config.py, raise the bar:
HIGH_CONFIDENCE_SCORE = 7  # Was 6
MIN_LIQUIDITY_USD = 10000  # Was 5000
VOL_24H_MIN_FOR_ALERT = 15000  # Was 10000
REQUIRE_SMART_MONEY_FOR_ALERT = True  # Was False
```

### If Score Difference is Low (<1.0)

```python
# In app/analyze_token.py, increase smart money bonus:
if smart_money_detected:
    score += 3  # Was 2
```

### If Smart Money Advantage is Low (<10%)

Check feed alternation is working:
```bash
# Look for smart_cycle in logs
docker logs callsbot-worker --tail 100 | grep "smart_cycle"
```

### If Specific Conviction Underperforms

```python
# Disable underperforming conviction:
# In config.py
NUANCED_SCORE_REDUCTION = 2  # Increase from 1
```

---

## Files Created

| File | Purpose |
|------|---------|
| `analyze_signals.py` | Main signal performance analyzer |
| `track_signal_reasons.py` | Records WHY each signal was sent (optional) |
| `SIGNAL_ANALYSIS.md` | Comprehensive documentation |
| `MONITORING_SYSTEM.md` | Updated with signal analysis section |
| `QUICK_START.md` | This file |

---

## Regular Workflow

### Weekly Check (5 minutes)

```powershell
# 1. Copy database
scp root@64.227.157.221:/opt/callsbotonchain/var/alerted_tokens.db var/

# 2. Run analysis
python monitoring/analyze_signals.py 7

# 3. Review win rate and recommendations
# 4. If changes needed, SSH to server and edit config
```

### Monthly Deep Dive (30 minutes)

```powershell
# 1. Copy database
scp root@64.227.157.221:/opt/callsbotonchain/var/alerted_tokens.db var/

# 2. Run 30-day analysis
python monitoring/analyze_signals.py 30

# 3. Compare with previous month
# 4. Implement 1-2 high-priority recommendations
# 5. Document changes in tuning log
```

---

## Next Steps

1. **Run your first analysis**
   ```powershell
   scp root@64.227.157.221:/opt/callsbotonchain/var/alerted_tokens.db var/
   python monitoring/analyze_signals.py
   ```

2. **Wait for more data if needed**
   - Need 10+ signals minimum
   - 50+ signals for good statistics
   - 100+ signals for confidence

3. **Implement top recommendations**
   - Focus on HIGH priority first
   - Change 1-2 things at a time
   - Wait 1 week to see impact

4. **Re-analyze and iterate**
   - Run weekly analysis
   - Track win rate over time
   - Fine-tune based on data

---

## Documentation

- **[SIGNAL_ANALYSIS.md](SIGNAL_ANALYSIS.md)** - Full documentation
- **[MONITORING_SYSTEM.md](MONITORING_SYSTEM.md)** - Overall monitoring
- **[../ops/ANALYSIS_GUIDE.md](../ops/ANALYSIS_GUIDE.md)** - Manual SQL queries

---

## Support

If analysis shows unexpected results:

1. Verify database is up-to-date (check last modified time)
2. Ensure tracking is running (check `alerted_token_stats` has data)
3. Review ops/TROUBLESHOOTING.md for common issues

---

**Created**: October 4, 2025
**Ready to use immediately**

