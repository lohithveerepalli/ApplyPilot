"""Detect which ATS / careers platform a job URL uses."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class AtsInfo:
    """Detected ATS metadata for a job URL."""

    name: str                 # greenhouse | lever | ashby | workday | amazon | ...
    difficulty: str           # easy | medium | hard | manual
    supports_auto: bool       # whether auto-apply is recommended
    notes: str = ""


# Order matters: more specific domains first
_RULES: list[tuple[str, AtsInfo]] = [
    ("boards.greenhouse.io", AtsInfo("greenhouse", "easy", True, "Standard Greenhouse embed")),
    ("greenhouse.io", AtsInfo("greenhouse", "easy", True, "Greenhouse board/API")),
    ("jobs.lever.co", AtsInfo("lever", "easy", True, "Lever postings")),
    ("lever.co", AtsInfo("lever", "easy", True, "Lever")),
    ("jobs.ashbyhq.com", AtsInfo("ashby", "easy", True, "Ashby job board")),
    ("ashbyhq.com", AtsInfo("ashby", "easy", True, "Ashby")),
    ("myworkdayjobs.com", AtsInfo("workday", "medium", True, "Workday CXS portal")),
    ("workdayjobs.com", AtsInfo("workday", "medium", True, "Workday")),
    ("wd1.myworkday", AtsInfo("workday", "medium", True)),
    ("wd2.myworkday", AtsInfo("workday", "medium", True)),
    ("wd3.myworkday", AtsInfo("workday", "medium", True)),
    ("wd5.myworkday", AtsInfo("workday", "medium", True)),
    ("smartrecruiters.com", AtsInfo("smartrecruiters", "medium", True)),
    ("icims.com", AtsInfo("icims", "medium", True)),
    ("successfactors", AtsInfo("successfactors", "hard", False, "SAP SF — flaky automation")),
    ("taleo", AtsInfo("taleo", "hard", False)),
    ("jobvite.com", AtsInfo("jobvite", "medium", True)),
    ("bamboohr.com", AtsInfo("bamboohr", "medium", True)),
    ("applytojob.com", AtsInfo("jazzhr", "medium", True)),
    ("amazon.jobs", AtsInfo("amazon", "hard", False, "Custom Amazon careers — high bot defense")),
    ("careers.google.com", AtsInfo("google", "hard", False, "Google careers — often blocked for bots")),
    ("google.com/about/careers", AtsInfo("google", "hard", False)),
    ("metacareers.com", AtsInfo("meta", "hard", False, "Meta careers — login walls common")),
    ("facebook.com/careers", AtsInfo("meta", "hard", False)),
    ("jobs.careers.microsoft.com", AtsInfo("microsoft", "hard", False)),
    ("careers.microsoft.com", AtsInfo("microsoft", "hard", False)),
    ("jobs.apple.com", AtsInfo("apple", "hard", False)),
    ("careers.nvidia.com", AtsInfo("workday", "medium", True, "NVIDIA often Workday-backed")),
    ("indeed.com", AtsInfo("indeed", "medium", True, "Indeed Easy Apply / company redirect")),
    ("linkedin.com", AtsInfo("linkedin", "hard", False, "LinkedIn Easy Apply needs logged-in session")),
    ("glassdoor.com", AtsInfo("glassdoor", "hard", False)),
    ("ziprecruiter.com", AtsInfo("ziprecruiter", "medium", True)),
]


def detect_ats(url: str | None) -> AtsInfo:
    """Return ATS info for a job or application URL."""
    if not url:
        return AtsInfo("unknown", "hard", False, "No URL")

    raw = url.lower().strip()
    host = urlparse(raw).netloc or raw

    for needle, info in _RULES:
        if needle in raw or needle in host:
            return info

    return AtsInfo("unknown", "medium", True, "Generic form — use generic browser agent")
