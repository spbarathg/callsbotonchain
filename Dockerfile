# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

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


