#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null
command -v ffmpeg >/dev/null
command -v ffprobe >/dev/null
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/content-rewards-uv-cache}"
export UV_LINK_MODE=copy
uv sync --frozen
uv run --frozen rewards init
uv run --frozen ruff check .
uv run --frozen pytest -q
