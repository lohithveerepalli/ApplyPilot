#!/usr/bin/env bash
# 24/7 laptop helper — run ApplyPilot daemon under tmux/screen or bare.
# Usage:
#   ./scripts/run-daemon.sh
#   ./scripts/run-daemon.sh --dry-run
#   tmux new -s applypilot './scripts/run-daemon.sh'

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
elif [[ -f venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

export APPLY_BACKEND="${APPLY_BACKEND:-grok}"
export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot}"

# Soft resource friendliness on old laptops
export APPLY_MAX_TURNS="${APPLY_MAX_TURNS:-60}"
export APPLY_TIMEOUT="${APPLY_TIMEOUT:-420}"

INTERVAL="${HUNT_INTERVAL:-300}"
MIN_SCORE="${MIN_SCORE:-7}"
APPLY_LIMIT="${APPLY_LIMIT:-2}"

echo "[applypilot] daemon starting (backend=$APPLY_BACKEND interval=${INTERVAL}s)"
echo "[applypilot] logs: $APPLYPILOT_DIR/logs"
echo "[applypilot] Ctrl+C to stop"

exec applypilot daemon \
  --interval "$INTERVAL" \
  --min-score "$MIN_SCORE" \
  --apply-limit "$APPLY_LIMIT" \
  --workers 1 \
  --backend "$APPLY_BACKEND" \
  "$@"
