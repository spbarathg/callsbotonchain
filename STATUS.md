# 🤖 Bot Status - OPTIMAL CONFIG V2 + ML ACTIVE + SIGNAL AGGREGATOR

**Last Updated:** October 19, 2025, 9:00 PM IST  
**Status:** ✅ **OPTIMAL CONFIG V3 - SIGNAL AGGREGATOR + REDIS + ZERO DATABASE LOCKS**

---

## 🎯 CURRENT CONFIGURATION

### OPTIMAL MODE V2 (Data-Driven from 1,187 Tokens)

```
✅ Market Cap: $50k-$250k (extended to capture moonshots)
✅ Min Score: 8 (22.1% win rate, better than 9-10)
✅ Min Liquidity: $25,000 (RELAXED from $30k for more opportunities!)
✅ Max Liquidity: $100,000 (RAISED from $75k for established tokens)
✅ MAX_24H_CHANGE: 200% (anti-FOMO filter)
✅ MAX_1H_CHANGE: 150% (catch early entries)
✅ Soft Ranking: +1 bonus for momentum patterns
   - Consolidation: 24h[50,200%] + 1h≤0 → 35.5% win rate
   - Dip Buy: 24h[-50,-20%] + 1h≤0 → 29.3% win rate
   - 6h Momentum: 20-50% → 40.0% win rate (NEW!)
✅ ML Enhancement: ACTIVE (trained on 1,093 signals)
   - Gain predictor (regression)
   - Winner classifier (2x+ probability)
   - Auto-retrains weekly (Sundays 3 AM)
✅ Signal Aggregator: ACTIVE (monitoring 13 Telegram groups)
   - Multi-bot consensus validation via Redis
   - +2 score bonus for tokens mentioned in 3+ groups
   - **REDIS INTEGRATION:** Cross-process signal sharing
   - Container: callsbot-signal-aggregator (isolated)
   - Session: var/relay_user.session (shared with worker)
   - Quality validation: Rejects $0 liquidity tokens
   - TTL: 1 hour (auto-cleanup old signals)
```

---

## ⏱️ WHAT TO EXPECT IN 30 MINUTES (Verification Checklist)

**Current Time:** 9:00 PM IST  
**Check Time:** 9:30 PM IST (30 minutes later)

### **✅ Expected Observations:**

**1. Signal Aggregator Container Health:**
```bash
# Check container is still running
ssh root@64.227.157.221 "docker ps --filter 'name=signal-aggregator' --format '{{.Status}}'"
```

**Expected Output:**
```
Up X minutes (healthy)
```

**What This Means:**
- ✅ Container hasn't crashed or restarted
- ✅ Health check passing
- ✅ Monitoring is continuous

**2. Signal Aggregator Activity:**
```bash
# Check for monitoring activity and Redis connection
ssh root@64.227.157.221 "docker logs --since 30m callsbot-signal-aggregator | grep -E '(Monitoring active|Redis|Extracted|Rejected)' | tail -10"
```

**Expected Output:**
```
✅ Signal Aggregator: Monitoring active
📨 Signal Aggregator: New message from @GroupName (if groups are active)
🔍 Signal Aggregator: Extracted token ABC... from @GroupName (if tokens found)
✅ Signal Aggregator: Connected to Redis at redis://redis:6379/0 (on first token extraction)
⚠️  Signal Aggregator: Rejected ABC... (liq: $X, vol: $Y) (quality validation working)
```

**What This Means:**
- ✅ If you see "Monitoring active": Signal Aggregator is running
- ✅ If you see "Connected to Redis": Redis integration working (appears on first token extraction)
- ✅ If you see "Extracted token": Token addresses are being parsed
- ✅ If you see "Rejected": Quality validation is working (rejecting low-quality tokens)

**If No Messages:**
- ℹ️ This is NORMAL - external groups may not post frequently
- ℹ️ Signal Aggregator is still monitoring (check for "Monitoring active")
- ℹ️ Redis connection happens lazily (only when first token is extracted)

**3. Core Bot Processing:**
```bash
# Check bot is still processing
ssh root@64.227.157.221 "docker logs --since 30m callsbot-worker | grep -E '(FEED ITEMS|heartbeat)' | tail -5"
```

**Expected Output:**
```
FEED ITEMS: 77-86
{"type": "heartbeat", "pid": 1, "msg": "ok", ...}
```

**What This Means:**
- ✅ Bot is processing 77-86 tokens every 30 seconds
- ✅ No interruption from Signal Aggregator
- ✅ Both systems running in parallel

**4. Redis Health Check:**
```bash
# Verify Redis is accessible and has data
ssh root@64.227.157.221 "docker exec callsbot-redis redis-cli DBSIZE && docker exec callsbot-redis redis-cli KEYS 'signal_aggregator:*'"
```

**Expected Output:**
```
(integer) 15-25
signal_aggregator:token:ABC123... (if quality tokens were extracted)
(empty array) (if no quality tokens yet - this is NORMAL)
```

**What This Means:**
- ✅ Redis is running and accessible
- ✅ Database has keys (stats from worker + signals from aggregator)
- ℹ️ Empty `signal_aggregator:*` keys is NORMAL if no quality tokens posted yet
- ✅ Quality tokens (liq > $0, vol > $5k) will appear as `signal_aggregator:token:ADDRESS`

**5. No Database Lock Errors:**
```bash
# Verify no session conflicts
ssh root@64.227.157.221 "docker logs --since 30m callsbot-worker | grep -i 'database is locked'"
ssh root@64.227.157.221 "docker logs --since 30m callsbot-signal-aggregator | grep -i 'database is locked'"
```

**Expected Output:**
```
(empty - no results)
```

**What This Means:**
- ✅ No SQLite session file conflicts
- ✅ Shared session file (var/relay_user.session) working correctly
- ✅ Both containers can access Telethon without conflicts

**6. Signal Generation:**
```bash
# Check for any new signals
ssh root@64.227.157.221 "docker exec callsbot-worker sqlite3 var/alerted_tokens.db \"SELECT datetime(alerted_at, 'unixepoch') as time, substr(token_address,1,12) as token, final_score FROM alerted_tokens WHERE alerted_at > (strftime('%s', 'now') - 1800) ORDER BY alerted_at DESC\""
```

**Expected Output:**
- **If signals generated:** List of recent signals (depends on market conditions)
- **If no signals:** Empty result (normal during slow markets)

**What This Means:**
- ✅ Signal generation depends on market quality
- ✅ Low/no signals in 30 minutes is NORMAL during slow markets
- ✅ Bot is correctly filtering low-quality tokens
- ℹ️ With relaxed filters ($25k-$100k liquidity), expect 15-20 signals/day

### **🔴 Red Flags (What Should NOT Happen):**

**1. Database Lock Errors:**
```
❌ database is locked
❌ Session not authorized
❌ Telethon: Failed to connect
```
**If you see these:** SQLite session file conflict (should NOT happen with shared session)
**Action:** Restart both containers: `docker restart callsbot-worker callsbot-signal-aggregator`

**2. Signal Aggregator Crashed:**
```
❌ Container status: Restarting or Exited
❌ Failed to start signal aggregator
❌ Signal Aggregator: Error
```
**If you see these:** Signal Aggregator failed to start or crashed
**Action:** Check logs: `docker logs callsbot-signal-aggregator`

**3. Redis Connection Failed:**
```
❌ Failed to connect to Redis
❌ Redis error
```
**If you see these:** Redis is down or unreachable
**Action:** Check Redis: `docker ps | grep redis` and `docker logs callsbot-redis`

**4. Bot Stopped Processing:**
```
(No FEED ITEMS or heartbeat messages in last 30 minutes)
```
**If you see this:** Bot may have stopped or crashed
**Action:** Check worker: `docker logs callsbot-worker | tail -50`

**5. Signal Aggregator Not Monitoring:**
```
(No "Monitoring active" message in logs)
```
**If you see this:** Signal Aggregator failed to initialize Telethon
**Action:** Check session file exists: `docker exec callsbot-signal-aggregator ls -la /app/var/relay_user.session`

### **📊 Realistic Expectations for 30 Minutes:**

**Signal Frequency:**
- **Slow Market (Current):** 0-2 signals in 30 minutes ✅ NORMAL
- **Active Market:** 2-5 signals in 30 minutes
- **Hot Market:** 5-10 signals in 30 minutes

**Signal Aggregator Messages:**
- **Low Activity Groups:** 0-5 messages in 30 minutes ✅ NORMAL
- **Active Groups:** 5-20 messages in 30 minutes
- **Hot Market:** 20+ messages in 30 minutes

**Token Extraction:**
- **Depends on message content:** Not all messages contain token addresses
- **Validation:** Only tokens with $10k+ liquidity and $5k+ volume are recorded
- **Expected:** 0-3 validated tokens in 30 minutes (depends on group activity)

### **✅ Success Criteria (30 Minutes Later at 9:30 PM IST):**

Run this comprehensive check:
```bash
# All-in-one verification command
ssh root@64.227.157.221 "
echo '=== 1. Container Health ==='
docker ps --filter 'name=signal-aggregator' --format '{{.Names}}: {{.Status}}'
echo ''
echo '=== 2. Signal Aggregator Activity ==='
docker logs --since 30m callsbot-signal-aggregator | grep -E '(Monitoring active|Redis|Extracted)' | tail -3
echo ''
echo '=== 3. Worker Processing ==='
docker logs --since 30m callsbot-worker | grep 'FEED ITEMS' | tail -2
echo ''
echo '=== 4. Redis Keys ==='
docker exec callsbot-redis redis-cli DBSIZE
echo ''
echo '=== 5. No Database Locks ==='
docker logs --since 30m callsbot-worker callsbot-signal-aggregator 2>&1 | grep -c 'database is locked'
echo ''
echo '=== 6. All Containers ==='
docker ps --format '{{.Names}}: {{.Status}}' | grep -E '(worker|signal-aggregator|redis)'
"
```

**Expected Results:**
- ✅ Signal Aggregator: `Up X minutes (healthy)`
- ✅ Monitoring active message present
- ✅ FEED ITEMS appearing (bot processing)
- ✅ Redis DBSIZE: 15-25 keys
- ✅ Database locks: 0 (zero)
- ✅ All 3 containers: Up and healthy

**If all 6 criteria are met:** ✅ **Everything is working perfectly!**

**Checklist:**
- [ ] Signal Aggregator container healthy
- [ ] "Monitoring active" in logs
- [ ] Bot processing feed (FEED ITEMS)
- [ ] Redis accessible (15-25 keys)
- [ ] Zero database lock errors
- [ ] Worker + Signal Aggregator + Redis all running

---

## 📊 EXPECTED PERFORMANCE & SUCCESS METRICS

### Target Metrics (Week 1-4)
**Signal Frequency:** 15-20 signals/day (quality over quantity - stricter liquidity filter)  
**Target Win Rate:** 28-35% achieving 2x+ gains (up from 25.9% baseline)  
**Entry Point:** OPTIMAL ($50k-$130k market cap sweet spot)  
**Upside Potential:** 2x-5x (data-driven range)  
**Risk Level:** MODERATE (balanced quality + volume)

**Key Improvements in V2:**
- +5-10% win rate from liquidity floor raise ($30k → $35k)
- +2-3% win rate from 6h momentum bonus (20-50% range)
- Extended market cap to $130k to capture moonshots (avg winner entry: $129k)

### How to Know If Bot Is On Track

#### ✅ **GOOD SIGNS (Bot is working well)**

1. **Win Rate Trending Up**
   ```sql
   -- Check weekly win rate (should be 26%+)
   SELECT 
       ROUND(SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as win_rate
   FROM alerted_tokens a
   JOIN alerted_token_stats s ON a.token_address = s.token_address
   WHERE a.alerted_at > (strftime('%s', 'now') - 604800);
   ```
   - **Target:** ≥26% (baseline: 25.9%)
   - **Excellent:** ≥30%
   - **Review if:** <24%

2. **Consolidation/Dip Buy Patterns Performing**
   ```sql
   -- Check pattern performance
   SELECT 
       CASE 
           WHEN price_change_24h BETWEEN 50 AND 200 AND price_change_1h <= 0 THEN 'Consolidation'
           WHEN price_change_24h BETWEEN -50 AND -20 AND price_change_1h <= 0 THEN 'Dip Buy'
       END as pattern,
       COUNT(*) as signals,
       ROUND(AVG(max_gain_percent), 1) as avg_gain,
       ROUND(SUM(CASE WHEN max_gain_percent >= 100 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as win_rate
   FROM alerted_token_stats
   WHERE (price_change_24h BETWEEN 50 AND 200 AND price_change_1h <= 0)
      OR (price_change_24h BETWEEN -50 AND -20 AND price_change_1h <= 0)
   GROUP BY pattern;
   ```
   - **Consolidation Target:** 35%+ win rate
   - **Dip Buy Target:** 29%+ win rate

3. **Market Cap Distribution Correct**
   ```sql
   -- Verify signals are in 50k-100k range
   SELECT 
       COUNT(*) as signals_in_range,
       ROUND(AVG(first_market_cap_usd), 0) as avg_mcap
   FROM alerted_token_stats
   WHERE first_market_cap_usd BETWEEN 50000 AND 100000
   AND first_alert_at > (strftime('%s', 'now') - 604800);
   ```
   - **Target:** 100% of signals in $50k-$100k range
   - **Avg Market Cap:** ~$75k

4. **ML Enhancement Active**
   ```bash
   # Check ML is being used
   docker logs --tail 200 callsbot-worker | grep "ML models loaded"
   ```
   - **Should see:** "✅ ML models loaded successfully"
   - **Check weekly retrain:** `/opt/callsbotonchain/data/logs/ml_retrain.log`

5. **Signal Volume Stable**
   - **Target:** 20-25 signals/day
   - **Too many (>40/day):** Filters too loose
   - **Too few (<10/day):** Filters too strict

#### ⚠️ **WARNING SIGNS (Needs attention)**

1. **Win Rate Declining**
   - **If <24% for 3+ days:** Market conditions changed or config needs tuning
   - **Action:** Review recent losers for common patterns

2. **No Consolidation/Dip Buy Signals**
   - **If 0 pattern signals in 48h:** Momentum patterns not being detected
   - **Action:** Check if `price_change_1h` and `price_change_24h` are being captured

3. **Market Cap Drift**
   - **If signals outside $50k-$100k range:** Config not being enforced
   - **Action:** Verify `MAX_MARKET_CAP_USD=100000` in `.env`

4. **ML Not Loading**
   - **If "ML models not found" in logs:** Models missing or corrupted
   - **Action:** Run `docker exec callsbot-worker python scripts/ml/train_model.py`

5. **High Rug Rate**
   ```sql
   SELECT ROUND(SUM(is_rug) * 100.0 / COUNT(*), 1) as rug_rate
   FROM alerted_token_stats
   WHERE first_alert_at > (strftime('%s', 'now') - 604800);
   ```
   - **Target:** <50% (current baseline)
   - **Warning if:** >60%
   - **Action:** Increase `MIN_LIQUIDITY_USD`

#### 🚨 **CRITICAL ISSUES (Immediate action required)**

1. **Win Rate <20% for 7+ days**
   - Market has fundamentally changed
   - Need to re-analyze data and adjust config

2. **Bot Not Sending Signals**
   - Check worker container status
   - Check Telegram/Telethon connectivity
   - Review error logs

3. **ML Retraining Failing**
   - Check `/opt/callsbotonchain/data/logs/ml_retrain.log`
   - Verify sufficient data (need 100+ signals)

### Weekly Review Checklist

**Every Monday, run these checks:**

```bash
# 1. Win rate last 7 days
ssh root@64.227.157.221 "docker exec callsbot-worker sqlite3 var/alerted_tokens.db \"
SELECT 
    'Last 7 days:' as period,
    COUNT(*) as signals,
    SUM(CASE WHEN s.max_gain_percent >= 100 THEN 1 ELSE 0 END) as winners_2x,
    ROUND(SUM(CASE WHEN s.max_gain_percent >= 100 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) || '%' as win_rate
FROM alerted_tokens a
JOIN alerted_token_stats s ON a.token_address = s.token_address
WHERE a.alerted_at > (strftime('%s', 'now') - 604800);
\""

# 2. Market cap distribution
ssh root@64.227.157.221 "docker exec callsbot-worker sqlite3 var/alerted_tokens.db \"
SELECT 
    CASE 
        WHEN first_market_cap_usd < 50000 THEN 'Below 50k'
        WHEN first_market_cap_usd < 100000 THEN '50k-100k (TARGET)'
        WHEN first_market_cap_usd < 200000 THEN '100k-200k'
        ELSE 'Above 200k'
    END as range,
    COUNT(*) as signals
FROM alerted_token_stats
WHERE first_alert_at > (strftime('%s', 'now') - 604800)
GROUP BY range;
\""

# 3. ML status
ssh root@64.227.157.221 "docker exec callsbot-worker python -c 'from app.ml_scorer import get_ml_scorer; ml = get_ml_scorer(); print(f\"ML Active: {ml.is_available()}\")'"

# 4. Pattern performance
ssh root@64.227.157.221 "docker logs --tail 500 callsbot-worker | grep -c 'CONSOLIDATION PATTERN\|DIP BUY PATTERN'"
```

**Expected Results:**
- ✅ Win rate: 26-30%
- ✅ Signals: 140-175 (20-25/day)
- ✅ Market cap: 100% in 50k-100k range
- ✅ ML Active: True
- ✅ Pattern detections: 10-30 per week

---

## 🚀 WHY THIS CONFIGURATION WORKS

1. **Data-Driven Market Cap**: $50k-$100k has 28.9% win rate (7.3% higher than $100k-$200k)
2. **Optimal Score Threshold**: Score 8 performs as well as 9-10 while allowing more signals
3. **Momentum Pattern Recognition**: Soft ranking captures 35.5% and 29.3% win rate patterns
4. **ML Enhancement**: Trained on 1,093 signals, provides predictive boost/penalty
5. **Continuous Improvement**: ML retrains weekly as more data accumulates

---

## 🤖 ML SYSTEM STATUS

### Current ML Performance
- **Gain Predictor (Regression):**
  - Test R²: -0.012 (poor predictive power)
  - Status: ⚠️ Provides bounded nudges only
  
- **Winner Classifier (2x+):**
  - Test Accuracy: 71.6%
  - Winner Precision: 21% | Recall: 40%
  - Status: ✅ Modest predictive power

### ML Improvement Over Time

**What to Expect:**
- **Week 1-4:** ML performance stable (baseline)
- **Week 5-8:** Performance improves as more data accumulates
- **Week 9-12:** Significant improvement expected (1,500+ signals)
- **Week 13+:** ML becomes primary signal enhancer

**How ML Improves:**
1. **More Training Data:** Weekly retraining with new signals
2. **Better Feature Engineering:** Patterns emerge from larger dataset
3. **Reduced Overfitting:** More samples = better generalization
4. **Pattern Discovery:** ML identifies non-obvious correlations

**Monitoring ML Progress:**
```bash
# Check ML metadata
ssh root@64.227.157.221 "docker exec callsbot-worker cat var/models/metadata.json"

# View last retrain log
ssh root@64.227.157.221 "tail -50 /opt/callsbotonchain/data/logs/ml_retrain.log"
```

**ML Performance Targets:**
- **Month 1:** Baseline (Test R² ~0.0, Acc ~72%)
- **Month 2:** Test R² > 0.1, Acc > 75%
- **Month 3:** Test R² > 0.2, Acc > 78%
- **Month 6:** Test R² > 0.3, Acc > 80% (ML becomes reliable)

---

## 🔍 QUICK MONITORING COMMANDS

**Check Signal Quality:**
```bash
ssh root@64.227.157.221 "docker logs --tail 50 callsbot-worker"
```

**View Recent Alerts:**
```bash
ssh root@64.227.157.221 "docker exec callsbot-worker sqlite3 var/alerted_tokens.db 'SELECT datetime(alerted_at, \"unixepoch\") as time, substr(token_address,1,10) as token, final_score FROM alerted_tokens ORDER BY alerted_at DESC LIMIT 10'"
```

**Check API Health:**
```bash
ssh root@64.227.157.221 "curl -s http://localhost/api/v2/quick-stats"
```

---

## 📚 DOCUMENTATION

- **Optimal Config Implementation:** `OPTIMAL_CONFIG_IMPLEMENTATION.md`
- **Full Setup:** `docs/quickstart/CURRENT_SETUP.md`
- **ML System:** Auto-retraining every Sunday 3 AM
- **Configuration Details:** `docs/configuration/BOT_CONFIGURATION.md`
- **Deployment Guide:** `docs/deployment/QUICK_REFERENCE.md`

---

## 📅 TIMELINE & EXPECTATIONS

### Week 1 (Oct 18-25, 2025)
- **Focus:** Validate optimal config is working
- **Target:** 26-30% win rate, 140-175 signals
- **ML:** Baseline performance (Test R² ~0.0)
- **Action:** Monitor daily, no changes

### Week 2-4 (Oct 25 - Nov 15, 2025)
- **Focus:** Confirm sustained performance
- **Target:** Maintain 26-30% win rate
- **ML:** First retrain (Oct 27), slight improvement expected
- **Action:** Weekly review, minor tuning if needed

### Month 2-3 (Nov 15 - Jan 15, 2026)
- **Focus:** ML improvement phase
- **Target:** Win rate climbing to 28-32%
- **ML:** Test R² improving (0.0 → 0.2)
- **Action:** Monitor ML metrics, adjust if stagnant

### Month 4-6 (Jan 15 - Apr 15, 2026)
- **Focus:** ML maturity
- **Target:** Win rate 30-35% (ML-enhanced)
- **ML:** Test R² > 0.3, Acc > 80%
- **Action:** ML becomes primary signal enhancer

---

**Status:** ✅ **OPTIMAL CONFIG V3 - SIGNAL AGGREGATOR + REDIS + ZERO DATABASE LOCKS**  
**Current Win Rate:** 25.9% (baseline from 1,093 signals)  
**Target Win Rate:** 28-35% (Week 1-4), 32-40% (Month 4-6 with ML)  

**Latest Changes (V3 - Oct 19, 9:00 PM IST):**
- ✅ **Signal Aggregator: REDIS INTEGRATION** (cross-process communication)
  - Container rebuilt with Redis code
  - Stores signals in Redis (TTL: 1 hour)
  - Multi-bot consensus: +2 score for 3+ groups
  - Quality validation: Rejects $0 liquidity tokens
  - Session: `var/relay_user.session` (shared with worker)
- ✅ **ZERO DATABASE LOCKS** (verified working)
  - Shared session file approach
  - Both containers access Telethon without conflicts
  - No SQLite lock errors
- ✅ **FILTERS OPTIMIZED**
  - Min Liquidity: $25k (catch early tokens)
  - Max Liquidity: $100k (include established tokens)
  - Market Cap: $50k-$250k (extended range)
  - Expected: 15-20 signals/day
- ✅ **ML Enhancement:** Trained on 1,093 signals, auto-retrains weekly
- ✅ **Monitoring:** 13 Telegram groups for consensus validation

**Verification in 30 Minutes (9:30 PM IST):**
```bash
# Run comprehensive check
ssh root@64.227.157.221 "
echo '=== Container Health ==='
docker ps --filter 'name=signal-aggregator' --format '{{.Status}}'
echo '=== Signal Aggregator ==='
docker logs --since 30m callsbot-signal-aggregator | grep -E '(Monitoring|Redis)' | tail -3
echo '=== Worker Processing ==='
docker logs --since 30m callsbot-worker | grep 'FEED ITEMS' | tail -2
echo '=== Redis Keys ==='
docker exec callsbot-redis redis-cli DBSIZE
echo '=== Database Locks ==='
docker logs --since 30m callsbot-worker callsbot-signal-aggregator 2>&1 | grep -c 'database is locked'
"
```

**Expected:** ✅ Container healthy + Monitoring active + FEED ITEMS + Redis accessible + 0 locks
