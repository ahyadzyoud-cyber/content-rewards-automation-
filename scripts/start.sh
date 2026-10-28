#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Retain state on disk. Processes must be restarted after an environment restore.
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/content-rewards-uv-cache}"
export UV_LINK_MODE=copy
uv run --frozen rewards init
uv run --frozen rewards worker >.data/worker.log 2>&1 &
worker_pid=$!
trap 'kill "$worker_pid" 2>/dev/null || true' EXIT INT TERM
uv run --frozen rewards serve
