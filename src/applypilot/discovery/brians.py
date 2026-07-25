"""Brian-style Google dork discovery for ATS career pages without public APIs.

Inspired by briansjobsearch.com: build time-bounded site: queries against
known ATS hostnames and either:
  1. SerpAPI (preferred — polite, stable) when SERPAPI_KEY is set
  2. A strongly rate-limited HTTP search fallback (optional, often blocked)

This is an *optional* extra source. Primary discovery remains Greenhouse /
Lever / Ashby public JSON APIs + JobSpy/Workday.
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import quote_plus, urlparse

import requests

from applypilot.config import load_search_config
from applypilot.database import get_connection

log = logging.getLogger(__name__)

# Domains that often lack easy public board APIs (Brian-style surface area)
DEFAULT_ATS_SITES = [
    "jobs.lever.co",
    "boards.greenhouse.io",
    "jobs.ashbyhq.com",
    "jobs.workable.com",
    "*.myworkdayjobs.com",
    "jobs.smartrecruiters.com",
    "apply.workable.com",
    "jobs.jobvite.com",
    "careers.icims.com",
    "*.taleo.net",
    "jobs.bamboohr.com",
    "applytojob.com",
    "recruiting.ultipro.com",
    "jobs.dayforcehcm.com",
]

# Minimum seconds between outbound search requests
MIN_REQUEST_GAP = float(os.environ.get("BRIANS_MIN_GAP_SEC", "8"))


def _queries_from_searches() -> list[str]:
    cfg = load_search_config()
    titles: list[str] = []
    for q in cfg.get("queries") or []:
        if isinstance(q, dict) and q.get("query"):
            titles.append(str(q["query"]).strip())
        elif isinstance(q, str) and q.strip():
            titles.append(q.strip())
    # Fallbacks if searches.yaml empty
    if not titles:
        titles = ["Data Center Technician", "AI Infrastructure", "Hardware Validation"]
    return titles[:12]  # cap per pass


def _site_clause(sites: Iterable[str]) -> str:
    parts = []
    for s in sites:
        s = s.strip()
        if not s:
            continue
        # Google treats bare host; wildcards are approximate
        host = s.replace("*.", "")
        parts.append(f"site:{host}")
    if not parts:
        return ""
    return "(" + " OR ".join(parts) + ")"


def build_dork(title: str, hours: int = 24, location: str = "USA") -> str:
    """Build a Brian-style query string (for SerpAPI or manual use)."""
    site = _site_clause(DEFAULT_ATS_SITES)
    # tbs for time is SerpAPI-specific; free text still helps
    loc = f'"{location}"' if location else ""
    return f'"{title}" {site} {loc}'.strip()


def _store_job(url: str, title: str, site_label: str = "brians") -> bool:
    """Insert job if new. Returns True if inserted."""
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO jobs "
            "(url, title, site, strategy, discovered_at, application_url) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (url, title, site_label, "brians_dork", now, url),
        )
        conn.commit()
        # rowcount is not reliable for IGNORE; check existence path
        row = conn.execute("SELECT strategy FROM jobs WHERE url = ?", (url,)).fetchone()
        return bool(row and row["strategy"] == "brians_dork")
    except Exception:
        log.debug("store failed for %s", url, exc_info=True)
        return False


def _search_serpapi(query: str, num: int = 10) -> list[dict]:
    key = os.environ.get("SERPAPI_KEY")
    if not key:
        return []
    resp = requests.get(
        "https://serpapi.com/search.json",
        params={
            "engine": "google",
            "q": query,
            "num": num,
            "api_key": key,
            "tbs": "qdr:d",  # past day
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    out = []
    for item in data.get("organic_results") or []:
        link = item.get("link") or ""
        title = item.get("title") or "Job"
        if link.startswith("http"):
            out.append({"url": link, "title": title})
    return out


_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)


def _search_duckduckgo_html(query: str) -> list[dict]:
    """Very polite DDG HTML scrape — best-effort, may break."""
    if os.environ.get("BRIANS_ALLOW_SCRAPE", "").lower() not in ("1", "true", "yes"):
        log.info("Brians scrape disabled (set BRIANS_ALLOW_SCRAPE=1 or use SERPAPI_KEY)")
        return []
    headers = {
        "User-Agent": "ApplyPilot-Brians/1.0 (+local job search; polite)",
    }
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    resp = requests.get(url, headers=headers, timeout=25)
    resp.raise_for_status()
    found = []
    for m in _URL_RE.findall(resp.text):
        # DDG wraps redirects; keep direct-looking ATS links
        if any(
            host in m
            for host in (
                "greenhouse.io", "lever.co", "ashbyhq.com", "workable.com",
                "myworkdayjobs.com", "smartrecruiters.com", "jobvite.com",
                "icims.com", "bamboohr.com", "dayforcehcm.com",
            )
        ):
            clean = m.rstrip(").,;\"'")
            found.append({"url": clean, "title": "Job"})
    # de-dupe
    seen = set()
    uniq = []
    for item in found:
        if item["url"] not in seen:
            seen.add(item["url"])
            uniq.append(item)
    return uniq[:15]


def run_brians_discovery(
    hours: int = 24,
    location: str = "USA",
    max_queries: int = 8,
) -> dict:
    """Run one Brian-style discovery pass. Returns stats dict."""
    titles = _queries_from_searches()[:max_queries]
    seen = 0
    new = 0
    errors = 0
    last_req = 0.0

    use_serp = bool(os.environ.get("SERPAPI_KEY"))
    if not use_serp and os.environ.get("BRIANS_ALLOW_SCRAPE", "").lower() not in (
        "1", "true", "yes",
    ):
        log.warning(
            "Brians discovery: set SERPAPI_KEY (recommended) or BRIANS_ALLOW_SCRAPE=1"
        )
        return {"seen": 0, "new": 0, "queries": 0, "skipped": True}

    for title in titles:
        q = build_dork(title, hours=hours, location=location)
        # rate limit
        gap = time.time() - last_req
        if gap < MIN_REQUEST_GAP:
            time.sleep(MIN_REQUEST_GAP - gap)
        try:
            if use_serp:
                results = _search_serpapi(q)
            else:
                results = _search_duckduckgo_html(q)
            last_req = time.time()
        except Exception as e:
            log.warning("Brians query failed for %r: %s", title, e)
            errors += 1
            last_req = time.time()
            continue

        for item in results:
            seen += 1
            host = urlparse(item["url"]).netloc or "brians"
            if _store_job(item["url"], item.get("title") or title, site_label=host[:80]):
                new += 1

    return {"seen": seen, "new": new, "queries": len(titles), "errors": errors}
