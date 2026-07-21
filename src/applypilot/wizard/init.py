"""ApplyPilot first-time setup wizard.

Interactive flow that creates ~/.applypilot/ with:
  - resumes/ library (one or more base resumes)
  - profile.json
  - searches.yaml (infra-focused presets available)
  - .env (LLM API key)
  - CONFIG.md (quick reference for where things live)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from applypilot.config import (
    APP_DIR,
    ENV_PATH,
    PROFILE_PATH,
    RESUME_PATH,
    RESUME_PDF_PATH,
    RESUMES_DIR,
    SEARCH_CONFIG_PATH,
    ensure_dirs,
)

console = Console()


# ---------------------------------------------------------------------------
# Resume(s)
# ---------------------------------------------------------------------------

def _setup_resume() -> None:
    """Prompt for one or more base resumes and register them in the library."""
    from applypilot.resumes import add_resume, INFRA_ROLE_PRESETS

    console.print(Panel(
        "[bold]Step 1: Resume(s)[/bold]\n"
        "Add one or more plain-text base resumes (.txt).\n"
        "Multiple resumes let you target different role families\n"
        "(e.g. networking vs SRE vs platform) without inventing experience."
    ))

    first = True
    while True:
        if first:
            path_str = Prompt.ask(
                "Resume file path (.txt preferred; .pdf accepted for upload only)"
            )
        else:
            path_str = Prompt.ask(
                "Another resume path (or press Enter to finish)",
                default="",
            )
            if not path_str.strip():
                break

        src = Path(path_str.strip().strip('"').strip("'")).expanduser().resolve()
        if not src.exists():
            console.print(f"[red]File not found:[/red] {src}")
            if first:
                continue
            break

        suffix = src.suffix.lower()
        if suffix == ".pdf":
            shutil.copy2(src, RESUME_PDF_PATH)
            console.print(f"[green]PDF copied to {RESUME_PDF_PATH}[/green]")
            txt_path_str = Prompt.ask("Plain-text version of this resume (.txt) — required for AI", default="")
            if not txt_path_str.strip():
                console.print("[yellow]Skipping — AI stages need .txt. Add later with: applypilot resumes add[/yellow]")
                if first:
                    continue
                break
            src = Path(txt_path_str.strip().strip('"').strip("'")).expanduser().resolve()
            if not src.exists():
                console.print(f"[red]File not found:[/red] {src}")
                if first:
                    continue
                break
        elif suffix not in (".txt", ".md"):
            console.print("[red]Unsupported format.[/red] Provide a .txt file.")
            if first:
                continue
            break

        default_id = "default" if first else src.stem.lower().replace(" ", "-")[:40]
        rid = Prompt.ask("Resume id (short slug)", default=default_id)
        label = Prompt.ask("Label", default=rid.replace("-", " ").title())

        # Keyword hints from role families
        console.print(
            "[dim]Keywords help auto-select this resume for matching jobs.\n"
            f"Examples: {', '.join(list(INFRA_ROLE_PRESETS.keys())[:5])} "
            "or free-form: network, bgp, sre, kubernetes[/dim]"
        )
        kw_raw = Prompt.ask("Match keywords (comma-separated)", default="")
        keywords = [k.strip() for k in kw_raw.split(",") if k.strip()]

        make_default = first or Confirm.ask(f"Make '{rid}' the default resume?", default=False)
        try:
            entry = add_resume(
                src,
                resume_id=rid,
                label=label,
                keywords=keywords,
                make_default=make_default,
            )
            console.print(
                f"[green]Registered resume[/green] id={entry['id']} → ~/.applypilot/{entry['path']}"
            )
        except Exception as e:
            console.print(f"[red]Failed to add resume:[/red] {e}")
            if first:
                continue

        first = False
        if not Confirm.ask("Add another base resume?", default=False):
            break

    if not RESUME_PATH.exists() and not any(RESUMES_DIR.glob("*.txt")):
        console.print(
            "[yellow]No plain-text resume registered yet.[/yellow] "
            "AI scoring/tailoring will fail until you add one:\n"
            "  [bold]applypilot resumes add path/to/resume.txt --id default[/bold]"
        )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def _setup_profile() -> dict:
    """Walk through profile questions and return a nested profile dict."""
    console.print(Panel(
        "[bold]Step 2: Profile[/bold]\n"
        "Personal data for scoring, tailoring, and form auto-fill.\n"
        "Skills boundary + resume facts keep tailoring honest (no invented experience)."
    ))

    profile: dict = {}

    # Preserve any resumes already registered in step 1
    if PROFILE_PATH.exists():
        try:
            existing = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            if existing.get("resumes"):
                profile["resumes"] = existing["resumes"]
            if existing.get("default_resume_id"):
                profile["default_resume_id"] = existing["default_resume_id"]
        except (json.JSONDecodeError, OSError):
            pass

    # -- Personal --
    console.print("\n[bold cyan]Personal Information[/bold cyan]")
    full_name = Prompt.ask("Full name")
    profile["personal"] = {
        "full_name": full_name,
        "preferred_name": Prompt.ask("Preferred/nickname (leave blank to use first name)", default=""),
        "email": Prompt.ask("Email address"),
        "phone": Prompt.ask("Phone number", default=""),
        "city": Prompt.ask("City"),
        "province_state": Prompt.ask("Province/State (e.g. Ontario, California)", default=""),
        "country": Prompt.ask("Country"),
        "postal_code": Prompt.ask("Postal/ZIP code", default=""),
        "address": Prompt.ask("Street address (optional, used for form auto-fill)", default=""),
        "linkedin_url": Prompt.ask("LinkedIn URL", default=""),
        "github_url": Prompt.ask("GitHub URL (optional)", default=""),
        "portfolio_url": Prompt.ask("Portfolio URL (optional)", default=""),
        "website_url": Prompt.ask("Personal website URL (optional)", default=""),
        "password": Prompt.ask("Job site password (used for login walls during auto-apply)", password=True, default=""),
    }

    # -- Work Authorization --
    console.print("\n[bold cyan]Work Authorization[/bold cyan]")
    profile["work_authorization"] = {
        "legally_authorized_to_work": Confirm.ask("Are you legally authorized to work in your target country?"),
        "require_sponsorship": Confirm.ask("Will you now or in the future need sponsorship?"),
        "work_permit_type": Prompt.ask("Work permit type (e.g. Citizen, PR, Open Work Permit — leave blank if N/A)", default=""),
    }

    # -- Compensation --
    console.print("\n[bold cyan]Compensation[/bold cyan]")
    salary = Prompt.ask("Expected annual salary (number)", default="")
    salary_currency = Prompt.ask("Currency", default="USD")
    salary_range = Prompt.ask("Acceptable range (e.g. 80000-120000)", default="")
    range_parts = salary_range.split("-") if "-" in salary_range else [salary, salary]
    profile["compensation"] = {
        "salary_expectation": salary,
        "salary_currency": salary_currency,
        "salary_range_min": range_parts[0].strip(),
        "salary_range_max": range_parts[1].strip() if len(range_parts) > 1 else range_parts[0].strip(),
    }

    # -- Experience --
    console.print("\n[bold cyan]Experience[/bold cyan]")
    current_title = Prompt.ask("Current/most recent job title", default="")
    target_role = Prompt.ask(
        "Primary target role (e.g. 'Data Center Network Engineer', 'SRE')",
        default=current_title,
    )
    profile["experience"] = {
        "years_of_experience_total": Prompt.ask("Years of professional experience", default=""),
        "education_level": Prompt.ask("Highest education (e.g. Bachelor's, Master's, PhD, Self-taught)", default=""),
        "current_title": current_title,
        "target_role": target_role,
    }

    # -- Skills Boundary (critical for honest tailoring) --
    console.print("\n[bold cyan]Skills Boundary[/bold cyan]")
    console.print(
        "[dim]List ONLY skills you actually have. Tailoring will not invent tools "
        "outside this list + your base resume text.[/dim]"
    )
    langs = Prompt.ask("Languages / protocols (e.g. Python, BGP, SQL)", default="")
    frameworks = Prompt.ask("Frameworks & libraries", default="")
    infra = Prompt.ask("Infra / platform (e.g. Linux, Kubernetes, Cisco NX-OS, AWS)", default="")
    tools = Prompt.ask("Tools (e.g. Git, Terraform, Wireshark, Prometheus)", default="")
    profile["skills_boundary"] = {
        "languages": [s.strip() for s in langs.split(",") if s.strip()],
        "frameworks": [s.strip() for s in frameworks.split(",") if s.strip()],
        "infra": [s.strip() for s in infra.split(",") if s.strip()],
        "tools": [s.strip() for s in tools.split(",") if s.strip()],
    }

    # -- Resume Facts (preserved truths for tailoring) --
    console.print("\n[bold cyan]Resume Facts[/bold cyan]")
    console.print("[dim]Preserved exactly during tailoring — companies, projects, metrics never change.[/dim]")
    companies = Prompt.ask("Companies to always keep (comma-separated)", default="")
    projects = Prompt.ask("Projects to always keep (comma-separated)", default="")
    school = Prompt.ask("School name(s) to preserve", default="")
    metrics = Prompt.ask("Real metrics to preserve (e.g. '99.9% uptime, 500-node fabric')", default="")
    profile["resume_facts"] = {
        "preserved_companies": [s.strip() for s in companies.split(",") if s.strip()],
        "preserved_projects": [s.strip() for s in projects.split(",") if s.strip()],
        "preserved_school": school.strip(),
        "real_metrics": [s.strip() for s in metrics.split(",") if s.strip()],
    }

    # -- EEO Voluntary (defaults) --
    profile["eeo_voluntary"] = {
        "gender": "Decline to self-identify",
        "race_ethnicity": "Decline to self-identify",
        "veteran_status": "Decline to self-identify",
        "disability_status": "Decline to self-identify",
    }

    # -- Availability --
    profile["availability"] = {
        "earliest_start_date": Prompt.ask("Earliest start date", default="Immediately"),
    }

    # -- Tailoring policy note --
    profile["tailoring"] = {
        "strict_no_fabrication": True,
        "notes": "Skills outside skills_boundary + base resume are rejected by validators.",
    }

    PROFILE_PATH.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"\n[green]Profile saved to {PROFILE_PATH}[/green]")
    return profile


# ---------------------------------------------------------------------------
# Search config
# ---------------------------------------------------------------------------

def _setup_searches() -> None:
    """Generate a searches.yaml — with optional infrastructure role presets."""
    from applypilot.resumes import (
        INFRA_ROLE_PRESETS,
        build_search_queries_for_presets,
        default_exclude_titles_for_presets,
    )

    console.print(Panel(
        "[bold]Step 3: Job Search Config[/bold]\n"
        "Define target roles and locations. Infra presets available for faster setup."
    ))

    location = Prompt.ask("Target location (e.g. 'Remote', 'United States', 'Austin, TX')", default="Remote")
    distance_str = Prompt.ask("Search radius in miles (0 for remote-only)", default="0")
    try:
        distance = int(distance_str)
    except ValueError:
        distance = 0

    country = Prompt.ask("Country code for Indeed/LinkedIn (e.g. USA, Canada)", default="USA")

    console.print("\n[bold cyan]Role focus[/bold cyan]")
    console.print("Presets tuned for high-volume technical infrastructure applications:")
    preset_keys = list(INFRA_ROLE_PRESETS.keys())
    for i, key in enumerate(preset_keys, 1):
        console.print(f"  {i}. [bold]{key}[/bold] — {INFRA_ROLE_PRESETS[key]['label']}")
    console.print(f"  {len(preset_keys) + 1}. custom — type your own titles")

    choice = Prompt.ask(
        "Select presets (comma-separated numbers, e.g. 1,4,5) or 'custom'",
        default="1,4,5",
    )

    selected_presets: list[str] = []
    custom_roles: list[str] = []

    if choice.strip().lower() == "custom":
        roles_raw = Prompt.ask(
            "Target job titles (comma-separated)",
            default="Site Reliability Engineer, Platform Engineer",
        )
        custom_roles = [r.strip() for r in roles_raw.split(",") if r.strip()]
    else:
        for part in choice.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                idx = int(part) - 1
                if 0 <= idx < len(preset_keys):
                    selected_presets.append(preset_keys[idx])
                elif idx == len(preset_keys):
                    roles_raw = Prompt.ask("Additional custom titles (comma-separated)", default="")
                    custom_roles.extend(r.strip() for r in roles_raw.split(",") if r.strip())
            except ValueError:
                # allow typing preset key directly
                if part in INFRA_ROLE_PRESETS:
                    selected_presets.append(part)

    if not selected_presets and not custom_roles:
        selected_presets = ["sre", "platform"]
        console.print("[yellow]No roles selected — defaulting to SRE + Platform.[/yellow]")

    queries = build_search_queries_for_presets(selected_presets)
    for i, role in enumerate(custom_roles):
        queries.append({"query": role, "tier": 1 if i < 2 else 2})

    # De-dupe queries
    seen: set[str] = set()
    deduped = []
    for q in queries:
        key = q["query"].lower()
        if key not in seen:
            seen.add(key)
            deduped.append(q)
    queries = deduped

    exclude = default_exclude_titles_for_presets(selected_presets)

    # Build YAML content
    lines = [
        "# ApplyPilot search configuration",
        "# Generated by: applypilot init",
        "# Edit freely — re-run init only if you want to regenerate from scratch.",
        "",
        "defaults:",
        f'  location: "{location}"',
        f"  distance: {distance}",
        "  hours_old: 72",
        "  results_per_site: 50",
        "",
        f'country: "{country}"',
        "",
        "boards:",
        "  - indeed",
        "  - linkedin",
        "  - glassdoor",
        "  - zip_recruiter",
        "  - google",
        "",
        "locations:",
        f'  - location: "{location}"',
        f"    remote: {str(distance == 0).lower()}",
        "",
        "location:",
        "  accept_patterns:",
        f'    - "{location}"',
        '    - "Remote"',
        '    - "Anywhere"',
        '    - "United States"',
        '    - "US"',
        '    - "USA"',
        "  reject_patterns:",
        '    - "India only"',
        '    - "Philippines"',
        '    - "onsite only"',
        "",
        "queries:",
    ]
    for q in queries:
        lines.append(f'  - query: "{q["query"]}"')
        lines.append(f"    tier: {q['tier']}")

    lines.append("")
    lines.append("# Skip noisy / wrong-seniority titles")
    lines.append("exclude_titles:")
    for ex in exclude:
        lines.append(f'  - "{ex}"')
    lines.append("")

    SEARCH_CONFIG_PATH.write_text("\n".join(lines), encoding="utf-8")
    console.print(f"[green]Search config saved to {SEARCH_CONFIG_PATH}[/green]")
    console.print(f"[dim]  {len(queries)} queries from presets={selected_presets or ['custom']}[/dim]")


# ---------------------------------------------------------------------------
# AI Features
# ---------------------------------------------------------------------------

def _setup_ai_features() -> None:
    """Ask about AI scoring/tailoring — optional LLM configuration."""
    console.print(Panel(
        "[bold]Step 4: AI Features (optional)[/bold]\n"
        "An LLM powers job scoring, resume tailoring, and cover letters.\n"
        "Without this, you can still discover and enrich jobs.\n"
        "[dim]Tip: Gemini free tier works well. Tailoring defaults to strict mode.[/dim]"
    ))

    if not Confirm.ask("Enable AI scoring and resume tailoring?", default=True):
        console.print("[dim]Discovery-only mode. Configure AI later by re-running applypilot init.[/dim]")
        return

    console.print("Supported providers: [bold]Gemini[/bold] (recommended, free tier), OpenAI, local (Ollama/llama.cpp)")
    provider = Prompt.ask(
        "Provider",
        choices=["gemini", "openai", "local"],
        default="gemini",
    )

    env_lines = [
        "# ApplyPilot configuration",
        "# Generated by: applypilot init",
        "",
    ]

    if provider == "gemini":
        console.print("[dim]Get a free key: https://aistudio.google.com/apikey[/dim]")
        api_key = Prompt.ask("Gemini API key")
        model = Prompt.ask("Model", default="gemini-2.0-flash")
        env_lines.append(f"GEMINI_API_KEY={api_key}")
        env_lines.append(f"LLM_MODEL={model}")
    elif provider == "openai":
        api_key = Prompt.ask("OpenAI API key")
        model = Prompt.ask("Model", default="gpt-4o-mini")
        env_lines.append(f"OPENAI_API_KEY={api_key}")
        env_lines.append(f"LLM_MODEL={model}")
    elif provider == "local":
        url = Prompt.ask("Local LLM endpoint URL", default="http://localhost:8080/v1")
        model = Prompt.ask("Model name", default="local-model")
        env_lines.append(f"LLM_URL={url}")
        env_lines.append(f"LLM_MODEL={model}")

    env_lines.append("")
    ENV_PATH.write_text("\n".join(env_lines), encoding="utf-8")
    console.print(f"[green]AI configuration saved to {ENV_PATH}[/green]")


# ---------------------------------------------------------------------------
# Auto-Apply
# ---------------------------------------------------------------------------

def _setup_auto_apply() -> None:
    """Configure autonomous job application (requires Claude Code CLI)."""
    console.print(Panel(
        "[bold]Step 5: Auto-Apply (optional)[/bold]\n"
        "Browser agent fills and submits applications using Claude Code + Chrome.\n"
        "You can skip this and still use discovery + tailored resumes manually."
    ))

    if not Confirm.ask("Enable autonomous job applications?", default=True):
        console.print("[dim]Manual apply path: use tailored resumes from ~/.applypilot/tailored_resumes/[/dim]")
        return

    if shutil.which("claude"):
        console.print("[green]Claude Code CLI detected.[/green]")
    else:
        console.print(
            "[yellow]Claude Code CLI not found on PATH.[/yellow]\n"
            "Install: [bold]https://claude.ai/code[/bold]\n"
            "Auto-apply won't work until Claude Code is installed."
        )

    console.print("\n[dim]Some job sites use CAPTCHAs. CapSolver can handle them automatically.[/dim]")
    if Confirm.ask("Configure CapSolver API key? (optional)", default=False):
        capsolver_key = Prompt.ask("CapSolver API key")
        if ENV_PATH.exists():
            existing = ENV_PATH.read_text(encoding="utf-8")
            if "CAPSOLVER_API_KEY" not in existing:
                ENV_PATH.write_text(
                    existing.rstrip() + f"\nCAPSOLVER_API_KEY={capsolver_key}\n",
                    encoding="utf-8",
                )
        else:
            ENV_PATH.write_text(
                f"# ApplyPilot configuration\nCAPSOLVER_API_KEY={capsolver_key}\n",
                encoding="utf-8",
            )
        console.print("[green]CapSolver key saved.[/green]")
    else:
        console.print("[dim]Skipped. Add CAPSOLVER_API_KEY to ~/.applypilot/.env later if needed.[/dim]")


# ---------------------------------------------------------------------------
# Config guide written next to user data
# ---------------------------------------------------------------------------

_CONFIG_GUIDE = """# ApplyPilot config map

Everything user-specific lives in `~/.applypilot/` (override with APPLYPILOT_DIR).

| Path | Purpose |
|------|---------|
| `profile.json` | Identity, work auth, skills_boundary, resume_facts, resumes[] |
| `resumes/*.txt` | Base resume library (multi-resume) |
| `resume.txt` | Legacy/default resume (synced from default library entry) |
| `searches.yaml` | Queries, locations, boards, exclude_titles |
| `.env` | GEMINI_API_KEY / OPENAI_API_KEY / LLM_URL, CAPSOLVER_API_KEY |
| `applypilot.db` | Jobs + application tracking SQLite DB |
| `tailored_resumes/` | Per-job tailored outputs + reports |
| `cover_letters/` | Per-job cover letters |
| `logs/` | Runtime logs |

## Day-to-day commands

```bash
applypilot doctor              # verify setup
applypilot run -w 4            # discover → enrich → score → tailor → cover
applypilot track               # applied total / today / success / failed
applypilot status              # full pipeline + tracking
applypilot apply --dry-run     # fill forms without submit
applypilot apply -w 2          # auto-apply with 2 browsers
applypilot resumes list        # show base resumes
applypilot resumes add r.txt --id sre -k sre,kubernetes --default
```

## Quality knobs

- Tailoring defaults to `--validation strict` (no invented skills/experience).
- Use `--validation normal` only if free-tier models keep failing validation.
- Keep `skills_boundary` and `resume_facts` accurate — they are the truth source.

## Multi-resume tips

Tag each base resume with keywords that appear in target job titles:
- networking: network, bgp, cisco, data center
- sre: sre, reliability, on-call, observability
- platform: platform, kubernetes, terraform, developer experience
- ai-infra: gpu, ml infra, cuda, training cluster
- hardware: validation, silicon, bring-up, pcie
"""


def _write_config_guide() -> None:
    guide_path = APP_DIR / "CONFIG.md"
    guide_path.write_text(_CONFIG_GUIDE, encoding="utf-8")
    console.print(f"[dim]Wrote config map → {guide_path}[/dim]")


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def run_wizard() -> None:
    """Run the full interactive setup wizard."""
    console.print()
    console.print(
        Panel.fit(
            "[bold green]ApplyPilot Setup Wizard[/bold green]\n\n"
            "Creates config at:\n"
            f"  [cyan]{APP_DIR}[/cyan]\n\n"
            "Optimized for technical roles:\n"
            "  Network · AI Infra · Hardware Validation · SRE · Platform\n\n"
            "Re-run anytime: [bold]applypilot init[/bold]",
            border_style="green",
        )
    )

    ensure_dirs()
    console.print(f"[dim]Created {APP_DIR}[/dim]\n")

    _setup_resume()
    console.print()

    _setup_profile()
    console.print()

    _setup_searches()
    console.print()

    _setup_ai_features()
    console.print()

    _setup_auto_apply()
    console.print()

    _write_config_guide()

    from applypilot.config import get_tier, TIER_LABELS, TIER_COMMANDS

    tier = get_tier()

    tier_lines: list[str] = []
    for t in range(1, 4):
        label = TIER_LABELS[t]
        cmds = ", ".join(f"[bold]{c}[/bold]" for c in TIER_COMMANDS[t])
        if t <= tier:
            tier_lines.append(f"  [green]✓ Tier {t} — {label}[/green]  ({cmds})")
        elif t == tier + 1:
            tier_lines.append(f"  [yellow]→ Tier {t} — {label}[/yellow]  ({cmds})")
        else:
            tier_lines.append(f"  [dim]✗ Tier {t} — {label}  ({cmds})[/dim]")

    unlock_hint = ""
    if tier == 1:
        unlock_hint = "\n[dim]Unlock Tier 2: set GEMINI_API_KEY (re-run init).[/dim]"
    elif tier == 2:
        unlock_hint = "\n[dim]Unlock Tier 3: install Claude Code CLI + Chrome + Node.js.[/dim]"

    console.print(
        Panel.fit(
            "[bold green]Setup complete![/bold green]\n\n"
            f"[bold]Your tier: Tier {tier} — {TIER_LABELS[tier]}[/bold]\n\n"
            + "\n".join(tier_lines)
            + unlock_hint
            + "\n\n[bold]Next steps[/bold]\n"
            "  1. [bold]applypilot doctor[/bold]   — verify setup\n"
            "  2. [bold]applypilot run -w 4[/bold] — discover + tailor\n"
            "  3. [bold]applypilot track[/bold]    — watch application stats\n"
            "  4. [bold]applypilot apply --dry-run[/bold] — test auto-apply",
            border_style="green",
        )
    )
