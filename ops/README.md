# Operations Documentation

This folder contains comprehensive operational guides for managing and monitoring the callsbotonchain bot.

---

## 📚 Available Guides

### 1. **HEALTH_CHECK.md**
Complete guide for checking bot health and system status.

**Use when:**
- Daily routine checks
- Verifying bot is operational
- Quick diagnostics before troubleshooting

**Key sections:**
- Quick 30-second health check
- Comprehensive 5-minute validation
- Automated health check script
- Monitoring schedule
- Alert thresholds

**Quick command:**
```bash
docker ps && \
curl -s http://127.0.0.1/api/v2/quick-stats | jq && \
curl -s http://127.0.0.1/api/v2/budget-status | jq
```

---

### 2. **ANALYSIS_GUIDE.md**
In-depth performance analysis and optimization recommendations.

**Use when:**
- Evaluating signal quality
- Analyzing bot performance
- Identifying optimization opportunities
- Comparing strategies
- Generating reports

**Key sections:**
- Signal quality analysis
- Tracking performance metrics
- Budget efficiency analysis
- Feed quality evaluation
- Best/worst token analysis
- KPI tracking

**Quick command:**
```bash
# Generate daily report
/opt/callsbotonchain/ops/generate_report.sh
```

---

### 3. **TROUBLESHOOTING.md**
Solutions for common issues and emergency procedures.

**Use when:**
- Bot stops working
- Errors in logs
- Performance degradation
- Database issues
- Any unexpected behavior

**Key sections:**
- Common issues and solutions
- Step-by-step diagnosis procedures
- Emergency recovery procedures
- Backup and restore
- Diagnostic report generation

**Quick command:**
```bash
# Check for problems
docker logs callsbot-worker --tail 50 2>&1 | grep -iE 'error|exception'
```

---

## 🚀 Quick Start

### First Time Setup
1. Review `HEALTH_CHECK.md` to understand what "healthy" looks like
2. Run comprehensive health check to establish baseline
3. Create automated monitoring scripts
4. Set up daily reporting

### Daily Operations
```bash
# Morning check (30 seconds)
docker ps && curl -s http://127.0.0.1/api/v2/quick-stats | jq

# Review dashboard
open http://64.227.157.221/

# Check for issues
docker logs callsbot-worker --tail 100 | grep -i error
```

### Weekly Analysis
```bash
# Generate performance report
/opt/callsbotonchain/ops/generate_report.sh > weekly_report_$(date +%Y%m%d).txt

# Review KPIs
# - Smart money detection rate
# - Average peak multiples
# - Budget utilization
# - Top performing tokens
```

---

## 📊 Key Metrics to Monitor

### Signal Quality
- **Smart Money %**: Should be > 50%
- **Average Score**: Should be > 6.0
- **High Score Rate**: Should be > 30%

### Performance
- **Avg Peak Multiple**: Should be > 2.0x
- **≥5x Rate**: Should be > 10%
- **Flat Rate (<1.5x)**: Should be < 40%

### Operational
- **Budget Usage**: Should be 50-80% (optimal)
- **Container Uptime**: Should be 100% (0 restarts)
- **Heartbeat**: Should be < 2 minutes old
- **API Efficiency**: Should be > 90% filtering

---

## 🆘 Emergency Response

### Bot Stopped / No Heartbeat
```bash
# Quick fix
docker restart callsbot-worker

# If doesn't help, see TROUBLESHOOTING.md section 1
```

### Budget Exhausted
```bash
# Quick fix - increase budget
vim /opt/callsbotonchain/.env
# Set: BUDGET_PER_DAY_MAX=15000
docker restart callsbot-worker

# Long term solution - see TROUBLESHOOTING.md section 2
```

### No Alerts
```bash
# Quick diagnosis
docker logs callsbot-worker --tail 100 | grep -E 'feed_items|REJECTED'

# See TROUBLESHOOTING.md section 3 for solutions
```

### Database Errors
```bash
# Quick fix
chown 10001:10001 /opt/callsbotonchain/var/*.db
docker restart callsbot-worker

# See TROUBLESHOOTING.md section 4 for details
```

---

## 📁 File Structure

```
ops/
├── README.md              # This file - overview and quick reference
├── HEALTH_CHECK.md        # Daily health monitoring procedures
├── ANALYSIS_GUIDE.md      # Performance analysis and optimization
└── TROUBLESHOOTING.md     # Problem diagnosis and solutions
```

---

## 🔗 Related Documentation

### In Repository:
- `STATUS.md` - Current operational status and recent changes
- `docker-compose.yml` - Container configuration
- `docs/PRODUCTION_SAFETY.md` - System stability measures
- `docs/TRADING_DEPLOYMENT.md` - Trading system setup
- `docs/TRADING_MONITORING.md` - Trading performance tracking

### External Resources:
- Dashboard: http://64.227.157.221/
- Cielo API: https://feed-api.cielo.finance/
- Jupiter V6: https://station.jup.ag/docs/apis/swap-api

---

## 💡 Tips & Best Practices

### 1. Regular Monitoring
- Check dashboard daily
- Run health check weekly
- Generate performance report weekly
- Review KPIs monthly

### 2. Proactive Maintenance
- Clean Docker images monthly: `docker system prune -af`
- Check disk space weekly: `df -h /`
- Review logs for patterns: Look for recurring errors
- Update gates based on performance: Adjust if quality drops

### 3. Data Preservation
- Backup databases before major changes
- Keep last 3 weeks of logs
- Export performance reports for trend analysis
- Document any configuration changes

### 4. Performance Optimization
- If budget < 60%: Increase tracking frequency
- If flat rate > 50%: Tighten gates (increase thresholds)
- If smart money < 50%: Verify detection logic
- If errors > 30%: Review and adjust filters

### 5. Trading Preparation
- Run paper trading for 1+ week before going live
- Verify win rate > 60% in paper mode
- Start with small position sizes
- Monitor closely for first 24 hours

---

## 🎯 Goals & Objectives

### Short Term (Daily/Weekly)
- ✅ Maintain 100% uptime
- ✅ Keep budget utilization 50-80%
- ✅ Generate quality signals (avg score > 6.0)
- ✅ Smart money detection > 50%

### Medium Term (Monthly)
- 📊 Achieve avg peak multiple > 2.5x
- 📊 Maintain ≥5x rate > 15%
- 📊 Optimize gates for best risk/reward
- 📊 Reduce flat rate to < 30%

### Long Term (Quarterly)
- 🎯 Deploy live trading with proven strategy
- 🎯 Achieve consistent profitability
- 🎯 Scale to multiple strategies
- 🎯 Automate reporting and alerts

---

## 📞 Support

### Self-Service:
1. Check `TROUBLESHOOTING.md` for your issue
2. Review recent logs for errors
3. Compare current metrics to baselines in `HEALTH_CHECK.md`
4. Try common fixes documented in guides

### Escalation:
If issue persists after troubleshooting:
1. Generate diagnostic report (see TROUBLESHOOTING.md)
2. Document steps already tried
3. Note any recent changes to system
4. Collect relevant logs and metrics

---

## 🔄 Updates

This documentation is living and should be updated when:
- New issues are discovered and solved
- Performance baselines change
- New features are added
- Configuration changes are made
- Best practices evolve

**Last Updated**: October 4, 2025
**Version**: 1.0
**Status**: Production Ready

