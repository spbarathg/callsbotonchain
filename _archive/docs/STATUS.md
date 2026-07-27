# Status Summary (auto)

Last update: 2026-01-25 (runtime check at 10:43 UTC)

## Purpose
This file records the key changes made, the current server setup, and expected behavior so we can quickly resume and improve without re-discovery.

## Deployment Target
- Server IP: 188.166.63.71
- OS: Ubuntu 24.04
- Docker Compose: `deployment/docker-compose.yml`
- Services: worker, trader, tracker, atm-ingest, signal-aggregator, redis, web, caddy

## Key Fixes and Changes
### Jupiter API
- Supports the new Jupiter swap API when configured:
  - Base URL: `https://api.jup.ag` (set `JUPITER_BASE_URL`)
  - Quote path: `/swap/v1/quote`
  - Swap path: `/swap/v1/swap`
- Default remains `https://quote-api.jup.ag` unless `JUPITER_BASE_URL` is set.
- Env controls:
  - `JUPITER_BASE_URL`
  - `JUPITER_API_VERSION=swap-v1`
- Removed hardcoded `extra_hosts` that pinned `quote-api.jup.ag`.

### Telegram Alerts (Trades Only)
- Added trade execution alerts for BUY/SELL in `src/tradingSystem/trader_optimized.py`.
- Added `TRADING_TELEGRAM_ALERTS` toggle (default true).
- Added `TELEGRAM_TRADE_ONLY` to suppress non-trade chatter.
- Trade alerts include token, USD size, qty, price, PnL, trade ID, and tx link (if present).

### ATM + Signal Ingest
- Telethon session is authorized and shared:
  - `TELEGRAM_USER_SESSION_FILE=var/atm_ingest.session`
  - `SIGNAL_AGGREGATOR_SESSION_FILE=var/atm_ingest.session`
  - `ATM_TELETHON_SESSION_FILE=var/atm_ingest.session`
- ATM ingest and signal-aggregator both running and monitoring 11 channels.
### Feed Fallbacks
- GeckoTerminal is now the primary fallback feed (works reliably on server IPs).
- DexScreener trending is disabled by default due to 403/WAF blocks:
  - `CALLSBOT_DEXSCREENER_TRENDING_ENABLED=false`
### Token Stats
- Token stats now fall back to GeckoTerminal when DexScreener returns no pairs.

### ATM Relaxed Trade Mode
- Added `ATM_TRADE_MODE=relaxed` option to loosen filters for ATM signals.
- Relaxed floors for ATM:
  - `ATM_RELAXED_MIN_LIQUIDITY_USD`
  - `ATM_RELAXED_MIN_MARKET_CAP_USD`
  - `ATM_RELAXED_MAX_MARKET_CAP_USD`
  - `ATM_RELAXED_MAX_24H_CHANGE_FOR_ALERT`, `ATM_RELAXED_MAX_1H_CHANGE_FOR_ALERT`
  - `ATM_RELAXED_MIN_SCORE`

### Logging
- All containers now log to repo root `data/logs` via compose volume fix:
  - `../data/logs:/app/data/logs`
- Core logs present:
  - `alerts.jsonl`, `tracking.jsonl`, `process.jsonl`
  - `atm_messages.jsonl`, `atm_signals.jsonl`, `errors.jsonl`
  - `trading.jsonl`, `stdout.log`

### Rejection / Winner Tracking
- New `rejections.jsonl` log for rejected signals.
- `atm_listener.py` now logs rejected ATM signals with metadata.
- `signal_aggregator.py` now logs rejected signals with liquidity/volume and reason.
- `track_performance.py` now evaluates rejected signals to find missed winners:
  - Emits `rejection_winner_check` entries in `tracking.jsonl`.
  - Maintains `data/logs/rejection_state.json` to avoid repeats.

### Trade Caps (Live Testing)
- Enforced daily trade caps and cooldowns in `trader_optimized.py`.
- New limits:
  - `TRADING_MAX_TRADES_PER_DAY`
  - `TRADING_MAX_DAILY_USD`
  - `TRADING_MAX_POSITION_PCT`
  - `TRADING_MIN_COOLDOWN_SEC`
  - `TRADING_LIMITS_STATE_FILE` (state persistence)
  - `TRADING_VOLATILITY_TRAIL_ENABLED` (mechanical trailing adjustment)
  - `TRADING_MAX_HOLD_SEC`, `TRADING_FORCE_MAX_HOLD`

## Expected Behavior (Now)
- Bot is running ATM-only ingestion.
- Trade executions trigger Telegram alerts in the configured group.
- Signals rejected for filters (late pump, low liquidity, no Jupiter route) are logged.
- Tracker continuously logs price snapshots and checks rejected signals for winners.

## Current Runtime Check
- Containers: all services up and healthy (worker, trader, tracker, atm-ingest, signal-aggregator, redis, web, caddy).
- Worker: ATM-only mode; sleeping between cycles (expected).
- Trader: running with empty watchlist (no open positions).
- Tracker: actively tracking tokens; rejection-winner checks running without errors.
- Logs: `data/logs` updating with fresh entries; ATM rejections logged with reasons and metadata.

## Known Controls (Env)
- `TRADING_TELEGRAM_ALERTS` (true/false)
- `TELEGRAM_TRADE_ONLY` (true = only BUY/SELL alerts)
- `JUPITER_BASE_URL`, `JUPITER_API_VERSION`
- `ATM_TRADE_MODE` (strict/relaxed)
- `ATM_RELAXED_MIN_LIQUIDITY_USD`, `ATM_RELAXED_MIN_MARKET_CAP_USD`, `ATM_RELAXED_MAX_MARKET_CAP_USD`
- `ATM_RELAXED_MAX_24H_CHANGE_FOR_ALERT`, `ATM_RELAXED_MAX_1H_CHANGE_FOR_ALERT`
- `ATM_RELAXED_MIN_SCORE`
- `TRADING_MAX_TRADES_PER_DAY`, `TRADING_MAX_DAILY_USD`, `TRADING_MAX_POSITION_PCT`, `TRADING_MIN_COOLDOWN_SEC`
- `TRADING_VOLATILITY_TRAIL_ENABLED`, `TRADING_VOLATILITY_WINDOW_SEC`, `TRADING_VOLATILITY_MIN_SAMPLES`
- `TRADING_VOLATILITY_BASE_TRAIL_PCT`, `TRADING_VOLATILITY_MULTIPLIER`, `TRADING_VOLATILITY_MAX_TRAIL_PCT`
- `TRADING_MAX_HOLD_SEC`, `TRADING_FORCE_MAX_HOLD`
- `REJECTION_WINNER_MIN_AGE_MINUTES` (default 30)
- `REJECTION_WINNER_MAX_AGE_HOURS` (default 24)
- `REJECTION_WINNER_MULTIPLIER` (default 2.0)
- `REJECTION_WINNER_MAX_PER_CYCLE` (default 30)

## Notes
- If trades don’t appear in Telegram, verify bot is in the correct supergroup and has permission to post.
- If Jupiter quotes fail, ensure `JUPITER_BASE_URL=https://api.jup.ag` and `JUPITER_API_VERSION=swap-v1`.
