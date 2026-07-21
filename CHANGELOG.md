# Changelog

All notable changes to ApplyPilot will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-07-21

### Added
- **Hunt mode** (`applypilot hunt`) — poll Greenhouse/Lever/Ashby boards on an interval,
  score + tailor only fresh jobs, optional auto-apply (speed path toward ~30 min apply)
- **ATS board scrapers** — public JSON APIs for dozens of company career boards
  (`config/ats_boards.yaml`)
- **Per-ATS apply playbooks** — Greenhouse, Lever, Ashby, Workday, Indeed, Amazon,
  Google, Meta, Microsoft, LinkedIn injected into browser agent prompts
- **`applypilot ats [url]`** — detect ATS type or list configured boards
- Docs: `docs/HUNT_AND_ATS.md`

### Changed
- Full `run discover` also crawls ATS boards alongside JobSpy/Workday

## [0.4.0] - 2026-07-21

Fork-focused release for high-quality technical volume applications
(Data Center Network, AI Infrastructure, Hardware Validation, SRE, Platform).

### Added
- **Multi-resume library** — `~/.applypilot/resumes/` + `profile.json` `resumes[]`
  with keyword-based auto-selection per job (`applypilot resumes list|add|set-default|remove`)
- **Application tracking** — `applypilot track` and enhanced `status` show total applied,
  applied today, failed today, success/failed counts, success rate, and recent apps
- **Infra role presets** in `applypilot init` for network / AI infra / hardware validation /
  SRE / platform search query generation
- **CONFIG.md** written next to user data during init (config map + day-to-day commands)
- **Stricter default validation** — `--validation strict` is now the default for tailor/cover
- Expanded `searches.example.yaml` and `profile.example.json` for infrastructure roles

### Changed
- **Tailoring prompts** — closed skills set; no "closely related tool" padding; under-claim policy
- **LLM judge** — zero-tolerance fabrication policy (Docker≠K8s, AWS≠Terraform, etc.)
- **Setup wizard** — multi-resume registration, clearer skills_boundary guidance, role presets
- **README** — 10-minute setup path for technical users
- Scoring and tailoring both use multi-resume selection when multiple bases are registered

### Fixed
- Judge failure in strict mode no longer silently "approves with warning" on last retry

## [0.2.0] - 2026-02-17

### Added
- **Parallel workers for discovery/enrichment** - `applypilot run --workers N` enables
  ThreadPoolExecutor-based parallelism for Workday scraping, smart extract, and detail
  enrichment. Default is sequential (1); power users can scale up.
- **Apply utility modes** - `--gen` (generate prompt for manual debugging), `--mark-applied`,
  `--mark-failed`, `--reset-failed` flags on `applypilot apply`
- **Dry-run mode** - `applypilot apply --dry-run` fills forms without clicking Submit
- **5 new tracking columns** - `agent_id`, `last_attempted_at`, `apply_duration_ms`,
  `apply_task_id`, `verification_confidence` for better apply-stage observability
- **Manual ATS detection** - `manual_ats` list in `config/sites.yaml` skips sites with
  unsolvable CAPTCHAs (e.g. TCS iBegin)
- **Qwen3 `/no_think` optimization** - automatically saves tokens when using Qwen models
- **`config.DEFAULTS`** - centralized dict for magic numbers (`min_score`, `max_apply_attempts`,
  `poll_interval`, `apply_timeout`, `viewport`)

### Fixed
- **Config YAML not found after install** - moved `config/` into the package at
  `src/applypilot/config/` so YAML files (employers, sites, searches) ship with `pip install`
- **Search config format mismatch** - wizard wrote `searches:` key but discovery code
  expected `queries:` with tier support. Aligned wizard output and example config
- **JobSpy install isolation** - removed python-jobspy from package dependencies due to
  broken numpy==1.26.3 exact pin in jobspy metadata. Installed separately with `--no-deps`
- **Scoring batch limit** - default limit of 50 silently left jobs unscored across runs.
  Changed to no limit (scores all pending jobs in one pass)
- **Missing logging output** - added `logging.basicConfig(INFO)` so per-job progress for
  scoring, tailoring, and cover letters is visible during pipeline runs

### Changed
- **Blocked sites externalized** - moved from hardcoded sets in launcher.py to
  `config/sites.yaml` under `blocked:` key
- **Site base URLs externalized** - moved from hardcoded dict in detail.py to
  `config/sites.yaml` under `base_urls:` key
- **SSO domains externalized** - moved from hardcoded list in prompt.py to
  `config/sites.yaml` under `blocked_sso:` key
- **Prompt improvements** - screening context uses `target_role` from profile,
  salary section includes `currency_conversion_note` and dynamic hourly rate examples
- **`acquire_job()` fixed** - writes `agent_id` and `last_attempted_at` to proper columns
  instead of misusing `apply_error`
- **`profile.example.json`** - added `currency_conversion_note` and `target_role` fields

## [0.1.0] - 2026-02-17

### Added
- 6-stage pipeline: discover, enrich, score, tailor, cover letter, apply
- Multi-source job discovery: Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs
- Workday employer portal support (46 preconfigured employers)
- Direct career site scraping (28 preconfigured sites)
- 3-tier job description extraction cascade (JSON-LD, CSS selectors, AI fallback)
- AI-powered job scoring (1-10 fit scale with rationale)
- Resume tailoring with factual preservation (no fabrication)
- Cover letter generation per job
- Autonomous browser-based application submission via Playwright
- Interactive setup wizard (`applypilot init`)
- Cross-platform Chrome/Chromium detection (Windows, macOS, Linux)
- Multi-provider LLM support (Gemini, OpenAI, local models via OpenAI-compatible endpoints)
- Pipeline stats and HTML results dashboard
- YAML-based configuration for employers, career sites, and search queries
- Job deduplication across sources
- Configurable score threshold filtering
- Safety limits for maximum applications per run
- Detailed application results logging
