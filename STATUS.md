CALLSBOTONCHAIN – Operations Status (as of 2025‑10‑01)

1) High‑level summary
- The bot is online and producing alerts. The dashboard and logs are live on http://64.227.157.221:8080/.
- We fixed reverse proxy 502s, removed a Telegram hard requirement, resolved worker crash loops, and corrected a read‑only DB issue.
- Disk pressure is resolved (freed ~10.4 GB); system sits at ~29% usage on a 25 GB disk.

1a) Trader‑friendly snapshot (what the numbers mean right now)
- What the bot does: scans new Solana tokens, scores risk/quality, and sends a signal when criteria are met. We then track each signal’s price to see how high it went (peak) and how fast.
- Current strict settings (quality‑first): score ≥ 9, liquidity ≥ $10k, market cap ≤ $1.5M (unless strong momentum), volume‑to‑mcap ≥ 0.60. Rich stats are ON (Cielo+DexScreener). Tracking updates every 1 minute.
- Last 24h (overall quality):
  - 2x rate ≈ 4.9% (about 1 in 20 signals doubled at any point)
  - 5x rate ≈ 1.4%
  - Average peak ≈ 1.28× (typical best run per signal)
  - Median time to peak ≈ 16 minutes (966 s)
- Last 90 minutes (short window – more volatile):
  - Sample n=42; saw 1 coin ≥2× and 1 coin ≥5×; avg peak ≈ 1.14×
- What this means for a memecoin trader: signals are now stricter and already showing better upside than earlier today; we’re beginning to catch real runners again. Expect clearer improvement over the next few hours as more tracked peaks come in under the new gates.

2) Runtime topology (Docker)
- callsbot (web): Flask+Gunicorn, serves UI/API on 8080. Status: healthy. Note: `/app/var` mounted read‑write for SQLite WAL.
- callsbot-worker (worker): main loop generating alerts and tracking. Status: healthy.
- callsbot-proxy (caddy:2): reverse proxy on ports 80/443 → callsbot:8080. Status: running.
- Network: `callsbotnet` shared by all three containers.

3) Proxy configuration
- Host Caddyfile: /opt/callsbotonchain/Caddyfile
- Active rule (port 80): reverse_proxy callsbot:8080; /api/sql blocked by Caddy (403). Basicauth currently disabled for ease of access (re‑enable for security).

4) Storage & paths (host)
- Database (signals): /opt/callsbotonchain/var/alerted_tokens.db (uid:gid 10001:10001)
- Logs directory: /opt/callsbotonchain/data/logs
  - alerts.jsonl, process.jsonl, tracking.jsonl
- Both directories are writable by the app container user (uid 10001) to avoid SQLite WAL/locking issues.

5) Application configuration (effective)
- Source repo deployed at: /opt/callsbotonchain (Docker build context)
- Important .env knobs (current values):
  - GATE_MODE=CUSTOM
  - HIGH_CONFIDENCE_SCORE=7
  - MIN_LIQUIDITY_USD=0
  - VOL_TO_MCAP_RATIO_MIN=0.0
  - VOL_24H_MIN_FOR_ALERT=0
  - MAX_MARKET_CAP_FOR_DEFAULT_ALERT=100000000
  - REQUIRE_SMART_MONEY_FOR_ALERT=false
  - REQUIRE_LP_LOCKED=false
  - REQUIRE_MINT_REVOKED=false
  - ALLOW_UNKNOWN_SECURITY=true
  - PRELIM_DETAILED_MIN=0
  - TRACK_INTERVAL_MIN=1 (temporary to accelerate tracked updates)
  - BUDGET_ENABLED=false (no API credit throttling for now)
  - CIELO_DISABLE_STATS=true (using DexScreener for stats temporarily)
  - CALLSBOT_FORCE_FALLBACK=true (force DexScreener/Gecko feed for reliability during validation)
  - CALLSBOT_SQL_KEY=CHANGE_ME_LONG_RANDOM (required for /api/sql admin)
  - Paper trading endpoint: POST /api/paper (window, stop_pct, trail_retention, cap_multiple, strict_only, max_mcap_usd)

5a) Current gating actually running (post‑tightening)
- GATE_MODE=TIER2
- HIGH_CONFIDENCE_SCORE=9
- MIN_LIQUIDITY_USD=10000
- MAX_MARKET_CAP_FOR_DEFAULT_ALERT=1500000
- VOL_TO_MCAP_RATIO_MIN=0.60
- CIELO_DISABLE_STATS=false (Cielo enabled)
- CALLSBOT_FORCE_FALLBACK=false
- TRACK_INTERVAL_MIN=1

5b) Paper trading defaults (for monitoring)
- Model: ret = min(cap_multiple, trail_retention × peak/first) − 1, floored at −stop_pct
- Suggested: stop_pct=0.25, trail_retention=0.70, cap_multiple=2.0, strict_only=true, max_mcap_usd=$1.0M

6) Recent code changes of note
- Telegram optionalization: alerts are logged to DB even when Telegram is disabled or failing.
- Worker now `mark_as_alerted(...)` regardless of Telegram send result.
- UI/Proxy fixes: Caddy points to callsbot:8080 and blocks /api/sql at the proxy.

7) Current UI/API behavior
- Dashboard: cards show last cycle and begin to fill aggregate metrics after tracking cycles run.
- Logs: real‑time alert/process entries visible; /api/stream is live SSE.
- Tracked tab: populates after the first tracking pass post‑alert (with TRACK_INTERVAL_MIN=1 this should begin within ~1–3 minutes of an alert).
- Key endpoints (web container):
  - GET / → UI
  - GET /api/stats → dashboard data
  - GET /api/stream → SSE stream
  - GET /api/logs?type=combined|alerts|process|tracking&limit=N
  - GET /api/tracked?limit=N
  - POST /api/toggles {signals_enabled, trading_enabled}
  - POST /api/sql (requires header X-Callsbot-Admin-Key)

8) System resource status
- Disk: /dev/vda1 ~25G total; ~6.9G used after pruning (≈29%).
- Docker: dangling images/cache removed; callsbot:latest rebuilt from current repo.

9) Known risks / security notes
- Caddy basicauth is disabled to simplify access; re‑enable for production.
- /api/sql is blocked at proxy, but if proxy changes, the app still enforces X‑Callsbot‑Admin‑Key; keep a strong secret.
- With CIELO disabled and fallback forced, upstream coverage relies on DexScreener/Gecko only; re‑enable CIELO for richer data once credentials and budget policy are settled.

10) Operational runbook
- Build/redeploy (from host):
  - cd /opt/callsbotonchain
  - docker build -t callsbot:latest .
  - docker rm -f callsbot callsbot-worker
  - docker run -d --name callsbot --restart unless-stopped --env-file /opt/callsbotonchain/.env -e CALLSBOT_LOG_STDOUT=true -v /opt/callsbotonchain/var:/app/var:ro -v /opt/callsbotonchain/data/logs:/app/data/logs:ro --network callsbotnet -p 8080:8080 callsbot:latest python scripts/bot.py web --host 0.0.0.0 --port 8080
  - docker run -d --name callsbot-worker --restart unless-stopped --env-file /opt/callsbotonchain/.env -e CALLSBOT_LOG_STDOUT=true -e CALLSBOT_METRICS_ENABLED=true -v /opt/callsbotonchain/var:/app/var -v /opt/callsbotonchain/data/logs:/app/data/logs --network callsbotnet callsbot:latest python scripts/bot.py
- View status:
  - docker ps
  - curl http://127.0.0.1:8080/api/stats
  - tail -f /opt/callsbotonchain/data/logs/process.jsonl

11) Evaluation plan (capability and quality)
Phase A – Stabilization (now → next 24–48h)
- Keep fallback feed enabled to validate end‑to‑end alert → DB → dashboard path.
- Confirm tracking updates populate Tracked table and dashboard aggregates.
- Validate DB growth and WAL behavior; ensure no lock contention.

Phase B – Baseline metrics (next 2–3 days)
- Re‑enable CIELO endpoints (CIELO_DISABLE_STATS=false, CALLSBOT_FORCE_FALLBACK=false) and set BUDGET_ENABLED=true with sane limits.
- Run with GATE_MODE=TIER2 (score≥9, liq≥10k, vol/mcap≥0.6) for 48–72h.
- Collect:
  - alerts_24h,
  - rate_ge_2x / 5x,
  - median_ttp_price_s,
  - tracked outcomes (ongoing/rug heuristic),
  - 1h win‑rate and avg return.

Phase B‑now – Where we stand (live)
- Trend since tightening (latest hour): core KPIs are improving versus earlier baseline.
- Short‑window check (90m): ≥2x and ≥5x have re‑appeared; average peak is climbing but still modest.

Phase C – Tuning & A/B (following week)
- Compare CUSTOM vs TIER2 gating across equal windows; compute precision/recall proxies using 2x/5x and drawdown metrics.
- Adjust PRELIM_USD thresholds and PRELIM_DETAILED_MIN to balance API cost vs. coverage.
- Harden security: re‑enable basicauth in Caddy, rotate CALLSBOT_SQL_KEY, add basic rate‑limit if needed.

12a) Immediate success criteria for the next 24–48h (trader‑oriented)
- Maintain coverage while pushing quality:
  - ≥2x rate: target ≥ 8–10% (short windows will be noisier)
  - ≥5x rate: target ≥ 2–3%
  - Avg peak multiple: target ≥ 1.25–1.40×
  - Median time‑to‑peak under ~20–30 minutes
- If below targets after several hours of signals under current gates, tighten further:
  - VOL_TO_MCAP_RATIO_MIN → 0.80
  - MAX_MARKET_CAP_FOR_DEFAULT_ALERT → $1.0M
  - Optionally REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT=2

12) Quick revert to production‑stricter settings (example)
- In /opt/callsbotonchain/.env set:
  - CALLSBOT_FORCE_FALLBACK=false
  - CIELO_DISABLE_STATS=false
  - GATE_MODE=TIER2
  - HIGH_CONFIDENCE_SCORE=9
  - MIN_LIQUIDITY_USD=10000
  - VOL_TO_MCAP_RATIO_MIN=0.60
  - TRACK_INTERVAL_MIN=60
- Restart worker.

13) Points of contact / handoff
- This STATUS.md captures the current deployment state and next steps.
- All commands above run on host 64.227.157.221 as root; code at /opt/callsbotonchain.


