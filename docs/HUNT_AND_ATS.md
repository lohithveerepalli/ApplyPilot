# Hunt mode + multi-ATS strategy

## What you asked for

| Goal | Reality |
|------|---------|
| 24/7 scraping | **Hunt loop** / **daemon** polls boards every N minutes |
| Apply within ~10–30 min of post | Possible on **Greenhouse / Lever / Ashby / Workday** when agent + apply are funded |
| Hundreds of company sites | **Public board APIs** + Workday registry + JobSpy + optional Brian dorks |
| Auto-apply agent | **Grok Build** (default) or Claude Code via `apply/backend/` |
| Custom ATS playbooks | Injected into the browser agent prompt |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  HUNT / DAEMON LOOP                                     │
│  every 5 min (default)                                  │
├─────────────────────────────────────────────────────────┤
│  1. Greenhouse API  ──┐                                 │
│  2. Lever API       ──┼─► SQLite jobs DB                │
│  3. Ashby API       ──┤   (dedupe by URL)               │
│  4. optional JobSpy ──┤                                 │
│  5. optional Workday──┤                                 │
│  6. optional Brians ──┘  (Google dorks / SerpAPI)       │
│                                                         │
│  7. Score only FRESH jobs (last --max-age minutes)      │
│  8. Tailor score >= min  → PDF (resume-tailor optional) │
│  9. optional: auto-apply via Grok/Claude + Playwright   │
└─────────────────────────────────────────────────────────┘
```

## Commands

```bash
# One fast pass (cron-friendly)
applypilot hunt --once -w 4

# 24/7 discovery + tailor
applypilot hunt -i 300 -w 4

# 24/7 + headless auto-apply (Grok)
applypilot hunt --apply --apply-limit 2 --headless -i 300

# Laptop all-in-one
applypilot daemon
./scripts/run-daemon.sh

# Brian-style extra discovery
export SERPAPI_KEY=...
applypilot hunt --brians --once
```

## Agent backends

| Backend | Env / flag | CLI |
|---------|------------|-----|
| **grok** (default) | `APPLY_BACKEND=grok` | `grok --prompt-file … --permission-mode bypassPermissions` |
| claude | `APPLY_BACKEND=claude` | `claude -p --mcp-config … --permission-mode bypassPermissions` |

Playwright attaches to Chrome CDP. Worker dir gets either Claude MCP JSON or Grok `.grok/config.toml`.

## Timing (~10 min target)

| Step | Time |
|------|------|
| Board poll interval | 5 min (default) or 2 min (`-i 120`) |
| Score + tailor 1 job | 1–3 min |
| Browser apply | 3–15 min |
| **Total if posted mid-cycle** | ~10–25 min typical |

## Cost reminder

| Piece | Cost |
|-------|------|
| Hunt discovery (HTTP APIs) | Free |
| Score + tailor | Gemini free or paid LLM |
| Auto-apply | Grok / Claude usage |

## Honest limits

1. Grok or Claude quota required for `--apply`.
2. Amazon/Google/Meta often block automation.
3. CAPTCHAs / SSO still kill runs without CapSolver + sessions.
4. Prefer public APIs over aggressive scraping.
