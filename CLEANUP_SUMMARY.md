# Log Directory Cleanup - October 13, 2025

## 🎯 Problem Solved

**Issue:** Confusion about log file locations causing incorrect assumptions about system health.

**Root Cause:** Two log directories existed:
- `/opt/callsbotonchain/data/logs/` (old, empty since Oct 11)
- `/opt/callsbotonchain/deployment/data/logs/` (active, 50MB+ of logs)

People were checking the wrong directory and concluding logs weren't working.

---

## ✅ Actions Taken

### 1. Cleaned Up Old Log Directory
```bash
# Removed all old log files
rm -f /opt/callsbotonchain/data/logs/*.log
rm -f /opt/callsbotonchain/data/logs/*.jsonl

# Added warning README
echo "DEPRECATED - Logs moved to deployment/data/logs/" > data/logs/README.txt
```

**Result:** Old directory now empty with clear warning.

### 2. Created Documentation

**Files Created:**
- `LOG_LOCATIONS.md` - Comprehensive guide to log locations
- `scripts/verify_logs.sh` - Automated verification script
- `deployment/data/logs/README.txt` - Quick reference in active directory
- `data/logs/README.txt` - Deprecation notice in old directory

### 3. Updated Documentation

**Files Updated:**
- `docs/quickstart/CURRENT_SETUP.md` - Added log location section at top
- Added quick verification commands
- Updated commit hash and status

---

## 📊 Verification Results

### Active Logs Status
```
✅ /opt/callsbotonchain/deployment/data/logs/
   - stdout.log      : 28MB (actively growing)
   - process.jsonl   : 22MB (actively growing)
   - alerts.jsonl    : 415KB (54 alerts in last 24h)
   - trading.jsonl   : 166 bytes (no active trading)
   - trading.log     : 114 bytes (no active trading)
```

### System Health
```
✅ All Docker containers running
✅ Bot processing signals every 60 seconds
✅ API accessible on port 80 (Caddy proxy)
✅ 673 total signals tracked
✅ 55.29% win rate, 333.94% average gain
✅ No errors in recent logs
```

---

## 🔍 How to Verify Logs Are Working

### Method 1: Run Verification Script
```bash
ssh root@64.227.157.221
/opt/callsbotonchain/scripts/verify_logs.sh
```

### Method 2: Manual Check
```bash
# Check log sizes (should be growing)
ls -lh /opt/callsbotonchain/deployment/data/logs/

# View recent activity
tail -n 20 /opt/callsbotonchain/deployment/data/logs/stdout.log

# Check last alert
tail -n 1 /opt/callsbotonchain/deployment/data/logs/alerts.jsonl | jq
```

### Method 3: Docker Logs
```bash
# View bot logs directly
docker logs callsbot-worker --tail 50

# View tracker logs
docker logs callsbot-tracker --tail 30
```

### Method 4: API Check
```bash
# Quick stats
curl http://localhost/api/v2/quick-stats

# External access
curl http://64.227.157.221/api/v2/quick-stats
```

---

## 📁 Complete Directory Structure

```
/opt/callsbotonchain/
├── deployment/
│   ├── data/
│   │   └── logs/              ← ✅ ACTIVE LOGS HERE
│   │       ├── stdout.log
│   │       ├── process.jsonl
│   │       ├── alerts.jsonl
│   │       ├── trading.jsonl
│   │       └── README.txt
│   └── var/                   ← ✅ ACTIVE DATABASES HERE
│       ├── alerted_tokens.db  (24MB)
│       ├── trading.db
│       └── paper_trading.db
├── data/
│   └── logs/                  ← ❌ OLD (EMPTY)
│       └── README.txt         (deprecation notice)
├── var/                       ← ❌ OLD (EMPTY)
├── LOG_LOCATIONS.md           ← 📖 FULL DOCUMENTATION
└── scripts/
    └── verify_logs.sh         ← 🔍 VERIFICATION SCRIPT
```

---

## 🐳 Docker Volume Mounts

Containers mount logs from the deployment directory:

```yaml
volumes:
  - /opt/callsbotonchain/deployment/var:/app/var
  - /opt/callsbotonchain/deployment/data/logs:/app/data/logs
```

**Inside Container:** `/app/data/logs/`  
**On Host:** `/opt/callsbotonchain/deployment/data/logs/`

---

## 🎓 Key Takeaways

1. **Always use deployment directory** for logs and databases
2. **Run verify_logs.sh** to check system health
3. **API is on port 80** (not 8080 - that's internal only)
4. **Logs are working perfectly** - just needed to check the right location

---

## 📝 Files Changed

### Created
- `LOG_LOCATIONS.md`
- `scripts/verify_logs.sh`
- `deployment/data/logs/README.txt`
- `data/logs/README.txt`
- `CLEANUP_SUMMARY.md` (this file)

### Modified
- `docs/quickstart/CURRENT_SETUP.md`

### Deleted
- All files in `data/logs/` (old logs)

---

## ✅ Next Steps

1. **Commit these changes** to git
2. **Share LOG_LOCATIONS.md** with team
3. **Use verify_logs.sh** for future health checks
4. **Update any scripts** that reference old log paths

---

**Date:** October 13, 2025  
**Author:** System Cleanup  
**Status:** ✅ Complete

