#!/bin/sh
# Run on the data host after the upstream monthly delivery.
set -eu
cd "$(dirname "$0")/../../.."

: "${MARKET_MONITOR_KUBE_CONTEXT:?Set the Sealos Kubernetes context}"
: "${MARKET_MONITOR_NAMESPACE:?Set the Sealos application namespace}"
snapshot_dir="${MARKET_MONITOR_SNAPSHOT_DIR:-apps/market_monitor/var}"
python="${MARKET_MONITOR_PYTHON:-.venv/bin/python}"
workload="${MARKET_MONITOR_WORKLOAD:-deployment/market-monitor}"

case "${1:-all}" in
  all) set -- insurance miit ;;
  insurance|miit) ;;
  *) printf '%s\n' 'Usage: sync-sealos.sh [all|insurance|miit]' >&2; exit 2 ;;
esac

status=0
for source do
  if "$python" -m apps.market_monitor.backend refresh --source "$source"; then
    kubectl --context "$MARKET_MONITOR_KUBE_CONTEXT" -n "$MARKET_MONITOR_NAMESPACE" \
      exec -i "$workload" -c snapshot-writer -- \
      python -m apps.market_monitor.backend import-snapshot --source "$source" \
      < "$snapshot_dir/$source.json" || status=1
  else
    status=1
  fi
done
exit "$status"
