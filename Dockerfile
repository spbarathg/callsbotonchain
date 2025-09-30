# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
 && rm -rf /var/lib/apt/lists/* \
 && apt-get purge -y --auto-remove && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better layer caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create non-root user
RUN useradd -m -u 10001 appuser \
 && mkdir -p /app/var /app/data/logs \
 && chown -R appuser:appuser /app

USER appuser

# Expose Prometheus metrics optionally
EXPOSE 9108

# Default environment (override in runtime)
ENV CALLSBOT_LOG_STDOUT=true \
    CALLSBOT_METRICS_ENABLED=false

# Entrypoint runs the bot
CMD ["python", "scripts/bot.py"]

# Healthcheck: ensure recent heartbeats in process.jsonl (<=300s)
HEALTHCHECK --interval=30s --timeout=5s --retries=5 CMD python - <<'PY'
import os, json, time
p = os.path.join('data','logs','process.jsonl')
try:
    if not os.path.exists(p):
        raise SystemExit(1)
    last_ts = 0
    with open(p, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get('type') == 'heartbeat':
                    ts = rec.get('ts')
                    if isinstance(ts, (int, float)):
                        last_ts = max(last_ts, int(ts))
            except Exception:
                continue
    now = int(time.time())
    # consider healthy if we saw a heartbeat within last 300 seconds
    ok = (now - last_ts) < 300 if last_ts > 0 else False
    raise SystemExit(0 if ok else 1)
except SystemExit as e:
    raise
except Exception:
    raise SystemExit(1)
PY







