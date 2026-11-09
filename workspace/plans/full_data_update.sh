#!/bin/bash
# Full data update — 业务实现由现有 Make target 维护。
set -euo pipefail
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
exec make -j1 allupdate "$@"
