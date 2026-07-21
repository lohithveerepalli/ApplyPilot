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
  hunt)     applypilot hunt --once -w 8 "$@" ;;
  hunt-loop) applypilot hunt -i 300 -w 8 "$@" ;;
  help|*)
    cat <<'H'
Usage: ./start.sh <command>

  doctor      Check setup
  run         Full pipeline (discover → tailor)
  discover    Discover + enrich only
  tailor      Score + tailor + cover only
  hunt        One fast ATS-board pass (Greenhouse/Lever/Ashby)
  hunt-loop   Poll every 5 min (24/7 style) — Ctrl+C to stop
  track       Application stats
  status      Full status
  dry         Auto-apply dry-run (needs Claude + Chrome)
  apply       Auto-apply live (needs Claude + Chrome)
  continuous  Auto-apply forever (needs Claude + Chrome)
  resumes     List base resumes
H
    ;;
esac
