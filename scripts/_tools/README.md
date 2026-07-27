# Archived Debug & Maintenance Scripts

This directory contains archived debug, maintenance, and investigation scripts.

## Rules

- **Nothing here is imported by production**
- **Nothing here is mounted into Docker**
- **Scripts must be manually executed**

## Contents

| Script | Purpose |
|--------|---------|
| `backtest_data_collector.py` | Collect data for backtesting |
| `check_bot_db_path.py` | Verify database path configuration |
| `check_db_status.py` | Check database status |
| `check_dyra_pnl.py` | Check specific token PnL |
| `check_dyra_trade.py` | Check specific trade details |
| `check_token_history.py` | View token price history |
| `check_token_position.py` | View position details |
| `check_wallet_balance.py` | Check wallet token balances |
| `check_watchlist.py` | View Redis watchlist |
| `close_all_positions.sh` | Emergency: close all positions |
| `close_ghost_positions.py` | Maintenance: close ghost positions |
| `diagnose_and_fix_positions.py` | Debug position issues |
| `emergency_close_ghosts.py` | Emergency: close ghost positions |
| `force_close_all.py` | Emergency: force close all |
| `force_close_ghost_positions.py` | Maintenance: force close ghosts |
| `force_close_orphans.py` | Maintenance: close orphaned positions |
| `health_check.sh` | Health check script |
| `investigate_wallet.py` | Wallet investigation |
| `monitoring_dashboard.py` | CLI monitoring dashboard |
| `sync_positions_with_wallet.py` | Sync DB with wallet |
| `test_recovery_pattern.py` | Test recovery pattern detector |
| `track_alert_performance.py` | Alert performance analytics |
| `validate_pnl.py` | Validate PnL calculations |

## Usage

These scripts are run manually from the project root:

```bash
# Example: check wallet balance
python scripts/_tools/check_wallet_balance.py

# Example: force close ghost positions
python scripts/_tools/force_close_ghost_positions.py
```

## Warning

Do not import these scripts from production code. They may have stale dependencies or make assumptions that are no longer valid.
