#!/usr/bin/env bash
set -euo pipefail

# Usage: ./ops/tune_env.sh /opt/callsbotonchain/.env
# Idempotently set key=value pairs in the provided .env file.

ENV_FILE=${1:-.env}

touch "$ENV_FILE"

set_kv() {
  local key="$1"; shift
  local value="$1"; shift || true
  if grep -q -E "^${key}=" "$ENV_FILE"; then
    sed -i -E "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf "%s\n" "${key}=${value}" >> "$ENV_FILE"
  fi
}

# Speed/Asymmetry tuning
set_kv VOL_TO_MCAP_RATIO_MIN 0.80
set_kv MAX_MARKET_CAP_FOR_DEFAULT_ALERT 1000000
set_kv REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT 2
set_kv REQUIRE_MOMENTUM_1H_MIN_FOR_ALERT 5
set_kv TRACK_INTERVAL_MIN 1

# Ensure strict preset is active with rich stats
set_kv GATE_MODE TIER2
set_kv CIELO_DISABLE_STATS false
set_kv CALLSBOT_FORCE_FALLBACK false

# Budget/cost controls
set_kv BUDGET_ENABLED true
set_kv BUDGET_PER_MINUTE_MAX 40
set_kv BUDGET_PER_DAY_MAX 15000
# Avoid early heavy fetches unless prelim strong
set_kv PRELIM_DETAILED_MIN 6

echo "--- Effective overrides written to ${ENV_FILE} ---"
grep -E '^(VOL_TO_MCAP_RATIO_MIN|MAX_MARKET_CAP_FOR_DEFAULT_ALERT|REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT|REQUIRE_MOMENTUM_1H_MIN_FOR_ALERT|TRACK_INTERVAL_MIN|GATE_MODE|CIELO_DISABLE_STATS|CALLSBOT_FORCE_FALLBACK)=' "$ENV_FILE" | sort


