#!/bin/bash
# ---
# name: mashang_dataset_daily_update
# description: Update local datasets from Tableau and run daily order observation.
# schedule:
#   time: "08:30"
#   start_interval_seconds: 300
# gate:
#   policy: "once_per_day_after_time"
#   timezone: "local"
# outputs:
#   log_dir: daemon/logs
#   state_dir: daemon/state
# ---
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
daemon_dir="$script_dir"
state_dir="$daemon_dir/state"
log_dir="$daemon_dir/logs"

mkdir -p "$state_dir" "$log_dir"

lock_dir="$state_dir/run.lock"
if ! mkdir "$lock_dir" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$lock_dir" 2>/dev/null || true' EXIT

today="$(/bin/date +%F)"
stamp="$state_dir/last_success_${today}.stamp"
if [[ -f "$stamp" ]]; then
  existing="$(tr -d '\r\n\t ' <"$stamp" 2>/dev/null || true)"
  if [[ -z "$existing" ]]; then
    ts="$(/bin/date '+%Y-%m-%dT%H:%M:%S%z' 2>/dev/null || true)"
    if [[ -z "$ts" ]]; then
      ts="$(/bin/date +%s)"
    fi
    printf '%s\n' "$ts" >"$stamp"
  fi
  exit 0
fi

hour="$(/bin/date +%H)"
minute="$(/bin/date +%M)"
now=$((10#$hour * 60 + 10#$minute))
target=$((8 * 60 + 30))
if (( now < target )); then
  exit 0
fi

python_bin="$repo_root/.venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  python_bin="/usr/bin/python3"
  if [[ ! -x "$python_bin" ]]; then
    python_bin="$(command -v python3)"
  fi
fi

{
  echo ""
  echo "===== $(/bin/date '+%Y-%m-%d %H:%M:%S%z') START update_all_datasets ====="

  rc=1
  attempts="${UPDATE_ALL_ATTEMPTS:-3}"
  sleep_seconds="${UPDATE_ALL_RETRY_SLEEP_SECONDS:-120}"
  base_timeout="${TABLEAU_TIMEOUT_SECONDS:-900}"
  retry_timeout="${TABLEAU_TIMEOUT_RETRY_SECONDS:-1800}"

  host="${TABLEAU_HOSTNAME:-tableau-hs.immotors.com}"
  dns_tries="${TABLEAU_DNS_RETRY_COUNT:-5}"
  dns_sleep="${TABLEAU_DNS_RETRY_SLEEP_SECONDS:-3}"
  i=1
  while (( i <= dns_tries )); do
    set +e
    "$python_bin" - <<PY >/dev/null 2>&1
import socket
socket.getaddrinfo("${host}", 443)
PY
    dns_rc=$?
    set -e
    if (( dns_rc == 0 )); then
      break
    fi
    echo "[preflight] dns resolve failed (${host}) try=${i}/${dns_tries}"
    /bin/sleep "$dns_sleep"
    i=$((i + 1))
  done

  attempt=1
  while (( attempt <= attempts )); do
    timeout="$base_timeout"
    extra_args=()
    if (( attempt >= 2 )); then
      timeout="$retry_timeout"
    fi
    if (( attempt == attempts )); then
      if [[ -n "${TABLEAU_SERVER_URL_MOBILE:-}" || "${UPDATE_ALL_USE_MOBILE_FALLBACK:-0}" == "1" ]]; then
        extra_args+=(--mobile)
      fi
    fi

    echo "[update_all] attempt=${attempt}/${attempts} timeout=${timeout} args=${extra_args[*]:-}"
    set +e
    "$python_bin" "$repo_root/dataset/updater/update_all_datasets.py" --timeout "$timeout" "${extra_args[@]}"
    rc=$?
    set -e
    if (( rc == 0 )); then
      break
    fi
    echo "[update_all] failed rc=${rc}"
    if (( attempt < attempts )); then
      /bin/sleep "$sleep_seconds"
    fi
    attempt=$((attempt + 1))
  done

  if (( rc != 0 )); then
    echo "===== $(/bin/date '+%Y-%m-%d %H:%M:%S%z') FAILED update_all_datasets rc=${rc} ====="
    exit "$rc"
  fi

  echo "===== $(/bin/date '+%Y-%m-%d %H:%M:%S%z') END update_all_datasets ====="
  echo ""
  echo "===== $(/bin/date '+%Y-%m-%d %H:%M:%S%z') START skills_order_observation_daily ====="
  "$python_bin" "$repo_root/daemon/skills_order_observation_daily.py"
  echo "===== $(/bin/date '+%Y-%m-%d %H:%M:%S%z') END skills_order_observation_daily ====="
  echo ""
} >>"$log_dir/update_all.log" 2>&1
ts="$(/bin/date '+%Y-%m-%dT%H:%M:%S%z' 2>/dev/null || true)"
if [[ -z "$ts" ]]; then
  ts="$(/bin/date +%s)"
fi
printf '%s\n' "$ts" >"$stamp"

/usr/bin/find "$state_dir" -name 'last_success_*.stamp' -mtime +14 -delete >/dev/null 2>&1 || true
