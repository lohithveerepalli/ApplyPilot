# ApplyPilot (fork)

**Discover jobs → score fit → tailor resume honestly → cover letter → auto-apply with Grok Build.**

Tuned for technical infrastructure roles. Auto-apply is driven by **[Grok Build](https://grok.x.ai/)** (xAI’s terminal agent) + Playwright MCP on headless Chrome. Claude Code remains an optional fallback backend.

> Fork of [Pickle-Pixel/ApplyPilot](https://github.com/Pickle-Pixel/ApplyPilot). Not affiliated with applypilot.app or useapplypilot.com.

---

## What changed in this fork

| Area | Behavior |
|------|----------|
| **Apply agent** | **Grok Build** by default (`APPLY_BACKEND=grok`). Claude Code still works (`--backend claude`). |
| **24/7 laptop** | `applypilot daemon` + `scripts/run-daemon.sh` + systemd unit |
| **Hunt** | Greenhouse / Lever / Ashby APIs; optional `--brians` Google-dork source |
| **Resume PDF** | Optional bridge to [resume-tailor](https://github.com/lohithveerepalli/resume-tailor) for 1-page PDFs |
| **Dashboard** | Role · company · pay · ATS · fit · **exact resume PDF** · status · timestamp |

Pipeline stages **discover → enrich → score → tailor → cover → pdf** are unchanged and still work without any agent CLI.

---

## Requirements

| Component | Required for | Notes |
|-----------|--------------|--------|
| Python 3.11+ | Everything | |
| Gemini (or OpenAI/local) API key | Score / tailor / cover | Free Gemini tier is enough for prep |
| **Grok Build CLI** (`grok`) | Auto-apply (default) | Install Grok Build; `grok --help` must work |
| Chrome / Chromium | Auto-apply | Headless supported |
| Node.js 18+ (`npx`) | Auto-apply | Playwright MCP |
| Claude Code CLI | Optional only | `APPLY_BACKEND=claude` |

---

## 10-minute setup

```bash
git clone https://github.com/lohithveerepalli/ApplyPilot.git
cd ApplyPilot
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
pip install --no-deps python-jobspy
pip install pydantic tls-client requests markdownify regex

# One-time profile + resume + searches
applypilot init
applypilot doctor
```

Configure `~/.applypilot/.env` (see `.env.example`):

```bash
GEMINI_API_KEY=...
APPLY_BACKEND=grok
# XAI_API_KEY=...          # if Grok needs an API key
# APPLY_GROK_MODEL=grok-4.5
```

---

## Daily usage

```bash
# Discovery + AI prep (no browser agent)
applypilot run -w 4
# or fast ATS-only pass
applypilot hunt --once -w 4

# Auto-apply (headless Grok + Playwright)
applypilot apply --dry-run          # fill forms, don't submit
applypilot apply --limit 5          # live, headless by default
applypilot apply --backend claude   # optional Claude Code path

# Continuous apply only (queue already tailored)
applypilot apply --continuous --poll-interval 120
```

### 24/7 laptop mode (recommended)

Headless hunt every 5 minutes → score/tailor fresh jobs → auto-apply a few with Grok:

```bash
applypilot daemon
# or
./scripts/run-daemon.sh
# dry run (no submits):
applypilot daemon --dry-run
```

**tmux**

```bash
tmux new -s applypilot './scripts/run-daemon.sh'
```

**systemd** — see [deploy/README.md](deploy/README.md) and `deploy/applypilot-daemon.service`.

Laptop defaults: 1 apply worker, headless Chrome, polite hunt interval (300s), soft CPU/memory limits in the unit file.

---

## Pipeline

| Stage | What happens |
|-------|----------------|
| **1. Discover** | JobSpy boards + Workday + Greenhouse/Lever/Ashby (+ optional Brian dorks) |
| **2. Enrich** | Full JD via JSON-LD → CSS → AI |
| **3. Score** | AI fit 1–10 against **your** resume |
| **4. Tailor** | Per-job rewrite — **strict: no invented experience** |
| **5. Cover** | Targeted cover letter |
| **6. PDF** | Upload-ready PDF (resume-tailor bridge when configured) |
| **7. Apply** | Grok Build + Playwright MCP drives the form, uploads PDF, emits `RESULT:*` |

---

## Agent backends

```text
src/applypilot/apply/backend/
  base.py      # interface + RESULT:* parser
  grok.py      # Grok Build headless + project .grok/config.toml (Playwright MCP)
  claude.py    # Claude Code (original path)
```

| Flag / env | Meaning |
|------------|---------|
| `--backend grok` | Default — `grok --prompt-file … --permission-mode bypassPermissions` |
| `--backend claude` | Legacy Claude Code stream-json path |
| `APPLY_BACKEND` | Same as `--backend` |
| `APPLY_GROK_MODEL` / `APPLY_CLAUDE_MODEL` | Model overrides |

The prompt builder (`apply/prompt.py`) is **shared**. Both backends must finish with:

```text
RESULT:APPLIED
RESULT:FAILED:reason
RESULT:CAPTCHA
RESULT:EXPIRED
RESULT:LOGIN_ISSUE
```

---

## Hunt + early apply

```bash
# Poll ATS APIs every 5 minutes
applypilot hunt -i 300

# Also Brian-style dorks (needs SERPAPI_KEY preferred)
applypilot hunt --brians --once

# Hunt + auto-apply up to 2 jobs per pass
applypilot hunt --apply --apply-limit 2 --headless
```

Details: [docs/HUNT_AND_ATS.md](docs/HUNT_AND_ATS.md).

Typical timing if a job posts mid-cycle: **~10–25 minutes** from post → tailored materials → submit (easy ATS).

---

## Resume-tailor integration (optional)

For the same 1-page Awesome-CV style PDFs as [resume-tailor](https://github.com/lohithveerepalli/resume-tailor):

```bash
# ~/.applypilot/.env
RESUME_TAILOR_PATH=/path/to/resume-tailor
RESUME_TAILOR_MASTER=/path/to/master_resume.yaml
```

When a master YAML is found, PDF generation prefers that pipeline; otherwise ApplyPilot’s built-in HTML→PDF path is used. The **exact PDF path** is stored on the job (`tailored_resume_path`) and shown in the dashboard.

---

## Dashboard

```bash
applypilot dashboard
```

Applications table columns:

**Role · Company/site · Pay · Source ATS · Fit score · Resume PDF · Status · Timestamp**

---

## CLI cheat sheet

```bash
applypilot init
applypilot doctor
applypilot run                          # stages 1–6 (no apply)
applypilot hunt --once -w 4
applypilot hunt --apply --apply-limit 2
applypilot apply --dry-run
applypilot apply -w 1 --backend grok
applypilot daemon                       # 24/7 headless
applypilot track | status | dashboard
```

---

## Honest limits

1. **No unlimited free auto-apply** — Grok/Claude usage costs money/quota.
2. Amazon / Google / Meta careers often defeat bots; Greenhouse / Lever / Ashby work best.
3. CAPTCHAs still fail without CapSolver + sometimes human help.
4. Scraping can violate site ToS — prefer public ATS APIs; use `--brians` carefully.
5. Tailoring **must not fabricate** experience (`--validation strict` default on full `run`).

---

## License

AGPL-3.0 — same as upstream ApplyPilot.
