#!/bin/bash
# Start Signal Aggregator with environment variables from .env
set -a  # Auto-export all variables
source .env
set +a

# Use -u flag for unbuffered output (fixes empty log file issue)
exec python3 -u scripts/signal_aggregator_daemon.py

