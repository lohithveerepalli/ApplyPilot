"""Pluggable auto-apply agent backends (Grok Build default, Claude Code optional)."""

from __future__ import annotations

import os
from typing import Literal

from applypilot.apply.backend.base import (
    AgentRunContext,
    AgentRunResult,
    ApplyBackend,
    parse_result_text,
)
from applypilot.apply.backend.claude import ClaudeBackend
from applypilot.apply.backend.grok import GrokBackend

BackendName = Literal["grok", "claude"]

_BACKENDS: dict[str, type[ApplyBackend]] = {
    "grok": GrokBackend,
    "claude": ClaudeBackend,
}


def get_backend(name: str | None = None) -> ApplyBackend:
    """Return an apply backend instance.

    Resolution order:
      1. Explicit ``name`` argument
      2. ``APPLY_BACKEND`` env (grok|claude)
      3. Default: ``grok``
    """
    key = (name or os.environ.get("APPLY_BACKEND") or "grok").strip().lower()
    if key not in _BACKENDS:
        raise ValueError(
            f"Unknown apply backend '{key}'. Choose from: {', '.join(_BACKENDS)}"
        )
    return _BACKENDS[key]()


def list_backends() -> list[dict]:
    """Describe available backends and whether their CLIs are installed."""
    out = []
    for key, cls in _BACKENDS.items():
        inst = cls()
        out.append({
            "name": key,
            "available": inst.is_available(),
            "default_model": inst.default_model(),
            "describe": inst.describe(),
        })
    return out


__all__ = [
    "AgentRunContext",
    "AgentRunResult",
    "ApplyBackend",
    "ClaudeBackend",
    "GrokBackend",
    "get_backend",
    "list_backends",
    "parse_result_text",
]
