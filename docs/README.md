# CallsBotOnChain Documentation

**Complete guide to understanding, operating, and optimizing your trading signal bot.**

---

## 📚 Documentation Index

### 🚀 Getting Started
- **[Quick Start Guide](./quickstart/GETTING_STARTED.md)** - Set up and deploy the bot in 15 minutes
- **[Current Setup Overview](./quickstart/CURRENT_SETUP.md)** - What's running right now (updated Oct 6, 2025)
- **[Goals & Vision](./quickstart/GOALS.md)** - What this bot aims to achieve

### 🔧 Configuration & Setup
- **[Bot Configuration Guide](./configuration/BOT_CONFIGURATION.md)** - All settings explained
- **[Server Rules & Safety](./configuration/SERVER_RULES.md)** - Critical operating procedures
- **[Environment Variables](./configuration/ENVIRONMENT_VARS.md)** - Complete .env reference

### 📊 Performance & Analysis
- **[Daily Performance Reports](./performance/DAILY_REPORTS.md)** - How to read and use daily reports
- **[Signal Analysis](./performance/SIGNAL_ANALYSIS.md)** - Understanding signal quality
- **[Trading Strategy Guide](./performance/TRADING_STRATEGY.md)** - How to profit from signals
- **[Performance Tracking](./performance/TRACKING_SYSTEM.md)** - Metrics and KPIs

### 🔍 Monitoring & Operations
- **[Health Checks](./operations/HEALTH_CHECK.md)** - Monitor bot health
- **[Troubleshooting Guide](./operations/TROUBLESHOOTING.md)** - Fix common issues
- **[Analysis Guide](./operations/ANALYSIS_GUIDE.md)** - Analyze bot performance

### 📈 Historical Records
- **[Fixes Changelog](./history/FIXES_CHANGELOG.md)** - All changes and improvements
- **[Optimization Summary](./history/OPTIMIZATION_SUMMARY.md)** - Performance improvements
- **[Verification Reports](./history/VERIFICATION_REPORTS.md)** - System validations

### 🛠️ Development
- **[Developer Setup](./development/DEVELOPER_SETUP.md)** - Set up dev environment
- **[API Documentation](./api/README.md)** - REST API reference
- **[Architecture](./development/ARCHITECTURE.md)** - System design

---

## 🎯 Common Tasks

### Daily Operations
```bash
# View daily performance report
ssh root@64.227.157.221 "/opt/callsbotonchain/run_daily_report.sh"

# Check bot health
docker ps --filter name=callsbot

# View recent signals
docker logs callsbot-worker --tail 100 | grep ALERTED
```

### Troubleshooting
```bash
# Check container logs
docker logs callsbot-worker --tail 100
docker logs callsbot-tracker --tail 100

# Check configuration
docker logs callsbot-worker | grep "gates"

# Restart worker
docker compose restart worker
```

### Performance Analysis
```bash
# Run signal analysis
cd /opt/callsbotonchain
python3 docs/monitoring/analyze_signals.py

# View latest metrics
cat analytics/latest_daily_report.json | jq .
```

---

## 📖 Quick Reference

### Key Files
- `var/alerted_tokens.db` - Signal database
- `var/toggles.json` - Bot toggles
- `.env` - Configuration
- `analytics/` - Performance reports

### Key Metrics
- **Win Rate Target:** 15-20%
- **Avg Multiplier Target:** 2.5-3.5x
- **Rug Rate Limit:** <10%
- **Score Threshold:** 7+

### Support Resources
- GitHub Issues: https://github.com/spbarathg/callsbotonchain/issues
- Server: root@64.227.157.221
- Database: `var/alerted_tokens.db`

---

**Last Updated:** October 6, 2025  
**Bot Version:** v2.0 (Optimized Configuration)  
**Status:** 🟢 OPERATIONAL
