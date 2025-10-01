#!/usr/bin/env bash
set -euo pipefail

curl_json() {
  local url="$1"
  if ! curl -fsS "$url" 2>/dev/null; then
    echo '{}' 
  fi
}

TS=$(date -Is)
CONTAINERS=$(docker ps --format '{{.Names}}\t{{.Status}}' | sort | jq -R -s 'split("\n") | map(select(length>0)) | map(split("\t") | {name: .[0], status: .[1]})')
STATS=$(curl_json http://127.0.0.1:8080/api/stats)
TRACKED=$(curl_json 'http://127.0.0.1:8080/api/tracked?limit=50')
DISK=$(df -hT / | tail -n1 | awk '{print $7" "$3"/"$2" "$6}' | awk '{print "{\"mount\":\""$1"\",\"used_total\":\""$2"\",\"pct\":\""$3"\"}"}')
RECENT=$(echo "$STATS" | jq '(.recent_alerts|length) // 0')
TOTAL=$(echo "$STATS" | jq '.signals_summary.total_alerts // 0')
LAST_HB=$(echo "$STATS" | jq -r '.last_heartbeat.ts // empty')
TRACKED_COUNT=$(echo "$TRACKED" | jq '(.rows|length) // 0')
PROCESS_TAIL=$(tail -n 40 /opt/callsbotonchain/data/logs/process.jsonl 2>/dev/null | tail -n 40 | jq -R -s 'split("\n") | map(select(length>0))')

jq -n --arg ts "$TS" \
      --arg last_hb "$LAST_HB" \
      --argjson containers "$CONTAINERS" \
      --argjson stats "$STATS" \
      --argjson recent "$RECENT" \
      --argjson total "$TOTAL" \
      --argjson tracked_count "$TRACKED_COUNT" \
      --argjson disk "$DISK" \
      --argjson process_tail "$PROCESS_TAIL" \
      '{ts: $ts, containers: $containers, last_heartbeat: $last_hb, recent_alerts: $recent, total_alerts: $total, tracked_count: $tracked_count, disk: $disk, stats: $stats, process_tail: $process_tail}' |
  tee /opt/callsbotonchain/ops/last_health.json


