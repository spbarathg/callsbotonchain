# Server Setup & Configuration Guide

**Last Updated**: October 30, 2025  
**Server**: `root@64.227.157.221`  
**Repository**: https://github.com/spbarathg/callsbotonchain

---

## Quick Reference

### Server Paths
```
Deployment Directory: /opt/callsbotonchain/
Docker Compose: /opt/callsbotonchain/deployment/docker-compose.yml
Main .env: /opt/callsbotonchain/.env
Deployment .env: /opt/callsbotonchain/deployment/.env
Logs: /opt/callsbotonchain/data/logs/
Database: /opt/callsbotonchain/var/trading.db
```

### Wallet Configuration
```
Private Key: 2eChRagM49m2mXqASyuDHCoh9GkF2xwaUUioHL8XgcHJuivxZi8JfSinVXtvzS1vbH5gcRyDZBTT7ded6caT8hBU
Wallet Address: 6Qpu7Muez374WgTvpY56pQ3wWbnefX7wSHZU9z21HJX8
Environment Variable: TS_WALLET_SECRET

Configured in:
- /opt/callsbotonchain/.env
- /opt/callsbotonchain/deployment/.env
```

### Git Remotes
```
origin: https://github.com/spbarathg/callsbotonchain (fetch/push)
production: ssh://root@64.227.157.221/opt/callsbotonchain.git (fetch/push)
```

---

## Making Changes & Deploying

### 1. Local Development
Work in this directory: `C:\Users\barat\yesv2\callsbotonchain\`

### 2. Testing Changes
```powershell
# Test locally if possible
python -m tradingSystem.cli_optimized
```

### 3. Commit & Push
```powershell
git add <files>
git commit -m "Description of changes"
git push origin main
```

### 4. Deploy to Server
```powershell
# SSH into server
ssh root@64.227.157.221

# Pull latest code
cd /opt/callsbotonchain
git pull origin main

# Rebuild containers (only if code changed)
cd deployment
docker compose down
docker compose up -d --build

# OR restart specific container without rebuild
docker compose restart trader
```

### 5. Verify Deployment
```bash
# Check containers running
docker ps

# Check trader logs
docker logs -f callsbot-trader

# Verify wallet
docker exec callsbot-trader printenv | grep TS_WALLET_SECRET

# Check for errors
docker logs callsbot-trader 2>&1 | grep -i error | tail -20
```

---

## Docker Containers

### All Services
```
callsbot-trader         - Trading execution engine
callsbot-worker         - Signal processing
callsbot-tracker        - Performance tracking
callsbot-signal-aggregator - Telegram monitoring
callsbot-web            - Dashboard (port 8080)
callsbot-redis          - Message queue
callsbot-proxy          - Caddy reverse proxy (ports 80/443)
```

### Common Commands
```bash
# View all containers
docker ps

# View logs (follow mode)
docker logs -f callsbot-trader

# View logs (last 100 lines)
docker logs callsbot-trader --tail 100

# Restart a container
docker compose restart trader

# Stop all
cd /opt/callsbotonchain/deployment
docker compose down

# Start all
docker compose up -d

# Rebuild all
docker compose up -d --build

# Check environment variables in container
docker exec callsbot-trader printenv
```

---

## Critical Files to Edit

### 1. Trading Configuration
**File**: `/opt/callsbotonchain/deployment/.env`

Key variables:
```bash
# Wallet (MUST be set correctly)
TS_WALLET_SECRET=2eChRagM49m2mXqASyuDHCoh9GkF2xwaUUioHL8XgcHJuivxZi8JfSinVXtvzS1vbH5gcRyDZBTT7ded6caT8hBU

# RPC & Jupiter
TS_RPC_URL=<your_rpc_url>
JUPITER_API_KEY=<your_api_key>

# Trading Parameters
TS_BANKROLL_USD=500.0
TS_MAX_CONCURRENT=5
TS_STOP_LOSS_PCT=10.0

# Net Strategy (commented out by default)
# TS_NET_STRATEGY_MODE=true
# TS_MAX_CONCURRENT=15
# TS_NET_TAKE_PROFIT_PCT=500.0
# TS_STOP_LOSS_PCT=25.0
```

### 2. Docker Compose
**File**: `/opt/callsbotonchain/deployment/docker-compose.yml`

Trader service configuration at line ~74

### 3. Trading Logic
**Files**:
- `tradingSystem/cli_optimized.py` - Main trading loop, Net Strategy
- `tradingSystem/config_optimized.py` - Configuration
- `tradingSystem/broker_optimized.py` - Buy/sell execution
- `tradingSystem/trader_optimized.py` - TradeEngine class

---

## Net Strategy Configuration

### To Enable Net Strategy
1. SSH into server
2. Edit docker-compose.yml:
```bash
nano /opt/callsbotonchain/deployment/docker-compose.yml
```

3. Uncomment these lines in `trader` service (around line 95-100):
```yaml
- TS_NET_STRATEGY_MODE=true
- TS_MAX_CONCURRENT=15
- TS_NET_TAKE_PROFIT_PCT=500.0
- TS_STOP_LOSS_PCT=25.0
```

4. Restart trader:
```bash
cd /opt/callsbotonchain/deployment
docker compose restart trader
```

5. Verify:
```bash
docker logs callsbot-trader | grep "NET_STRATEGY_MODE"
```

---

## Monitoring & Debugging

### Check Wallet Balance
```bash
# In container
docker exec callsbot-trader python -c "from tradingSystem.wallet_balance import get_wallet_balance_usd; print(f'Balance: ${get_wallet_balance_usd():.2f}')"

# From logs
docker logs callsbot-trader 2>&1 | grep "Balance:" | tail -1
```

### Check Open Positions
```bash
docker exec callsbot-trader python -c "from tradingSystem.db import init; init(); import sqlite3; conn = sqlite3.connect('/app/var/trading.db'); cur = conn.execute('SELECT id, token_address, entry_price, qty, status FROM positions WHERE status=\"open\"'); print('Open Positions:'); [print(f'#{r[0]}: {r[1][:8]}... entry=${r[2]:.8f} qty={r[3]:.2f}') for r in cur.fetchall()]"
```

### Check Recent Trades
```bash
docker logs callsbot-trader 2>&1 | grep -E "BUY SUCCESS|SELL SUCCESS" | tail -10
```

### Check Errors
```bash
docker logs callsbot-trader 2>&1 | grep -i "error\|critical\|failed" | tail -20
```

### Dashboard
```
URL: http://64.227.157.221/
```

---

## Common Issues & Fixes

### Issue: Insufficient SOL Balance
**Error**: `❌ INSUFFICIENT SOL BALANCE: 0.000000 SOL`

**Fix**: Send SOL to wallet address
```
Wallet: 6Qpu7Muez374WgTvpY56pQ3wWbnefX7wSHZU9z21HJX8
Minimum: 0.1 SOL
Recommended: 0.5 SOL
```

### Issue: Container Won't Start
```bash
# Check logs for error
docker logs callsbot-trader

# Check if port conflicts
docker ps -a

# Rebuild from scratch
cd /opt/callsbotonchain/deployment
docker compose down
docker compose up -d --build
```

### Issue: Trader Not Processing Signals
```bash
# Check Redis connection
docker logs callsbot-trader | grep Redis

# Check worker is running
docker logs callsbot-worker | grep "signal"

# Restart both
docker compose restart worker trader
```

### Issue: Database Locked
```bash
# Stop all containers
docker compose down

# Check for stale lock files
ls -la /opt/callsbotonchain/var/

# Remove lock files if present
rm /opt/callsbotonchain/var/*.db-wal
rm /opt/callsbotonchain/var/*.db-shm

# Restart
docker compose up -d
```

---

## Backup & Restore

### Backup
```bash
# On server
cd /opt/callsbotonchain

# Backup database
cp var/trading.db var/trading.db.backup.$(date +%Y%m%d_%H%M%S)

# Backup .env files
tar -czf backup_$(date +%Y%m%d).tar.gz .env deployment/.env var/

# Download to local
# From local machine:
scp root@64.227.157.221:/opt/callsbotonchain/backup_*.tar.gz ./
```

### Restore
```bash
# On server
cd /opt/callsbotonchain

# Stop containers
docker compose -f deployment/docker-compose.yml down

# Restore database
cp var/trading.db.backup.YYYYMMDD_HHMMSS var/trading.db

# Restore config
tar -xzf backup_YYYYMMDD.tar.gz

# Start containers
docker compose -f deployment/docker-compose.yml up -d
```

---

## Security Checklist

- [ ] Wallet private key in .env only (not in source code)
- [ ] .env files have proper permissions (600)
- [ ] No other wallet keys on server
- [ ] SSH key authentication enabled
- [ ] Firewall configured (UFW)
- [ ] Regular backups of database
- [ ] Monitoring alerts configured

---

## Performance Tuning

### If Hitting Rate Limits
Edit docker-compose.yml trader service:
```yaml
- TS_EXIT_CHECK_INTERVAL=10.0  # Increase from 5.0 to 10.0
- JUP_RPM_LIMIT=30              # Decrease from 35 to 30
```

### If Memory Issues
```bash
# Check memory usage
docker stats

# Restart specific container
docker compose restart trader
```

---

## Git Workflow

### When Making Code Changes

1. **On Local Machine**:
```powershell
cd C:\Users\barat\yesv2\callsbotonchain
git pull origin main  # Get latest
# Make changes
git add <files>
git commit -m "Description"
git push origin main
```

2. **On Server**:
```bash
ssh root@64.227.157.221
cd /opt/callsbotonchain
git pull origin main
cd deployment
docker compose down
docker compose up -d --build
```

3. **Verify**:
```bash
docker logs callsbot-trader --tail 50
```

---

## Important Notes

1. **Always verify wallet** after any config change:
   ```bash
   docker exec callsbot-trader printenv | grep TS_WALLET_SECRET
   ```

2. **Test in dry run mode first** for major changes:
   ```bash
   # In docker-compose.yml
   - TS_DRY_RUN=true
   ```

3. **Monitor logs** after deployment for at least 5 minutes:
   ```bash
   docker logs -f callsbot-trader
   ```

4. **Keep SOL balance** above 0.1 SOL at all times

5. **Backup database** before major changes:
   ```bash
   cp /opt/callsbotonchain/var/trading.db /opt/callsbotonchain/var/trading.db.backup
   ```

---

## Contact & Support

- Repository: https://github.com/spbarathg/callsbotonchain
- Server: root@64.227.157.221
- Wallet: 6Qpu7Muez374WgTvpY56pQ3wWbnefX7wSHZU9z21HJX8

---

## Recent Changes Log

### October 30, 2025 - Net Strategy Implementation
- Fixed critical bug in `cli_optimized.py` (market_sell parameters)
- Implemented Net Strategy (equal-weighted, 5x take profit)
- Validated Jupiter API rate limiting (10 RPS safe)
- Updated wallet to: 6Qpu7Muez374WgTvpY56pQ3wWbnefX7wSHZU9z21HJX8
- All containers rebuilt and verified

---

**Remember**: This is the SINGLE SOURCE OF TRUTH for server configuration. Update this file whenever making infrastructure changes.





