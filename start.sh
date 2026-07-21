#!/usr/bin/env bash
# ApplyPilot daily helper
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate

cmd="${1:-help}"
shift || true

case "$cmd" in
  doctor)   applypilot doctor ;;
  run)      applypilot run -w 4 "$@" ;;
  discover) applypilot run discover enrich -w 4 "$@" ;;
  tailor)   applypilot run score tailor cover pdf "$@" ;;
  track)    applypilot track ;;
  status)   applypilot status ;;
  dry)      applypilot apply --dry-run "$@" ;;
  apply)    applypilot apply -w 2 "$@" ;;
  continuous) applypilot apply --continuous -w 2 "$@" ;;
  resumes)  applypilot resumes list ;;
  help|*)
    cat <<'H'
Usage: ./start.sh <command>

  doctor      Check setup
  run         Full pipeline (discover → tailor)
  discover    Discover + enrich only
  tailor      Score + tailor + cover only
  track       Application stats
  status      Full status
  dry         Auto-apply dry-run (needs Chrome)
  apply       Auto-apply live (needs Chrome)
  continuous  Auto-apply forever (needs Chrome)
  resumes     List base resumes
H
    ;;
esac
