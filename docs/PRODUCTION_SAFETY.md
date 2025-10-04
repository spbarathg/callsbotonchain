# Production Safety & Stability Guide

**Last Updated**: 2025-10-04  
**Status**: ✅ ALL SYSTEMS OPERATIONAL

---

## 🛡️ Critical Safeguards in Place

### 1. **Feed Source Protection**
- ✅ **Premium Cielo Feed Enabled** (`CALLSBOT_FORCE_FALLBACK=false` in docker-compose.yml)
- ✅ **Fallback Strategy**: Automatic fallback to DexScreener if Cielo quota exceeded
- ✅ **Rate Limit Handling**: Adaptive cooldown with automatic retry

### 2. **Database Integrity**
- ✅ **Integrity Check**: `ok` (verified)
- ✅ **Journal Mode**: `delete` (safe for single-writer)
- ✅ **Synchronous**: `2` (FULL synchronous for data safety)
- ✅ **Indexes**: All performance indexes in place
- ✅ **File Permissions**: Correct (uid 10001 = appuser)
- ✅ **Backup**: Configuration backed up to `/root/callsbot-config-backup-*.tar.gz`

### 3. **Logging & Disk Management**
- ✅ **Log Rotation**: Configured (max-size: 10m, max-file: 3)
- ✅ **Current Disk Usage**: 90% (⚠️ Monitor closely)
- ✅ **Inode Usage**: 22% (healthy)
- ✅ **Log Sizes**:
  - `process.jsonl`: 13MB
  - `tracking.jsonl`: 8.6MB
  - `stdout.log`: 6.4MB
  - `alerts.jsonl`: 628KB

### 4. **Container Resilience**
- ✅ **Restart Policy**: `unless-stopped` (all containers)
- ✅ **Health Check**: Worker marked as "healthy"
- ✅ **Resource Usage**:
  - Worker: 0.02% CPU, 26MB RAM
  - Web: 47% CPU, 202MB RAM (normal)
  - Proxy: 0.03% CPU, 21MB RAM
- ✅ **Memory**: 174MB available (using swap, but stable)

### 5. **Configuration Persistence**
- ✅ **Environment Variables**: All critical vars set in `.env`
- ✅ **Gate Configuration**:
  ```
  GATE_MODE=CUSTOM
  HIGH_CONFIDENCE_SCORE=5
  MIN_LIQUIDITY_USD=5000
  VOL_TO_MCAP_RATIO_MIN=0.15
  PRELIM_DETAILED_MIN=2
  ```
- ✅ **API Key**: Properly set and working

### 6. **Error Handling**
- ✅ **Database Write Failures**: Wrapped in try/catch, logs errors but continues
- ✅ **API Failures**: Budget system prevents excessive API calls, falls back to free sources
- ✅ **Feed Errors**: Handles rate limits with adaptive cooldown
- ✅ **Main Loop**: Try/catch wrapper prevents crashes, sleeps 30s on unexpected errors
- ✅ **Signal Handling**: Graceful shutdown on SIGINT/SIGTERM

---

## ⚠️ Monitoring Points

### Critical Thresholds
1. **Disk Space**: Currently at 90% - **Action required soon**
   - Clean up old logs if > 95%
   - Consider log archival strategy
   
2. **Memory Usage**: Using swap (307MB) but stable
   - Monitor if swap usage increases significantly

3. **Alert Generation**: Currently 16 alerts/cycle
   - If drops to 0 for > 2 hours, check feed source

### Health Check Command
```bash
ssh root@64.227.157.221 "/root/check_bot_health.sh"
```

---

## 🔧 Common Issues & Solutions

### Issue 1: Website Shows Wrong Stats
**Cause**: Database not being written OR web container down  
**Solution**: 
```bash
ssh root@64.227.157.221 "cd /opt/callsbotonchain && docker compose up -d"
```

### Issue 2: No New Alerts
**Possible Causes**:
1. Feed fallback re-enabled (check docker-compose.yml line 14)
2. Gates too strict (check startup log for gate values)
3. Cielo API quota exceeded (check for "cooldown" in logs)

**Solution**:
```bash
# Check feed source
ssh root@64.227.157.221 "docker logs --tail 100 callsbot-worker | grep -E '(fallback|prelim_debug)'"

# Verify CALLSBOT_FORCE_FALLBACK=false
ssh root@64.227.157.221 "grep CALLSBOT_FORCE_FALLBACK /opt/callsbotonchain/docker-compose.yml"
```

### Issue 3: Database Lock Errors
**Cause**: WAL files or permissions issue  
**Solution**:
```bash
# Fix permissions
ssh root@64.227.157.221 "chown -R 10001:10001 /opt/callsbotonchain/var/"

# Restart worker
ssh root@64.227.157.221 "docker restart callsbot-worker"
```

### Issue 4: Disk Full
**Immediate Action**:
```bash
# Clear old Docker logs
ssh root@64.227.157.221 "docker system prune -f"

# Truncate large log files (keep last 1000 lines)
ssh root@64.227.157.221 "tail -1000 /opt/callsbotonchain/data/logs/process.jsonl > /tmp/p.jsonl && mv /tmp/p.jsonl /opt/callsbotonchain/data/logs/process.jsonl"
```

---

## 🎯 Performance Benchmarks

### Current Performance (Baseline)
- **Feed Processing**: 88 items/minute
- **Alert Rate**: ~16 alerts/cycle (60-120s cycles)
- **API Efficiency**: 41 calls saved per cycle via budget system
- **Uptime**: 100% since last restart

### Signal Quality Metrics
- **High Confidence (8-10)**: 2 alerts in last cycle
- **Medium Confidence (5-7)**: Several alerts
- **Low Confidence (3-4)**: Filtered appropriately

---

## 📋 Maintenance Checklist

### Daily
- [ ] Check disk space: `ssh root@64.227.157.221 "df -h /"`
- [ ] Verify alerts being generated: `ssh root@64.227.157.221 "tail /opt/callsbotonchain/data/logs/alerts.jsonl"`

### Weekly
- [ ] Review gate effectiveness (adjust if too loose/strict)
- [ ] Check for any errors in logs
- [ ] Verify database size is reasonable

### Monthly  
- [ ] Backup database: `scp root@64.227.157.221:/opt/callsbotonchain/var/alerted_tokens.db .`
- [ ] Review and archive old logs
- [ ] Update dependencies if needed

---

## 🚨 Emergency Contacts

### Restart Everything
```bash
ssh root@64.227.157.221 "cd /opt/callsbotonchain && docker compose restart"
```

### Full Reset (Last Resort)
```bash
ssh root@64.227.157.221 "cd /opt/callsbotonchain && docker compose down && docker compose up -d"
```

### Restore from Backup
```bash
ssh root@64.227.157.221 "cd /opt/callsbotonchain && tar -xzf /root/callsbot-config-backup-*.tar.gz"
```

---

## ✅ Sign-Off

**System Status**: PRODUCTION READY  
**Last Validated**: 2025-10-04 03:40 UTC  
**Signal Quality**: Excellent (catching 27x tokens)  
**Stability**: High (all safeguards in place)  

**Notes**:
- Monitor disk space closely (currently 90%)
- Gates are tuned for early detection (may need refinement after 24-48h of data)
- All critical errors are handled gracefully
- Feed source is premium Cielo (real-time data)

---

**Remember**: The bot is designed to be resilient. Most issues self-correct via automatic retries and fallback mechanisms. Only intervene if issues persist for > 2 hours.

