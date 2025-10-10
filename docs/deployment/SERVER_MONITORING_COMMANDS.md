# Server Monitoring Commands - Liquidity Filter Deployment

**Server:** root@64.227.157.221  
**Deployed:** October 10, 2025  
**Improvement:** Liquidity-based filtering (analyst recommendations)

---

## 🔍 Quick Checks

### 1. Watch Live Logs (See Liquidity Filter in Action)
```bash
ssh root@64.227.157.221 "docker logs -f callsbot-worker | grep 'LIQUIDITY'"
```

**What to look for:**
- `✅ LIQUIDITY CHECK PASSED: xxxxx - $45,000 (GOOD)`
- `❌ REJECTED (LOW LIQUIDITY): xxxxx - $5,000 < $15,000`
- `❌ REJECTED (ZERO LIQUIDITY): xxxxx - Liquidity: $0`

### 2. Check Recent Activity
```bash
ssh root@64.227.157.221 "docker logs callsbot-worker --tail 100"
```

### 3. Run Impact Analysis (After 48 hours)
```bash
ssh root@64.227.157.221 "cd /opt/callsbotonchain && python monitoring/liquidity_filter_impact.py"
```

### 4. Check Container Health
```bash
ssh root@64.227.157.221 "cd /opt/callsbotonchain/deployment && docker compose ps"
```

---

## 📊 Performance Tracking

### Daily Check (First Week)
```bash
# Run this every morning
ssh root@64.227.157.221 "cd /opt/callsbotonchain && python monitoring/liquidity_filter_impact.py 24"
```

### Weekly Review
```bash
# After 7 days
ssh root@64.227.157.221 "cd /opt/callsbotonchain && python monitoring/liquidity_filter_impact.py 168"
```

---

## 🔧 Troubleshooting

### If No Signals Generated
```bash
# Lower threshold temporarily
ssh root@64.227.157.221 "echo 'Manually set MIN_LIQUIDITY_USD=5000 in .env if needed'"
```

### If Too Many Losing Signals
```bash
# Raise threshold
ssh root@64.227.157.221 "echo 'Manually set MIN_LIQUIDITY_USD=25000 in .env if needed'"
```

### Restart Worker (if needed)
```bash
ssh root@64.227.157.221 "cd /opt/callsbotonchain/deployment && docker compose restart worker"
```

### View All Logs
```bash
ssh root@64.227.157.221 "docker logs callsbot-worker --tail 500 > /tmp/worker_logs.txt && cat /tmp/worker_logs.txt"
```

---

## 📈 Success Metrics

**Check after 48-72 hours:**
- [ ] Win rate improved (target: >25%)
- [ ] Signals still being generated regularly
- [ ] No system errors or crashes
- [ ] Liquidity filter visible in logs

**Check after 7 days:**
- [ ] Win rate >30% (2x improvement)
- [ ] Average liquidity of accepted signals >$20k
- [ ] Filter blocking 60-70% of previous signals
- [ ] System stable and healthy

---

## 🚨 Emergency Commands

### Stop Bot Immediately
```bash
ssh root@64.227.157.221 "cd /opt/callsbotonchain/deployment && docker compose stop worker"
```

### Disable Liquidity Filter (Rollback)
```bash
ssh root@64.227.157.221 "cd /opt/callsbotonchain/deployment && echo 'USE_LIQUIDITY_FILTER=false' >> .env && docker compose restart worker"
```

### Check System Resources
```bash
ssh root@64.227.157.221 "df -h && free -h && docker stats --no-stream"
```

---

## 📞 Next Steps

1. **Now:** Let bot run for 48 hours
2. **48h:** Run impact analysis
3. **7d:** Full performance review
4. **14d:** Consider threshold adjustments if needed

---

**Keep this file handy for daily monitoring!**

