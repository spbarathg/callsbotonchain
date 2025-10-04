# Dashboard v2 - Deployment Issues & Fixes

**Date**: October 4, 2025  
**Status**: 🔄 Fixing issues discovered during deployment  

---

## 🔍 ISSUES IDENTIFIED

### **Issue #1: Missing `psutil` Dependency**
**Symptom**: System tab showing empty data (no CPU, Memory, Disk stats)

**Root Cause**: 
- `psutil` was added to `requirements.txt` but Docker was using cached build layers
- Even after `--no-cache` rebuild, docker-compose wasn't using the new image

**Status**: 🔄 Rebuilding with forced recreation

---

### **Issue #2: NaN Values in JSON**
**Symptom**: JavaScript unable to parse alerts data

**Root Cause**:
```json
{"liquidity": NaN, "market_cap": 123456}
```
- Python logs write `NaN` as a literal (not valid JSON)
- JavaScript `JSON.parse()` fails on `NaN`

**Fix Applied**:
```python
# Before
alerts.append(json.loads(line.strip()))

# After
line_clean = line.strip().replace(': NaN', ': null')
alerts.append(json.loads(line_clean))
```

**Status**: ✅ Fixed in commit `7b20551`

---

### **Issue #3: Timestamp Parsing**
**Symptom**: API returning `"status": "no_recent_data"`

**Root Cause**:
- ISO timestamp comparison was failing
- Some timestamps had timezone info, some didn't

**Fix Applied**:
```python
# Before
cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
recent = [a for a in alerts if a.get('ts', '') >= cutoff]

# After  
cutoff_ts = (datetime.now() - timedelta(hours=24))
for a in alerts:
    alert_ts = datetime.fromisoformat(a.get('ts', '').replace('Z', '+00:00'))
    if alert_ts >= cutoff_ts:
        recent.append(a)
```

**Status**: ✅ Fixed in commit `7b20551`

---

### **Issue #4: Empty API Responses**
**Symptom**: All v2 endpoints returning minimal/empty data

**Root Cause**: Multiple factors:
1. ❌ `psutil` not installed → System health unavailable
2. ✅ NaN in JSON → Parsing failures
3. ✅ Timestamp comparison → No "recent" data found
4. ❌ Docker image caching → Old code running

**Status**: 🔄 Partially fixed, waiting for rebuild

---

## 🛠️ FIXES APPLIED

### **Commit: `cd5af87`**
- Added `psutil>=5.9.0` to `requirements.txt`

### **Commit: `7b20551`**
- Handle NaN in JSON parsing
- Improved timestamp parsing with proper ISO format handling
- Better error handling in API functions
- Round percentages to 1 decimal place
- Return `"status": "no_data"` when no alerts found

---

## 🔄 CURRENT STATUS

### **Completed**:
- ✅ NaN handling in JSON parsing
- ✅ Timestamp comparison logic fixed
- ✅ Error handling improved
- ✅ `psutil` added to requirements.txt
- ✅ Code committed and pushed

### **In Progress**:
- 🔄 Docker image rebuild with `psutil`
- 🔄 Container recreation to use new image

### **Expected After Rebuild**:
- ✅ System tab will show CPU, Memory, Disk usage
- ✅ Smart Money Status will show actual metrics
- ✅ Feed Health will display current cycle info
- ✅ Budget Status will show API usage
- ✅ All v2 endpoints will return real data

---

## 📊 VALIDATION CHECKLIST

Once rebuild completes, verify:

### **1. psutil Installation**
```bash
docker exec callsbot-web pip show psutil
# Should show: Version: 5.x.x
```

### **2. Smart Money API**
```bash
curl http://64.227.157.221/api/v2/smart-money-status
# Should show: smart_count, avg_score, smart_percentage, etc.
```

### **3. Feed Health API**
```bash
curl http://64.227.157.221/api/v2/feed-health
# Should show: status: "connected", current_cycle, feed_items
```

### **4. System Health API**
```bash
curl http://64.227.157.221/api/v2/system-health
# Should show: cpu_percent, memory_percent, disk_percent
```

### **5. Budget Status API**
```bash
curl http://64.227.157.221/api/v2/budget-status
# Should show: daily_used, daily_max, resets_in
```

---

## 🔧 TECHNICAL DETAILS

### **Why Docker Caching Was Problematic**:

1. **Build Layer Caching**: Docker caches `RUN pip install` if requirements.txt hasn't changed (by content hash)
2. **Image Reuse**: Even with `--no-cache`, if an identical image exists, docker-compose may reuse it
3. **Container Persistence**: Stopping/starting containers doesn't change the underlying image

### **Solution**:
```bash
# Force complete rebuild
docker compose build --no-cache web

# Force container recreation (not just restart)
docker compose up -d --force-recreate web

# Verify image
docker inspect callsbot-web --format='{{.Image}}'
docker run --rm <image_id> pip show psutil
```

---

## 📝 LESSONS LEARNED

1. **Always verify dependencies are installed** after Docker builds
2. **Handle NaN in log files** - Python writes NaN, JavaScript can't parse it
3. **Use proper ISO timestamp parsing** with timezone handling
4. **Force Docker image recreation** when adding dependencies
5. **Test API endpoints** before declaring "deployment complete"

---

## ⏱️ ESTIMATED TIME TO RESOLUTION

- ✅ Issue identification: 10 minutes
- ✅ Code fixes: 15 minutes
- 🔄 Docker rebuild: ~15 minutes (in progress)
- ⏳ Validation: 5 minutes
- **Total**: ~45 minutes

---

**Next Update**: After rebuild completes and validation passes


