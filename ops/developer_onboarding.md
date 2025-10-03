Developer Onboarding

Setup
- Python 3.11+
- pip install -r requirements.txt
- Copy .env.example to .env and set non-secret defaults. Secrets must be injected at runtime from your secret manager.

Running
- Unit tests: pytest -q
- Web: python scripts/bot.py web
- Worker: python scripts/bot.py run
- Dry-run: set DRY_RUN=true (no external alerts)

Useful
- Metrics: enable with CALLSBOT_METRICS_ENABLED=true (binds to 127.0.0.1)
- Export data: python tools/export_stats.py --mode db

