#!/usr/bin/env python3
"""
Periodic tracker to refresh performance stats for alerted tokens.

Fetches recent alerted tokens, pulls fresh stats, records price snapshots,
and updates performance metrics (peak, drawdown, realistic gains).
"""
import os
import sys
import time

# Ensure project root importable
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.storage import (
    init_db,
    get_alerted_tokens_for_tracking,
    record_price_snapshot,
    update_token_performance,
)
from app.analyze_token import get_token_stats


def main():
    init_db()
    tokens = get_alerted_tokens_for_tracking()
    if not tokens:
        print("[TRACKER] No recent alerted tokens to refresh.")
        return

    refreshed = 0
    errors = 0
    for idx, ca in enumerate(tokens, 1):
        try:
            stats = get_token_stats(ca, force_refresh=False)
            if not stats:
                continue
            record_price_snapshot(ca, stats)
            update_token_performance(ca, stats)
            refreshed += 1
            # gentle pacing to avoid hammering APIs
            time.sleep(0.2)
        except Exception as e:
            errors += 1
            print(f"[TRACKER] Error refreshing {ca[:8]}...: {e}")

    print(f"[TRACKER] Done. Refreshed {refreshed} tokens, errors: {errors}")


if __name__ == "__main__":
    main()


