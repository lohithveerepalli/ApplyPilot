"""Multi-resume library: register, list, and select base resumes by role match.

Users can keep several base resumes (e.g. networking vs. SRE vs. platform)
under ~/.applypilot/resumes/ and tag them with keywords. During scoring and
tailoring, ApplyPilot picks the best-matching resume for each job title/JD.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

from applypilot.config import (
    APP_DIR,
    PROFILE_PATH,
    RESUME_PATH,
    RESUMES_DIR,
    load_profile,
)

log = logging.getLogger(__name__)

# Default filename for the primary resume (also mirrored at RESUME_PATH for
# backward compatibility with older configs / single-resume setups).
DEFAULT_RESUME_ID = "default"


def ensure_resumes_dir() -> Path:
    """Create the resumes library directory if missing."""
    RESUMES_DIR.mkdir(parents=True, exist_ok=True)
    return RESUMES_DIR


def _profile_resumes(profile: dict | None = None) -> list[dict]:
    """Return the resumes[] list from profile (empty if absent)."""
    if profile is None:
        try:
            profile = load_profile()
        except FileNotFoundError:
            return []
    resumes = profile.get("resumes")
    if isinstance(resumes, list):
        return [r for r in resumes if isinstance(r, dict) and r.get("id")]
    return []


def _save_profile_resumes(resumes: list[dict], profile: dict | None = None) -> None:
    """Write resumes[] back into profile.json, preserving other fields."""
    if profile is None:
        profile = load_profile() if PROFILE_PATH.exists() else {}
    profile["resumes"] = resumes
    # Keep a simple default_resume_id pointer for clarity
    default = next((r for r in resumes if r.get("is_default")), None)
    if default:
        profile["default_resume_id"] = default["id"]
    elif resumes:
        profile["default_resume_id"] = resumes[0]["id"]
    PROFILE_PATH.write_text(
        json.dumps(profile, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def list_resumes(profile: dict | None = None) -> list[dict]:
    """List registered base resumes with resolved paths.

    Each entry: {id, label, path, keywords, is_default, exists}
    Falls back to legacy single resume.txt when no multi-resume config exists.
    """
    ensure_resumes_dir()
    registered = _profile_resumes(profile)

    if not registered:
        # Legacy single-resume fallback
        if RESUME_PATH.exists():
            return [{
                "id": DEFAULT_RESUME_ID,
                "label": "Default resume",
                "path": str(RESUME_PATH),
                "keywords": [],
                "is_default": True,
                "exists": True,
            }]
        return []

    results = []
    for r in registered:
        path = _resolve_resume_path(r)
        results.append({
            "id": r["id"],
            "label": r.get("label") or r["id"],
            "path": str(path),
            "keywords": list(r.get("keywords") or []),
            "is_default": bool(r.get("is_default")),
            "exists": path.exists(),
        })
    return results


def _resolve_resume_path(entry: dict) -> Path:
    """Resolve a resume entry path relative to APP_DIR or absolute."""
    raw = entry.get("path") or f"resumes/{entry['id']}.txt"
    p = Path(raw)
    if p.is_absolute():
        return p
    return APP_DIR / p


def get_resume_path(resume_id: str | None = None, profile: dict | None = None) -> Path:
    """Return the filesystem path for a resume id (or the default)."""
    resumes = list_resumes(profile)
    if not resumes:
        return RESUME_PATH

    if resume_id:
        for r in resumes:
            if r["id"] == resume_id:
                return Path(r["path"])
        raise FileNotFoundError(f"Resume id '{resume_id}' not found. Run: applypilot resumes list")

    for r in resumes:
        if r["is_default"]:
            return Path(r["path"])
    return Path(resumes[0]["path"])


def read_resume_text(resume_id: str | None = None, profile: dict | None = None) -> str:
    """Load plain-text content for a resume id (or default)."""
    path = get_resume_path(resume_id, profile)
    if not path.exists():
        raise FileNotFoundError(
            f"Resume file not found: {path}. Add one with `applypilot resumes add` "
            "or re-run `applypilot init`."
        )
    return path.read_text(encoding="utf-8")


def select_resume_for_job(
    job: dict,
    profile: dict | None = None,
) -> tuple[str, str]:
    """Pick the best base resume for a job by keyword match against title + site.

    Matching is case-insensitive substring match of each resume's keywords
    against the job title (weighted higher) and site/description snippet.

    Returns:
        (resume_id, resume_text)
    """
    if profile is None:
        profile = load_profile()

    resumes = list_resumes(profile)
    if not resumes:
        text = RESUME_PATH.read_text(encoding="utf-8") if RESUME_PATH.exists() else ""
        return DEFAULT_RESUME_ID, text

    if len(resumes) == 1:
        rid = resumes[0]["id"]
        return rid, read_resume_text(rid, profile)

    title = (job.get("title") or "").lower()
    site = (job.get("site") or "").lower()
    # Lightweight JD snippet for keyword boost (first 1500 chars)
    desc = (job.get("full_description") or job.get("description") or "")[:1500].lower()
    haystack_title = title
    haystack_rest = f"{site} {desc}"

    best_id = None
    best_score = -1
    default_id = None

    for r in resumes:
        if r["is_default"]:
            default_id = r["id"]
        if not r["exists"]:
            continue

        keywords = [k.lower().strip() for k in (r.get("keywords") or []) if k.strip()]
        if not keywords:
            # No keywords → only use as default fallback
            score = 0
        else:
            score = 0
            for kw in keywords:
                if kw in haystack_title:
                    score += 3
                elif kw in haystack_rest:
                    score += 1
            # Prefer more specific resumes when tied (more keywords that matched)
            matched = sum(1 for kw in keywords if kw in haystack_title or kw in haystack_rest)
            score = score * 10 + matched

        if score > best_score:
            best_score = score
            best_id = r["id"]

    # If nothing matched keywords, use default
    if best_score <= 0:
        best_id = default_id or resumes[0]["id"]

    assert best_id is not None
    log.debug("Selected resume '%s' for job '%s' (score=%s)", best_id, job.get("title"), best_score)
    return best_id, read_resume_text(best_id, profile)


def add_resume(
    source: Path | str,
    resume_id: str | None = None,
    label: str | None = None,
    keywords: list[str] | None = None,
    make_default: bool = False,
    profile: dict | None = None,
) -> dict:
    """Copy a resume file into the library and register it in profile.json.

    Args:
        source: Path to .txt (preferred) resume file.
        resume_id: Stable id (slug). Derived from filename if omitted.
        label: Human label.
        keywords: Match keywords for auto-selection (e.g. network, sre, kubernetes).
        make_default: Mark as the default resume.
        profile: Optional preloaded profile.

    Returns:
        The registered resume entry dict.
    """
    ensure_resumes_dir()
    src = Path(source).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"Resume file not found: {src}")
    if src.suffix.lower() not in (".txt", ".md"):
        raise ValueError("Multi-resume library expects plain-text (.txt). Convert PDFs first.")

    rid = resume_id or re.sub(r"[^\w-]+", "-", src.stem.lower()).strip("-") or "resume"
    rid = rid[:64]

    dest = RESUMES_DIR / f"{rid}.txt"
    shutil.copy2(src, dest)

    # Also keep legacy resume.txt in sync when this is the first/default
    if profile is None:
        profile = load_profile() if PROFILE_PATH.exists() else {}

    resumes = _profile_resumes(profile)
    # Remove existing same id
    resumes = [r for r in resumes if r.get("id") != rid]

    if make_default or not resumes:
        for r in resumes:
            r["is_default"] = False
        is_default = True
    else:
        is_default = False

    entry = {
        "id": rid,
        "label": label or rid.replace("-", " ").title(),
        "path": f"resumes/{rid}.txt",
        "keywords": keywords or [],
        "is_default": is_default,
    }
    resumes.append(entry)

    # If first resume, also copy to legacy RESUME_PATH for back-compat
    if is_default or not RESUME_PATH.exists():
        shutil.copy2(dest, RESUME_PATH)

    _save_profile_resumes(resumes, profile)
    log.info("Registered resume '%s' → %s", rid, dest)
    return entry


def set_default_resume(resume_id: str, profile: dict | None = None) -> None:
    """Mark a resume as the default base resume."""
    if profile is None:
        profile = load_profile()
    resumes = _profile_resumes(profile)
    found = False
    for r in resumes:
        if r["id"] == resume_id:
            r["is_default"] = True
            found = True
        else:
            r["is_default"] = False
    if not found:
        raise FileNotFoundError(f"Resume id '{resume_id}' not registered.")

    path = _resolve_resume_path(next(r for r in resumes if r["id"] == resume_id))
    if path.exists():
        shutil.copy2(path, RESUME_PATH)

    _save_profile_resumes(resumes, profile)


def remove_resume(resume_id: str, delete_file: bool = False, profile: dict | None = None) -> None:
    """Unregister a resume (optionally delete the file from the library)."""
    if profile is None:
        profile = load_profile()
    resumes = _profile_resumes(profile)
    target = next((r for r in resumes if r["id"] == resume_id), None)
    if not target:
        raise FileNotFoundError(f"Resume id '{resume_id}' not registered.")

    if target.get("is_default") and len(resumes) > 1:
        raise ValueError(
            f"Cannot remove default resume '{resume_id}'. "
            "Set another default first: applypilot resumes set-default <id>"
        )

    resumes = [r for r in resumes if r["id"] != resume_id]
    if delete_file:
        path = _resolve_resume_path(target)
        if path.exists() and path.parent == RESUMES_DIR:
            path.unlink()

    _save_profile_resumes(resumes, profile)


def migrate_legacy_resume(profile: dict | None = None) -> dict | None:
    """If only legacy resume.txt exists, register it as the default multi-resume.

    Returns the created entry, or None if nothing to migrate.
    """
    ensure_resumes_dir()
    if profile is None:
        if not PROFILE_PATH.exists():
            return None
        profile = load_profile()

    if _profile_resumes(profile):
        return None  # already multi-resume

    if not RESUME_PATH.exists():
        return None

    dest = RESUMES_DIR / f"{DEFAULT_RESUME_ID}.txt"
    if not dest.exists():
        shutil.copy2(RESUME_PATH, dest)

    entry = {
        "id": DEFAULT_RESUME_ID,
        "label": "Default resume",
        "path": f"resumes/{DEFAULT_RESUME_ID}.txt",
        "keywords": [],
        "is_default": True,
    }
    _save_profile_resumes([entry], profile)
    return entry


# Role presets used by the wizard for infrastructure-focused job searches
INFRA_ROLE_PRESETS: dict[str, dict[str, Any]] = {
    "datacenter-network": {
        "label": "Data Center Network Engineer",
        "titles": [
            "Data Center Network Engineer",
            "Network Engineer Data Center",
            "DC Network Engineer",
            "Network Engineer",
            "Senior Network Engineer",
        ],
        "keywords": [
            "network", "networking", "bgp", "ospf", "evpn", "vxlan",
            "cisco", "arista", "juniper", "data center", "datacenter",
            "switch", "routing", "leaf", "spine",
        ],
        "exclude_extra": ["wireless only", "wifi only", "help desk"],
    },
    "ai-infra": {
        "label": "AI Infrastructure Engineer",
        "titles": [
            "AI Infrastructure Engineer",
            "ML Infrastructure Engineer",
            "AI Platform Engineer",
            "GPU Cluster Engineer",
            "Machine Learning Infrastructure",
        ],
        "keywords": [
            "ai infra", "ml infra", "gpu", "cuda", "kubernetes", "k8s",
            "training cluster", "inference", "mlops", "ray", "slurm",
            "nvidia", "ai platform",
        ],
        "exclude_extra": ["data scientist", "ml researcher", "prompt engineer"],
    },
    "hardware-validation": {
        "label": "Hardware Validation Engineer",
        "titles": [
            "Hardware Validation Engineer",
            "Hardware Test Engineer",
            "Silicon Validation Engineer",
            "System Validation Engineer",
            "Bring-up Engineer",
        ],
        "keywords": [
            "validation", "hardware", "silicon", "bring-up", "bringup",
            "board test", "pcie", "ddr", "fpga", "lab", "oscilloscope",
            "protocol analyzer", "post-silicon",
        ],
        "exclude_extra": ["software qa", "manual tester", "sdet only"],
    },
    "sre": {
        "label": "SRE (Infrastructure)",
        "titles": [
            "Site Reliability Engineer",
            "SRE",
            "Infrastructure SRE",
            "Production Engineer",
            "Reliability Engineer",
        ],
        "keywords": [
            "sre", "site reliability", "reliability", "on-call", "oncall",
            "observability", "prometheus", "terraform", "kubernetes",
            "incident", "sla", "slo", "production engineer",
        ],
        "exclude_extra": ["security analyst only", "soc analyst"],
    },
    "platform": {
        "label": "Platform Engineer",
        "titles": [
            "Platform Engineer",
            "Developer Platform Engineer",
            "Cloud Platform Engineer",
            "Infrastructure Platform Engineer",
            "DevOps Platform Engineer",
        ],
        "keywords": [
            "platform", "developer experience", "devex", "internal tools",
            "paas", "self-service", "terraform", "kubernetes", "ci/cd",
            "github actions", "gitlab", "infrastructure as code",
        ],
        "exclude_extra": ["product manager", "scrum master"],
    },
}


def build_search_queries_for_presets(preset_ids: list[str]) -> list[dict]:
    """Build searches.yaml query entries from role preset ids."""
    queries: list[dict] = []
    seen: set[str] = set()
    for i, pid in enumerate(preset_ids):
        preset = INFRA_ROLE_PRESETS.get(pid)
        if not preset:
            continue
        tier = 1 if i < 2 else 2
        for title in preset["titles"]:
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            queries.append({"query": title, "tier": tier})
    return queries


def default_exclude_titles_for_presets(preset_ids: list[str]) -> list[str]:
    """Merge base excludes with preset-specific noise filters."""
    base = [
        "senior director",
        "VP ",
        "vice president",
        "chief",
        "intern",
        "internship",
        "co-op",
        "clearance required",
        "TS/SCI",
        "principal scientist",
        "sales engineer",
        "account executive",
        "recruiter",
    ]
    extras: list[str] = []
    for pid in preset_ids:
        preset = INFRA_ROLE_PRESETS.get(pid)
        if preset:
            extras.extend(preset.get("exclude_extra") or [])
    # de-dupe preserving order
    out: list[str] = []
    seen: set[str] = set()
    for item in base + extras:
        low = item.lower()
        if low not in seen:
            seen.add(low)
            out.append(item)
    return out
