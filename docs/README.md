# 📚 CallsBot Documentation

This folder contains all operational documentation for the CallsBot trading system.

---

## 📄 Documents

### **1. PRODUCTION_SAFETY.md**
**Purpose**: Comprehensive safety measures and stability guide  
**Topics**:
- Database protection
- Error handling
- Resource management
- Restart resilience
- Configuration persistence
- Monitoring tools
- Performance metrics

**When to read**: Before deploying, after any major changes, troubleshooting issues

---

### **2. OPTIMIZATION_REPORT.md**
**Purpose**: 24/7 API budget optimization analysis  
**Topics**:
- Tracking settings optimization
- Budget consumption analysis
- Sustainable operation strategy
- Monitoring commands
- Fine-tuning options
- Performance projections

**When to read**: Understanding bot efficiency, adjusting tracking, budget issues

---

### **3. TRADING_DEPLOYMENT.md**
**Purpose**: Trading system deployment guide  
**Topics**:
- Trading system architecture
- Configuration options
- Deployment steps
- Wallet setup
- Risk parameters
- Strategy selection

**When to read**: Before enabling trading, configuring strategies, managing risk

---

### **4. TRADING_MONITORING.md**
**Purpose**: Trading performance monitoring and analysis  
**Topics**:
- Performance metrics
- Position tracking
- Win/loss analysis
- Risk metrics
- Dashboard interpretation
- Optimization techniques

**When to read**: Daily trading review, performance analysis, strategy tuning

---

## 🚀 Quick Reference

### **System Health Check**
```bash
# All containers running
ssh root@64.227.157.221 "docker ps --filter name=callsbot"

# Worker logs
ssh root@64.227.157.221 "docker logs callsbot-worker --tail 50"

# Budget status
ssh root@64.227.157.221 "cat /opt/callsbotonchain/var/credits_budget.json"
```

### **Performance Metrics**
```bash
# Recent alerts
ssh root@64.227.157.221 "tail -20 /opt/callsbotonchain/data/logs/alerts.jsonl"

# Trading positions
ssh root@64.227.157.221 "docker exec callsbot-trader sqlite3 /app/var/trading.db 'SELECT * FROM positions;'"

# Signal quality
ssh root@64.227.157.221 "docker logs callsbot-worker --tail 100 | grep PASSED"
```

### **Troubleshooting**
```bash
# Fix database permissions
ssh root@64.227.157.221 "chown 10001:10001 /opt/callsbotonchain/var/*.db*"

# Restart worker
ssh root@64.227.157.221 "cd /opt/callsbotonchain && docker compose restart worker"

# Reset budget
ssh root@64.227.157.221 "echo '{\"minute_epoch\":0,\"minute_count\":0,\"day_utc\":0,\"day_count\":0}' > /opt/callsbotonchain/var/credits_budget.json"
```

---

## 📊 Current Configuration

### **Bot Settings**
- **Gate Mode**: CUSTOM
- **High Confidence Score**: 5
- **Min Liquidity**: $5,000
- **Vol/MCap Ratio**: 0.15
- **Track Interval**: 15 minutes
- **Track Batch Size**: 30 tokens

### **Trading System**
- **Bankroll**: $500
- **Max Concurrent**: 5 positions
- **Position Sizes**:
  - Runner (Smart Money): $70
  - Scout (High Velocity): $40
  - Strict (High Confidence): $50
  - Nuanced (Low Confidence): $25
- **Mode**: Dry-run (trading_enabled: false)

### **API Budget**
- **Per Minute**: 15 calls
- **Per Day**: 4,300 calls
- **Current Strategy**: Sustainable 24/7 operation

---

## 🎯 Key Metrics to Monitor

### **Daily**
- [ ] Budget usage < 4,300 calls/day
- [ ] 20-40 quality alerts generated
- [ ] No database errors
- [ ] All containers healthy
- [ ] Cielo feed active (not fallback)

### **Weekly**
- [ ] Signal quality remains high
- [ ] No budget exhaustion incidents
- [ ] Trading performance (when enabled)
- [ ] System uptime > 99%

### **Monthly**
- [ ] ROI analysis (when trading live)
- [ ] Strategy effectiveness review
- [ ] Risk parameter adjustments
- [ ] Infrastructure optimization

---

## 🔄 Update History

| Date | Document | Changes |
|------|----------|---------|
| 2025-10-04 | OPTIMIZATION_REPORT.md | Created - 24/7 optimization |
| 2025-10-04 | PRODUCTION_SAFETY.md | Updated - Final safety audit |
| 2025-10-04 | TRADING_DEPLOYMENT.md | Created - Trading system deployment |
| 2025-10-04 | TRADING_MONITORING.md | Created - Performance monitoring |

---

## 📞 Support

For issues or questions:
1. Check relevant documentation above
2. Review logs on server
3. Verify configuration matches docs
4. Check STATUS.md in project root for latest status

---

**Last Updated**: October 4, 2025  
**System Version**: v2.0 (Optimized for 24/7)  
**Status**: Production Ready ✅

