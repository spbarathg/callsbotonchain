CallsBotOnChain – 1‑Hour Ops Checklist (Cursor‑friendly)

This checklist runs a focused health pass across containers, proxy, pipeline (alert → DB → dashboard), tracking, and storage.

Prereqs
- SSH: root@64.227.157.221
- Paths: /opt/callsbotonchain
- Admin key for /api/sql: X-Callsbot-Admin-Key: CHANGE_ME_LONG_RANDOM

Quick Reference
- Web UI: http://64.227.157.221:8080/
- Local API base (from host): http://127.0.0.1:8080

---

0) Preflight (5–7 min)
Run:
```bash
ssh root@64.227.157.221 "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'; echo '---'; curl -fsS http://127.0.0.1:8080/api/stats | jq '{last_heartbeat: .last_heartbeat.ts, recent: (.recent_alerts|length), total: .signals_summary.total_alerts}'; echo '--- logs tail'; tail -n 40 /opt/callsbotonchain/data/logs/process.jsonl | tail -n 40; echo '--- disk'; df -hT /; docker system df"
```
Expect:
- callsbot, callsbot-worker healthy; recent>0; last_heartbeat ~now.
If not:
- 502s: check Caddyfile → reverse_proxy callsbot:8080 and network `callsbotnet`.
- Worker restarting: `docker logs callsbot-worker` for env/schema errors.

1) Alert → DB → Dashboard path (10–12 min)
Run (host):
```bash
curl -fsS http://127.0.0.1:8080/api/stats | jq '.last_alert, (.recent_alerts|length)'
```
- last_alert should be non‑null; recent_alerts ≥ 1.

DB spot‑check (signals DB):
```bash
curl -fsS -H 'X-Callsbot-Admin-Key: CHANGE_ME_LONG_RANDOM' \
     -H 'Content-Type: application/json' \
     -d '{"target":"signals","query":"SELECT COUNT(1) AS alerted FROM alerted_tokens"}' \
     http://127.0.0.1:8080/api/sql | jq .
```
Expect `alerted` increasing during session.

2) Tracking updates (8–10 min)
- Tracking runs every TRACK_INTERVAL_MIN (currently 1). Wait 1–3 minutes after new alerts.
Run:
```bash
curl -fsS http://127.0.0.1:8080/api/tracked?limit=50 | jq '.rows | length'
```
Expect count ≥ 1 once tracking pass completes.
If 0:
- Check worker logs for tracking errors.
- Confirm DB writable (no “readonly database” messages) and perms of /opt/callsbotonchain/var.

3) Proxy/public check (2–3 min)
```bash
curl -fsS -o /dev/null -w '%{http_code}\n' http://64.227.157.221:80/
```
Expect 200.
If 502:
- Reload caddy; ensure upstream `callsbot:8080` and container is on `callsbotnet`.

4) Storage & logs (5–7 min)
```bash
ssh root@64.227.157.221 "du -xhd1 /opt/callsbotonchain/data/logs; du -xh /opt/callsbotonchain/var/alerted_tokens.db; docker system df"
```
Guidelines:
- data/logs ≤ 1–2 GB; DB file size reasonable for retention.
- If large, rotate/truncate logs, export DB if needed.

5) Quick remediation playbook (time‑boxed)
- 502 proxy → fix Caddy upstream + network + reload.
- Worker crash → verify .env gates, HIGH_CONFIDENCE_SCORE ∈ [1,10], and DB perms.
- No tracked rows → wait interval or lower TRACK_INTERVAL_MIN and confirm DB writes.
- Disk high → `docker system prune -a --volumes --force` (confirm impact first).

6) Exit report (5 min)
Capture:
- Container health, last heartbeat time.
- Alerts in last 15–30 min, tracked count.
- Disk/log footprint.
- Any deviations + fixes applied.

---

Appendix – Redeploy commands (from host)
```bash
cd /opt/callsbotonchain && docker build -t callsbot:latest . && \
  docker rm -f callsbot callsbot-worker && \
  docker run -d --name callsbot --restart unless-stopped --env-file /opt/callsbotonchain/.env \
    -e CALLSBOT_LOG_STDOUT=true -v /opt/callsbotonchain/var:/app/var:ro \
    -v /opt/callsbotonchain/data/logs:/app/data/logs:ro --network callsbotnet \
    -p 8080:8080 callsbot:latest python scripts/bot.py web --host 0.0.0.0 --port 8080 && \
  docker run -d --name callsbot-worker --restart unless-stopped --env-file /opt/callsbotonchain/.env \
    -e CALLSBOT_LOG_STDOUT=true -e CALLSBOT_METRICS_ENABLED=true \
    -v /opt/callsbotonchain/var:/app/var -v /opt/callsbotonchain/data/logs:/app/data/logs \
    --network callsbotnet callsbot:latest python scripts/bot.py
```


