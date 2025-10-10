# Quick Reference - Liquidity Filter Implementation

---

## 🚀 Quick Start

### Restart Bot
```bash
cd deployment
docker-compose restart worker
```

### Check if Working
```bash
# Watch logs for these messages:
docker-compose logs -f worker | grep "LIQUIDITY"

# You should see:
✅ LIQUIDITY CHECK PASSED: xxxxx - $XX,XXX (GOOD)
❌ REJECTED (LOW LIQUIDITY): xxxxx - $X,XXX < $15,000
```

### Run Impact Analysis (After 48h)
```bash
python monitoring/liquidity_filter_impact.py
```

---

## ⚙️ Configuration

### Current Settings
```bash
MIN_LIQUIDITY_USD=15000          # Minimum threshold ($15k recommended)
EXCELLENT_LIQUIDITY_USD=50000    # High confidence threshold
USE_LIQUIDITY_FILTER=true        # Enable/disable filter
```

### Adjust Thresholds (in .env)
```bash
# More conservative (fewer signals)
MIN_LIQUIDITY_USD=50000

# Recommended (balanced)
MIN_LIQUIDITY_USD=15000

# More aggressive (more signals)
MIN_LIQUIDITY_USD=5000

# Disable filter
USE_LIQUIDITY_FILTER=false
```

---

## 📊 Expected Results

| Metric | Before | After (Expected) |
|--------|--------|------------------|
| Win Rate | 14.3% | 30-40% |
| Signals/Day | ~177 | 50-70 |
| Avg Peak | +59.6% | +80%+ |
| False Positives | 85.7% | <60% |

---

## 🔍 Monitoring

### Daily Checks
```bash
# Run impact analysis
python monitoring/liquidity_filter_impact.py

# Check logs
docker-compose logs worker | tail -100
```

### What to Look For
✅ "LIQUIDITY CHECK PASSED" messages  
✅ Win rate improving  
✅ Signals still being generated  
❌ No system errors

---

## 🔧 Troubleshooting

### No Signals Generated
```bash
# Lower threshold temporarily
MIN_LIQUIDITY_USD=5000
```

### Too Many Losing Signals
```bash
# Raise threshold
MIN_LIQUIDITY_USD=25000
```

### Rollback (Emergency)
```bash
# In .env:
USE_LIQUIDITY_FILTER=false
# Then restart bot
```

---

## 📈 Key Analyst Findings

1. **Liquidity is #1 predictor** (not score!)
   - Winner median: $17,811
   - Loser median: $0

2. **Our score doesn't work alone**
   - Winners & losers have similar scores
   - Must combine with liquidity

3. **Smart money doesn't help**
   - Already disabled (bonus = 0)

4. **Critical thresholds:**
   - $15k = 75th percentile (recommended)
   - $50k = 90th percentile (excellent)

---

## 💡 Quick Commands

```bash
# Restart bot
cd deployment && docker-compose restart worker

# Check if filter is working
docker-compose logs worker | grep "LIQUIDITY CHECK"

# Run impact analysis
python monitoring/liquidity_filter_impact.py

# View recent signals
sqlite3 var/alerted_tokens.db "SELECT * FROM alerted_tokens ORDER BY alerted_at DESC LIMIT 10"

# Disable filter (emergency)
echo "USE_LIQUIDITY_FILTER=false" >> .env && docker-compose restart worker
```

---

## 📞 Next Steps

1. ✅ Restart bot now
2. ⏳ Wait 48-72 hours
3. 📊 Run impact analysis
4. 📧 Report results to analyst
5. 🔧 Optimize thresholds if needed

---

**Status:** READY TO DEPLOY  
**Expected Win Rate:** 30-40%  
**Time to Results:** 48-72 hours  

🚀 **Deploy now!**

