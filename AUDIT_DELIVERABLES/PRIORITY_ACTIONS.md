# 🎯 PRIORITY REMEDIATION PLAN

## VERIFIED ROOT CAUSES

1. **Docker Cache Bug** - Container running OLD code (before 99% fix)
2. **Price Feed Failure** - Silent exits when price=0, no fallback/retry
3. **No Rug Detection** - Bot retries dead tokens 14+ times
4. **State Desync** - live dict ≠ database during restarts
5. **Stop Loss Never Triggers** - Due to #2 above

---

## IMMEDIATE ACTIONS (NEXT 30 MINUTES)

### ⚠️ **ACTION 1: STOP BLEEDING** (Difficulty: 1/10, Impact: HIGH)
```bash
# Stop bot NOW
ssh root@64.227.157.221 "docker stop callsbot-trader"

# Close ghost positions
ssh root@64.227.157.221 "cd /opt/callsbotonchain/deployment && sqlite3 var/trading.db \"UPDATE positions SET status='closed' WHERE status='open'\""

# Verify
ssh root@64.227.157.221 "cd /opt/callsbotonchain/deployment && sqlite3 var/trading.db 'SELECT COUNT(*) FROM positions WHERE status=\"open\"'"
# Expected: 0
```

**Why:** Current bot is losing -83% per trade vs expected -15% max.

---

### 🔧 **ACTION 2: REBUILD WITH ACTUAL FIXES** (Difficulty: 3/10, Impact: HIGH)
```bash
# Force rebuild (NO CACHE)
ssh root@64.227.157.221 "
cd /opt/callsbotonchain && \
git pull origin main && \
docker build --no-cache --pull -t callsbot:$(git rev-parse --short HEAD) -f deployment/Dockerfile . && \
docker stop callsbot-trader 2>/dev/null || true && \
docker rm callsbot-trader 2>/dev/null || true && \
docker run -d \
  --name callsbot-trader \
  --restart unless-stopped \
  --env-file deployment/.env \
  -v /opt/callsbotonchain/deployment/var:/opt/callsbotonchain/var \
  callsbot:$(git rev-parse --short HEAD)
"

# VERIFY fix is active (critical!)
ssh root@64.227.157.221 "docker exec callsbot-trader grep -n 'in_amount = int(float(qty) \* (10 \*\* dec) \* 0.99)' /opt/callsbotonchain/tradingSystem/broker_optimized.py"
# Expected: Line 576 with 0.99 multiplier

# Check logs
ssh root@64.227.157.221 "docker logs --tail 50 callsbot-trader"
```

**Validation:**
- If grep returns line 576 → ✅ Fix active
- If grep returns nothing → ❌ Still using old code, rebuild again

---

### 🩹 **ACTION 3: APPLY EMERGENCY PATCHES** (Difficulty: 5/10, Impact: HIGH)

Apply patches from `EMERGENCY_PATCHES/`:

```bash
# On local machine
cd /path/to/callsbotonchain

# Apply patches
git apply EMERGENCY_PATCHES/01_price_fallback.diff
git apply EMERGENCY_PATCHES/02_rug_detection.diff
git apply EMERGENCY_PATCHES/03_hard_stop_loss.diff

# Test locally
python -m pytest tests/test_trading_system_integration.py -v

# Commit
git add -A
git commit -m "Emergency fixes: price fallback, rug detection, hard stop loss"
git push origin main

# Deploy (repeat ACTION 2 rebuild)
```

**What These Fix:**
1. **01_price_fallback.diff**: Force exit after 5 consecutive price failures
2. **02_rug_detection.diff**: Immediately abort on "COULD_NOT_FIND_ANY_ROUTE"
3. **03_hard_stop_loss.diff**: -40% hard stop if normal -15% stop fails

---

## URGENT FIXES (NEXT 2 HOURS)

### 🔍 **ACTION 4: ADD WALLET VALIDATION** (Difficulty: 6/10, Impact: MEDIUM)

**Problem:** Bot creates positions even if buy transaction failed.

**Fix Location:** `tradingSystem/trader_optimized.py:205-214`

```python
# After line 210: if not fill.success: return None
# ADD THIS:

# CRITICAL: Verify tokens actually in wallet
print(f"[TRADER] Verifying wallet balance for {token[:8]}...", flush=True)
time.sleep(5)  # Wait for blockchain confirmation

# Query actual balance
from solana.rpc.api import Client
from solders.pubkey import Pubkey
client = Client(RPC_URL)

try:
    accounts = client.get_token_accounts_by_owner(
        self.broker._kp.pubkey(),
        {'mint': Pubkey.from_string(token)}
    )
    
    if accounts.value:
        actual_balance = float(accounts.value[0].account.data.parsed['parsed']['info']['tokenAmount']['uiAmount'])
        expected = fill.qty
        
        if actual_balance < expected * 0.95:  # Allow 5% slippage
            self._log("buy_validation_failed", 
                     token=token, 
                     expected=expected, 
                     actual=actual_balance,
                     discrepancy_pct=((expected - actual_balance) / expected * 100))
            print(f"[TRADER] ❌ Balance mismatch: expected {expected}, got {actual_balance}", flush=True)
            return None  # Don't create position!
    else:
        self._log("buy_validation_no_account", token=token)
        print(f"[TRADER] ❌ No token account found after buy!", flush=True)
        return None
        
except Exception as e:
    self._log("buy_validation_error", token=token, error=str(e))
    # Proceed but log warning
    print(f"[TRADER] ⚠️ Could not verify balance: {e}", flush=True)

# NOW create position (line 213)
```

**Test:**
```python
# tests/test_wallet_validation.py
def test_buy_creates_no_position_if_tokens_missing(mock_broker):
    """Verify bot doesn't create ghost positions"""
    mock_broker.market_buy.return_value = Fill(success=True, qty=1000)
    mock_wallet_has_zero_tokens()
    
    engine = TradeEngine()
    pid = engine.open_position("TOKEN", {"usd_size": 10, "trail_pct": 10})
    
    assert pid is None  # Should NOT create position
    assert len(engine.live) == 0
```

---

### 📊 **ACTION 5: FIX STATE RECOVERY** (Difficulty: 7/10, Impact: MEDIUM)

**Problem:** `_recover_positions()` loads with old code after restart.

**Fix:** Add version check and validation:

```python
# tradingSystem/trader_optimized.py:132

def _recover_positions(self):
    """Recover open positions with validation"""
    try:
        import sqlite3
        con = sqlite3.connect(DB_PATH)
        
        # Check code version matches
        expected_version = "v2.1.0"  # Update with each deploy
        try:
            with open("/opt/callsbotonchain/VERSION", "r") as f:
                running_version = f.read().strip()
            if running_version != expected_version:
                self._log("recovery_version_mismatch", 
                         expected=expected_version, 
                         running=running_version)
                print(f"[TRADER] ⚠️ Version mismatch: expected {expected_version}, running {running_version}", flush=True)
        except Exception:
            pass
        
        cur = con.execute("""
            SELECT id, token_address, strategy, entry_price, peak_price, open_at
            FROM positions 
            WHERE status='open'
        """)
        
        recovered = 0
        for pid, ca, strategy, entry_price, peak_price, open_at in cur.fetchall():
            # Validate position age (don't recover very old positions)
            from datetime import datetime
            if open_at:
                age_hours = (time.time() - open_at) / 3600
                if age_hours > 24:
                    self._log("recovery_skipped_old", token=ca, age_hours=age_hours)
                    continue
            
            self.live[str(ca)] = {
                "pid": int(pid),
                "strategy": str(strategy),
                "entry_price": float(entry_price or 0),
                "peak_price": float(peak_price or entry_price or 0),
                "price_failures": 0,  # Reset counters
                "sell_failures": 0,
                "open_at": open_at or time.time(),
            }
            recovered += 1
            
        con.close()
        if recovered > 0:
            self._log("recovery_loaded", count=recovered, positions=list(self.live.keys()))
            print(f"[TRADER] ✅ Recovered {recovered} positions", flush=True)
    except Exception as e:
        self._log("recovery_failed", error=str(e))
```

**Add VERSION file to Docker:**
```dockerfile
# deployment/Dockerfile
RUN echo "v2.1.0-$(date +%s)" > /opt/callsbotonchain/VERSION
```

---

## MEDIUM PRIORITY (NEXT WEEK)

### **ACTION 6: ADD MONITORING & ALERTS** (Difficulty: 4/10, Impact: MEDIUM)

Create `tradingSystem/monitoring.py`:

```python
import prometheus_client as prom

# Metrics
price_fetch_failures = prom.Counter('price_fetch_failures_total', 'Price fetch failures')
emergency_exits = prom.Counter('emergency_exits_total', 'Emergency exits triggered')
stop_loss_failures = prom.Counter('stop_loss_failures_total', 'Stop losses that failed to trigger')
avg_loss_pct = prom.Gauge('avg_loss_pct', 'Average loss percentage on closed positions')

# Alert if:
# - price_fetch_failures > 10/min
# - emergency_exits > 0
# - avg_loss_pct < -30%
```

---

### **ACTION 7: REFACTOR DUPLICATE CODE** (Difficulty: 6/10, Impact: LOW)

**Files to Merge:**
- `scripts/bot.py` (old) → Delete, use `tradingSystem/cli_optimized.py`
- `src/api_system.py` vs `src/api_enhanced.py` → Merge into one
- `app/http_client.py` redundant with `requests` → Simplify

**Safe Removal Script:**
```bash
git mv scripts/bot.py archive/deprecated/bot.py.bak
git mv src/api_system.py archive/deprecated/
git commit -m "Archive deprecated files"
```

---

### **ACTION 8: ADD COMPREHENSIVE TESTS** (Difficulty: 8/10, Impact: MEDIUM)

**Missing Critical Tests:**
```python
# tests/test_stop_loss_triggers.py
def test_stop_loss_triggers_at_minus_15_percent()
def test_emergency_stop_triggers_at_minus_40_percent()
def test_stop_loss_with_failed_price_feeds()

# tests/test_rug_detection.py
def test_rug_detected_immediately_no_retries()
def test_no_route_error_closes_position()

# tests/test_docker_deployment.py
def test_docker_image_contains_latest_code()
def test_docker_version_matches_git_commit()
```

**Run Tests:**
```bash
pytest tests/ -v --cov=tradingSystem --cov-report=html
```

---

## LOW PRIORITY (BACKLOG)

### **ACTION 9: PERFORMANCE OPTIMIZATION** (Difficulty: 5/10, Impact: LOW)
- Cache DexScreener responses (5s TTL)
- Batch price fetches for multiple positions
- Async price monitoring

### **ACTION 10: CODE CLEANUP** (Difficulty: 3/10, Impact: LOW)
- Remove commented code
- Fix linter warnings
- Standardize naming conventions

---

## VALIDATION CHECKLIST

After each action, verify:

```bash
# ✅ Docker running latest code
docker exec callsbot-trader cat /opt/callsbotonchain/VERSION
docker exec callsbot-trader python3 -c "from tradingSystem.broker_optimized import Broker; import inspect; print('0.99' in inspect.getsource(Broker.market_sell))"

# ✅ No open positions
ssh root@64.227.157.221 "cd /opt/callsbotonchain/deployment && sqlite3 var/trading.db 'SELECT COUNT(*) FROM positions WHERE status=\"open\"'"

# ✅ Price cache working
docker logs --tail 100 callsbot-trader | grep "valid_entries"
# Should show valid_entries > 0

# ✅ No catastrophic losses
docker logs --tail 100 callsbot-trader | grep "exit_"
# Check loss percentages are < 20%
```

---

## ESTIMATED TIMELINE

| Phase | Actions | Time | Cumulative |
|-------|---------|------|------------|
| **Emergency** | 1-3 | 30 min | 30 min |
| **Urgent** | 4-5 | 2 hours | 2.5 hours |
| **Medium** | 6-8 | 1 week | 1 week |
| **Low** | 9-10 | 2 weeks | 3 weeks |

**CRITICAL:** Complete Actions 1-3 **TODAY** to stop losses.

---

## SUCCESS METRICS

After fixes deployed:

| Metric | Before | Target | Measurement |
|--------|--------|--------|-------------|
| Avg Loss % | -83% | -15% | DB query on closed positions |
| Price Cache Hit Rate | 0% | >80% | Logs |
| Stop Loss Trigger Rate | 0% | ~80% of losses | Logs |
| Rug Detection Speed | 14+ retries | 1 attempt | Logs |
| Docker-Git Sync | Desync | Always synced | Version check |

---

## ROLLBACK PLAN

If issues after deployment:

```bash
# Emergency rollback
ssh root@64.227.157.221 "
docker stop callsbot-trader && \
docker run -d --name callsbot-trader-rollback \
  --env-file deployment/.env \
  -v /opt/callsbotonchain/deployment/var:/opt/callsbotonchain/var \
  callsbot:LAST_KNOWN_GOOD_HASH
"
```

Keep last 3 Docker images for quick rollback:
```bash
docker images | grep callsbot | head -3
```

