# AI Assistant Operating Rules for CallsBotOnChain

**Purpose:** These rules ensure I (the AI assistant) don't break the production bot through negligence, incorrect assumptions, or incomplete verification. Follow these RELIGIOUSLY.

---

## 🚨 CRITICAL: Deployment & Container Management

### Rule 1: NEVER Use `docker compose restart` for Code Changes
- **I MUST use:** `ssh root@64.227.157.221 "cd /opt/callsbotonchain && docker compose up -d --build web"`
- **Why:** `restart` does NOT rebuild - it uses the OLD image with stale code baked in
- **When I forget this:** User sees no changes despite "successful deployment" → wastes 30+ minutes debugging

### Rule 2: Clean Up Docker Regularly to Prevent Disk Full
- **After every few deployments, I MUST run:**
  ```bash
  ssh root@64.227.157.221 "docker system df"  # Check space first
  ssh root@64.227.157.221 "docker system prune -a --volumes -f"  # Clean everything unused
  ```
- **Why:** Docker build cache accumulates FAST (17GB observed) and fills 25GB disk
- **Before pruning:** Verify all bot containers are running and healthy

### Rule 3: ALWAYS Verify Files Inside Container After Deployment
- **I MUST check:**
  ```bash
  ssh root@64.227.157.221 "docker exec callsbot-web stat -c '%y' /app/src/templates/index.html"
  ```
- **Compare to host file timestamp** - if container file is older, rebuild didn't happen
- **Don't trust git pull alone** - verify the container actually got the new code

### Rule 4: Test What's ACTUALLY Being Served
- **I MUST verify:**
  ```bash
  ssh root@64.227.157.221 "curl -s http://localhost:80 | grep 'SPECIFIC_CHANGE_I_MADE'"
  ```
- **Why:** Files can exist on disk but container serves old cached version
- **Look for:** Specific HTML/JS changes I made, version numbers, unique strings

---

## 🔄 Version Control & Git Workflow

### Rule 5: ALWAYS Check Git Hashes Match Local vs Server
- **Before deploying, I MUST verify:**
  ```bash
  git log --oneline -1  # Local
  ssh root@64.227.157.221 "cd /opt/callsbotonchain && git log --oneline -1"  # Server
  ```
- **If they don't match:** Either I didn't push, or server didn't pull

### Rule 6: ALWAYS Push After Committing Locally
- **My workflow MUST be:**
  1. `git add <files>`
  2. `git commit -m "message"`
  3. `git push origin main` ← **I CANNOT SKIP THIS**
- **Why:** Server pulls from GitHub, not my local machine
- **I MUST verify push succeeded:** Check GitHub web UI or `git log origin/main`

### Rule 7: Verify Server Actually Got the Updates
- **After `git pull` on server, I MUST check:**
  ```bash
  ssh root@64.227.157.221 "cd /opt/callsbotonchain && git log --oneline -3"
  ```
- **Look for:** My latest commit message in the log
- **If not there:** Pull failed silently, need to investigate

---

## ✅ Verification Checklist (Before Saying "It's Fixed")

### Rule 8: Check Container Logs for Errors After Every Change
```bash
ssh root@64.227.157.221 "docker logs callsbot-web --tail 50"
ssh root@64.227.157.221 "docker logs callsbot-bot --tail 50"
```
- **Look for:** Import errors, syntax errors, runtime exceptions
- **Never assume silence = success** - check explicitly

### Rule 9: Verify API Endpoints Return Expected Data
```bash
ssh root@64.227.157.221 "curl -s http://localhost:80/api/stats | python3 -m json.tool | head -50"
```
- **I MUST confirm:** The field I added/modified is present with correct values
- **Don't assume the endpoint works** - test it explicitly

### Rule 10: Test Live Site, Not Just Source Files
- **I MUST load the actual webpage:**
  - If it's frontend: Instruct user to hard refresh (Ctrl+Shift+R)
  - If data missing: Check the API endpoint directly
- **Why:** Browser cache, CDN cache, container cache can all hide issues

### Rule 11: Timestamps Are My Friend
- **Host file newer than container file = REBUILD NEEDED**
- **I MUST check both:**
  ```bash
  ssh root@64.227.157.221 "stat -c '%y' /opt/callsbotonchain/src/templates/index.html"  # Host
  ssh root@64.227.157.221 "docker exec callsbot-web stat -c '%y' /app/src/templates/index.html"  # Container
  ```

---

## 🌐 Browser & Frontend Issues

### Rule 12: When User Says "I Don't See Changes" → Browser Cache
- **My first response MUST be:** "Hard refresh: Ctrl+Shift+R or clear cache"
- **Not:** Making more code changes assuming my fix didn't work
- **Also suggest:** Test in incognito window to rule out cache

### Rule 13: Bump Version Params After Every Frontend Change
- **I MUST update:** `<link rel="stylesheet" href="/static/styles.css?v=5">`
- **Increment v=X** with each CSS/JS/HTML change
- **Why:** Forces browser to fetch fresh files

### Rule 14: Test in Incognito First
- **Before debugging further, I MUST:** Instruct user to test in incognito/private window
- **This rules out:** Browser extensions, cookies, localStorage, cache issues

---

## 💾 Database & Data Integrity

### Rule 15: Check BOTH API and Database When Data Is Missing
- **API first:**
  ```bash
  ssh root@64.227.157.221 "curl -s http://localhost:80/api/stats"
  ```
- **Then database:**
  ```bash
  ssh root@64.227.157.221 "sqlite3 /opt/callsbotonchain/var/alerted_tokens.db 'SELECT * FROM alerted_tokens ORDER BY alerted_at DESC LIMIT 5;'"
  ```
- **Why:** Issue could be in API logic OR database query OR both

### Rule 16: Verify Which Database Path Is Being Used
- **The app auto-picks the DB with most rows**
- **Check logs:** `grep "picked" /var/log/...` or container logs
- **Don't assume:** Check all candidate paths: `/app/var/`, `/app/state/`, `var/`

---

## 🏥 Container Health & System Status

### Rule 17: ALWAYS Check Container Status Before and After Changes
```bash
ssh root@64.227.157.221 "docker ps --filter name=callsbot"
```
- **I MUST verify:** All containers show "Up X minutes/hours" (not "Restarting")
- **If any container is restarting:** Check logs immediately, don't proceed

### Rule 18: Know the Reverse Proxy Setup
- **Web container listens on 8080 internally**
- **Nginx/Caddy exposes on port 80 externally**
- **When testing, I MUST use:** `curl http://localhost:80` not `http://localhost:8080`

### Rule 19: Check Port Mappings When Network Issues Occur
```bash
ssh root@64.227.157.221 "docker port callsbot-web"
ssh root@64.227.157.221 "netstat -tlnp | grep 8080"
```
- **Verify:** Ports are actually bound and listening

---

## 📊 Performance & Resource Monitoring

### Rule 20: Monitor Disk Space Proactively
```bash
ssh root@64.227.157.221 "df -h"
```
- **I MUST check this:** Before any Docker build operation
- **If >80% full:** Run cleanup BEFORE proceeding
- **Bot generates logs continuously** - they accumulate fast

### Rule 21: Check for Database Locks If Queries Hang
```bash
ssh root@64.227.157.221 "lsof | grep alerted_tokens.db"
```
- **Or:** Check if multiple processes are trying to write
- **Solution:** Restart bot container if locked

### Rule 22: Review Process Logs for API Rate Limiting
```bash
ssh root@64.227.157.221 "tail -100 /opt/callsbotonchain/data/logs/process.jsonl | grep error"
```
- **Look for:** rate_limited, api_error, 429 responses
- **Why:** Bot may appear broken but it's just hitting API limits

---

## 🛠️ Before Making ANY Changes

### Rule 23: Read Current Code First - NEVER Assume
- **I MUST use:** `read_file`, `grep`, `codebase_search` to understand current implementation
- **Don't assume:** A function does what its name suggests
- **Don't assume:** A feature works a certain way without verifying

### Rule 24: Search Codebase Thoroughly Before Implementing
- **Use `grep` or `codebase_search`** to check if feature already exists
- **Why:** User may have forgotten, or it exists with different name
- **Don't duplicate:** Wastes time and creates maintenance burden

### Rule 25: For Critical Bot Logic, Suggest Testing Locally First
- **Especially for:** Trading logic, signal processing, scoring algorithms
- **Why:** Production bot runs 24/7 - bugs = missed opportunities or lost money
- **When can't test locally:** Be extra careful with verification steps

### Rule 26: Use DevTools When Debugging Frontend
- **I MUST instruct user:** Open DevTools (F12) → Network tab
- **Check for:** Failed API calls (red), 404s, CORS errors, slow requests
- **Console tab:** JavaScript errors that break functionality

---

## 🆘 Emergency Procedures

### Rule 27: Note Working Commit Hash BEFORE Risky Changes
```bash
git log --oneline -1 > /tmp/last_working_commit.txt
```
- **Especially before:** Database migrations, major refactors, algorithm changes

### Rule 28: Know How to Rollback Quickly
```bash
ssh root@64.227.157.221 "cd /opt/callsbotonchain && git checkout <HASH> && docker compose up -d --build"
```
- **Test rollback works IMMEDIATELY after deploying the fix**
- **Don't wait for production failure** to discover rollback is broken

### Rule 29: Database Changes Are PERMANENT - Backup First
- **Before ANY schema changes:**
  ```bash
  ssh root@64.227.157.221 "cp /opt/callsbotonchain/var/alerted_tokens.db /opt/callsbotonchain/var/alerted_tokens.db.backup.$(date +%s)"
  ```
- **Why:** Can't git revert database data
- **Verify backup is readable:** Try to open it with sqlite3

---

## 📝 Self-Check Before Replying "Done" or "Fixed"

- [ ] Did I rebuild the container with `--build` flag?
- [ ] Did I verify files inside container have new timestamps?
- [ ] Did I test the actual endpoint/page being served?
- [ ] Did I check container logs for errors?
- [ ] Did I verify git hashes match?
- [ ] Did I push my commits to origin?
- [ ] Did I check disk space isn't critical?
- [ ] Did I instruct user to hard refresh if frontend change?
- [ ] Did I verify the specific data/feature user asked for is working?
- [ ] Would I bet money that this fix actually works? (If no → verify more)

---

**Remember:** User is running a live production bot. My negligence = missed trading opportunities, wasted time, or system failure. Better to over-verify than to assume. 