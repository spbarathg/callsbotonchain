# 🔐 Security Fixes - Quick Start Guide

All security weaknesses have been fixed! This guide will help you deploy the fixes to your server.

---

## 🎯 What Was Fixed

| Issue | Status | Impact |
|-------|--------|--------|
| No HTTPS enforcement | ✅ Fixed | High - All traffic now encrypted |
| No authentication | ✅ Fixed | High - Login required |
| Tracker format error | ✅ Fixed | Low - Clean logs |
| Database growth | ✅ Fixed | Medium - Automatic cleanup |

---

## 🚀 Quick Deploy (5 Minutes)

### Option 1: Automated Script (Recommended)

```bash
# SSH to server
ssh root@64.227.157.221

# Navigate to project
cd /opt/callsbotonchain

# Pull latest changes
git pull origin main

# Run automated deployment
chmod +x scripts/deploy_security_fixes.sh
bash scripts/deploy_security_fixes.sh
```

The script will:
- ✅ Create backups automatically
- ✅ Configure authentication (prompts for password)
- ✅ Rebuild and restart containers
- ✅ Setup database cleanup
- ✅ Test all fixes
- ✅ Show deployment summary

**That's it!** The script handles everything.

---

### Option 2: Manual Deployment

If you prefer manual control, follow these steps:

```bash
# 1. SSH to server
ssh root@64.227.157.221
cd /opt/callsbotonchain

# 2. Backup
cp deployment/Caddyfile deployment/Caddyfile.backup
cp src/server.py src/server.py.backup
cp scripts/track_performance.py scripts/track_performance.py.backup

# 3. Pull changes
git pull origin main

# 4. Configure authentication
nano deployment/.env
# Add these lines:
DASHBOARD_AUTH_ENABLED=true
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=YourSecurePassword123!

# 5. Restart containers
cd deployment
docker-compose down
docker-compose build --no-cache web tracker
docker-compose up -d

# 6. Setup cleanup
cd ..
chmod +x scripts/cleanup_database.py scripts/setup_cleanup_cron.sh
bash scripts/setup_cleanup_cron.sh

# 7. Verify
docker ps --filter name=callsbot
curl -k -u admin:YourPassword https://127.0.0.1/api/v2/quick-stats
```

---

## 🔍 Verify Deployment

After deployment, check:

```bash
# 1. All containers running
docker ps --filter name=callsbot
# Should show 6 containers

# 2. HTTPS redirect working
curl -I http://127.0.0.1/
# Should return 301 or 308

# 3. Authentication working
curl -k https://127.0.0.1/
# Should return 401 (unauthorized)

curl -k -u admin:YourPassword https://127.0.0.1/
# Should return 200 (success)

# 4. API working
curl -k -u admin:YourPassword https://127.0.0.1/api/v2/quick-stats | jq

# 5. No tracker errors
docker logs callsbot-tracker --tail 50 | grep -i error

# 6. Cleanup cron installed
crontab -l | grep cleanup_database
```

---

## 🌐 Access Dashboard

### From Browser

1. Go to: `https://64.227.157.221/`
2. Accept certificate warning (self-signed cert)
3. Enter credentials:
   - Username: `admin`
   - Password: (from your .env file)

### From Command Line

```bash
# With credentials
curl -k -u admin:YourPassword https://64.227.157.221/api/v2/quick-stats

# Save credentials (optional)
echo "machine 64.227.157.221 login admin password YourPassword" >> ~/.netrc
chmod 600 ~/.netrc
```

---

## 🔧 Configuration

### Disable Authentication (Not Recommended)

```bash
# In deployment/.env
DASHBOARD_AUTH_ENABLED=false

# Restart
docker-compose restart web
```

### Change Password

```bash
# Edit .env
nano deployment/.env

# Change this line:
DASHBOARD_PASSWORD=NewSecurePassword

# Restart
docker-compose restart web
```

### Adjust Database Retention

```bash
# In deployment/.env
SNAPSHOT_RETENTION_DAYS=60  # Keep 60 days instead of 30

# No restart needed - applies on next cleanup
```

### Use Production SSL Certificate

```bash
# Edit deployment/Caddyfile
# Replace:
#   tls internal
# With:
#   tls your-email@example.com

# Restart
docker-compose restart caddy
```

---

## 🐛 Troubleshooting

### Containers Won't Start

```bash
# Check logs
docker-compose logs web
docker-compose logs caddy

# Rebuild
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Can't Login

```bash
# Check if auth is enabled
docker exec callsbot-web env | grep DASHBOARD_AUTH_ENABLED

# Verify credentials
cat deployment/.env | grep DASHBOARD

# Restart web container
docker-compose restart web
```

### HTTPS Not Working

```bash
# Check Caddy logs
docker logs callsbot-proxy

# Verify port 443 is open
netstat -tlnp | grep 443

# Test locally
curl -k https://127.0.0.1/
```

---

## 🔄 Rollback

If something goes wrong:

```bash
# Stop containers
cd /opt/callsbotonchain/deployment
docker-compose down

# Restore backups
cp Caddyfile.backup Caddyfile
cp ../src/server.py.backup ../src/server.py
cp ../scripts/track_performance.py.backup ../scripts/track_performance.py

# Restart
docker-compose up -d
```

Or use the automated backup:

```bash
# Find latest backup
ls -lt /opt/callsbotonchain/backups/

# Restore from backup directory
cd /opt/callsbotonchain/deployment
docker-compose down
cp /opt/callsbotonchain/backups/YYYYMMDD_HHMMSS/* .
docker-compose up -d
```

---

## 📚 Documentation

- **Quick Start:** This file
- **Detailed Deployment:** `SECURITY_FIXES_DEPLOYMENT.md`
- **Technical Summary:** `FIXES_SUMMARY.md`
- **Security Config:** `.env.security.example`

---

## ✅ Success Checklist

After deployment:

- [ ] All 6 containers running
- [ ] HTTP redirects to HTTPS
- [ ] Dashboard requires login
- [ ] Can login with credentials
- [ ] API endpoints work
- [ ] No tracker errors
- [ ] Cleanup cron installed
- [ ] Bot still processing signals
- [ ] Tracker still updating prices

---

## 🎯 What's Next

### Immediate
1. ✅ Deploy fixes (you're here!)
2. Change default password
3. Test all functionality
4. Monitor for 24 hours

### This Week
1. Get production SSL certificate
2. Setup monitoring/alerting
3. Document credentials securely
4. Test backup/restore

### This Month
1. Implement IP whitelisting
2. Add audit logging
3. Setup automated backups
4. Create incident response plan

---

## 📞 Need Help?

**Automated Deployment:** `bash scripts/deploy_security_fixes.sh`  
**Manual Deployment:** See `SECURITY_FIXES_DEPLOYMENT.md`  
**Troubleshooting:** Check deployment guide  
**Rollback:** See section above

---

## 📊 Summary

**Files Modified:** 3  
**Files Created:** 7  
**Deployment Time:** 5-20 minutes  
**Downtime:** ~2 minutes  
**Risk Level:** 🟢 Low (tested, rollback available)

**Status:** ✅ Ready to Deploy

---

**Deploy now with:** `bash scripts/deploy_security_fixes.sh`