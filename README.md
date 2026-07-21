> **⚠️ ApplyPilot** is originally open-source by [Pickle-Pixel](https://github.com/Pickle-Pixel), first published on GitHub on **February 17, 2026**. This fork improves setup, multi-resume support, stricter tailoring, and application tracking for high-quality technical roles. Not affiliated with applypilot.app or useapplypilot.com.

# ApplyPilot (fork)

**Discover jobs → score fit → tailor resume honestly → cover letter → auto-apply.**  
Tuned for volume applications to technical infrastructure roles — without inventing experience.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-green.svg)](LICENSE)

**Best-fit roles:** Data Center Network Engineer · AI Infrastructure Engineer · Hardware Validation Engineer · SRE (Infrastructure) · Platform Engineer

---

## 10-minute setup

```bash
# 1. Install
pip install -e .                                    # from this repo
# or: pip install applypilot                        # upstream PyPI (missing fork features)
pip install --no-deps python-jobspy
pip install pydantic tls-client requests markdownify regex

# 2. Configure (interactive — resume, profile, role presets, API key)
applypilot init

# 3. Verify
applypilot doctor

# 4. Run pipeline (discover → enrich → score → tailor → cover)
applypilot run -w 4

# 5. Track applications
applypilot track          # total / today / success / failed
applypilot status         # full pipeline + recent apps

# 6. Auto-apply (optional — needs Claude Code + Chrome + Node)
applypilot apply --dry-run
applypilot apply -w 2
```

**Gemini API key (free):** [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

> **Why two install commands for jobspy?** `python-jobspy` pins an exact numpy version that fights pip’s resolver. `--no-deps` + installing its real runtime deps works at runtime.

---

## What you get

| Stage | What happens |
|-------|----------------|
| **1. Discover** | Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs + Workday portals + direct career sites |
| **2. Enrich** | Full JD via JSON-LD → CSS → AI extraction |
| **3. Score** | AI fit score 1–10 against **your** resume (multi-resume aware) |
| **4. Tailor** | Per-job resume rewrite — **strict: no invented tools/experience** |
| **5. Cover** | Targeted cover letter |
| **6. Apply** | Browser agent fills forms, uploads docs, answers questions, submits |

Use stages 1–5 only if you prefer to submit manually.

---

## Two paths

### A) Discovery + tailoring (fastest start)

**Needs:** Python 3.11+, Gemini API key  

```bash
applypilot init
applypilot run -w 4
# Materials land in ~/.applypilot/tailored_resumes/
```

### B) Full auto-apply

**Also needs:** Node.js 18+, Chrome, [Claude Code CLI](https://claude.ai/code)

```bash
applypilot apply --dry-run   # practice
applypilot apply -w 2        # live
```

---

## Configuration map

All user data: **`~/.applypilot/`** (override with `APPLYPILOT_DIR`).

| File / dir | Purpose |
|------------|---------|
| `profile.json` | Contact, work auth, **skills_boundary**, resume_facts, **resumes[]** |
| `resumes/*.txt` | Base resume library (multiple role-tagged resumes) |
| `searches.yaml` | Queries, locations, boards, title excludes |
| `.env` | `GEMINI_API_KEY`, `LLM_MODEL`, optional `CAPSOLVER_API_KEY` |
| `applypilot.db` | Jobs + application tracking |
| `tailored_resumes/` | Per-job outputs + validation reports |
| `CONFIG.md` | Written by `init` — same map, local copy |

Package-shipped registries (edit only if you know why):  
`src/applypilot/config/employers.yaml`, `sites.yaml`, `searches.example.yaml`

### Profile essentials (honest tailoring)

```json
"skills_boundary": {
  "languages": ["Python", "BGP"],
  "infra": ["Linux", "Cisco NX-OS", "Kubernetes"],
  "tools": ["Git", "Terraform", "Wireshark"]
},
"resume_facts": {
  "preserved_companies": ["Acme", "Globex"],
  "preserved_projects": ["Leaf-Spine Fabric"],
  "preserved_school": "State University",
  "real_metrics": ["99.99% uptime", "500-node fabric"]
}
```

Tailoring **may not invent** skills outside `skills_boundary` + your base resume text. Default validation mode is **`strict`**.

---

## Multiple base resumes

Keep separate base resumes for different role families. Scoring and tailoring auto-pick by keyword match on the job title/JD.

```bash
# After init — add more bases
applypilot resumes add ~/resumes/network.txt \
  --id network -k "network,bgp,evpn,cisco,data center" --default

applypilot resumes add ~/resumes/sre.txt \
  --id sre -k "sre,reliability,kubernetes,observability,on-call"

applypilot resumes add ~/resumes/platform.txt \
  --id platform -k "platform,terraform,kubernetes,developer experience"

applypilot resumes list
applypilot resumes set-default network
```

Or declare them in `profile.json` under `resumes[]` (see `profile.example.json`).

---

## Application tracking

```bash
applypilot track
# Total applied | Applied today | Failed today | Success | Failed | Success rate

applypilot status
# Tracking + pipeline funnel + recent applications + score distribution
```

Manual markers (no browser needed):

```bash
applypilot apply --mark-applied 'https://...'
applypilot apply --mark-failed 'https://...' --fail-reason 'captcha'
applypilot apply --reset-failed
```

---

## CLI cheat sheet

```bash
applypilot init                         # setup wizard (role presets + multi-resume)
applypilot doctor                       # diagnose missing deps / config
applypilot run                          # full pipeline stages 1–5
applypilot run discover enrich -w 4     # discovery only, parallel
applypilot run score tailor cover       # AI stages only
applypilot run --min-score 8            # stricter fit gate
applypilot run --validation strict      # default: no fabrication
applypilot run --validation normal      # looser (free-tier friendlier)
applypilot apply                        # auto-apply
applypilot apply --dry-run              # fill forms, don't submit
applypilot apply -w 3 --headless
applypilot track                        # application stats
applypilot status                       # full dashboard in terminal
applypilot dashboard                    # HTML results
applypilot resumes list|add|set-default|remove
```

---

## Role presets (`applypilot init`)

The wizard offers search presets for:

1. **datacenter-network** — Data Center / DC Network Engineer  
2. **ai-infra** — AI / ML Infrastructure, GPU clusters  
3. **hardware-validation** — Hardware / Silicon / System Validation  
4. **sre** — Site Reliability / Production Engineering  
5. **platform** — Platform / Cloud Platform / Developer Platform  

Select any combination; `searches.yaml` is generated with sensible `exclude_titles`.

---

## Requirements

| Component | For | Notes |
|-----------|-----|--------|
| Python 3.11+ | Everything | |
| Gemini API key | Score / tailor / cover | Free tier is enough for most users |
| Node.js 18+ | Auto-apply | `npx` Playwright MCP |
| Chrome | Auto-apply | Or set `CHROME_PATH` |
| Claude Code CLI | Auto-apply | [claude.ai/code](https://claude.ai/code) |
| CapSolver (optional) | CAPTCHAs | Graceful skip if missing |

Also supported: OpenAI, local OpenAI-compatible servers (`LLM_URL`).

---

## Develop from this fork

```bash
git clone https://github.com/lohithveerepalli/ApplyPilot.git
cd ApplyPilot
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pip install --no-deps python-jobspy
pip install pydantic tls-client requests markdownify regex
applypilot init
```

Upstream project: [Pickle-Pixel/ApplyPilot](https://github.com/Pickle-Pixel/ApplyPilot)

---

## License

[GNU Affero General Public License v3.0](LICENSE) — same as upstream.  
If you deploy a modified version as a service, you must release source under AGPL-3.0.
