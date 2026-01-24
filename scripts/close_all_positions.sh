#!/bin/bash
# Convenience wrapper to close all open positions

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "Closing all open positions using force_close_all.py..."
python "${PROJECT_ROOT}/scripts/force_close_all.py"
