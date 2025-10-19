#!/bin/bash
# Start Signal Aggregator with environment variables from .env
set -a  # Auto-export all variables
source .env
set +a

exec python3 scripts/signal_aggregator_daemon.py

