"""Minimal, fast trading system integrated with the bot's logs.

Components
- watcher: tails `data/logs/stdout.log` and emits normalized signals
- strategy: converts signals into trade plans (Runner, Scout)
- broker: pluggable execution; default DryRun (logs only)
- trader: position manager with stops/trails/ladder
- db: lightweight SQLite persistence under var/trading.db

Environment variables are read via `tradingSystem.config`.
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


