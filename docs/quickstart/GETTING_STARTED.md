# Getting Started with CallsBotOnChain

**Get your trading signal bot up and running in 15 minutes.**

---

## ✅ Prerequisites

- Server with Docker and Docker Compose installed
- GitHub repository access
- Telegram bot token (for alerts)
- Cielo Finance API key

---

## 🚀 Quick Setup

### 1. Clone and Configure

```bash
# Clone repository
git clone https://github.com/spbarathg/callsbotonchain
cd callsbotonchain

# Copy environment template
cp .env.example .env

# Edit configuration
nano .env
```

### 2. Key Configuration Settings

```bash
# Required
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
CIELO_API_KEY=your_cielo_key_here

# Optimal Settings (as of Oct 6, 2025)
REQUIRE_MINT_REVOKED=false          # Critical for pump.fun tokens
REQUIRE_LP_LOCKED=false             # Critical for new tokens
HIGH_CONFIDENCE_SCORE=7             # Optimal per 2,189 signal analysis
MIN_LIQUIDITY_USD=30000             # Filters rugs
VOL_TO_MCAP_RATIO_MIN=0.40          # Quality filter
```

### 3. Deploy

```bash
# Build and start all services
docker compose up -d

# Verify containers are running
docker ps --filter name=callsbot

# Check logs
docker logs callsbot-worker --tail 100
```

---

## 📊 Verify It's Working

### Check Bot Status
```bash
# All containers should show "Up" and "healthy"
docker ps --filter name=callsbot
```

### Check for Signals
```bash
# Should see tokens being evaluated
docker logs callsbot-worker --tail 50 | grep -E "FETCHING|prelim"
```

### View Dashboard
```
http://your-server-ip/
```

---

## 📈 First 48 Hours

**What to Expect:**
1. **Hour 1:** Bot starts evaluating tokens
2. **Hour 6:** First signals should appear
3. **Hour 24:** ~20-50 signals collected
4. **Hour 48:** Enough data for first performance report

**Daily Report:**
```bash
/opt/callsbotonchain/run_daily_report.sh
```

---

## 🎯 Next Steps

1. ✅ **Monitor for 24-48 hours** - Let data accumulate
2. 📊 **Review daily reports** - Check win rate and avg gains
3. 📝 **Analyze performance** - See [DAILY_REPORTS.md](../performance/DAILY_REPORTS.md)
4. 💰 **Paper trade** - Simulate before going live
5. 🚀 **Live trading** - Start with small positions

---

## 🆘 Troubleshooting

### No signals appearing?
```bash
# Check configuration
docker logs callsbot-worker | grep "gates"

# Should show:
# REQUIRE_MINT_REVOKED: false
# REQUIRE_LP_LOCKED: false
```

### Container not healthy?
```bash
# Restart the container
docker compose restart worker

# Check logs for errors
docker logs callsbot-worker --tail 100
```

### Need help?
- See [TROUBLESHOOTING.md](../operations/TROUBLESHOOTING.md)
- Check [SERVER_RULES.md](../configuration/SERVER_RULES.md)
- Review [CURRENT_SETUP.md](./CURRENT_SETUP.md)

---

**Ready to start?** Follow the steps above and you'll be collecting trading signals within the hour! 🚀

