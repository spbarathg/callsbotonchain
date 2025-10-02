Incident Playbook

API Outage
- Observe alert ApiErrorRateHigh in Prometheus.
- Enable DRY_RUN or set CIELO_DISABLE_STATS=true to conserve credits.
- Verify fallback path (DexScreener) continues.

DB Corruption
- Stop worker (KILL_SWITCH=true).
- Copy DB from var/ and attempt .dump recovery.
- Restore from last good backup if necessary.

False-Positive Surge
- Set GATE_MODE to TIER1 temporarily.
- Increase MIN_LIQUIDITY_USD and VOL_TO_MCAP_RATIO_MIN via env.
- Investigate scoring logs.

Compromised Key
- Rotate keys in secret manager immediately.
- Update deployment with new secrets.
- Review admin_audit.jsonl and admin_actions table for misuse.
