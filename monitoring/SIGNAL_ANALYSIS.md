# Signal Performance Analysis System

## Overview

This system answers the most critical question for your trading bot: **"Are my signals actually profitable?"**

It tracks:
1. ✅ **Which tokens pumped or dumped** after your alerts
2. 🔍 **WHY the bot sent each signal** (detailed criteria)
3. 📊 **Which conditions correlate with wins** vs losses
4. 🎯 **Specific tuning recommendations** based on performance

---

## Quick Start

### 1. Download Database from Server

```bash
# Copy the database locally for analysis
scp root@64.227.157.221:/opt/callsbotonchain/var/alerted_tokens.db var/
```

### 2. Run Signal Analysis

```bash
# Analyze last 7 days
python monitoring/analyze_signals.py

# Analyze last 30 days
python monitoring/analyze_signals.py 30
```

### 3. Review Results

The analyzer will show:
- Win rate and outcome distribution
- Score correlation with outcomes
- Smart money detection effectiveness
- Market cap sweet spots
- Specific tuning recommendations

---

## Understanding Outcomes

### Outcome Classifications

| Outcome | Meaning | Peak Gain | Current Status |
|---------|---------|-----------|----------------|
| 🚀 `big_win` | Hit 3x and held | ≥200% | Still ≥50% up |
| ✅ `win` | Strong pump holding | ≥50% | Still ≥50% up |
| 📈 `small_win` | Modest gain | ≥10% | Still positive |
| ➡️ `flat` | Sideways | -10% to +10% | Minimal movement |
| 📉 `small_loss` | Minor dump | -30% to -10% | Losing position |
| ❌ `loss` | Major dump | <-30% | Down 50%+ |
| 💀 `rug` | Rugpull | Any | Down 80%+ or LP gone |
| ⚠️ `pumped_then_dumped` | Gave back gains | ≥200% | Now <50% |
| ⚠️ `pumped_then_faded` | Faded after pump | ≥50% | Now <50% |

### Target Win Rate

- **Good**: 40-50% win rate
- **Excellent**: >50% win rate
- **Needs Tuning**: <35% win rate

---

## What Gets Analyzed

### 1. Overall Performance

```
📊 Overall Performance:
  Total Signals: 45
  Win Rate: 42.2%
  Wins: 19
  Losses: 12
```

**Key Metrics:**
- Total signals sent in period
- Overall win rate (wins / total)
- Number of winning vs losing signals

### 2. Outcome Distribution

```
📈 Outcome Distribution:
  big_win              :   7 (15.6%) | Avg Gain: +320.5% | Avg Score: 8.4
  win                  :  12 (26.7%) | Avg Gain: +85.3% | Avg Score: 7.8
  small_win            :   8 (17.8%) | Avg Gain: +15.2% | Avg Score: 6.9
  ...
```

**Shows:**
- How many signals fall into each outcome category
- Average gain for each outcome type
- Average score for each outcome (higher = bot was more confident)

**Look For:**
- Are high-score signals actually performing better?
- Are "big wins" associated with higher scores?
- Are losses associated with lower scores?

### 3. Conviction Performance

```
🎯 Conviction Performance:
  Smart Money         :  25 signals | Win Rate: 52.0%
  Nuanced             :  12 signals | Win Rate: 33.3%
  Velocity            :   8 signals | Win Rate: 37.5%
```

**Conviction Types:**
- **Smart Money** - Top wallets actively buying
- **Nuanced** - Relaxed criteria, higher risk
- **Velocity** - High transaction velocity detected
- **Strict** - All strict criteria passed

**Action Items:**
- If one conviction type underperforms, tighten its criteria
- If one conviction type excels, favor it more

### 4. Score Analysis

```
📊 Score Analysis:
  Winners Avg Score: 7.8/10
  Losers Avg Score: 6.0/10
  Difference: +1.8 ✅
```

**Interpretation:**
- ✅ **Good** (>1.5 difference): Scoring logic is effective
- ⚠️ **Warning** (0.5-1.5): Scoring needs improvement
- ❌ **Bad** (<0.5): Scoring is broken, not differentiating quality

**If Difference is Low:**
- Review scoring weights in `app/analyze_token.py`
- Smart money bonus may be too low
- Volume/momentum weights may need adjustment

### 5. Smart Money Analysis

```
💎 Smart Money Analysis:
  Smart Money Win Rate: 52.0%
  No Smart Money Win Rate: 28.6%
  Smart Money Advantage: +23.4% ✅
```

**Interpretation:**
- ✅ **Strong** (>15% advantage): Smart money detection working
- ⚠️ **Weak** (5-15%): Some false positives likely
- ❌ **Broken** (<5%): Feed alternation or detection issue

**If Advantage is Low:**
- Check feed alternation is working (`is_smart_cycle` logic)
- Verify smart wallet detection in feed
- Consider requiring smart money for all alerts

### 6. Market Cap Performance

```
💰 Market Cap Performance:
  micro (<100k)       : Win Rate 55.6% (n=18)
  small (100k-500k)   : Win Rate 41.7% (n=12)
  mid (500k-2M)       : Win Rate 35.3% (n=8)
  large (>2M)         : Win Rate 28.6% (n=7)
```

**Action Items:**
- Focus on market cap ranges with highest win rates
- Adjust `MAX_MARKET_CAP_FOR_DEFAULT_ALERT` accordingly
- Consider tighter criteria for underperforming ranges

### 7. Timing Analysis

```
⏱️  Average Time to Peak: 47 minutes
```

**Interpretation:**
- **Fast** (<30 min): Signals pump quickly, reduce tracking interval
- **Moderate** (30-60 min): Current setup likely optimal
- **Slow** (>90 min): May be catching moves too late

---

## Tuning Recommendations

The system generates prioritized, actionable recommendations:

```
[HIGH  ] Win Rate
  Issue: Low win rate: 28.5%
  Recommendation: Increase HIGH_CONFIDENCE_SCORE threshold to be more selective
  Action: Consider raising HIGH_CONFIDENCE_SCORE from current to +1 or +2

[MEDIUM] Conviction Type
  Issue: Nuanced conviction underperforming: 33.3% win rate
  Recommendation: Disable or tighten criteria for Nuanced conviction alerts
  Action: Review why Nuanced signals are failing - may need higher thresholds

[LOW   ] Market Cap
  Issue: micro (<100k) range performs best (55.6% vs 42.2% overall)
  Recommendation: Consider focusing more on micro (<100k) tokens
  Action: Adjust MAX_MARKET_CAP_FOR_DEFAULT_ALERT to favor this range
```

### Priority Levels

- **HIGH** - Critical issues, immediate action needed
- **MEDIUM** - Important optimizations, schedule soon
- **LOW** - Nice-to-have improvements

### Common Recommendations

#### 1. Low Win Rate

**Problem:** Overall win rate <35%

**Solutions:**
- Increase `HIGH_CONFIDENCE_SCORE` (raise the bar)
- Increase `MIN_LIQUIDITY_USD` (avoid low liquidity)
- Increase `VOL_24H_MIN_FOR_ALERT` (require more activity)
- Enable `REQUIRE_SMART_MONEY_FOR_ALERT=true`

#### 2. Score Not Differentiating

**Problem:** Winners and losers have similar scores

**Solutions:**
- Increase smart money bonus in `score_token()`
- Adjust momentum weights (1h change)
- Review market cap scoring logic
- Add more weight to volume metrics

#### 3. Smart Money Not Working

**Problem:** Smart money advantage <10%

**Solutions:**
- Verify feed alternation (check logs for `is_smart_cycle`)
- Check if smart wallets are in the feed
- Increase smart money bonus in scoring
- Tighten non-smart money criteria

#### 4. Specific Conviction Underperforming

**Problem:** One conviction type has low win rate

**Solutions:**
- **Nuanced**: Reduce `NUANCED_LIQUIDITY_FACTOR` (tighten)
- **Velocity**: Increase `REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT`
- **Strict**: May need to relax slightly if too restrictive

#### 5. Wrong Market Cap Range

**Problem:** Best performers are in unexpected range

**Solutions:**
- Adjust `MAX_MARKET_CAP_FOR_DEFAULT_ALERT`
- Set `MICROCAP_SWEET_MIN` and `MICROCAP_SWEET_MAX`
- Add market cap multipliers in scoring

---

## Workflow for Tuning

### Step 1: Run Analysis (Weekly)

```bash
# Copy latest database
scp root@64.227.157.221:/opt/callsbotonchain/var/alerted_tokens.db var/

# Run analysis
python monitoring/analyze_signals.py 7
```

### Step 2: Review Key Metrics

1. **Win Rate** - Is it above 40%?
2. **Score Difference** - Is it above 1.5?
3. **Smart Money Advantage** - Is it above 15%?
4. **Conviction Performance** - Any type underperforming?

### Step 3: Implement Recommendations

Focus on HIGH priority items first:

```bash
# SSH to server
ssh root@64.227.157.221

# Edit config
cd /opt/callsbotonchain
nano config.py

# Restart bot
docker-compose restart callsbot-worker
```

### Step 4: Monitor Impact

Wait 3-7 days, then re-analyze:

```bash
python monitoring/analyze_signals.py 7
```

Compare win rates before/after changes.

### Step 5: Iterate

Continue tuning based on new data. Track changes:

```bash
# Document what you changed
echo "2025-10-04: Increased HIGH_CONFIDENCE_SCORE from 6 to 7" >> tuning_log.txt
```

---

## Advanced: Recording Signal Reasons

For deep analysis of WHY each signal was sent:

### Setup (Optional)

The `track_signal_reasons.py` module can record detailed criteria for each alert:

- Score breakdown with weights
- All metrics at alert time (price, mcap, liquidity, volume)
- Momentum indicators (1h, 24h change)
- Security metrics (mint revoked, LP locked)
- Holder composition (top10, bundlers, insiders)
- Gating path taken (strict vs nuanced)
- Transaction context

### Integration

To enable, add to `scripts/bot.py` in the `process_feed_item()` function after `mark_as_alerted()`:

```python
try:
    from monitoring.track_signal_reasons import record_signal_reason
    
    gating_results = {
        'senior_strict': passed_senior_strict,
        'senior_nuanced': passed_senior_nuanced,
        'junior_strict': passed_junior_strict,
        'junior_nuanced': passed_junior_nuanced
    }
    
    record_signal_reason(
        token_address=token_address,
        alerted_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        final_score=score,
        preliminary_score=preliminary_score,
        smart_money_detected=smart_involved,
        conviction_type=conviction_type,
        stats=stats,
        tx_data=tx,
        scoring_details=scoring_details,
        gating_results=gating_results
    )
except Exception as e:
    # Don't fail alert on recording error
    pass
```

### Benefits

With detailed reasons recorded, you can answer:
- Do tokens with >5% 1h momentum perform better?
- Does top10 concentration <40% correlate with wins?
- Are LP-locked tokens safer?
- Which dex has better signals?

---

## Troubleshooting

### "Database not found"

```bash
# Make sure you copied it locally
scp root@64.227.157.221:/opt/callsbotonchain/var/alerted_tokens.db var/

# Check it exists
ls -lh var/alerted_tokens.db
```

### "No signals found"

Database may be too old or empty. Check:

```bash
sqlite3 var/alerted_tokens.db "SELECT COUNT(*) FROM alerted_tokens;"
```

If 0, bot hasn't sent any alerts yet.

### "Insufficient data"

Need at least 10-15 signals for meaningful analysis. Wait a few days.

### Analysis shows all "unknown" outcomes

Tracking system may not be running. Check:

```bash
sqlite3 var/alerted_tokens.db "SELECT COUNT(*) FROM alerted_token_stats WHERE peak_price_usd > 0;"
```

If 0, tracking isn't updating prices. Verify `TRACK_INTERVAL_MIN` is set and bot is tracking tokens.

---

## FAQ

**Q: How often should I run this?**
A: Weekly for active tuning, monthly for monitoring.

**Q: What's a good win rate target?**
A: 40-50% is good for crypto. >50% is excellent. <35% needs tuning.

**Q: Should I trust early results?**
A: No. Need at least 50+ signals for statistical significance. 100+ is ideal.

**Q: Why are some outcomes "unknown"?**
A: Token price data missing. Bot may have stopped tracking it, or price API failed.

**Q: Can I analyze specific time periods?**
A: Yes, modify the script to accept date ranges, or use SQL queries directly.

**Q: How do I know if changes worked?**
A: Run analysis before/after. Compare win rates. Wait 1-2 weeks between major changes.

---

## Related Documentation

- [MONITORING_SYSTEM.md](MONITORING_SYSTEM.md) - Overall monitoring setup
- [../ops/ANALYSIS_GUIDE.md](../ops/ANALYSIS_GUIDE.md) - Manual analysis queries
- [../docs/TRADING_MONITORING.md](../docs/TRADING_MONITORING.md) - Trading system monitoring

---

**Last Updated**: October 4, 2025
**Version**: 1.0
**Status**: Production Ready

