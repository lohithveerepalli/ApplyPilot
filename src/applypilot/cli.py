"""ApplyPilot CLI — the main entry point."""

from __future__ import annotations

import logging
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from applypilot import __version__

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

app = typer.Typer(
    name="applypilot",
    help="AI-powered end-to-end job application pipeline.",
    no_args_is_help=True,
)
console = Console()
log = logging.getLogger(__name__)

# Valid pipeline stages (in execution order)
VALID_STAGES = ("discover", "enrich", "score", "tailor", "cover", "pdf")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bootstrap() -> None:
    """Common setup: load env, create dirs, init DB."""
    from applypilot.config import load_env, ensure_dirs
    from applypilot.database import init_db

    load_env()
    ensure_dirs()
    init_db()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold]applypilot[/bold] {__version__}")
        raise typer.Exit()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """ApplyPilot — AI-powered end-to-end job application pipeline."""


@app.command()
def init() -> None:
    """Run the first-time setup wizard (profile, resume, search config)."""
    from applypilot.wizard.init import run_wizard

    run_wizard()


@app.command()
def run(
    stages: Optional[list[str]] = typer.Argument(
        None,
        help=(
            "Pipeline stages to run. "
            f"Valid: {', '.join(VALID_STAGES)}, all. "
            "Defaults to 'all' if omitted."
        ),
    ),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score for tailor/cover stages."),
    workers: int = typer.Option(1, "--workers", "-w", help="Parallel threads for discovery/enrichment stages."),
    stream: bool = typer.Option(False, "--stream", help="Run stages concurrently (streaming mode)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview stages without executing."),
    validation: str = typer.Option(
        "strict",
        "--validation",
        help=(
            "Validation strictness for tailor/cover stages. "
            "strict (default): no invented skills/experience; judge must pass. "
            "normal: banned words = warnings; judge warning allowed on last retry. "
            "lenient: banned words ignored, LLM judge skipped (fastest, fewest API calls)."
        ),
    ),
) -> None:
    """Run pipeline stages: discover, enrich, score, tailor, cover, pdf."""
    _bootstrap()

    from applypilot.pipeline import run_pipeline

    stage_list = stages if stages else ["all"]

    # Validate stage names
    for s in stage_list:
        if s != "all" and s not in VALID_STAGES:
            console.print(
                f"[red]Unknown stage:[/red] '{s}'. "
                f"Valid stages: {', '.join(VALID_STAGES)}, all"
            )
            raise typer.Exit(code=1)

    # Gate AI stages behind Tier 2
    llm_stages = {"score", "tailor", "cover"}
    if any(s in stage_list for s in llm_stages) or "all" in stage_list:
        from applypilot.config import check_tier
        check_tier(2, "AI scoring/tailoring")

    # Validate the --validation flag value
    valid_modes = ("strict", "normal", "lenient")
    if validation not in valid_modes:
        console.print(
            f"[red]Invalid --validation value:[/red] '{validation}'. "
            f"Choose from: {', '.join(valid_modes)}"
        )
        raise typer.Exit(code=1)

    result = run_pipeline(
        stages=stage_list,
        min_score=min_score,
        dry_run=dry_run,
        stream=stream,
        workers=workers,
        validation_mode=validation,
    )

    if result.get("errors"):
        raise typer.Exit(code=1)


@app.command()
def apply(
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max applications to submit."),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of parallel browser workers."),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score for job selection."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Agent model (default: backend default)."),
    backend: str = typer.Option(
        "grok", "--backend", "-b",
        help="Apply agent backend: grok (default) or claude.",
    ),
    continuous: bool = typer.Option(False, "--continuous", "-c", help="Run forever, polling for new jobs."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview actions without submitting."),
    headless: bool = typer.Option(True, "--headless/--headed", help="Run browsers headless (default: headless)."),
    url: Optional[str] = typer.Option(None, "--url", help="Apply to a specific job URL."),
    gen: bool = typer.Option(False, "--gen", help="Generate prompt file for manual debugging instead of running."),
    mark_applied: Optional[str] = typer.Option(None, "--mark-applied", help="Manually mark a job URL as applied."),
    mark_failed: Optional[str] = typer.Option(None, "--mark-failed", help="Manually mark a job URL as failed (provide URL)."),
    fail_reason: Optional[str] = typer.Option(None, "--fail-reason", help="Reason for --mark-failed."),
    reset_failed: bool = typer.Option(False, "--reset-failed", help="Reset all failed jobs for retry."),
    poll_interval: int = typer.Option(120, "--poll-interval", help="Seconds between DB polls when queue empty."),
) -> None:
    """Launch auto-apply to submit job applications (Grok Build by default)."""
    _bootstrap()

    from applypilot.config import check_tier, PROFILE_PATH as _profile_path
    from applypilot.database import get_connection

    # --- Utility modes (no Chrome/agent needed) ---

    if mark_applied:
        from applypilot.apply.launcher import mark_job
        mark_job(mark_applied, "applied")
        console.print(f"[green]Marked as applied:[/green] {mark_applied}")
        return

    if mark_failed:
        from applypilot.apply.launcher import mark_job
        mark_job(mark_failed, "failed", reason=fail_reason)
        console.print(f"[yellow]Marked as failed:[/yellow] {mark_failed} ({fail_reason or 'manual'})")
        return

    if reset_failed:
        from applypilot.apply.launcher import reset_failed as do_reset
        count = do_reset()
        console.print(f"[green]Reset {count} failed job(s) for retry.[/green]")
        return

    # --- Full apply mode ---

    backend = backend.strip().lower()
    if backend not in ("grok", "claude"):
        console.print("[red]--backend must be 'grok' or 'claude'[/red]")
        raise typer.Exit(code=1)

    import os
    os.environ["APPLY_BACKEND"] = backend

    # Check 1: Tier 3 required (Grok Build or Claude Code + Chrome + Node)
    check_tier(3, "auto-apply")

    # Check 2: Profile exists
    if not _profile_path.exists():
        console.print(
            "[red]Profile not found.[/red]\n"
            "Run [bold]applypilot init[/bold] to create your profile first."
        )
        raise typer.Exit(code=1)

    # Check 3: Tailored resumes exist (skip for --gen with --url)
    if not (gen and url):
        conn = get_connection()
        ready = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL AND applied_at IS NULL"
        ).fetchone()[0]
        if ready == 0:
            console.print(
                "[red]No tailored resumes ready.[/red]\n"
                "Run [bold]applypilot run score tailor[/bold] first to prepare applications."
            )
            raise typer.Exit(code=1)

    if gen:
        from applypilot.apply.backend import get_backend
        from applypilot.apply.launcher import gen_prompt
        target = url or ""
        if not target:
            console.print("[red]--gen requires --url to specify which job.[/red]")
            raise typer.Exit(code=1)
        b = get_backend(backend)
        prompt_file = gen_prompt(
            target, min_score=min_score, model=model or b.default_model(),
            backend_name=backend,
        )
        if not prompt_file:
            console.print("[red]No matching job found for that URL.[/red]")
            raise typer.Exit(code=1)
        mcp_path = _profile_path.parent / ".mcp-apply-0.json"
        console.print(f"[green]Wrote prompt to:[/green] {prompt_file}")
        console.print(f"\n[bold]Run manually ({backend}):[/bold]")
        if backend == "claude":
            console.print(
                f"  claude --model {model or b.default_model()} -p "
                f"--mcp-config {mcp_path} "
                f"--permission-mode bypassPermissions < {prompt_file}"
            )
        else:
            console.print(
                f"  grok --prompt-file {prompt_file} "
                f"--permission-mode bypassPermissions --always-approve "
                f"--output-format json -m {model or b.default_model()}"
            )
        return

    from applypilot.apply.backend import get_backend
    from applypilot.apply.launcher import main as apply_main

    b = get_backend(backend)
    effective_limit = limit if limit is not None else (0 if continuous else 1)
    resolved_model = model or b.default_model()

    console.print("\n[bold blue]Launching Auto-Apply[/bold blue]")
    console.print(f"  Backend:  {backend}")
    console.print(f"  Limit:    {'unlimited' if continuous else effective_limit}")
    console.print(f"  Workers:  {workers}")
    console.print(f"  Model:    {resolved_model}")
    console.print(f"  Headless: {headless}")
    console.print(f"  Dry run:  {dry_run}")
    console.print(f"  Poll:     {poll_interval}s")
    if url:
        console.print(f"  Target:   {url}")
    console.print()

    apply_main(
        limit=effective_limit,
        target_url=url,
        min_score=min_score,
        headless=headless,
        model=resolved_model,
        dry_run=dry_run,
        continuous=continuous,
        poll_interval=poll_interval,
        workers=workers,
        backend_name=backend,
    )


@app.command()
def status() -> None:
    """Show pipeline statistics and application tracking from the database."""
    _bootstrap()

    from applypilot.database import get_stats, get_application_stats

    stats = get_stats()
    app_stats = get_application_stats()

    console.print("\n[bold]ApplyPilot Pipeline Status[/bold]\n")

    # Application tracking (front and center for volume applicants)
    tracking = Table(title="Application Tracking", show_header=True, header_style="bold green")
    tracking.add_column("Metric", style="bold")
    tracking.add_column("Count", justify="right")

    tracking.add_row("Total applied", str(app_stats["total_applied"]))
    tracking.add_row("Applied today", str(app_stats["applied_today"]))
    tracking.add_row("Failed today", str(app_stats["failed_today"]))
    tracking.add_row("Success (submitted)", str(app_stats["success"]))
    tracking.add_row("Failed", str(app_stats["failed"]))
    tracking.add_row("In progress", str(app_stats["in_progress"]))
    tracking.add_row("Ready to apply", str(app_stats["ready_to_apply"]))
    tracking.add_row("Success rate", f"{app_stats['success_rate_pct']}%")

    console.print(tracking)

    # Summary table
    summary = Table(title="\nPipeline Overview", show_header=True, header_style="bold cyan")
    summary.add_column("Metric", style="bold")
    summary.add_column("Count", justify="right")

    summary.add_row("Total jobs discovered", str(stats["total"]))
    summary.add_row("With full description", str(stats["with_description"]))
    summary.add_row("Pending enrichment", str(stats["pending_detail"]))
    summary.add_row("Enrichment errors", str(stats["detail_errors"]))
    summary.add_row("Scored by LLM", str(stats["scored"]))
    summary.add_row("Pending scoring", str(stats["unscored"]))
    summary.add_row("Tailored resumes", str(stats["tailored"]))
    summary.add_row("Pending tailoring (7+)", str(stats["untailored_eligible"]))
    summary.add_row("Cover letters", str(stats["with_cover_letter"]))
    summary.add_row("Ready to apply", str(stats["ready_to_apply"]))
    summary.add_row("Applied", str(stats["applied"]))
    summary.add_row("Apply errors", str(stats["apply_errors"]))

    console.print(summary)

    # Recent applications
    if app_stats["recent"]:
        recent = Table(title="\nRecent Applications", show_header=True, header_style="bold blue")
        recent.add_column("Title", max_width=40)
        recent.add_column("Site", max_width=16)
        recent.add_column("Status")
        recent.add_column("When", max_width=20)

        for row in app_stats["recent"]:
            status_val = row["status"] or "?"
            if status_val == "applied":
                status_fmt = "[green]applied[/green]"
            elif status_val == "failed":
                status_fmt = "[red]failed[/red]"
            else:
                status_fmt = status_val
            when = row.get("applied_at") or row.get("last_attempted_at") or ""
            if when and len(when) > 19:
                when = when[:19]
            recent.add_row(
                (row.get("title") or "")[:40],
                (row.get("site") or "")[:16],
                status_fmt,
                when,
            )
        console.print(recent)

    # Score distribution
    if stats["score_distribution"]:
        dist_table = Table(title="\nScore Distribution", show_header=True, header_style="bold yellow")
        dist_table.add_column("Score", justify="center")
        dist_table.add_column("Count", justify="right")
        dist_table.add_column("Bar")

        max_count = max(count for _, count in stats["score_distribution"]) or 1
        for score, count in stats["score_distribution"]:
            bar_len = int(count / max_count * 30)
            if score >= 7:
                color = "green"
            elif score >= 5:
                color = "yellow"
            else:
                color = "red"
            bar = f"[{color}]{'=' * bar_len}[/{color}]"
            dist_table.add_row(str(score), str(count), bar)

        console.print(dist_table)

    # By site
    if stats["by_site"]:
        site_table = Table(title="\nJobs by Source", show_header=True, header_style="bold magenta")
        site_table.add_column("Site")
        site_table.add_column("Count", justify="right")

        for site, count in stats["by_site"]:
            site_table.add_row(site or "Unknown", str(count))

        console.print(site_table)

    console.print()


@app.command("track")
def track() -> None:
    """Show application tracking only (totals, today, success/failed)."""
    _bootstrap()

    from applypilot.database import get_application_stats

    app_stats = get_application_stats()

    console.print("\n[bold]Application Tracking[/bold]\n")
    table = Table(show_header=True, header_style="bold green")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Total applied", str(app_stats["total_applied"]))
    table.add_row("Applied today", str(app_stats["applied_today"]))
    table.add_row("Failed today", str(app_stats["failed_today"]))
    table.add_row("Success", str(app_stats["success"]))
    table.add_row("Failed", str(app_stats["failed"]))
    table.add_row("In progress", str(app_stats["in_progress"]))
    table.add_row("Ready to apply", str(app_stats["ready_to_apply"]))
    table.add_row("Success rate", f"{app_stats['success_rate_pct']}%")
    console.print(table)

    if app_stats["recent"]:
        recent = Table(title="\nRecent", show_header=True, header_style="bold blue")
        recent.add_column("Title", max_width=44)
        recent.add_column("Status")
        recent.add_column("When", max_width=20)
        for row in app_stats["recent"]:
            status_val = row["status"] or "?"
            color = "green" if status_val == "applied" else ("red" if status_val == "failed" else "white")
            when = row.get("applied_at") or row.get("last_attempted_at") or ""
            recent.add_row((row.get("title") or "")[:44], f"[{color}]{status_val}[/{color}]", when[:19] if when else "")
        console.print(recent)
    console.print()


# ---------------------------------------------------------------------------
# Multi-resume management
# ---------------------------------------------------------------------------

resumes_app = typer.Typer(help="Manage multiple base resumes (role-tagged library).")
app.add_typer(resumes_app, name="resumes")


@resumes_app.command("list")
def resumes_list() -> None:
    """List registered base resumes."""
    _bootstrap()
    from applypilot.resumes import list_resumes, migrate_legacy_resume

    migrate_legacy_resume()
    items = list_resumes()
    if not items:
        console.print(
            "[yellow]No resumes registered.[/yellow]\n"
            "Add one: [bold]applypilot resumes add path/to/resume.txt --id default[/bold]\n"
            "Or re-run [bold]applypilot init[/bold]."
        )
        return

    table = Table(title="Base Resumes", show_header=True, header_style="bold cyan")
    table.add_column("ID")
    table.add_column("Label")
    table.add_column("Default")
    table.add_column("Keywords")
    table.add_column("File")
    for r in items:
        table.add_row(
            r["id"],
            r["label"],
            "[green]yes[/green]" if r["is_default"] else "",
            ", ".join(r["keywords"][:8]) + ("…" if len(r["keywords"]) > 8 else ""),
            ("[green]ok[/green] " if r["exists"] else "[red]missing[/red] ") + r["path"],
        )
    console.print(table)


@resumes_app.command("add")
def resumes_add(
    path: str = typer.Argument(..., help="Path to plain-text resume (.txt)."),
    resume_id: Optional[str] = typer.Option(None, "--id", help="Stable id (default: filename)."),
    label: Optional[str] = typer.Option(None, "--label", help="Human-readable label."),
    keywords: Optional[str] = typer.Option(
        None,
        "--keywords",
        "-k",
        help="Comma-separated match keywords (e.g. 'network,bgp,sre,kubernetes').",
    ),
    make_default: bool = typer.Option(False, "--default", help="Mark as the default resume."),
) -> None:
    """Add a base resume to the library."""
    _bootstrap()
    from applypilot.resumes import add_resume

    kws = [k.strip() for k in (keywords or "").split(",") if k.strip()]
    try:
        entry = add_resume(
            path,
            resume_id=resume_id,
            label=label,
            keywords=kws,
            make_default=make_default,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[green]Added resume[/green] id=[bold]{entry['id']}[/bold] "
        f"keywords={entry['keywords']} default={entry['is_default']}"
    )


@resumes_app.command("set-default")
def resumes_set_default(
    resume_id: str = typer.Argument(..., help="Resume id to make default."),
) -> None:
    """Set the default base resume."""
    _bootstrap()
    from applypilot.resumes import set_default_resume

    try:
        set_default_resume(resume_id)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Default resume set to[/green] [bold]{resume_id}[/bold]")


@resumes_app.command("remove")
def resumes_remove(
    resume_id: str = typer.Argument(..., help="Resume id to remove."),
    delete_file: bool = typer.Option(False, "--delete-file", help="Also delete the file from ~/.applypilot/resumes/."),
) -> None:
    """Unregister a base resume."""
    _bootstrap()
    from applypilot.resumes import remove_resume

    try:
        remove_resume(resume_id, delete_file=delete_file)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Removed resume[/green] [bold]{resume_id}[/bold]")


@app.command()
def dashboard() -> None:
    """Generate and open the HTML dashboard in your browser."""
    _bootstrap()

    from applypilot.view import open_dashboard

    open_dashboard()


@app.command()
def hunt(
    interval: int = typer.Option(300, "--interval", "-i", help="Seconds between hunt passes (default 5 min)."),
    max_age: int = typer.Option(180, "--max-age", help="Only score/tailor jobs discovered in last N minutes."),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score to tailor/apply."),
    workers: int = typer.Option(4, "--workers", "-w", help="Parallel board fetch workers."),
    full: bool = typer.Option(False, "--full", help="Also run JobSpy + Workday each pass (slower)."),
    brians: bool = typer.Option(False, "--brians", help="Also run Google-dork / Brian-style discovery."),
    apply: bool = typer.Option(False, "--apply", help="Auto-apply ready jobs each pass (needs Tier 3 agent)."),
    apply_limit: int = typer.Option(2, "--apply-limit", help="Max applications per hunt pass."),
    headless: bool = typer.Option(True, "--headless/--headed", help="Headless browser for auto-apply."),
    backend: str = typer.Option("grok", "--backend", "-b", help="Apply agent: grok (default) or claude."),
    validation: str = typer.Option("normal", "--validation", help="strict|normal|lenient for tailoring."),
    once: bool = typer.Option(False, "--once", help="Single pass then exit (good for cron)."),
) -> None:
    """24/7-style hunt: poll ATS boards → score → tailor → optional apply.

    Targets Greenhouse / Lever / Ashby public APIs (dozens of companies) for
    fast discovery. Goal: materials ready within ~10–30 minutes of a new posting.

    Examples:
      applypilot hunt --once -w 4
      applypilot hunt -i 300 --min-score 7
      applypilot hunt --apply --apply-limit 2 --backend grok
      applypilot hunt --brians --once
    """
    _bootstrap()

    if validation not in ("strict", "normal", "lenient"):
        console.print(f"[red]Invalid --validation:[/red] {validation}")
        raise typer.Exit(code=1)

    backend = backend.strip().lower()
    if backend not in ("grok", "claude"):
        console.print("[red]--backend must be 'grok' or 'claude'[/red]")
        raise typer.Exit(code=1)

    import os
    os.environ["APPLY_BACKEND"] = backend

    if apply:
        from applypilot.config import check_tier
        check_tier(3, "hunt --apply")

    from applypilot.hunt import run_hunt_loop

    run_hunt_loop(
        interval_seconds=interval,
        max_age_minutes=max_age,
        min_score=min_score,
        workers=workers,
        include_jobspy=full,
        include_brians=brians,
        auto_apply=apply,
        apply_limit=apply_limit,
        validation_mode=validation,
        once=once,
        headless=headless,
        backend_name=backend,
    )


@app.command()
def daemon(
    interval: int = typer.Option(300, "--interval", "-i", help="Seconds between hunt passes."),
    max_age: int = typer.Option(180, "--max-age", help="Only process jobs discovered in last N minutes."),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score to tailor/apply."),
    workers: int = typer.Option(1, "--workers", "-w", help="Board fetch + apply workers (laptop default: 1)."),
    apply_limit: int = typer.Option(2, "--apply-limit", help="Max applications per hunt pass."),
    backend: str = typer.Option("grok", "--backend", "-b", help="Apply agent: grok or claude."),
    full: bool = typer.Option(False, "--full", help="Also run JobSpy + Workday each pass."),
    brians: bool = typer.Option(False, "--brians", help="Also run Brian-style Google dork discovery."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Hunt + tailor only; never submit."),
    validation: str = typer.Option("normal", "--validation", help="strict|normal|lenient."),
) -> None:
    """24/7 laptop mode: headless hunt + apply loop (low resource defaults).

    Designed to leave an old laptop running forever. Uses headless Chrome,
    a single apply worker, polite intervals, and Grok Build by default.

    Prefer: systemd unit (deploy/applypilot-daemon.service) or ./scripts/run-daemon.sh
    """
    _bootstrap()

    import os
    backend = backend.strip().lower()
    os.environ["APPLY_BACKEND"] = backend

    from applypilot.config import check_tier

    if not dry_run:
        check_tier(3, "daemon auto-apply")
    else:
        check_tier(2, "daemon dry-run")

    console.print("\n[bold green]ApplyPilot DAEMON (24/7 laptop mode)[/bold green]")
    console.print(f"  backend:     {backend}")
    console.print(f"  interval:    {interval}s")
    console.print(f"  workers:     {workers}")
    console.print(f"  apply/limit: {0 if dry_run else apply_limit}/pass")
    console.print(f"  headless:    True")
    console.print(f"  dry_run:     {dry_run}")
    console.print("  Ctrl+C to stop\n")

    from applypilot.hunt import run_hunt_loop

    run_hunt_loop(
        interval_seconds=interval,
        max_age_minutes=max_age,
        min_score=min_score,
        workers=max(1, workers),
        include_jobspy=full,
        include_brians=brians,
        auto_apply=not dry_run,
        apply_limit=apply_limit if not dry_run else 0,
        validation_mode=validation,
        once=False,
        headless=True,
        backend_name=backend,
        apply_workers=1,
    )


@app.command("ats")
def ats_info(
    url: Optional[str] = typer.Argument(None, help="Job URL to classify."),
) -> None:
    """Detect ATS type for a URL, or list configured boards."""
    from applypilot.ats import detect_ats
    from applypilot.discovery.ats_boards import load_ats_boards

    if url:
        info = detect_ats(url)
        console.print(f"URL:  {url}")
        console.print(f"ATS:  [bold]{info.name}[/bold]")
        console.print(f"Difficulty: {info.difficulty}")
        console.print(f"Auto-apply recommended: {info.supports_auto}")
        if info.notes:
            console.print(f"Notes: {info.notes}")
        return

    cfg = load_ats_boards()
    gh = cfg.get("greenhouse") or []
    lv = cfg.get("lever") or []
    ash = cfg.get("ashby") or []
    careers = cfg.get("careers") or []
    console.print(f"Greenhouse boards: {len(gh)}")
    console.print(f"Lever boards:      {len(lv)}")
    console.print(f"Ashby boards:      {len(ash)}")
    console.print(f"Careers targets:   {len(careers)} (hard apply — discovery notes only)")
    console.print("\nEdit registry: src/applypilot/config/ats_boards.yaml")


@app.command()
def doctor() -> None:
    """Check your setup and diagnose missing requirements."""
    import shutil
    from pathlib import Path

    from applypilot.config import (
        load_env, PROFILE_PATH, RESUME_PATH, RESUME_PDF_PATH,
        SEARCH_CONFIG_PATH, ENV_PATH, get_chrome_path,
    )

    load_env()

    ok_mark = "[green]OK[/green]"
    fail_mark = "[red]MISSING[/red]"
    warn_mark = "[yellow]WARN[/yellow]"

    results: list[tuple[str, str, str]] = []  # (check, status, note)

    # --- Tier 1 checks ---
    # Profile
    if PROFILE_PATH.exists():
        results.append(("profile.json", ok_mark, str(PROFILE_PATH)))
    else:
        results.append(("profile.json", fail_mark, "Run 'applypilot init' to create"))

    # Resume (legacy path + multi-resume library)
    from applypilot.resumes import list_resumes, migrate_legacy_resume
    try:
        migrate_legacy_resume()
    except Exception:
        pass
    resume_items = list_resumes()
    if resume_items:
        ok_count = sum(1 for r in resume_items if r["exists"])
        results.append((
            "resumes",
            ok_mark if ok_count else fail_mark,
            f"{ok_count}/{len(resume_items)} registered (applypilot resumes list)",
        ))
    elif RESUME_PATH.exists():
        results.append(("resume.txt", ok_mark, str(RESUME_PATH)))
    elif RESUME_PDF_PATH.exists():
        results.append(("resume.txt", warn_mark, "Only PDF found — plain-text needed for AI stages"))
    else:
        results.append(("resume.txt", fail_mark, "Run 'applypilot init' or 'applypilot resumes add'"))

    # Search config
    if SEARCH_CONFIG_PATH.exists():
        results.append(("searches.yaml", ok_mark, str(SEARCH_CONFIG_PATH)))
    else:
        results.append(("searches.yaml", warn_mark, "Will use example config — run 'applypilot init'"))

    # jobspy (discovery dep installed separately)
    try:
        import jobspy  # noqa: F401
        results.append(("python-jobspy", ok_mark, "Job board scraping available"))
    except ImportError:
        results.append(("python-jobspy", warn_mark,
                        "pip install --no-deps python-jobspy && pip install pydantic tls-client requests markdownify regex"))

    # --- Tier 2 checks ---
    import os
    has_gemini = bool(os.environ.get("GEMINI_API_KEY"))
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_local = bool(os.environ.get("LLM_URL"))
    if has_gemini:
        model = os.environ.get("LLM_MODEL", "gemini-2.0-flash")
        results.append(("LLM API key", ok_mark, f"Gemini ({model})"))
    elif has_openai:
        model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
        results.append(("LLM API key", ok_mark, f"OpenAI ({model})"))
    elif has_local:
        results.append(("LLM API key", ok_mark, f"Local: {os.environ.get('LLM_URL')}"))
    else:
        results.append(("LLM API key", fail_mark,
                        "Set GEMINI_API_KEY in ~/.applypilot/.env (run 'applypilot init')"))

    # --- Tier 3 checks ---
    from applypilot.apply.backend import list_backends
    from applypilot.config import apply_backend_name

    preferred = apply_backend_name()
    results.append(("APPLY_BACKEND", ok_mark, preferred))

    for b in list_backends():
        mark = ok_mark if b["available"] else (
            fail_mark if b["name"] == preferred else warn_mark
        )
        note = b["describe"]
        if b["name"] == preferred and not b["available"]:
            note += " — REQUIRED for auto-apply"
        elif b["name"] != preferred and not b["available"]:
            note += " (optional fallback)"
        results.append((f"Agent: {b['name']}", mark, note))

    # xAI key helps Grok auth when not using OAuth session
    if os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY"):
        results.append(("XAI_API_KEY", ok_mark, "present (Grok API)"))
    else:
        results.append(("XAI_API_KEY", "[dim]optional[/dim]",
                        "Set if Grok CLI needs API key (else use grok login/OAuth)"))

    # Chrome
    try:
        chrome_path = get_chrome_path()
        results.append(("Chrome/Chromium", ok_mark, chrome_path))
    except FileNotFoundError:
        results.append(("Chrome/Chromium", fail_mark,
                        "Install Chrome or set CHROME_PATH env var (needed for auto-apply)"))

    # Node.js / npx (for Playwright MCP)
    npx_bin = shutil.which("npx")
    if npx_bin:
        results.append(("Node.js (npx)", ok_mark, npx_bin))
    else:
        results.append(("Node.js (npx)", fail_mark,
                        "Install Node.js 18+ from nodejs.org (needed for Playwright MCP)"))

    # CapSolver (optional)
    capsolver = os.environ.get("CAPSOLVER_API_KEY")
    if capsolver:
        results.append(("CapSolver API key", ok_mark, "CAPTCHA solving enabled"))
    else:
        results.append(("CapSolver API key", "[dim]optional[/dim]",
                        "Set CAPSOLVER_API_KEY in .env for CAPTCHA solving"))

    # resume-tailor bridge (optional)
    rt_path = os.environ.get("RESUME_TAILOR_PATH", "")
    if rt_path and Path(rt_path).exists():
        results.append(("resume-tailor", ok_mark, rt_path))
    else:
        try:
            import resume_tailor  # noqa: F401
            results.append(("resume-tailor", ok_mark, "importable package"))
        except ImportError:
            results.append(("resume-tailor", "[dim]optional[/dim]",
                            "Set RESUME_TAILOR_PATH or pip install for 1-page Awesome-CV PDFs"))

    # --- Render results ---
    console.print()
    console.print("[bold]ApplyPilot Doctor[/bold]\n")

    col_w = max(len(r[0]) for r in results) + 2
    for check, status, note in results:
        pad = " " * (col_w - len(check))
        console.print(f"  {check}{pad}{status}  [dim]{note}[/dim]")

    console.print()

    # Tier summary
    from applypilot.config import get_tier, TIER_LABELS
    tier = get_tier()
    console.print(f"[bold]Current tier: Tier {tier} — {TIER_LABELS[tier]}[/bold]")

    if tier == 1:
        console.print("[dim]  → Tier 2 unlocks: scoring, tailoring, cover letters (needs LLM API key)[/dim]")
        console.print("[dim]  → Tier 3 unlocks: auto-apply (Grok Build CLI + Chrome + Node.js)[/dim]")
    elif tier == 2:
        console.print("[dim]  → Tier 3 unlocks: auto-apply (Grok Build CLI + Chrome + Node.js)[/dim]")
        console.print("[dim]  → Optional fallback: APPLY_BACKEND=claude with Claude Code CLI[/dim]")
    else:
        console.print("[dim]  → 24/7 laptop mode: applypilot daemon[/dim]")
        console.print("[dim]  → scripts/run-daemon.sh or deploy/applypilot-daemon.service[/dim]")

    console.print()


if __name__ == "__main__":
    app()
