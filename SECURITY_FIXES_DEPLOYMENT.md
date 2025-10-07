# 🔐 Security Fixes Deployment Guide

This guide walks you through deploying the security fixes to your CallsBotOnChain server.

**Estimated Time:** 15-20 minutes  
**Downtime:** ~2 minutes (during container restart)

---

## 📋 What's Being Fixed

1. ✅ **HTTPS Enforcement** - All HTTP traffic redirected to HTTPS
2. ✅ **Dashboard Authentication** - Login required for all routes
3. ✅ **Tracker Formatting Error** - Fixed NoneType format error
4. ✅ **Database Cleanup** - Automated cleanup of old snapshots

---

## 🚀 Deployment Steps

### Step 1: SSH to Server

```bash
ssh root@64.227.157.221
cd /opt/callsbotonchain
```

### Step 2: Backup Current Configuration

```bash
# Backup current files
cp deployment/Caddyfile deployment/Caddyfile.backup
cp src/server.py src/server.py.backup
cp scripts/track_performance.py scripts/track_performance.py.backup

# Backup database
cp var/alerted_tokens.db var/alerted_tokens.db.backup
```

### Step 3: Pull Latest Changes

```bash
# If using git
git pull origin main

# Or manually copy the updated files from your local machine
# (use scp or your preferred method)
```

### Step 4: Configure Authentication

```bash
# Edit .env file to add authentication credentials
nano deployment/.env

# Add these lines (change the password!):
DASHBOARD_AUTH_ENABLED=true
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=YourSecurePassword123!

# Optional: Disable auth temporarily for testing
# DASHBOARD_AUTH_ENABLED=false
```

**⚠️ IMPORTANT:** Choose a strong password! Use at least 20 characters with mixed case, numbers, and symbols.

### Step 5: Restart Containers

```bash
cd /opt/callsbotonchain/deployment

# Restart all containers to apply changes
docker-compose down
docker-compose up -d

# Wait 30 seconds for containers to start
sleep 30

# Check container status
docker ps --filter name=callsbot
```

**Expected Output:** All 6 containers should show "Up" status.

### Step 6: Verify HTTPS

```bash
# Test HTTPS redirect (should return 301 or 308)
curl -I http://127.0.0.1/

# Test HTTPS endpoint (may show cert warning - that's OK)
curl -k https://127.0.0.1/api/v2/quick-stats
```

**Expected:** HTTP requests redirect to HTTPS.

### Step 7: Verify Authentication

```bash
# Test without credentials (should return 401)
curl -k https://127.0.0.1/

# Test with credentials (should return 200)
curl -k -u admin:YourSecurePassword123! https://127.0.0.1/
```

**Expected:** Requests without credentials are rejected.

### Step 8: Setup Database Cleanup

```bash
# Make cleanup script executable
chmod +x scripts/cleanup_database.py
chmod +x scripts/setup_cleanup_cron.sh

# Test manual cleanup
python3 scripts/cleanup_database.py

# Setup automatic daily cleanup (runs at 3 AM)
bash scripts/setup_cleanup_cron.sh

# Verify cron job installed
crontab -l | grep cleanup_database
```

**Expected Output:**
```
0 3 * * * cd /opt/callsbotonchain && /usr/bin/python3 scripts/cleanup_database.py >> var/cleanup.log 2>&1
```

### Step 9: Verify Tracker Fix

```bash
# Check tracker logs (should see no format errors)
docker logs callsbot-tracker --tail 50

# Wait for next tracking cycle (10 minutes)
# Then check again - should see clean summary output
```

### Step 10: Final Health Check

```bash
# Check all containers
docker ps --filter name=callsbot

# Check quick stats
curl -k -u admin:YourSecurePassword123! https://127.0.0.1/api/v2/quick-stats | jq

# Check budget status
curl -k -u admin:YourSecurePassword123! https://127.0.0.1/api/v2/budget-status | jq

# Check worker logs
docker logs callsbot-worker --tail 20
```

---

## 🌐 Accessing Dashboard

### From Browser

1. Navigate to: `https://64.227.157.221/`
2. You'll see a certificate warning (expected with self-signed cert)
3. Click "Advanced" → "Proceed to site"
4. Enter credentials:
   - **Username:** admin
   - **Password:** (your password from .env)

### From Command Line

```bash
# With authentication
curl -k -u admin:YourPassword https://64.227.157.221/api/v2/quick-stats

# Save credentials in .netrc for convenience (optional)
echo "machine 64.227.157.221 login admin password YourPassword" >> ~/.netrc
chmod 600 ~/.netrc
```

---

## 🔧 Configuration Options

### Disable Authentication (Not Recommended)

```bash
# In deployment/.env
DASHBOARD_AUTH_ENABLED=false

# Restart web container
docker-compose restart web
```

### Use Production SSL Certificate

```bash
# Edit deployment/Caddyfile
# Replace:
#   tls internal
# With:
#   tls your-email@example.com

# Restart proxy
docker-compose restart caddy
```

### Adjust Database Retention

```bash
# In deployment/.env
SNAPSHOT_RETENTION_DAYS=60  # Keep snapshots for 60 days
TRACKING_RETENTION_DAYS=14  # Keep completed tracking for 14 days

# No restart needed - applies on next cleanup run
```

---

## 🐛 Troubleshooting

### Issue: Containers Won't Start

```bash
# Check logs
docker-compose logs web
docker-compose logs caddy

# Common fix: Rebuild containers
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Issue: Can't Access Dashboard

```bash
# Check if port 443 is open
netstat -tlnp | grep 443

# Check Caddy logs
docker logs callsbot-proxy

# Test locally first
curl -k https://127.0.0.1/
```

### Issue: Authentication Not Working

```bash
# Verify .env file loaded
docker exec callsbot-web env | grep DASHBOARD

# Check if auth is enabled
docker exec callsbot-web env | grep DASHBOARD_AUTH_ENABLED

# Restart web container
docker-compose restart web
```

### Issue: Tracker Still Showing Errors

```bash
# Verify file updated
docker exec callsbot-tracker cat scripts/track_performance.py | grep "Safe formatting"

# If not updated, rebuild
docker-compose build tracker
docker-compose up -d tracker
```

### Issue: Database Cleanup Fails

```bash
# Check database permissions
ls -la var/alerted_tokens.db

# Run cleanup with verbose output
python3 scripts/cleanup_database.py

# Check cleanup log
tail -f var/cleanup.log
```

---

## 📊 Monitoring

### Check Cleanup Logs

```bash
# View cleanup history
tail -100 var/cleanup.log

# Watch cleanup in real-time (during manual run)
tail -f var/cleanup.log
```

### Monitor Database Size

```bash
# Check current size
du -sh var/alerted_tokens.db

# Check growth over time
watch -n 60 'du -sh var/alerted_tokens.db'
```

### Monitor Failed Login Attempts

```bash
# Check web container logs for 401 responses
docker logs callsbot-web 2>&1 | grep "401"

# Check Caddy access logs
docker exec callsbot-proxy cat /var/log/caddy/access.log | jq 'select(.status == 401)'
```

---

## 🔄 Rollback Procedure

If something goes wrong, rollback to previous state:

```bash
# Stop containers
docker-compose down

# Restore backups
cp deployment/Caddyfile.backup deployment/Caddyfile
cp src/server.py.backup src/server.py
cp scripts/track_performance.py.backup scripts/track_performance.py

# Restart containers
docker-compose up -d

# Verify
docker ps --filter name=callsbot
curl http://127.0.0.1/api/v2/quick-stats
```

---

## ✅ Success Checklist

- [ ] All 6 containers running and healthy
- [ ] HTTP redirects to HTTPS (301/308 response)
- [ ] Dashboard requires authentication
- [ ] Tracker logs show no format errors
- [ ] Database cleanup script runs successfully
- [ ] Cron job installed for automatic cleanup
- [ ] Can access dashboard with credentials
- [ ] API endpoints return data correctly
- [ ] Worker still processing signals
- [ ] Tracker still updating prices

---

## 📞 Support

If you encounter issues:

1. Check the troubleshooting section above
2. Review container logs: `docker-compose logs`
3. Verify configuration: `cat deployment/.env`
4. Test individual components separately
5. Rollback if needed (see Rollback Procedure)

---

## 🎯 Next Steps

After successful deployment:

1. **Change Default Password** - Use a password manager to generate a strong password
2. **Setup SSL Certificate** - Get a free cert from Let's Encrypt for production
3. **Monitor Logs** - Check cleanup logs weekly to ensure it's working
4. **Test Backup/Restore** - Verify you can restore from backups
5. **Document Credentials** - Store credentials securely (password manager)

---

## 📝 Summary of Changes

### Files Modified:
- `deployment/Caddyfile` - Added HTTPS redirect and enhanced security headers
- `src/server.py` - Added authentication middleware
- `scripts/track_performance.py` - Fixed NoneType formatting error

### Files Created:
- `scripts/cleanup_database.py` - Database cleanup script
- `scripts/setup_cleanup_cron.sh` - Cron job installer
- `.env.security.example` - Security configuration template
- `SECURITY_FIXES_DEPLOYMENT.md` - This deployment guide

### Configuration Added:
- `DASHBOARD_AUTH_ENABLED` - Enable/disable authentication
- `DASHBOARD_USERNAME` - Dashboard login username
- `DASHBOARD_PASSWORD` - Dashboard login password
- `SNAPSHOT_RETENTION_DAYS` - Snapshot retention period
- `TRACKING_RETENTION_DAYS` - Tracking retention period

---

**Deployment Date:** _____________  
**Deployed By:** _____________  
**Status:** ⬜ Success  ⬜ Partial  ⬜ Rollback  
**Notes:** _____________________________________________