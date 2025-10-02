CALLSBOTONCHAIN – Ops Snapshot (2025‑10‑02)

### What’s live now
- **Signals:** Online, tuned, and tracked on `http://64.227.157.221/` (UI, `/api/stats`, `/api/stream`, `/api/tracked`).
- **Proxy/Infra:** Caddy on port 80 → web:8080; WAL-enabled SQLite; disk ~29% used.
- **Trading:** Real Jupiter v6 broker integrated (sign/send), exit loop with hard stops + dynamic trailing, DB fills/positions. Runs without subscriptions (public RPC + optional priority fee tip). `TS_DRY_RUN` defaults on; set `TS_DRY_RUN=false` to trade.

### Key runtime (essentials)
- **Gates:** `GATE_MODE=CUSTOM`, `HIGH_CONFIDENCE_SCORE=8` (test window), `MIN_LIQUIDITY_USD=10000`, `VOL_TO_MCAP_RATIO_MIN=0.80`, `MAX_MARKET_CAP_FOR_DEFAULT_ALERT=1_000_000`, `PRELIM_DETAILED_MIN=6`, `REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT=1`, `TRACK_INTERVAL_MIN=1`.
- **Budget:** `BUDGET_ENABLED=true`, `BUDGET_PER_MINUTE_MAX=15`, `BUDGET_PER_DAY_MAX=4300`.
- **Trading envs:** `TS_RPC_URL`, `TS_WALLET_SECRET`, `TS_SLIPPAGE_BPS` (150), `TS_PRIORITY_FEE_MICROLAMPORTS` (8000), `TS_JITO_TIP_SOL` (0.0006), `TS_MAX_CONCURRENT`.

### Paper expectancy
- Endpoint: `POST /api/paper` (window, stop_pct, trail_retention, cap_multiple, strict_only, max_mcap_usd)
- Suggested: `stop_pct=0.25`, `trail_retention=0.70`, `cap_multiple=2.0`, `strict_only=true`, `max_mcap_usd=$1.0M`.

### Trading plan (asymmetric growth)
- **Regime-aware:** Bull = higher size/frequency; Defense = smaller, stricter gates.
- **Profit-taking:** First ladder around **2.0×–2.5×** (sell 60–75% to withdraw initial + profit). Second ladder **3.5×–4.0×**. Trail remainder **18–25%** giveback.
- **Risk/limits:** Enforce `TS_MAX_CONCURRENT`, per-trade risk ≈ **3% (Defense)** / **10% (Bull)**. Treasury lock at equity checkpoints to avoid reset-to-zero.

### Next steps (short and focused)
- Add regime detection from `/api/stats` to auto-dial sizing/slippage/gates.
- Use real per-token stats for entries (replace placeholders) from signals DB.
- Add treasury accounting and dashboard tiles (risk capital vs treasury, streaks).
- Add loss-streak cool-down and daily trade caps (Defense mode).

### Quick ops
- HCS=8 test window
  - Applied at: live (see process.jsonl around ts of this STATUS update)
  - Purpose: increase throughput under CUSTOM while preserving quality bars
  - Verify: `docker exec callsbot-worker env | grep ^HIGH_CONFIDENCE_SCORE=` should show 8
  - Revert plan: set `HIGH_CONFIDENCE_SCORE=9` and restart worker if precision drops or alerts spike low‑quality
- Deploy: `docker compose down && docker compose up -d --build`
- Check: `curl http://127.0.0.1/api/stats` and UI. Logs under `data/logs/`.

### Operator cheat sheet (fresh AI/tab)
- Where:
  - Server: 64.227.157.221 (SSH root)
  - Root dir: `/opt/callsbotonchain`
  - Containers: `callsbot-worker`, `callsbot-web`, `callsbot-proxy`
  - Dashboard: `http://64.227.157.221/`

- Health (simple, non-blocking):
  - `docker ps`
  - `curl -fsS http://127.0.0.1/api/stats | head -c 800`
  - `curl -fsS 'http://127.0.0.1/api/tracked?limit=5' | head -c 800`
  - `tail -n 50 /opt/callsbotonchain/data/logs/process.jsonl`

- Restart only worker (fallback if compose misbehaves):
  - `docker rm -f callsbot-worker >/dev/null 2>&1 || true`
  - `docker run -d --name callsbot-worker --restart unless-stopped \
     --env-file /opt/callsbotonchain/.env -e CALLSBOT_LOG_STDOUT=true \
     -e CALLSBOT_METRICS_ENABLED=true -v /opt/callsbotonchain/var:/app/var \
     -v /opt/callsbotonchain/data/logs:/app/data/logs \
     callsbotonchain-worker:latest python scripts/bot.py run`

- Budget/tuning edits (credit-safe):
  - `sed -i -E 's/^BUDGET_PER_DAY_MAX=.*/BUDGET_PER_DAY_MAX=4300/' .env`
  - `sed -i -E 's/^BUDGET_PER_MINUTE_MAX=.*/BUDGET_PER_MINUTE_MAX=15/' .env`
  - `sed -i -E 's/^VOL_TO_MCAP_RATIO_MIN=.*/VOL_TO_MCAP_RATIO_MIN=0.80/' .env`
  - `sed -i -E 's/^MAX_MARKET_CAP_FOR_DEFAULT_ALERT=.*/MAX_MARKET_CAP_FOR_DEFAULT_ALERT=1000000/' .env`
  - `sed -i -E 's/^PRELIM_DETAILED_MIN=.*/PRELIM_DETAILED_MIN=6/' .env`
  - `sed -i -E 's/^REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT=.*/REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT=1/' .env`
  - Restart worker; verify runtime env with:
    - `docker exec callsbot-worker env | egrep '^(BUDGET_ENABLED|BUDGET_PER_DAY_MAX|BUDGET_PER_MINUTE_MAX|VOL_TO_MCAP_RATIO_MIN|MAX_MARKET_CAP_FOR_DEFAULT_ALERT|PRELIM_DETAILED_MIN|REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT)='`

- Hourly checks:
  - `curl -fsS http://127.0.0.1/api/stats | head -c 800` (heartbeat <5m, totals rise)
  - `grep '"type": "alert_sent"' /opt/callsbotonchain/data/logs/process.jsonl | tail -n 5`
  - `curl -fsS 'http://127.0.0.1/api/tracked?limit=5' | head -c 800` (peak_multiple > 1.0)
  - `docker ps` and `df -h` (<80%)

- Daily checks:
  - Ensure daily calls ≤ `BUDGET_PER_DAY_MAX`; `api_calls_saved` trending up
  - KPIs: ≥2×, ≥5×, avg_peak, median_ttp, alerts_24h
  - Confirm latest exports/backups if scheduled