# Current Server Status & Setup Validation
**Generated:** October 13, 2025  
**Server:** 64.227.157.221 (callsbotonchain.com)  
**Status:** ✅ OPERATIONAL

---

## 🎯 EXECUTIVE SUMMARY

The CallsBot system is currently **deployed and running** on the production server with the following setup:

### Active Services (Docker Containers)
- ✅ **callsbot-worker** - Main signal detection bot
- ✅ **callsbot-web** - Dashboard & API server (port 8080)
- ✅ **callsbot-tracker** - Performance tracking system
- ✅ **callsbot-paper-trader** - Paper trading simulator ($500 capital)
- ✅ **callsbot-redis** - Signal distribution & caching
- ✅ **callsbot-proxy** - Caddy reverse proxy (SSL/HTTPS)
- ⚠️ **callsbot-trader** - Real trading (DISABLED by default)

### Current Configuration (As of Oct 13, 2025)
```bash
# Signal Detection Thresholds
HIGH_CONFIDENCE_SCORE=3              # Very aggressive (was 7)
GENERAL_CYCLE_MIN_SCORE=6            # Lowered from 7
MIN_LIQUIDITY_USD=20000              # Lowered from 30k
MAX_24H_CHANGE_FOR_ALERT=150         # Raised from 50%
PRELIM_DETAILED_MIN=4                # Lowered from 5

# Tracking
TRACK_INTERVAL_MIN=30                # 30 seconds between price checks

# Safety Features
RUG_DETECTION=DISABLED               # Intentionally disabled
REQUIRE_MINT_REVOKED=false
REQUIRE_LP_LOCKED=false
REQUIRE_SMART_MONEY_FOR_ALERT=false
```

### Latest Deployment
- **Date:** October 13, 2025 21:54 IST
- **Commit:** 7e70e79 (cleanup + optimization)
- **Changes:** Disabled rug detection, lowered thresholds, fixed momentum scoring
- **Expected Impact:** Hit rate 2.8% → 15-20% within 7 days

---

## 📂 FILE LOCATIONS (CRITICAL)

### ✅ ACTIVE Locations (Use These)
```bash
# Logs
/opt/callsbotonchain/deployment/data/logs/
  - stdout.log
  - stderr.log

# Databases
/opt/callsbotonchain/deployment/var/
  - alerted_tokens.db    # Signal history
  - trading.db           # Trading positions
  - admin.db             # System config
  - treasury.json        # Capital tracking

# Configuration
/opt/callsbotonchain/deployment/.env
/opt/callsbotonchain/deployment/docker-compose.yml
```

### ❌ DEPRECATED Locations (Do Not Use)
```bash
/opt/callsbotonchain/data/logs/      # Old, empty
/opt/callsbotonchain/var/            # Old, empty
```

---

## 🔍 HOW TO VALIDATE SERVER

### Quick Check (30 seconds)
```bash
ssh root@64.227.157.221 "cd /opt/callsbotonchain/deployment && docker compose ps"
```

### Comprehensive Validation
```bash
# Run the validation script
ssh root@64.227.157.221 "bash /opt/callsbotonchain/docs/operations/SERVER_VALIDATION_SCRIPT.sh"
```

### Manual Checks
```bash
# 1. Check all containers are running
ssh root@64.227.157.221 "docker ps | grep callsbot"

# 2. View live worker logs
ssh root@64.227.157.221 "docker logs -f callsbot-worker"

# 3. Check API health
curl https://callsbotonchain.com/api/v2/quick-stats
curl https://callsbotonchain.com/api/v2/budget-status

# 4. Check recent signals
ssh root@64.227.157.221 "docker logs callsbot-worker --tail 100 | grep -E 'ALERT|PASSED'"

# 5. Database query
ssh root@64.227.157.221 "sqlite3 /opt/callsbotonchain/deployment/var/alerted_tokens.db 'SELECT COUNT(*) FROM alerted_tokens WHERE alerted_at > strftime(\"%s\", \"now\") - 86400'"
```

---

## 📊 EXPECTED BEHAVIOR

### Signal Generation
- **Frequency:** 8-12 signals per day (down from 40)
- **Score Range:** 6-9 (down from 9-10)
- **Liquidity Range:** $15k-$100k (down from $196k median)
- **Rug Detection:** DISABLED (no tokens marked as rugs)

### Performance Targets
- **Hit Rate:** 15-20% (up from 2.8%)
- **Average Return:** 2.5-3.5x per winner
- **Moonshot Rate:** 0.8-1.2% (10x+ gains)
- **Rug Rate:** <5% (via liquidity filter)

### System Health Indicators
✅ **Healthy:**
- All 6 containers running
- Heartbeat every 60 seconds
- API responding (200 status)
- Budget usage <80%
- No critical errors in logs

⚠️ **Warning:**
- Container restarts >0
- Budget usage 80-90%
- No signals for 2+ hours
- Disk/memory >80%

❌ **Critical:**
- Containers not running
- No heartbeat for 5+ minutes
- API not responding
- Budget exhausted
- Disk/memory >90%

---

## 🗄️ DATABASE SCHEMA

### alerted_tokens
Primary table for all signals:
```sql
- token_address (TEXT PRIMARY KEY)
- alerted_at (REAL) -- Unix timestamp
- final_score (INTEGER) -- 1-10
- prelim_score (INTEGER)
- conviction_type (TEXT)
- smart_money_detected (INTEGER)
- entry_price (REAL)
- entry_market_cap (REAL)
- entry_liquidity (REAL)
- entry_volume_24h (REAL)
```

### alerted_token_stats
Performance tracking:
```sql
- token_address (TEXT PRIMARY KEY)
- first_price_usd (REAL)
- peak_price_usd (REAL)
- peak_price_at (REAL)
- last_price_usd (REAL)
- max_gain_percent (REAL)
- time_to_peak_minutes (REAL)
- is_rug (INTEGER) -- Currently always 0 (disabled)
```

### price_snapshots
Historical data (30s intervals):
```sql
- token_address (TEXT)
- snapshot_at (REAL)
- price_usd (REAL)
- market_cap_usd (REAL)
- liquidity_usd (REAL)
- volume_24h_usd (REAL)
```

---

## 🔧 COMMON OPERATIONS

### Restart Services
```bash
ssh root@64.227.157.221
cd /opt/callsbotonchain/deployment

# Restart specific service
docker compose restart worker
docker compose restart web
docker compose restart tracker

# Restart all services
docker compose restart

# Full rebuild (after code changes)
docker compose down
docker compose build
docker compose up -d
```

### View Logs
```bash
# Live logs
docker compose logs -f worker
docker compose logs -f web

# Last 100 lines
docker compose logs --tail 100 worker

# Search logs
docker compose logs worker | grep "ALERT"
docker compose logs worker | grep "ERROR"
```

### Update Code
```bash
ssh root@64.227.157.221
cd /opt/callsbotonchain

# Pull latest changes
git pull origin main

# Rebuild and restart
cd deployment
docker compose build worker
docker compose up -d
```

### Database Queries
```bash
ssh root@64.227.157.221
sqlite3 /opt/callsbotonchain/deployment/var/alerted_tokens.db

# Quick stats
SELECT COUNT(*) as total FROM alerted_tokens;
SELECT COUNT(*) as last_24h FROM alerted_tokens WHERE alerted_at > strftime('%s', 'now') - 86400;

# Performance summary
SELECT 
  COUNT(*) as total,
  AVG(final_score) as avg_score,
  MIN(entry_liquidity) as min_liq,
  MAX(entry_liquidity) as max_liq
FROM alerted_tokens
WHERE alerted_at > strftime('%s', 'now') - 604800;
```

---

## 📈 MONITORING SCHEDULE

### Hourly
- Check dashboard: https://callsbotonchain.com
- Verify containers running: `docker compose ps`

### Daily
- Review signal count and quality
- Check budget usage
- Verify no critical errors
- Monitor disk/memory usage

### Weekly
- Run comprehensive health check
- Analyze win rate and performance
- Review top performers
- Clean up old Docker images if needed

---

## 🚨 TROUBLESHOOTING

### No Signals Being Generated
```bash
# Check worker logs
docker logs callsbot-worker --tail 100

# Verify API connectivity
curl 'https://feed-api.cielo.finance/api/v1/feed?limit=3' -H 'x-api-key: YOUR_KEY'

# Check configuration
grep -E "GENERAL_CYCLE_MIN_SCORE|MIN_LIQUIDITY_USD" /opt/callsbotonchain/deployment/.env
```

### Container Keeps Restarting
```bash
# Check logs for errors
docker logs callsbot-worker --tail 200

# Check resource usage
docker stats --no-stream

# Verify database permissions
ls -lh /opt/callsbotonchain/deployment/var/
```

### API Not Responding
```bash
# Check web container
docker logs callsbot-web --tail 100

# Verify port binding
docker ps | grep callsbot-web

# Test locally
curl http://localhost:8080/api/v2/quick-stats
```

---

## 📚 DOCUMENTATION STRUCTURE

```
docs/
├── quickstart/
│   ├── GETTING_STARTED.md          # Initial setup
│   ├── CURRENT_SETUP.md            # Current configuration
│   └── GOALS.md                    # Performance targets
├── deployment/
│   ├── DEPLOYMENT_2025_10_13.md    # Latest deployment
│   ├── QUICK_REFERENCE.md          # Common commands
│   └── SERVER_MONITORING_COMMANDS.md
├── operations/
│   ├── HEALTH_CHECK.md             # Health check guide
│   ├── TROUBLESHOOTING.md          # Common issues
│   └── SERVER_VALIDATION_SCRIPT.sh # This validation script
├── configuration/
│   ├── BOT_CONFIGURATION.md        # All settings explained
│   └── ENVIRONMENT_VARS.md         # .env reference
└── performance/
    └── AUDIT_2025_10_13.md         # Performance analysis
```

---

## 🔗 QUICK LINKS

- **Dashboard:** https://callsbotonchain.com
- **Server SSH:** `ssh root@64.227.157.221`
- **GitHub:** (private repository)
- **Cielo API:** https://feed-api.cielo.finance/
- **Jupiter API:** https://quote-api.jup.ag/

---

## ✅ VALIDATION CHECKLIST

Run this checklist to validate everything is working:

- [ ] All 6 Docker containers running
- [ ] Worker heartbeat within last 2 minutes
- [ ] API responding (quick-stats returns data)
- [ ] Database accessible and has recent signals
- [ ] Logs show no critical errors
- [ ] Budget usage <80%
- [ ] Disk usage <80%
- [ ] Memory usage <80%
- [ ] Cielo API connectivity working
- [ ] Configuration matches expected values

---

**Last Updated:** October 13, 2025  
**Next Review:** October 20, 2025  
**Maintained By:** System Administrator

