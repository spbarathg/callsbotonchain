# 📋 MONITORING CHECKLIST - V4 Moonshot Hunter (38% Win Rate)

**Date:** October 21, 2025  
**Purpose:** Daily/weekly monitoring to ensure system maintains 38% win rate  
**Performance Baseline:** 38% win rate (2x+ gains) in 1 day

---

## 🎯 MONITORING PHILOSOPHY

**Key Principle:** Trust but verify

This system achieved 38% win rate through data-driven optimization. Monitor regularly to ensure it maintains this performance.

**Monitoring Frequency:**
- **Daily:** Quick health checks (5 minutes)
- **Weekly:** Deep analysis (30 minutes)
- **Monthly:** Performance review (1 hour)

---

## 📅 DAILY MONITORING (5 Minutes)

Run these checks every day:

### **1. Container Health (30 seconds)**

```bash
ssh root@64.227.157.221 "docker ps --format '{{.Names}}: {{.Status}}' | grep callsbot"
```

**Expected:**
```
callsbot-worker: Up X hours (healthy)
callsbot-signal-aggregator: Up X hours (healthy)
callsbot-redis: Up X hours (healthy)
callsbot-trader: Up X hours (healthy)
```

**✅ PASS:** All containers "Up" and "healthy"  
**❌ FAIL:** Any container "Restarting" or missing

---

### **2. Signal Volume (1 minute)**

```bash
ssh root@64.227.157.221 "docker exec callsbot-worker sqlite3 var/alerted_tokens.db \"SELECT COUNT(*) FROM alerted_tokens WHERE alerted_at > (strftime('%s', 'now') - 86400)\""
```

**Expected:** 10-30 signals per day

**✅ PASS:** 10-30 signals  
**⚠️ WARNING:** 5-10 or 30-50 signals (monitor closely)  
**❌ FAIL:** <5 or >50 signals (investigate)

---

### **3. Score Distribution (1 minute)**

```bash
ssh root@64.227.157.221 "docker logs --since 24h callsbot-worker | grep -oP 'score.*?/10' | sort | uniq -c"
```

**Expected:**
```
   15 score 2/10
   12 score 3/10
    8 score 6/10
    5 score 7/10  ← Alerted
    3 score 8/10  ← Alerted
    2 score 9/10  ← Alerted
    1 score 10/10 ← Alerted
```

**✅ PASS:** All alerted signals have score ≥7  
**❌ FAIL:** Any signals with score <7 (threshold not enforced!)

---

### **4. Telegram Delivery (1 minute)**

```bash
ssh root@64.227.157.221 "docker logs --since 24h callsbot-worker | grep 'telegram_ok=True' | wc -l"
```

**Expected:** Should match signal count (100% delivery)

**✅ PASS:** Count matches signals  
**❌ FAIL:** Count < signals (notifications broken)

---

### **5. Error Scan (2 minutes)**

```bash
ssh root@64.227.157.221 "
echo '=== Database Locks ==='
docker logs --since 24h callsbot-worker callsbot-signal-aggregator | grep -c 'database is locked'

echo ''
echo '=== Telethon Errors ==='
docker logs --since 24h callsbot-worker | grep -c 'event loop must not change'

echo ''
echo '=== Python Exceptions ==='
docker logs --since 24h callsbot-worker | grep -c 'Traceback'
"
```

**Expected:**
```
=== Database Locks ===
0

=== Telethon Errors ===
0

=== Python Exceptions ===
0
```

**✅ PASS:** All counts are 0  
**❌ FAIL:** Any count > 0 (investigate immediately)

---

## 📊 WEEKLY MONITORING (30 Minutes)

Run these checks every week (e.g., Monday morning):

### **1. Win Rate Analysis (10 minutes)**

```bash
ssh root@64.227.157.221 "docker exec callsbot-worker sqlite3 var/alerted_tokens.db \"
SELECT 
    COUNT(*) as total_signals,
    SUM(CASE WHEN s.max_gain_percent >= 100 THEN 1 ELSE 0 END) as winners_2x,
    ROUND(SUM(CASE WHEN s.max_gain_percent >= 100 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) || '%' as win_rate,
    ROUND(AVG(CASE WHEN s.max_gain_percent >= 100 THEN s.max_gain_percent END), 1) as avg_win,
    ROUND(AVG(CASE WHEN s.max_gain_percent < 100 THEN s.max_gain_percent END), 1) as avg_loss
FROM alerted_tokens a
LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
WHERE a.alerted_at > (strftime('%s', 'now') - 604800)
\""
```

**Expected:**
```
total_signals | winners_2x | win_rate | avg_win | avg_loss
70-210        | 21-84      | 30-40%   | 80-120% | -10 to -15%
```

**✅ PASS:** Win rate 30-40%  
**⚠️ WARNING:** Win rate 25-30% (monitor closely)  
**❌ FAIL:** Win rate <25% (investigate)

---

### **2. Market Cap Distribution (5 minutes)**

```bash
ssh root@64.227.157.221 "docker exec callsbot-worker sqlite3 var/alerted_tokens.db \"
SELECT 
    CASE 
        WHEN s.first_market_cap_usd < 10000 THEN 'Below 10k (SHOULD BE NONE!)'
        WHEN s.first_market_cap_usd < 50000 THEN '10k-50k (Moonshot)'
        WHEN s.first_market_cap_usd < 100000 THEN '50k-100k (Sweet Spot)'
        WHEN s.first_market_cap_usd < 200000 THEN '100k-200k (Best Zone)'
        WHEN s.first_market_cap_usd < 500000 THEN '200k-500k (Established)'
        ELSE 'Above 500k (SHOULD BE NONE!)'
    END as range,
    COUNT(*) as signals
FROM alerted_tokens a
LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
WHERE a.alerted_at > (strftime('%s', 'now') - 604800)
GROUP BY range
ORDER BY MIN(s.first_market_cap_usd)
\""
```

**Expected:**
```
10k-50k (Moonshot)      | 20-40 signals (30%)
50k-100k (Sweet Spot)   | 30-50 signals (40%)
100k-200k (Best Zone)   | 15-30 signals (20%)
200k-500k (Established) | 5-15 signals (10%)
```

**✅ PASS:** 100% of signals in $10k-$500k range  
**❌ FAIL:** Any signals below $10k or above $500k (filters broken!)

---

### **3. Score Quality Check (5 minutes)**

```bash
ssh root@64.227.157.221 "docker exec callsbot-worker sqlite3 var/alerted_tokens.db \"
SELECT 
    final_score,
    COUNT(*) as signals,
    ROUND(AVG(s.max_gain_percent), 1) as avg_gain,
    ROUND(SUM(CASE WHEN s.max_gain_percent >= 100 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) || '%' as win_rate
FROM alerted_tokens a
LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
WHERE a.alerted_at > (strftime('%s', 'now') - 604800)
GROUP BY final_score
ORDER BY final_score
\""
```

**Expected:**
```
final_score | signals | avg_gain | win_rate
7           | 30-50   | 60-100%  | 25-35%
8           | 25-45   | 80-120%  | 30-40%
9           | 15-30   | 90-130%  | 32-42%
10          | 5-15    | 100-150% | 35-45%
```

**✅ PASS:** All scores ≥7, higher scores perform better  
**❌ FAIL:** Any scores <7 (threshold not enforced!)

---

### **4. Multi-Bot Consensus Check (5 minutes)**

```bash
ssh root@64.227.157.221 "
echo '=== Signal Aggregator Status ==='
docker logs --since 7d callsbot-signal-aggregator | grep 'Monitoring active' | tail -1

echo ''
echo '=== Redis Keys ==='
docker exec callsbot-redis redis-cli KEYS 'signal_aggregator:token:*' | wc -l

echo ''
echo '=== Consensus Signals (Last 7 Days) ==='
docker logs --since 7d callsbot-worker | grep 'MULTI-BOT CONSENSUS' | wc -l
"
```

**Expected:**
```
=== Signal Aggregator Status ===
✅ Signal Aggregator: Monitoring active

=== Redis Keys ===
5-20 (tokens from other bots)

=== Consensus Signals (Last 7 Days) ===
10-30 (signals with 3+ bot consensus)
```

**✅ PASS:** Signal Aggregator active, consensus signals present  
**⚠️ WARNING:** 0 consensus signals (other bots quiet or aggregator down)

---

### **5. System Resource Check (5 minutes)**

```bash
ssh root@64.227.157.221 "
echo '=== Disk Space ==='
df -h /opt/callsbotonchain | tail -1

echo ''
echo '=== Memory Usage ==='
free -h

echo ''
echo '=== Docker Stats (5s sample) ==='
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' | grep callsbot
"
```

**Expected:**
```
=== Disk Space ===
/dev/vda1  80G  15G  65G  19% /

=== Memory Usage ===
              total        used        free
Mem:           2.0G        1.2G        800M

=== Docker Stats ===
callsbot-worker             0.50%     150MB / 2GB
callsbot-signal-aggregator  0.20%     100MB / 2GB
callsbot-redis              0.10%     50MB / 2GB
callsbot-trader             0.30%     120MB / 2GB
```

**✅ PASS:** Disk <80%, Memory <80%, CPU <50%  
**⚠️ WARNING:** Any metric >80% (may need cleanup/upgrade)

---

## 📈 MONTHLY MONITORING (1 Hour)

Run these checks every month (e.g., 1st of month):

### **1. Comprehensive Performance Review (30 minutes)**

```bash
ssh root@64.227.157.221 "docker exec callsbot-worker python << 'PYEOF'
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('var/alerted_tokens.db')
c = conn.cursor()

month_ago = (datetime.now() - timedelta(days=30)).timestamp()

# Overall stats
c.execute(\"\"\"
    SELECT 
        COUNT(*) as signals,
        SUM(CASE WHEN s.max_gain_percent >= 100 THEN 1 ELSE 0 END) as winners,
        ROUND(SUM(CASE WHEN s.max_gain_percent >= 100 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as win_rate,
        ROUND(AVG(CASE WHEN s.max_gain_percent >= 100 THEN s.max_gain_percent END), 1) as avg_win,
        ROUND(AVG(CASE WHEN s.max_gain_percent < 100 THEN s.max_gain_percent END), 1) as avg_loss,
        MAX(s.max_gain_percent) as best_winner
    FROM alerted_tokens a
    LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
    WHERE a.alerted_at >= ?
\"\"\", (month_ago,))

result = c.fetchone()
print(f\"30-Day Performance:\")
print(f\"  Total Signals: {result[0]}\")
print(f\"  Winners (2x+): {result[1]}\")
print(f\"  Win Rate: {result[2]}%\")
print(f\"  Avg Win: {result[3]}%\")
print(f\"  Avg Loss: {result[4]}%\")
print(f\"  Best Winner: {result[5]}%\")

# Weekly breakdown
print(f\"\nWeekly Breakdown:\")
for week in range(4):
    week_start = (datetime.now() - timedelta(days=(week+1)*7)).timestamp()
    week_end = (datetime.now() - timedelta(days=week*7)).timestamp()
    
    c.execute(\"\"\"
        SELECT 
            COUNT(*) as signals,
            ROUND(SUM(CASE WHEN s.max_gain_percent >= 100 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as win_rate
        FROM alerted_tokens a
        LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
        WHERE a.alerted_at >= ? AND a.alerted_at < ?
    \"\"\", (week_start, week_end))
    
    result = c.fetchone()
    print(f\"  Week {4-week}: {result[0]} signals, {result[1]}% WR\")

conn.close()
PYEOF
"
```

**Expected:**
```
30-Day Performance:
  Total Signals: 300-900
  Winners (2x+): 90-360
  Win Rate: 30-40%
  Avg Win: 80-120%
  Avg Loss: -10 to -15%
  Best Winner: 500-2000%

Weekly Breakdown:
  Week 1: 70-210 signals, 30-40% WR
  Week 2: 70-210 signals, 30-40% WR
  Week 3: 70-210 signals, 30-40% WR
  Week 4: 70-210 signals, 30-40% WR
```

**✅ PASS:** Consistent 30-40% win rate across all weeks  
**⚠️ WARNING:** Win rate declining week-over-week  
**❌ FAIL:** Win rate <25% for 2+ weeks

---

### **2. Configuration Drift Check (15 minutes)**

```bash
ssh root@64.227.157.221 "
echo '=== Environment Variables ==='
docker exec callsbot-worker python -c 'from app.config_unified import MIN_MARKET_CAP_USD, MAX_MARKET_CAP_FOR_DEFAULT_ALERT, USE_LIQUIDITY_FILTER, MIN_LIQUIDITY_USD, GENERAL_CYCLE_MIN_SCORE, SMART_MONEY_SCORE_BONUS; print(f\"MIN_MARKET_CAP_USD: {MIN_MARKET_CAP_USD}\"); print(f\"MAX_MARKET_CAP_FOR_DEFAULT_ALERT: {MAX_MARKET_CAP_FOR_DEFAULT_ALERT}\"); print(f\"USE_LIQUIDITY_FILTER: {USE_LIQUIDITY_FILTER}\"); print(f\"MIN_LIQUIDITY_USD: {MIN_LIQUIDITY_USD}\"); print(f\"GENERAL_CYCLE_MIN_SCORE: {GENERAL_CYCLE_MIN_SCORE}\"); print(f\"SMART_MONEY_SCORE_BONUS: {SMART_MONEY_SCORE_BONUS}\")'

echo ''
echo '=== Trader Liquidity Filter ==='
docker exec callsbot-trader printenv TS_MIN_LIQUIDITY_USD
"
```

**Expected:**
```
=== Environment Variables ===
MIN_MARKET_CAP_USD: 10000.0
MAX_MARKET_CAP_FOR_DEFAULT_ALERT: 500000.0
USE_LIQUIDITY_FILTER: False
MIN_LIQUIDITY_USD: 0.0
GENERAL_CYCLE_MIN_SCORE: 7
SMART_MONEY_SCORE_BONUS: 0

=== Trader Liquidity Filter ===
0
```

**✅ PASS:** All values match snapshot  
**❌ FAIL:** Any value differs (configuration drift!)

---

### **3. Database Cleanup (15 minutes)**

```bash
ssh root@64.227.157.221 "
echo '=== Database Size ==='
du -h /opt/callsbotonchain/var/*.db

echo ''
echo '=== Old Records (>30 days) ==='
docker exec callsbot-worker sqlite3 var/alerted_tokens.db \"SELECT COUNT(*) FROM alerted_tokens WHERE alerted_at < (strftime('%s', 'now') - 2592000)\"

echo ''
echo '=== Cleanup Old Records ==='
docker exec callsbot-worker sqlite3 var/alerted_tokens.db \"DELETE FROM alerted_tokens WHERE alerted_at < (strftime('%s', 'now') - 2592000); VACUUM;\"

echo ''
echo '=== New Database Size ==='
du -h /opt/callsbotonchain/var/*.db
"
```

---

## 🚨 ALERT THRESHOLDS

### **🔴 CRITICAL (Immediate Action Required):**

| Metric | Threshold | Action |
|--------|-----------|--------|
| Win Rate | <20% for 3+ days | Restore from snapshot |
| Signals/Day | 0 for 6+ hours | Restart containers |
| Score <7 in DB | Any | Fix score enforcement |
| Database Locks | >10 in 24h | Fix Telethon session |
| Container Down | Any | Restart immediately |

### **🟡 WARNING (Monitor Closely):**

| Metric | Threshold | Action |
|--------|-----------|--------|
| Win Rate | 20-25% for 7+ days | Review signal quality |
| Signals/Day | <5 or >50 | Check filters |
| Telegram Delivery | <95% | Check Telethon |
| Disk Space | >80% | Cleanup old data |
| Memory Usage | >80% | Optimize or upgrade |

### **🟢 GOOD (System Healthy):**

| Metric | Threshold |
|--------|-----------|
| Win Rate | 30-40% |
| Signals/Day | 10-30 |
| Telegram Delivery | 100% |
| All Scores | ≥7 |
| Disk Space | <70% |
| Memory Usage | <70% |

---

## ✅ MONTHLY CHECKLIST

- [ ] **Performance Review:** 30-40% win rate maintained
- [ ] **Configuration Check:** No drift from snapshot
- [ ] **Database Cleanup:** Old records removed
- [ ] **Disk Space:** <80% used
- [ ] **Memory Usage:** <80% used
- [ ] **Error Rate:** <1% of cycles
- [ ] **Telegram Delivery:** 100%
- [ ] **Multi-Bot Consensus:** Active
- [ ] **Score Distribution:** All ≥7
- [ ] **Market Cap Range:** 100% in $10k-$500k

**If all checked: ✅ SYSTEM HEALTHY!**

---

**Last Updated:** October 21, 2025  
**Baseline Performance:** 38% win rate (2x+ gains)  
**Status:** ✅ MONITORING PROTOCOL ACTIVE

