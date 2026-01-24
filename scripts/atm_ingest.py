#!/usr/bin/env python3
"""
ATM ingestion daemon.

Listens to ATM Telegram channels and pipes parsed signals into SignalProcessor
so the existing gating/scoring/alert pipeline applies.
"""
import os
import sys
import asyncio

# Ensure project root importable
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.atm_listener import run_atm_listener  # noqa: E402


def main():
    try:
        asyncio.run(run_atm_listener())
    except KeyboardInterrupt:
        print("\n[ATM] Stopped by user")


if __name__ == "__main__":
    main()


