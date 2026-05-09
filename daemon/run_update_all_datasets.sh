#!/bin/bash
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
  python_bin="$(command -v python3)"
fi

"$python_bin" "$repo_root/dataset/updater/update_all_datasets.py" >>"$log_dir/update_all.log" 2>&1
ts="$(/bin/date '+%Y-%m-%dT%H:%M:%S%z' 2>/dev/null || true)"
if [[ -z "$ts" ]]; then
  ts="$(/bin/date +%s)"
fi
printf '%s\n' "$ts" >"$stamp"

/usr/bin/find "$state_dir" -name 'last_success_*.stamp' -mtime +14 -delete >/dev/null 2>&1 || true
