"""Scrape public Greenhouse / Lever / Ashby job board APIs.

These are the "hundreds of company career pages" path without browser automation:
each board exposes a JSON API. We normalize into the jobs table for hunt mode.
"""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import httpx
import yaml

from applypilot.config import CONFIG_DIR, load_search_config
import sqlite3

from applypilot.database import get_connection

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_TIMEOUT = 25.0


def load_ats_boards() -> dict:
    path = CONFIG_DIR / "ats_boards.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _title_priority(title: str, keywords: list[str]) -> bool:
    t = (title or "").lower()
    return any(k.lower() in t for k in keywords)


def _exclude_title(title: str, excludes: list[str]) -> bool:
    t = (title or "").lower()
    return any(x.lower() in t for x in excludes if x)


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=_TIMEOUT,
        headers={"User-Agent": _UA, "Accept": "application/json"},
        follow_redirects=True,
    )


# ── Greenhouse ────────────────────────────────────────────────────────────

def fetch_greenhouse_board(token: str, name: str = "") -> list[dict]:
    """GET boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"""
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    jobs: list[dict] = []
    try:
        with _client() as client:
            r = client.get(url, params={"content": "true"})
            if r.status_code != 200:
                log.debug("Greenhouse %s HTTP %s", token, r.status_code)
                return []
            data = r.json()
    except Exception as e:
        log.debug("Greenhouse %s error: %s", token, e)
        return []

    for j in data.get("jobs") or []:
        title = j.get("title") or ""
        abs_url = j.get("absolute_url") or ""
        if not abs_url:
            continue
        loc = ""
        if isinstance(j.get("location"), dict):
            loc = j["location"].get("name") or ""
        # content may be HTML
        content = j.get("content") or j.get("description") or ""
        if isinstance(content, str) and content:
            content = re.sub(r"<[^>]+>", " ", content)
            content = re.sub(r"\s+", " ", content).strip()
        jobs.append({
            "url": abs_url,
            "title": title,
            "salary": None,
            "description": content[:2000] if content else title,
            "location": loc,
            "site": name or f"greenhouse:{token}",
            "full_description": content or None,
            "application_url": abs_url,
            "strategy": "greenhouse_api",
            "company": name or token,
        })
    return jobs


# ── Lever ─────────────────────────────────────────────────────────────────

def fetch_lever_board(company: str, name: str = "") -> list[dict]:
    """GET api.lever.co/v0/postings/{company}?mode=json"""
    url = f"https://api.lever.co/v0/postings/{company}"
    try:
        with _client() as client:
            r = client.get(url, params={"mode": "json"})
            if r.status_code != 200:
                log.debug("Lever %s HTTP %s", company, r.status_code)
                return []
            data = r.json()
    except Exception as e:
        log.debug("Lever %s error: %s", company, e)
        return []

    if not isinstance(data, list):
        return []

    jobs: list[dict] = []
    for j in data:
        title = j.get("text") or j.get("title") or ""
        abs_url = j.get("hostedUrl") or j.get("applyUrl") or ""
        if not abs_url:
            continue
        loc = ""
        cats = j.get("categories") or {}
        if isinstance(cats, dict):
            loc = cats.get("location") or cats.get("commitment") or ""
        desc = j.get("descriptionPlain") or j.get("description") or ""
        if desc:
            desc = re.sub(r"<[^>]+>", " ", str(desc))
            desc = re.sub(r"\s+", " ", desc).strip()
        jobs.append({
            "url": abs_url,
            "title": title,
            "salary": None,
            "description": (desc or title)[:2000],
            "location": loc,
            "site": name or f"lever:{company}",
            "full_description": desc or None,
            "application_url": j.get("applyUrl") or abs_url,
            "strategy": "lever_api",
            "company": name or company,
        })
    return jobs


# ── Ashby ─────────────────────────────────────────────────────────────────

def fetch_ashby_board(board: str, name: str = "") -> list[dict]:
    """GET api.ashbyhq.com/posting-api/job-board/{board}"""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board}"
    try:
        with _client() as client:
            r = client.get(url)
            if r.status_code != 200:
                log.debug("Ashby %s HTTP %s", board, r.status_code)
                return []
            data = r.json()
    except Exception as e:
        log.debug("Ashby %s error: %s", board, e)
        return []

    jobs: list[dict] = []
    for j in data.get("jobs") or []:
        title = j.get("title") or ""
        abs_url = j.get("jobUrl") or j.get("applyUrl") or ""
        if not abs_url:
            continue
        loc = j.get("location") or ""
        if isinstance(loc, dict):
            loc = loc.get("name") or ""
        desc = j.get("descriptionPlain") or j.get("descriptionHtml") or ""
        if desc:
            desc = re.sub(r"<[^>]+>", " ", str(desc))
            desc = re.sub(r"\s+", " ", desc).strip()
        jobs.append({
            "url": abs_url,
            "title": title,
            "salary": None,
            "description": (desc or title)[:2000],
            "location": loc,
            "site": name or f"ashby:{board}",
            "full_description": desc or None,
            "application_url": abs_url,
            "strategy": "ashby_api",
            "company": name or board,
        })
    return jobs


def _store_enriched(jobs: list[dict], site: str, strategy: str) -> tuple[int, int]:
    """Store jobs; if full_description present, also set enrichment fields."""
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    new, dup = 0, 0
    for job in jobs:
        url = job.get("url")
        if not url:
            continue
        try:
            conn.execute(
                "INSERT INTO jobs (url, title, salary, description, location, site, strategy, "
                "discovered_at, full_description, application_url, detail_scraped_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    url,
                    job.get("title"),
                    job.get("salary"),
                    job.get("description"),
                    job.get("location"),
                    site,
                    strategy,
                    now,
                    job.get("full_description"),
                    job.get("application_url") or url,
                    now if job.get("full_description") else None,
                ),
            )
            new += 1
        except sqlite3.IntegrityError:
            dup += 1
            if job.get("full_description"):
                conn.execute(
                    "UPDATE jobs SET full_description=COALESCE(full_description, ?), "
                    "application_url=COALESCE(application_url, ?), "
                    "detail_scraped_at=COALESCE(detail_scraped_at, ?) "
                    "WHERE url=? AND full_description IS NULL",
                    (job.get("full_description"), job.get("application_url") or url, now, url),
                )
        except Exception as e:
            log.debug("store failed %s: %s", url[:60], e)
    conn.commit()
    return new, dup


def run_ats_discovery(workers: int = 8, priority_only: bool = False) -> dict:
    """Crawl all configured Greenhouse/Lever/Ashby boards.

    Args:
        workers: parallel HTTP workers
        priority_only: if True, only keep jobs matching priority title keywords

    Returns:
        stats dict
    """
    cfg = load_ats_boards()
    search_cfg = load_search_config()
    excludes = search_cfg.get("exclude_titles") or []
    priority_kw = cfg.get("priority_title_keywords") or []

    gh = cfg.get("greenhouse") or []
    lv = cfg.get("lever") or []
    ash = cfg.get("ashby") or []

    tasks: list[tuple[str, Any]] = []
    for b in gh:
        tasks.append(("gh", b))
    for b in lv:
        tasks.append(("lv", b))
    for b in ash:
        tasks.append(("ash", b))

    log.info(
        "ATS board crawl: %d greenhouse + %d lever + %d ashby (workers=%d)",
        len(gh), len(lv), len(ash), workers,
    )

    t0 = time.time()
    total_new = total_dup = total_seen = 0
    boards_ok = 0

    def _run(kind: str, board: dict) -> tuple[int, int, int]:
        if kind == "gh":
            jobs = fetch_greenhouse_board(board["token"], board.get("name", ""))
            site = board.get("name") or board["token"]
            strategy = "greenhouse_api"
        elif kind == "lv":
            jobs = fetch_lever_board(board["company"], board.get("name", ""))
            site = board.get("name") or board["company"]
            strategy = "lever_api"
        else:
            jobs = fetch_ashby_board(board["board"], board.get("name", ""))
            site = board.get("name") or board["board"]
            strategy = "ashby_api"

        filtered = []
        for j in jobs:
            title = j.get("title") or ""
            if _exclude_title(title, excludes):
                continue
            if priority_only and priority_kw and not _title_priority(title, priority_kw):
                continue
            filtered.append(j)

        n, d = _store_enriched(filtered, site=site, strategy=strategy)
        return n, d, len(filtered)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {ex.submit(_run, k, b): (k, b) for k, b in tasks}
        for fut in as_completed(futs):
            try:
                n, d, seen = fut.result()
                total_new += n
                total_dup += d
                total_seen += seen
                if seen:
                    boards_ok += 1
            except Exception as e:
                log.debug("Board task failed: %s", e)

    elapsed = time.time() - t0
    stats = {
        "boards": len(tasks),
        "boards_with_jobs": boards_ok,
        "jobs_seen": total_seen,
        "new": total_new,
        "dupes": total_dup,
        "elapsed": elapsed,
    }
    log.info(
        "ATS discovery done in %.1fs: %d new, %d dupes, %d seen across %d boards",
        elapsed, total_new, total_dup, total_seen, boards_ok,
    )
    return stats
