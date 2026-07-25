"""Optional bridge to the user's resume-tailor project for 1-page PDFs.

If resume-tailor is importable (or RESUME_TAILOR_PATH is set), use its
pipeline for the final upload PDF. Otherwise fall back to ApplyPilot's
built-in text→PDF renderer.

Repo: https://github.com/lohithveerepalli/resume-tailor
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def _ensure_resume_tailor_on_path() -> bool:
    """Add RESUME_TAILOR_PATH/src to sys.path if configured."""
    raw = os.environ.get("RESUME_TAILOR_PATH", "").strip()
    if not raw:
        return False
    root = Path(raw).expanduser().resolve()
    src = root / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))
        return True
    if (root / "resume_tailor").is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))
        return True
    return root.exists()


def resume_tailor_available() -> bool:
    _ensure_resume_tailor_on_path()
    try:
        import resume_tailor  # noqa: F401
        return True
    except ImportError:
        return False


def try_compile_one_page_pdf(
    plain_text_resume: str,
    job_description: str,
    output_pdf: Path,
    *,
    master_path: Optional[Path] = None,
) -> Optional[Path]:
    """Attempt resume-tailor 1-page PDF. Returns path on success, else None.

    Note: full ATS rewrite via resume-tailor requires a structured master YAML.
    When only plain text is available we still try ReportLab one-page compile
    through resume_tailor.pdf_render if present; otherwise return None and let
    ApplyPilot's scoring.pdf handle it.
    """
    _ensure_resume_tailor_on_path()
    try:
        from resume_tailor.pdf_render import compile_one_page_pdf  # type: ignore
    except ImportError:
        log.debug("resume-tailor not available for PDF compile")
        return None

    try:
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        # Prefer structured pipeline when master YAML is known
        master = master_path or _default_master()
        if master and master.exists():
            try:
                from resume_tailor.pipeline import tailor_and_compile  # type: ignore

                result = tailor_and_compile(
                    master_path=master,
                    job_description=job_description or plain_text_resume,
                    output_dir=output_pdf.parent,
                )
                if result.pdf_path and Path(result.pdf_path).exists():
                    dest = Path(output_pdf)
                    data = Path(result.pdf_path).read_bytes()
                    dest.write_bytes(data)
                    log.info("resume-tailor PDF written: %s", dest)
                    return dest
            except Exception:
                log.exception("resume-tailor full pipeline failed; trying simple PDF")

        # Lightweight: if API accepts text — not all versions do; best-effort skip
        log.info(
            "resume-tailor present but no master YAML — using ApplyPilot PDF path"
        )
        return None
    except Exception:
        log.exception("resume-tailor bridge failed")
        return None


def _default_master() -> Optional[Path]:
    raw = os.environ.get("RESUME_TAILOR_MASTER", "").strip()
    if raw:
        p = Path(raw).expanduser()
        if p.exists():
            return p
    rt = os.environ.get("RESUME_TAILOR_PATH", "").strip()
    if rt:
        for candidate in (
            Path(rt) / "data" / "master_resume.yaml",
            Path(rt) / "data" / "profiles",
        ):
            if candidate.is_file():
                return candidate
            if candidate.is_dir():
                yamls = sorted(candidate.glob("*.yaml"))
                if yamls:
                    return yamls[0]
    return None
