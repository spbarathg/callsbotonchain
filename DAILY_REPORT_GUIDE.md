# Daily Performance Report - User Guide

## 📊 What It Does

The daily performance report provides comprehensive insights into:
1. **Bot Health** - Are all containers running properly?
2. **Signal Performance** - Win rate, average gains, rug rate, top performers
3. **Trading Profitability** - Projected P&L for different trading strategies
4. **Actionable Recommendations** - What to do next to improve performance

---

## 🚀 How to Run

### Manual Execution (Anytime)
```bash
# SSH into server
ssh root@64.227.157.221

# Run the report
cd /opt/callsbotonchain
./run_daily_report.sh
```

### Automated Daily Reports
✅ **Already configured!** The report runs automatically every day at **9:00 AM UTC**.

**View automated report logs:**
```bash
ssh root@64.227.157.221 "tail -100 /var/log/callsbot-daily-report.log"
```

---

## 📈 Understanding the Report

### Bot Health Section
```
🏥 BOT HEALTH
Overall Status: HEALTHY
  ✅ callsbot-worker: Up 4 minutes (healthy)
  ✅ callsbot-tracker: Up 18 minutes (healthy)
```

**What to watch for:**
- ❌ If any container shows "unhealthy" → Check logs immediately
- 🔴 "Overall Status: ERROR" → Bot is down, needs immediate attention

---

### Signal Performance Section
```
📈 SIGNAL PERFORMANCE
Total Signals: 45
Tracked Signals: 42 (93.3%)

📊 Overall Metrics:
  Win Rate: 18.5% (8/42)
  Avg Gain: 145.2% (Multiplier: 2.45x)
  Max Gain: 856.3% (Multiplier: 9.56x)
  Rug Rate: 9.5% (4/42)

🎯 Success Tiers:
  2x+ Gains: 7
  5x+ Gains: 2
  10x+ Gains: 0

📊 Performance by Score:
  Score    Count    Win Rate    Avg Gain    2x+
  -------  -------  -----------  -----------  -------
  10       15       20.0%        178.5%       6
  9        12       25.0%        134.2%       3
  8        8        12.5%        98.3%        1
  7        7        14.3%        76.4%        0
```

**Key Metrics Explained:**

| Metric | Target | Good | Warning | Critical |
|--------|--------|------|---------|----------|
| **Win Rate** | 15-20% | ≥15% | 10-15% | <10% |
| **Avg Multiplier** | 2.5-3.5x | ≥2.5x | 1.5-2.5x | <1.5x |
| **Rug Rate** | <10% | <10% | 10-15% | >15% |
| **Tracking Rate** | >80% | >80% | 50-80% | <50% |

---

### Trading Profitability Section
```
💰 TRADING PROFITABILITY ANALYSIS

📋 Trade only signals with score 7+
  Signals/Day: 42
  Win Rate: 18.5%
  Avg Multiplier: 2.45x
  Expected ROI: 145% per trade
  Risk Level: MEDIUM

  💵 Projection ($100 per trade):
    Daily Investment: $4,200
    Daily Return: $10,290
    Daily Profit: $6,090
    Weekly Profit: $42,630
    Monthly Profit: $182,700
```

**How to Read This:**

1. **Expected ROI per trade** - Average return on each signal
2. **Projections** - Assumes you trade EVERY signal with $100 each
3. **Risk Level** - Based on rug rate and volatility

**⚠️ IMPORTANT:** Projections assume:
- You can execute at alert price (reality: slippage)
- You exit at peak price (reality: impossible to time)
- Equal position sizes (reality: may want to size differently)

**Real-world adjustment:** Divide projections by 2-3x for realistic expectations

---

### Recommendations Section
```
💡 RECOMMENDATIONS
1. ✅ GOOD: Win rate is 18.5% (within target range 15-20%).
2. ✅ EXCELLENT: Average multiplier is 2.45x (meets target 2.5-3.5x).
3. ⚠️ WARNING: Rug rate is 12.5% (target: <10%). Monitor liquidity filters.
4. 💡 INSIGHT: Score 9 has best win rate (25.0%). Focus trading on this tier.
```

**Action Items:**
- ✅ **GOOD/EXCELLENT** → Keep current settings
- ⚠️ **WARNING** → Monitor for 24-48h, may need adjustment
- 🔴 **CRITICAL** → Take action immediately

---

## 💰 Real-Time Trading Profitability

### What This Means for Trading

**Current Setup (After Today's Fixes):**
- Bot is now functional and alerting on quality signals
- Tracker is collecting performance data
- In 24-48 hours, you'll have real data to validate profitability

### Path to Profitable Trading

**Phase 1: Data Collection (NOW - Next 48 hours)**
- ✅ Bot is alerting on signals
- ✅ Tracker is recording performance
- 🔄 Daily reports show real win rates
- **Action:** Monitor, don't trade yet

**Phase 2: Validation (48-72 hours)**
- Analyze first 2-3 daily reports
- Confirm win rate ≥15%
- Confirm avg multiplier ≥2.0x
- Confirm rug rate <15%
- **Action:** Paper trade (track without real money)

**Phase 3: Paper Trading (1-2 weeks)**
- Simulate trades with $100 per signal
- Track actual vs projected returns
- Identify best score tiers (7, 8, 9, or 10)
- Refine entry/exit strategy
- **Action:** Build confidence, refine approach

**Phase 4: Live Trading (After validation)**
- Start with small position sizes ($50-100)
- Only trade highest performing score tier
- Use stop losses (e.g., -20%)
- Take profits at targets (e.g., 2x, 5x, 10x)
- **Action:** Real money, real gains

---

## 🎯 Trading Strategy Recommendations

### Conservative (Low Risk)
```
- Trade only: Score 9-10 signals
- Position size: $50-100 per signal
- Expected signals: ~5-15 per day
- Target win rate: 20%+
- Target multiplier: 2.5x+
```

### Moderate (Medium Risk)
```
- Trade only: Score 7+ signals  
- Position size: $100 per signal
- Expected signals: ~20-40 per day
- Target win rate: 15-20%
- Target multiplier: 2.0x+
```

### Aggressive (High Risk)
```
- Trade all signals
- Position size: Varies by score
- Expected signals: ~50-100 per day
- Target win rate: 12-15%
- Target multiplier: 1.8x+
```

**Recommended:** Start with **Conservative** until you validate the system works.

---

## 📊 Historical Reports

Reports are saved in two locations:

1. **Daily timestamped:** `analytics/daily_report_YYYY-MM-DD.json`
2. **Latest report:** `analytics/latest_daily_report.json`

**View historical reports:**
```bash
ssh root@64.227.157.221
cd /opt/callsbotonchain/analytics
ls -lh daily_report_*.json
```

**Compare week-over-week:**
```bash
cat daily_report_2025-10-06.json | jq '.signal_performance.win_rate_pct'
cat daily_report_2025-10-13.json | jq '.signal_performance.win_rate_pct'
```

---

## 🔔 Optional: Telegram Notifications

To receive daily reports via Telegram:

1. **Set environment variables in `.env`:**
```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

2. **Restart the cron service:**
```bash
systemctl restart cron
```

3. **Test manually:**
```bash
cd /opt/callsbotonchain
./run_daily_report.sh
```

You'll receive a summary like:
```
🤖 CallsBotOnChain - Daily Report

📊 Signals: 42 (24h)
📈 Win Rate: 18.5%
💰 Avg Gain: 145.2%
🏥 Bot Status: HEALTHY

📄 Full report: /opt/callsbotonchain/analytics/latest_daily_report.json
```

---

## 🚨 What to Do If...

### No signals in 24 hours
```bash
# Check if worker is processing
docker logs callsbot-worker --tail 100 | grep -E "PASSED|REJECTED"

# Check configuration
docker logs callsbot-worker | grep "gates"
```

### Tracking rate < 50%
```bash
# Check tracker logs
docker logs callsbot-tracker --tail 100

# Verify tracker is fetching data
docker logs callsbot-tracker | grep "stats_cache_miss"
```

### Win rate < 10%
```bash
# This may indicate filters are too loose
# Consider raising score threshold or liquidity minimum
# Check COMPREHENSIVE_BOT_ANALYSIS_AND_FIXES.md for guidance
```

### Bot status degraded
```bash
# Check all containers
docker ps --filter name=callsbot

# Check specific container logs
docker logs callsbot-worker --tail 100
docker logs callsbot-tracker --tail 100
```

---

## 📋 Quick Reference Commands

```bash
# Run daily report manually
ssh root@64.227.157.221 "/opt/callsbotonchain/run_daily_report.sh"

# View latest report (JSON)
ssh root@64.227.157.221 "cat /opt/callsbotonchain/analytics/latest_daily_report.json | jq ."

# View automated report logs
ssh root@64.227.157.221 "tail -100 /var/log/callsbot-daily-report.log"

# Check cron job status
ssh root@64.227.157.221 "cat /etc/cron.d/callsbot-daily-report"

# View historical reports
ssh root@64.227.157.221 "ls -lh /opt/callsbotonchain/analytics/"
```

---

## 🎯 Success Criteria (First Week)

After 7 days of daily reports, you should see:

- [ ] Win rate: 15-20%
- [ ] Avg multiplier: 2.0x+
- [ ] Rug rate: <15%
- [ ] At least 2-3 signals with 5x+ gains
- [ ] Consistent signal flow (20-50/day)
- [ ] Bot health: HEALTHY every day

**If all checked:** ✅ Ready for paper trading  
**If 4-5 checked:** 🟡 Monitor for another week  
**If <4 checked:** 🔴 Adjust configuration (see COMPREHENSIVE_BOT_ANALYSIS_AND_FIXES.md)

---

## 📞 Need Help?

1. **Check the logs** (see Quick Reference Commands)
2. **Review COMPREHENSIVE_BOT_ANALYSIS_AND_FIXES.md** for detailed guidance
3. **Compare daily reports** to identify trends
4. **Monitor for 48-72 hours** before making changes

**Remember:** The bot needs 24-48 hours of data before making any judgments about performance!

---

**Last Updated:** October 6, 2025  
**Next Review:** October 8, 2025 (48 hours after fixes deployed)

