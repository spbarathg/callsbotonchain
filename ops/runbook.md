# CallsBotOnChain – Ops Runbook

## Secrets Rotation
- All secrets must be sourced from a secret manager. Env files on disk must not contain long-lived secrets.
- Rotate monthly or on incident.
- Required secrets:
  - `CIELO_API_KEY`
  - `CALLSBOT_SQL_KEY`
  - `CALLSBOT_HMAC_KEY`

## Kill Switch
- Set `KILL_SWITCH=true` and restart worker to disable all processing and alerts.
- Dashboard will show Kill Switch status in the status bar.

## Dry-run / Paper Mode
- Set `DRY_RUN=true` to disable Telegram/external alert sending while keeping logs and metrics.

## API Quota Exhaustion
- System auto-backs off on 429 and can switch to DexScreener.
- Consider setting `CIELO_DISABLE_STATS=true` temporarily.

## DB Recovery
- DB lives at `var/alerted_tokens.db` by default.
- Use `tools/export_stats.py` to dump CSVs before surgery.
- For corruption: stop worker, copy DB, run `sqlite3 .dump | .read` into a new file.

## Prometheus & Alerts
- Metrics bind to `127.0.0.1` by default.
- Load alert rules from `ops/alert_rules.yml`.


