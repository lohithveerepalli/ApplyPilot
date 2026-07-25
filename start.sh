#!/usr/bin/env bash
# ApplyPilot daily helper (Grok Build default)
set -euo pipefail
cd "$(dirname "$0")"
if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

cmd="${1:-help}"
shift || true

export APPLY_BACKEND="${APPLY_BACKEND:-grok}"

case "$cmd" in
  doctor)     applypilot doctor ;;
  run)        applypilot run -w 4 "$@" ;;
  discover)   applypilot run discover enrich -w 4 "$@" ;;
  tailor)     applypilot run score tailor cover pdf "$@" ;;
  track)      applypilot track ;;
  status)     applypilot status ;;
  dry)        applypilot apply --dry-run --headless "$@" ;;
  apply)      applypilot apply --headless -w 1 "$@" ;;
  continuous) applypilot apply --continuous --headless -w 1 "$@" ;;
  resumes)    applypilot resumes list ;;
  hunt)       applypilot hunt --once -w 4 "$@" ;;
  hunt-loop)  applypilot hunt -i 300 -w 4 "$@" ;;
  hunt-apply) applypilot hunt -i 300 --apply --apply-limit 2 --headless -w 4 "$@" ;;
  daemon)     applypilot daemon "$@" ;;
  dashboard)  applypilot dashboard ;;
  help|*)
    cat <<'H'
Usage: ./start.sh <command>

  doctor      Check setup (Grok / Chrome / Node / LLM)
  run         Full pipeline (discover → tailor)
  discover    Discover + enrich only
  tailor      Score + tailor + cover + pdf
  hunt        One fast ATS-board pass (Greenhouse/Lever/Ashby)
  hunt-loop   Poll every 5 min (discovery + tailor)
  hunt-apply  Hunt loop + headless auto-apply (Grok)
  daemon      24/7 laptop mode (headless hunt + apply)
  track       Application stats
  status      Full status
  dry         Auto-apply dry-run (Grok + Chrome)
  apply       Auto-apply live headless (Grok default)
  continuous  Auto-apply forever
  dashboard   HTML dashboard (role/company/pay/resume/status)
  resumes     List base resumes

Env:
  APPLY_BACKEND=grok|claude   (default grok)
H
    ;;
esac
