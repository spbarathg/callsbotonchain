# 🚀 Security Fixes Deployment Checklist

Use this checklist to ensure a smooth deployment of all security fixes.

---

## 📋 Pre-Deployment Checklist

### 1. Preparation (5 minutes)

- [ ] **Review all changes**
  - [ ] Read `FIXES_SUMMARY.md` for overview
  - [ ] Review `SECURITY_FIXES_README.md` for quick start
  - [ ] Understand what each fix does

- [ ] **Backup current state**
  - [ ] Note current uptime: `uptime`
  - [ ] Check current stats: `curl http://127.0.0.1/api/v2/quick-stats`
  - [ ] Screenshot dashboard (optional)
  - [ ] Document current container status: `docker ps`

- [ ] **Prepare credentials**
  - [ ] Choose strong password (min 16 chars, mixed case, numbers, symbols)
  - [ ] Store in password manager
  - [ ] Have username ready (default: `admin`)

- [ ] **Check server resources**
  - [ ] Disk space: `df -h` (need at least 1GB free)
  - [ ] Memory: `free -h` (should have 500MB+ available)
  - [ ] No other deployments in progress

---

## 🔧 Deployment Checklist

### Option A: Automated Deployment (Recommended)

- [ ] **Step 1: SSH to server**
  ```bash
  ssh root@64.227.157.221
  cd /opt/callsbotonchain
  ```

- [ ] **Step 2: Pull latest changes**
  ```bash
  git status  # Check for local changes
  git pull origin main
  ```

- [ ] **Step 3: Run deployment script**
  ```bash
  chmod +x scripts/deploy_security_fixes.sh
  bash scripts/deploy_security_fixes.sh
  ```

- [ ] **Step 4: Follow prompts**
  - [ ] Enter dashboard username when prompted
  - [ ] Enter dashboard password when prompted
  - [ ] Confirm deployment when asked
  - [ ] Wait for completion (~5-10 minutes)

- [ ] **Step 5: Review output**
  - [ ] Check for "Deployment successful" message
  - [ ] Note backup location
  - [ ] Review any warnings

### Option B: Manual Deployment

- [ ] **Step 1: SSH and navigate**
  ```bash
  ssh root@64.227.157.221
  cd /opt/callsbotonchain
  ```

- [ ] **Step 2: Create backups**
  ```bash
  mkdir -p backups/$(date +%Y%m%d_%H%M%S)
  cp deployment/Caddyfile backups/$(date +%Y%m%d_%H%M%S)/
  cp src/server.py backups/$(date +%Y%m%d_%H%M%S)/
  cp scripts/track_performance.py backups/$(date +%Y%m%d_%H%M%S)/
  ```

- [ ] **Step 3: Pull changes**
  ```bash
  git pull origin main
  ```

- [ ] **Step 4: Configure authentication**
  ```bash
  nano deployment/.env
  # Add:
  # DASHBOARD_AUTH_ENABLED=true
  # DASHBOARD_USERNAME=admin
  # DASHBOARD_PASSWORD=YourSecurePassword123!
  ```

- [ ] **Step 5: Rebuild containers**
  ```bash
  cd deployment
  docker-compose down
  docker-compose build --no-cache web tracker
  docker-compose up -d
  ```

- [ ] **Step 6: Setup database cleanup**
  ```bash
  cd ..
  chmod +x scripts/cleanup_database.py scripts/setup_cleanup_cron.sh
  bash scripts/setup_cleanup_cron.sh
  ```

---

## ✅ Post-Deployment Verification

### Automated Verification

- [ ] **Run verification script**
  ```bash
  chmod +x scripts/verify_security_fixes.sh
  bash scripts/verify_security_fixes.sh
  ```

- [ ] **Check results**
  - [ ] All tests passed (green checkmarks)
  - [ ] No critical failures
  - [ ] Review any warnings

### Manual Verification

- [ ] **1. Container Health**
  ```bash
  docker ps --filter name=callsbot
  # Should show 6 containers, all "Up"
  ```

- [ ] **2. HTTPS Enforcement**
  ```bash
  curl -I http://127.0.0.1/
  # Should return 301 or 308 redirect
  
  curl -k -I https://127.0.0.1/
  # Should return 401 or 200
  ```

- [ ] **3. Authentication**
  ```bash
  # Without credentials (should fail)
  curl -k https://127.0.0.1/
  # Should return 401
  
  # With credentials (should work)
  curl -k -u admin:YourPassword https://127.0.0.1/
  # Should return HTML
  ```

- [ ] **4. API Functionality**
  ```bash
  curl -k -u admin:YourPassword https://127.0.0.1/api/v2/quick-stats | jq
  # Should return JSON with stats
  ```

- [ ] **5. Tracker Logs**
  ```bash
  docker logs callsbot-tracker --tail 50
  # Should NOT contain "unsupported format string" errors
  ```

- [ ] **6. Database Cleanup**
  ```bash
  crontab -l | grep cleanup_database
  # Should show cron job scheduled
  
  python3 scripts/cleanup_database.py --dry-run
  # Should run without errors
  ```

- [ ] **7. Bot Processing**
  ```bash
  docker logs callsbot-worker --tail 20
  # Should show recent activity
  
  docker logs callsbot-tracker --tail 20
  # Should show price updates
  ```

### Browser Verification

- [ ] **Access dashboard**
  - [ ] Open: `https://64.227.157.221/`
  - [ ] Accept certificate warning (self-signed)
  - [ ] See login prompt
  - [ ] Enter credentials
  - [ ] Dashboard loads successfully

- [ ] **Check dashboard features**
  - [ ] Stats display correctly
  - [ ] Recent alerts shown
  - [ ] Tracked tokens visible
  - [ ] Performance metrics accurate

---

## 📊 Success Criteria

All of these should be true:

- [ ] ✅ All 6 containers running
- [ ] ✅ HTTP redirects to HTTPS (301/308)
- [ ] ✅ HTTPS accessible (no connection errors)
- [ ] ✅ Login required (401 without credentials)
- [ ] ✅ Login works (200 with credentials)
- [ ] ✅ API returns valid data
- [ ] ✅ No tracker format errors in logs
- [ ] ✅ Cleanup cron job installed
- [ ] ✅ Bot still processing signals
- [ ] ✅ Dashboard accessible in browser

---

## 🐛 Troubleshooting

### Issue: Containers won't start

**Symptoms:** `docker ps` shows containers missing or restarting

**Solution:**
```bash
# Check logs
docker-compose logs web
docker-compose logs tracker

# Rebuild from scratch
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Issue: Can't login

**Symptoms:** 401 error even with correct credentials

**Solution:**
```bash
# Verify environment variables
docker exec callsbot-web env | grep DASHBOARD

# Check .env file
cat deployment/.env | grep DASHBOARD

# Restart web container
docker-compose restart web
```

### Issue: HTTPS not working

**Symptoms:** Connection refused on port 443

**Solution:**
```bash
# Check Caddy logs
docker logs callsbot-proxy

# Verify port binding
docker ps | grep callsbot-proxy

# Restart proxy
docker-compose restart caddy
```

### Issue: Tracker still has errors

**Symptoms:** Format errors still appearing in logs

**Solution:**
```bash
# Verify file was updated
grep -n "if feature_perf is None" scripts/track_performance.py

# Rebuild tracker
docker-compose build --no-cache tracker
docker-compose restart tracker
```

### Issue: Cleanup not working

**Symptoms:** Cron job not found or script errors

**Solution:**
```bash
# Re-run setup
bash scripts/setup_cleanup_cron.sh

# Test manually
python3 scripts/cleanup_database.py --dry-run

# Check cron logs
grep CRON /var/log/syslog | tail -20
```

---

## 🔄 Rollback Procedure

If deployment fails and you need to rollback:

### Quick Rollback

```bash
# Stop containers
cd /opt/callsbotonchain/deployment
docker-compose down

# Find backup
ls -lt /opt/callsbotonchain/backups/

# Restore latest backup
BACKUP_DIR=$(ls -t /opt/callsbotonchain/backups/ | head -1)
cp /opt/callsbotonchain/backups/$BACKUP_DIR/Caddyfile deployment/
cp /opt/callsbotonchain/backups/$BACKUP_DIR/server.py ../src/
cp /opt/callsbotonchain/backups/$BACKUP_DIR/track_performance.py ../scripts/

# Restart
docker-compose up -d
```

### Git Rollback

```bash
# Find commit before changes
git log --oneline -10

# Rollback to previous commit
git checkout <commit-hash>

# Rebuild and restart
cd deployment
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

---

## 📝 Post-Deployment Tasks

### Immediate (Within 1 hour)

- [ ] **Monitor logs**
  ```bash
  docker-compose logs -f --tail=50
  # Watch for errors for 10-15 minutes
  ```

- [ ] **Test all endpoints**
  - [ ] Dashboard: `https://64.227.157.221/`
  - [ ] Quick stats: `/api/v2/quick-stats`
  - [ ] Alerts: `/api/v2/alerts`
  - [ ] Tracked tokens: `/api/v2/tracked-tokens`

- [ ] **Verify bot activity**
  ```bash
  # Check signal processing
  curl -k -u admin:pass https://127.0.0.1/api/v2/quick-stats | jq '.total_signals'
  
  # Wait 5 minutes, check again (should increase)
  ```

### Within 24 hours

- [ ] **Change default password**
  - [ ] Generate strong random password
  - [ ] Update in `.env`
  - [ ] Restart web container
  - [ ] Test new password

- [ ] **Monitor cleanup**
  - [ ] Wait for 3 AM (cron time)
  - [ ] Check cleanup logs: `cat var/cleanup.log`
  - [ ] Verify database size: `du -h var/callsbot.db`

- [ ] **Document credentials**
  - [ ] Store in password manager
  - [ ] Share with team (securely)
  - [ ] Document access procedures

### Within 1 week

- [ ] **Get production SSL certificate**
  - [ ] Update Caddyfile with email
  - [ ] Remove `tls internal` line
  - [ ] Restart Caddy
  - [ ] Verify certificate in browser

- [ ] **Setup monitoring**
  - [ ] Configure Healthchecks.io or similar
  - [ ] Add uptime monitoring
  - [ ] Setup alert notifications

- [ ] **Test backup/restore**
  - [ ] Create test backup
  - [ ] Restore in test environment
  - [ ] Verify functionality

---

## 📈 Metrics to Track

Monitor these metrics after deployment:

| Metric | Before | After | Target |
|--------|--------|-------|--------|
| Uptime | 17 days | ___ | No decrease |
| Total Signals | 371 | ___ | Increasing |
| Total Alerts | 109 | ___ | Increasing |
| Tracked Tokens | 60 | ___ | Stable/Increasing |
| Database Size | 7.9 MB | ___ | <50 MB |
| Memory Usage | 210 MB | ___ | <300 MB |
| CPU Load | 0.17 | ___ | <1.0 |
| Container Restarts | 0 | ___ | 0 |

---

## ✅ Final Sign-Off

- [ ] All deployment steps completed
- [ ] All verification tests passed
- [ ] No critical errors in logs
- [ ] Bot processing signals normally
- [ ] Dashboard accessible and functional
- [ ] Credentials documented securely
- [ ] Team notified of changes
- [ ] Monitoring in place

**Deployed by:** _______________  
**Date/Time:** _______________  
**Backup location:** _______________  
**Issues encountered:** _______________  
**Notes:** _______________

---

## 📚 Reference Documents

- **Quick Start:** `SECURITY_FIXES_README.md`
- **Detailed Guide:** `SECURITY_FIXES_DEPLOYMENT.md`
- **Technical Summary:** `FIXES_SUMMARY.md`
- **This Checklist:** `DEPLOYMENT_CHECKLIST.md`

---

**Ready to deploy?** Start with: `bash scripts/deploy_security_fixes.sh`