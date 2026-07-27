"""Optimized trading system for Solana memecoin execution.

Signal Pipeline (2026-05-17):
  [Signal Sources]  →  app/signal_queue.py (Redis priority queue)
                    →  watcher.py (brpop consumer)
                    →  cli_optimized.py (entry strategy + risk gating)
                    →  trader_optimized.py (execution + lifecycle)
                    →  risk_phases.py (phased stop-loss / trailing stop)

Signal Sources:
  - app/atm_listener.py: Telegram ATM-bot channels (current)
  - app/signal_source_interface.py: protocol for adding new sources
    (e.g. Yellowstone gRPC pool streams, smart-wallet trackers)

Components:
  - watcher: Redis brpop consumer for real-time signal ingestion
  - entry_strategy: pluggable entry timing (Instant/Delayed/Dip/Hybrid)
  - strategy_optimized: trade plan sizing and trail selection
  - broker_optimized: Jupiter-based execution with slippage management
  - trader_optimized: position lifecycle (open/monitor/close)
  - risk_phases: phase-aware stop-loss (EARLY/MID/LATE)
  - db: SQLite persistence under var/trading.db

Environment variables are read from .env via config_optimized.py.
"""

__all__ = [
	"config",
	"db",
	"broker",
	"strategy",
	"trader",
	"watcher",
	"cli",
]


