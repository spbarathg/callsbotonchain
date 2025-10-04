CALLSBOTONCHAIN – Ops Snapshot (2025‑10‑04)

### What changed today
- **Major Cleanup**: Removed 30+ temporary docs/scripts; reclaimed 15GB disk space (96% → 38% usage).
- **Dashboard Enhancements**: Full tabbed interface (Overview, Performance, System, Config, Paper Trade, Logs, Tracked) with real-time data, interactive toggles, and paper trading engine.
- **Trading System**: Optimized for $500 bankroll with 4 strategies (runner/scout/strict/nuanced), strategy-specific stops, real-time validation, pump/bonk token filter.
- **Budget Optimization**: Increased daily budget to 10,000 calls, zero-cost feed calls, MIN_USD_VALUE=200, tracking reduced to 15min intervals.
- **Smart Money Detection**: Fixed logical flaw; now correctly detects smart money via feed cycle trust; dynamic USD filter for smart trades.

### Current health
- **Containers**: All healthy (Worker: 2h, Web: 2h, Trader: 8h dry-run, Proxy: 11h)
- **Signals**: 220 total alerts, 217 actively tracked, 500 alerts in 24h window
- **Performance**: Avg score 6.6/10, 63% Smart Money signals, 27% error rate (expected/good)
- **Feed**: Alternating general ↔ smart cycles correctly, 57-72 items/cycle, processing efficiently
- **Budget**: 1,293/10,000 daily (12.9%), 6/15 per-minute, zero-miss mode active
- **Resources**: Disk 38% (9.1GB/25GB), Memory 50% (477MB/957MB)

### One‑liners (copy/paste)
- Deploy all services:
  - `cd /opt/callsbotonchain && git pull && docker compose up -d --build`
- Quick health:
  - `curl -fsS http://127.0.0.1/api/v2/quick-stats | jq`
  - `curl -fsS http://127.0.0.1/api/v2/budget-status | jq`
  - `curl -fsS http://127.0.0.1/api/v2/feed-health | jq`
  - `curl -fsS 'http://127.0.0.1/api/tracked?limit=5' | jq '.rows | length'`
- Logs (last lines):
  - `docker logs callsbot-worker --tail 20 2>&1 | grep -E 'heartbeat|alert|error'`
  - `tail -n 20 /opt/callsbotonchain/data/logs/alerts.jsonl`
- Database stats:
  - `sqlite3 /opt/callsbotonchain/var/alerted_tokens.db 'SELECT COUNT(*) FROM alerted_tokens; SELECT conviction_type, COUNT(*) FROM alerted_tokens GROUP BY conviction_type;'`
- Free disk fast:
  - `docker system prune -af && docker image prune -af && df -h`

### Known issues / investigation
- ✅ **RESOLVED**: Feed parsing, smart money detection, database writes all working correctly
- ✅ **RESOLVED**: Storage issues cleared (15GB freed)
- ✅ **RESOLVED**: Dashboard now fully functional with all tabs and interactive controls
- ⚠️ **Normal**: 27% error rate (400/530 status codes) - these are junk tokens being correctly filtered
- ⚠️ **Normal**: Some liquidity values show `NaN` for new/low-cap tokens - fallback to DexScreener active

### Immediate next steps
1) ✅ **Monitor signal quality**: Currently at 6.6/10 avg, 63% smart money - excellent performance
2) ✅ **Budget tracking**: Zero-miss mode active, 87% daily budget remaining
3) 🎯 **Ready for live trading**: Set `trading_enabled=true` in toggles.json or via dashboard when ready
4) 📊 **Paper trading**: Use dashboard Paper Trade tab to test strategies with hypothetical capital


### What's live now
- **Dashboard**: Full-featured web UI at `http://64.227.157.221/` with 7 tabs (Overview, Performance, System, Config, Paper Trade, Logs, Tracked)
- **Signals**: Online, generating 6.6/10 avg quality, 63% Smart Money detection, 500 alerts/24h
- **API**: All v2 endpoints active (`/api/v2/quick-stats`, `/api/v2/budget-status`, `/api/v2/feed-health`, etc.)
- **Proxy/Infra**: Caddy on port 80 → web:8080; WAL-enabled SQLite; disk 38% used (15GB available)
- **Trading**: Jupiter v6 broker integrated, 4 strategies (runner/scout/strict/nuanced), pump/bonk filter active, dry-run mode (ready for live)
- **Tracking**: 217 tokens actively monitored, 15-min intervals, real-time price updates

### Key runtime (essentials)
- **Gates**: `HIGH_CONFIDENCE_SCORE=5`, `MIN_LIQUIDITY_USD=5000`, `VOL_TO_MCAP_RATIO_MIN=0.15`, `MAX_MARKET_CAP_FOR_DEFAULT_ALERT=1_000_000`, `PRELIM_DETAILED_MIN=2`, `MIN_USD_VALUE=200`
- **Budget**: `BUDGET_ENABLED=true`, `BUDGET_PER_MINUTE_MAX=15`, `BUDGET_PER_DAY_MAX=10000`, `BUDGET_FEED_COST=0` (zero-miss mode)
- **Tracking**: `TRACK_INTERVAL_MIN=15`, `TRACK_BATCH_SIZE=30`
- **Trading**: `TS_MAX_CONCURRENT=5`, `TS_BANKROLL_USD=500`, `CORE_SIZE_USD=70`, `SCOUT_SIZE_USD=40`, `STRICT_SIZE_USD=50`, `NUANCED_SIZE_USD=25`
- **Stops**: `CORE_STOP_PCT=15`, `SCOUT_STOP_PCT=10`, `STRICT_STOP_PCT=12`, `NUANCED_STOP_PCT=8`
- **Filters**: Only trades tokens ending in "pump" or "bonk"

### Paper trading (via dashboard)
- **UI Controls**: Available in Paper Trade tab - set capital, strategy, sizing, max concurrent
- **Live Testing**: Start/stop/reset paper sessions, view portfolio performance in real-time
- **Backtesting**: Test strategies against historical alerts (7/14/30 day windows)
- **API Endpoints**: 
  - `POST /api/v2/paper/start` - Start paper session
  - `GET /api/v2/paper/portfolio` - Get current portfolio
  - `POST /api/v2/paper/backtest` - Run historical backtest

### Trading plan (asymmetric growth - $500 bankroll)
- **Strategy Routing**:
  - **Runner** (Smart Money): $70 position, 15% stop, highest conviction
  - **Scout** (High Velocity): $40 position, 10% stop, momentum plays
  - **Strict** (High Confidence): $50 position, 12% stop, no smart money
  - **Nuanced** (Lower Confidence): $25 position, 8% stop, exceptional stats only
- **Risk Management**: Max 5 concurrent positions, pump/bonk tokens only, 30% dump rejection filter
- **Profit-taking**: Dynamic trailing stops (16-25% giveback), strategy-specific exits
- **Entry Validation**: Real-time stats fetch, token hasn't dumped >30% since alert

### Next steps (optional enhancements)
- ✅ **Real-time stats**: Trading CLI now fetches live stats from `/api/tracked` and `alerts.jsonl`
- ✅ **Entry validation**: Token dump check (>30%) before opening positions
- 🎯 **Test paper trading**: Run 24-48h paper session to validate strategies before live trading
- 📊 **Monitor performance**: Track win rate, avg multiple, best performers via dashboard
- 💰 **Go live**: Enable trading toggle when ready (`trading_enabled=true` via dashboard)

### Quick ops
- **Deploy changes**: `cd /opt/callsbotonchain && git pull && docker compose up -d --build`
- **Restart worker only**: `docker restart callsbot-worker`
- **Restart web only**: `docker restart callsbot-web`
- **View logs**: 
  - Worker: `docker logs callsbot-worker --tail 50 -f`
  - Web: `docker logs callsbot-web --tail 50 -f`
  - Trader: `docker logs callsbot-trader --tail 50 -f`
- **Check environment**: `docker exec callsbot-worker env | grep -E '^(HIGH_CONFIDENCE_SCORE|MIN_LIQUIDITY|BUDGET_PER_DAY)'`

### Operator cheat sheet (fresh AI/tab)
- **Where**:
  - Server: `64.227.157.221` (SSH root)
  - Root dir: `/opt/callsbotonchain`
  - Containers: `callsbot-worker`, `callsbot-web`, `callsbot-trader`, `callsbot-proxy`
  - Dashboard: `http://64.227.157.221/`

- **Quick health check**:
  ```bash
  # All in one
  docker ps && echo "" && \
  curl -fsS http://127.0.0.1/api/v2/quick-stats | jq && \
  curl -fsS http://127.0.0.1/api/v2/budget-status | jq && \
  docker logs callsbot-worker --tail 5 2>&1 | grep heartbeat
  ```

- **Database inspection**:
  ```bash
  sqlite3 /opt/callsbotonchain/var/alerted_tokens.db \
    'SELECT COUNT(*) as total FROM alerted_tokens; \
     SELECT conviction_type, COUNT(*) as count FROM alerted_tokens \
     GROUP BY conviction_type ORDER BY count DESC;'
  ```

- **Enable/disable features**:
  - Via dashboard: Config tab → Toggle switches
  - Via file: `vi /opt/callsbotonchain/var/toggles.json`
  - Then restart: `docker restart callsbot-worker callsbot-trader`

- **Hourly checks (automated via dashboard)**:
  - ✅ Feed alternating (general ↔ smart)
  - ✅ Budget usage trending correctly
  - ✅ New alerts appearing (check latest 3)
  - ✅ Tracking updates (peak_multiple changes)
  - ✅ Disk < 80%, Memory < 80%

- **Daily KPIs (Performance tab)**:
  - Signal quality: avg score ≥ 6.0
  - Smart money: ≥ 50% of signals
  - Budget efficiency: ≤ 70% daily usage
  - Best performers: track ≥5× tokens
  - Win rate: monitor via tracked outcomes