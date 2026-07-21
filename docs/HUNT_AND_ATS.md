# Hunt mode + multi-ATS strategy

## What you asked for

| Goal | Reality |
|------|---------|
| 24/7 scraping | **Hunt loop** polls boards every N minutes |
| Apply within ~30 min of post | Possible on **Greenhouse / Lever / Ashby / Workday** when AI + apply are funded |
| Hundreds of company sites | **Public board APIs** + Workday registry + JobSpy |
| Custom ATS per site (Workday, Amazon, Google, Meta…) | **Playbooks** per ATS injected into the browser agent |
| Amazon / Google / Meta careers auto-apply | **Hard** — bot defense / SSO; discovery + manual/best-effort only |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  HUNT LOOP (applypilot hunt)                            │
│  every 5 min (default)                                  │
├─────────────────────────────────────────────────────────┤
│  1. Greenhouse API  ──┐                                 │
│  2. Lever API       ──┼─► SQLite jobs DB                │
│  3. Ashby API       ──┤   (dedupe by URL)               │
│  4. optional JobSpy ──┤                                 │
│  5. optional Workday──┘                                 │
│                                                         │
│  6. Score only FRESH jobs (last --max-age minutes)      │
│  7. Tailor score >= min                                 │
│  8. optional: auto-apply (Claude + ATS playbook)        │
└─────────────────────────────────────────────────────────┘
```

### Per-ATS playbooks (`applypilot/ats/`)

| ATS | Discover | Auto-apply |
|-----|----------|------------|
| Greenhouse | Public boards API | Easy — playbook |
| Lever | Public postings API | Easy — playbook |
| Ashby | Public job-board API | Easy — playbook |
| Workday | employers.yaml CXS API | Medium — multi-page playbook |
| Indeed | JobSpy | Medium |
| LinkedIn | JobSpy | Hard (login session) |
| Amazon.jobs | careers registry (notes) | Hard / often manual |
| Google Careers | blocked / hard | Hard / often manual |
| Meta Careers | hard | Hard / often manual |

Detection: `applypilot ats <url>`  
Strategies injected into Claude apply prompts automatically.

## Commands

```bash
# List how many boards are configured
applypilot ats

# Classify a job link
applypilot ats 'https://boards.greenhouse.io/nvidia/jobs/...'

# One fast pass (cron-friendly)
applypilot hunt --once -w 8

# 24/7 style loop every 5 minutes
applypilot hunt -i 300 -w 8

# Also scrape Indeed/LinkedIn/Workday each pass (slower)
applypilot hunt --full -i 600

# Auto-submit (needs Claude Pro/Max logged in + Chrome/Brave)
applypilot hunt --apply --apply-limit 3 -i 300
```

Helper:

```bash
./start.sh hunt        # one pass
./start.sh hunt-loop   # continuous
```

## Add more companies

Edit `src/applypilot/config/ats_boards.yaml`:

```yaml
greenhouse:
  - { token: somecompany, name: "Some Company" }
lever:
  - { company: somecompany, name: "Some Company" }
ashby:
  - { board: somecompany, name: "Some Company" }
```

Find Greenhouse token: open their careers page → often `boards.greenhouse.io/{token}`.

## 30-minute target — what actually matters

| Step | Time |
|------|------|
| Board poll interval | 5 min (default) |
| Score + tailor 1 job | 1–3 min (API) |
| Browser apply | 3–15 min |
| **Total if posted mid-cycle** | ~10–25 min typical |
| If posted right after poll | up to interval + process |

Tighter: `applypilot hunt -i 120` (every 2 min) — more polite rate limiting needed.

## Cost reminder

| Piece | Cost |
|-------|------|
| Hunt discovery (HTTP APIs) | Free |
| Score + tailor | Gemini free or paid LLM |
| `--apply` | Claude subscription |

## Honest limits

1. **No free unlimited auto-apply** — Claude is paid.
2. **Amazon/Google/Meta** will often defeat bots; playbooks help but do not guarantee.
3. **CAPTCHAs / SSO** still kill runs without CapSolver + human accounts.
4. Scraping can violate site ToS — use at your own risk; prefer public APIs (GH/Lever/Ashby).

## Recommended setup for infra candidates

```bash
# Free prep machine
applypilot hunt -i 300 -w 8 --validation normal

# Separate terminal / machine with Claude when ready to burn quota
applypilot apply --limit 10 --min-score 8
```
