"""Hunt mode: fast poll → score → tailor → optional apply for newly posted roles.

Goal: shrink time-from-post to ready-to-apply (and optionally submitted)
toward ~30 minutes for Greenhouse/Lever/Ashby/Workday boards.

This is NOT magic bypass of Amazon/Google bot defenses — hard ATS sites are
queued for manual or best-effort apply with platform playbooks.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from rich.console import Console

from applypilot.config import load_env, ensure_dirs, DEFAULTS
from applypilot.database import get_connection, init_db, get_stats

log = logging.getLogger(__name__)
console = Console()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def run_discovery_pass(workers: int = 6, include_jobspy: bool = False) -> dict:
    """One discovery pass: ATS boards (+ optional JobSpy/Workday)."""
    stats: dict = {"ats": None, "jobspy": None, "workday": None}

    console.print("  [cyan]ATS boards (Greenhouse / Lever / Ashby)...[/cyan]")
    try:
        from applypilot.discovery.ats_boards import run_ats_discovery
        stats["ats"] = run_ats_discovery(workers=workers, priority_only=False)
        console.print(
            f"    → +{stats['ats'].get('new', 0)} new "
            f"({stats['ats'].get('jobs_seen', 0)} seen, "
            f"{stats['ats'].get('boards_with_jobs', 0)} boards)"
        )
    except Exception as e:
        log.exception("ATS discovery failed")
        stats["ats"] = {"error": str(e)}
        console.print(f"    [red]ATS error:[/red] {e}")

    if include_jobspy:
        console.print("  [cyan]JobSpy boards...[/cyan]")
        try:
            from applypilot.discovery.jobspy import run_discovery
            run_discovery()
            stats["jobspy"] = "ok"
        except Exception as e:
            stats["jobspy"] = f"error: {e}"
            console.print(f"    [red]JobSpy error:[/red] {e}")

        console.print("  [cyan]Workday employers...[/cyan]")
        try:
            from applypilot.discovery.workday import run_workday_discovery
            run_workday_discovery(workers=max(1, workers // 2))
            stats["workday"] = "ok"
        except Exception as e:
            stats["workday"] = f"error: {e}"
            console.print(f"    [red]Workday error:[/red] {e}")

    return stats


def process_new_jobs(
    max_age_minutes: int = 180,
    min_score: int = 7,
    score_limit: int = 40,
    tailor_limit: int = 15,
    validation_mode: str = "normal",
) -> dict:
    """Score + tailor recently discovered jobs only (speed path)."""
    conn = get_connection()
    cutoff = _iso(_utcnow() - timedelta(minutes=max_age_minutes))

    # Count fresh jobs needing score
    pending = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE discovered_at >= ? "
        "AND full_description IS NOT NULL AND fit_score IS NULL",
        (cutoff,),
    ).fetchone()[0]

    console.print(
        f"  [cyan]Fresh jobs (last {max_age_minutes}m) pending score:[/cyan] {pending}"
    )

    scored = tailored = 0
    if pending > 0:
        from applypilot.scoring.scorer import score_job
        from applypilot.resumes import select_resume_for_job
        from applypilot.config import load_profile, RESUME_PATH

        try:
            profile = load_profile()
        except FileNotFoundError:
            profile = {}

        rows = conn.execute(
            "SELECT * FROM jobs WHERE discovered_at >= ? "
            "AND full_description IS NOT NULL AND fit_score IS NULL "
            "ORDER BY discovered_at DESC LIMIT ?",
            (cutoff, score_limit),
        ).fetchall()

        for row in rows:
            job = dict(row)
            try:
                _, resume_text = select_resume_for_job(job, profile)
            except Exception:
                resume_text = RESUME_PATH.read_text(encoding="utf-8") if RESUME_PATH.exists() else ""
            result = score_job(resume_text, job)
            now = _iso(_utcnow())
            conn.execute(
                "UPDATE jobs SET fit_score=?, score_reasoning=?, scored_at=? WHERE url=?",
                (result["score"], result.get("reasoning", ""), now, job["url"]),
            )
            conn.commit()
            scored += 1
            console.print(f"    score={result['score']}  {(job.get('title') or '')[:55]}")

    # Tailor high-scoring fresh jobs
    from applypilot.scoring.tailor import tailor_resume
    from applypilot.resumes import select_resume_for_job
    from applypilot.config import load_profile, TAILORED_DIR
    import re
    from pathlib import Path

    try:
        profile = load_profile()
    except FileNotFoundError:
        console.print("  [red]No profile — skip tailor[/red]")
        return {"scored": scored, "tailored": 0}

    rows = conn.execute(
        "SELECT * FROM jobs WHERE discovered_at >= ? "
        "AND fit_score >= ? AND full_description IS NOT NULL "
        "AND tailored_resume_path IS NULL AND COALESCE(tailor_attempts,0) < 5 "
        "ORDER BY fit_score DESC, discovered_at DESC LIMIT ?",
        (cutoff, min_score, tailor_limit),
    ).fetchall()

    TAILORED_DIR.mkdir(parents=True, exist_ok=True)
    for row in rows:
        job = dict(row)
        try:
            rid, resume_text = select_resume_for_job(job, profile)
            tailored_text, report = tailor_resume(
                resume_text, job, profile, validation_mode=validation_mode,
            )
            if not tailored_text:
                conn.execute(
                    "UPDATE jobs SET tailor_attempts=COALESCE(tailor_attempts,0)+1 WHERE url=?",
                    (job["url"],),
                )
                conn.commit()
                continue

            safe_title = re.sub(r"[^\w\s-]", "", job["title"] or "job")[:50].strip().replace(" ", "_")
            safe_site = re.sub(r"[^\w\s-]", "", job["site"] or "site")[:20].strip().replace(" ", "_")
            path = TAILORED_DIR / f"{safe_site}_{safe_title}.txt"
            path.write_text(tailored_text, encoding="utf-8")
            try:
                from applypilot.scoring.pdf import convert_to_pdf
                convert_to_pdf(path)
            except Exception:
                pass

            now = _iso(_utcnow())
            ok = report.get("status") in ("approved", "approved_with_judge_warning") or bool(tailored_text)
            if ok:
                conn.execute(
                    "UPDATE jobs SET tailored_resume_path=?, tailored_at=?, "
                    "tailor_attempts=COALESCE(tailor_attempts,0)+1 WHERE url=?",
                    (str(path), now, job["url"]),
                )
                tailored += 1
                from applypilot.ats import detect_ats
                ats = detect_ats(job.get("application_url") or job.get("url"))
                console.print(
                    f"    [green]tailored[/green] score={job.get('fit_score')} "
                    f"ats={ats.name} resume={rid}  {(job.get('title') or '')[:40]}"
                )
            else:
                conn.execute(
                    "UPDATE jobs SET tailor_attempts=COALESCE(tailor_attempts,0)+1 WHERE url=?",
                    (job["url"],),
                )
            conn.commit()
        except Exception as e:
            log.error("Tailor failed for %s: %s", job.get("title"), e)
            conn.execute(
                "UPDATE jobs SET tailor_attempts=COALESCE(tailor_attempts,0)+1 WHERE url=?",
                (job["url"],),
            )
            conn.commit()

    return {"scored": scored, "tailored": tailored}


def ready_count(min_score: int = 7) -> int:
    conn = get_connection()
    return conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL "
        "AND applied_at IS NULL AND application_url IS NOT NULL "
        "AND (fit_score IS NULL OR fit_score >= ?)",
        (min_score,),
    ).fetchone()[0]


def run_hunt_loop(
    interval_seconds: int = 300,
    max_age_minutes: int = 180,
    min_score: int = 7,
    workers: int = 6,
    include_jobspy: bool = False,
    auto_apply: bool = False,
    apply_limit: int = 3,
    validation_mode: str = "normal",
    once: bool = False,
) -> None:
    """24/7-style hunt loop (or single pass with once=True)."""
    load_env()
    ensure_dirs()
    init_db()

    console.print()
    console.print("[bold green]ApplyPilot HUNT mode[/bold green]")
    console.print(f"  interval:     {interval_seconds}s")
    console.print(f"  fresh window: {max_age_minutes}m")
    console.print(f"  min score:    {min_score}")
    console.print(f"  jobspy/wd:    {include_jobspy}")
    console.print(f"  auto-apply:   {auto_apply} (limit {apply_limit}/pass)")
    console.print(f"  validation:   {validation_mode}")
    console.print("  Ctrl+C to stop\n")

    pass_num = 0
    while True:
        pass_num += 1
        console.print(f"[bold]── Hunt pass {pass_num} @ {_utcnow().strftime('%H:%M:%S')} ──[/bold]")
        try:
            run_discovery_pass(workers=workers, include_jobspy=include_jobspy)
            result = process_new_jobs(
                max_age_minutes=max_age_minutes,
                min_score=min_score,
                validation_mode=validation_mode,
            )
            ready = ready_count(min_score)
            console.print(
                f"  pass result: scored={result['scored']} tailored={result['tailored']} "
                f"ready_to_apply={ready}"
            )

            if auto_apply and ready > 0:
                from applypilot.config import get_tier
                if get_tier() < 3:
                    console.print(
                        "  [yellow]auto-apply skipped — need Claude login + Chrome (Tier 3)[/yellow]"
                    )
                else:
                    console.print(f"  [cyan]Auto-apply up to {apply_limit}...[/cyan]")
                    from applypilot.apply.launcher import main as apply_main
                    apply_main(
                        limit=apply_limit,
                        min_score=min_score,
                        headless=False,
                        model="haiku",
                        dry_run=False,
                        continuous=False,
                        workers=1,
                    )

            stats = get_stats()
            console.print(
                f"  DB totals: jobs={stats['total']} scored={stats['scored']} "
                f"tailored={stats['tailored']} applied={stats['applied']}"
            )
        except KeyboardInterrupt:
            console.print("\n[yellow]Hunt stopped.[/yellow]")
            return
        except Exception as e:
            log.exception("Hunt pass failed")
            console.print(f"  [red]Pass error:[/red] {e}")

        if once:
            console.print("[dim]Single pass done (--once).[/dim]")
            return

        console.print(f"  [dim]Sleeping {interval_seconds}s...[/dim]\n")
        try:
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            console.print("\n[yellow]Hunt stopped.[/yellow]")
            return
