"""Grok Build backend — default auto-apply agent for ApplyPilot.

Uses xAI Grok Build headless mode with project-scoped Playwright MCP
attached to the worker's Chrome CDP port.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

from applypilot import config
from applypilot.apply.backend.base import (
    AgentRunContext,
    AgentRunResult,
    ApplyBackend,
    make_grok_mcp_toml,
    parse_result_text,
)
from applypilot.apply.chrome import _kill_process_tree

logger = logging.getLogger(__name__)


class GrokBackend(ApplyBackend):
    name = "grok"

    def is_available(self) -> bool:
        return self._resolve_bin() is not None

    def _resolve_bin(self) -> str | None:
        explicit = os.environ.get("GROK_BIN")
        if explicit and Path(explicit).exists():
            return explicit
        return shutil.which("grok")

    def default_model(self) -> str:
        # Prefer apply-specific override, then general Grok model, then a sensible default
        return (
            os.environ.get("APPLY_GROK_MODEL")
            or os.environ.get("GROK_MODEL")
            or "grok-4.5"
        )

    def describe(self) -> str:
        path = self._resolve_bin() or "grok (not found)"
        return f"grok ({path})"

    def _write_worker_grok_config(self, worker_dir: Path, cdp_port: int) -> Path:
        """Write .grok/config.toml so this session gets Playwright on the right CDP port."""
        grok_dir = worker_dir / ".grok"
        grok_dir.mkdir(parents=True, exist_ok=True)
        cfg_path = grok_dir / "config.toml"
        cfg_path.write_text(
            make_grok_mcp_toml(cdp_port, config.DEFAULTS["viewport"]),
            encoding="utf-8",
        )
        return cfg_path

    def run(self, ctx: AgentRunContext) -> AgentRunResult:
        grok_bin = self._resolve_bin()
        if not grok_bin:
            return AgentRunResult(
                status="failed:grok_cli_not_found",
                duration_ms=0,
                raw_output="grok CLI not found on PATH. Install Grok Build and ensure `grok` works.",
                backend=self.name,
            )

        worker_dir = ctx.worker_dir
        worker_dir.mkdir(parents=True, exist_ok=True)
        self._write_worker_grok_config(worker_dir, ctx.cdp_port)

        prompt_path = worker_dir / "apply_prompt.txt"
        prompt_path.write_text(ctx.prompt, encoding="utf-8")

        model = ctx.model or self.default_model()
        max_turns = int(os.environ.get("APPLY_MAX_TURNS", "80"))
        timeout = ctx.timeout_seconds or int(
            os.environ.get("APPLY_TIMEOUT", str(config.DEFAULTS["apply_timeout"]))
        )

        # Headless, fully autonomous: prompt-file + bypass permissions + JSON result
        cmd = [
            grok_bin,
            "--prompt-file", str(prompt_path),
            "--cwd", str(worker_dir),
            "--permission-mode", "bypassPermissions",
            "--always-approve",
            "--output-format", "json",
            "--max-turns", str(max_turns),
            "-m", model,
            # Avoid accidental web search burn / distraction during form fill
            "--disable-web-search",
        ]

        env = os.environ.copy()
        # Ensure xAI auth is visible if user put keys only in applypilot .env
        if not env.get("XAI_API_KEY") and not env.get("GROK_API_KEY"):
            # config.load_env should already have run; still try APP_DIR .env via dotenv caller
            pass

        start = time.time()
        proc: subprocess.Popen | None = None
        raw_stdout = ""

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                cwd=str(worker_dir),
            )
            assert proc.stdout

            chunks: list[str] = []
            log_fh = open(ctx.log_path, "a", encoding="utf-8") if ctx.log_path else None
            try:
                if log_fh:
                    log_fh.write(f"[grok] cmd: {' '.join(cmd)}\n")
                for line in proc.stdout:
                    chunks.append(line)
                    if log_fh:
                        log_fh.write(line)
                    # Lightweight progress: surface tool-ish fragments if present
                    if ctx.on_action and ("RESULT:" in line or "browser_" in line.lower()):
                        snippet = line.strip()[:80]
                        if snippet:
                            ctx.on_action(snippet[:35])
            finally:
                if log_fh:
                    log_fh.close()

            try:
                proc.wait(timeout=max(30, timeout))
            except subprocess.TimeoutExpired:
                _kill_process_tree(proc.pid)
                duration_ms = int((time.time() - start) * 1000)
                raw_stdout = "".join(chunks)
                return AgentRunResult(
                    status="failed:timeout",
                    duration_ms=duration_ms,
                    raw_output=raw_stdout,
                    backend=self.name,
                )

            returncode = proc.returncode
            proc = None
            duration_ms = int((time.time() - start) * 1000)
            raw_stdout = "".join(chunks)

            if returncode and returncode < 0:
                return AgentRunResult(
                    status="skipped",
                    duration_ms=duration_ms,
                    raw_output=raw_stdout,
                    backend=self.name,
                )

            text, stats = self._extract_text_and_stats(raw_stdout)
            status = parse_result_text(text if text else raw_stdout)

            # If process failed hard and we got no RESULT, surface exit code
            if status == "failed:no_result_line" and returncode not in (0, None):
                status = f"failed:grok_exit_{returncode}"

            return AgentRunResult(
                status=status,
                duration_ms=duration_ms,
                raw_output=text or raw_stdout,
                cost_usd=float(stats.get("cost_usd") or 0),
                input_tokens=int(stats.get("input_tokens") or 0),
                output_tokens=int(stats.get("output_tokens") or 0),
                turns=int(stats.get("turns") or 0),
                backend=self.name,
                meta={"returncode": returncode},
            )
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.exception("Grok backend failed")
            return AgentRunResult(
                status=f"failed:{str(e)[:100]}",
                duration_ms=duration_ms,
                raw_output=str(e),
                backend=self.name,
            )
        finally:
            if proc is not None and proc.poll() is None:
                _kill_process_tree(proc.pid)

    @staticmethod
    def _extract_text_and_stats(raw: str) -> tuple[str, dict]:
        """Parse Grok headless --output-format json (or fallback plain)."""
        stats: dict = {}
        text = raw
        stripped = raw.strip()
        if not stripped:
            return "", stats

        # Prefer last JSON object (Grok emits one final object for json format)
        candidates = [stripped]
        # Also try last non-empty line if multi-line
        lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
        if lines:
            candidates.append(lines[-1])
            # Sometimes preamble text then JSON
            for i, ln in enumerate(lines):
                if ln.startswith("{"):
                    candidates.append("\n".join(lines[i:]))
                    break

        for cand in candidates:
            try:
                msg = json.loads(cand)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            if msg.get("type") == "error":
                text = msg.get("message") or cand
                return text, stats
            # Success object: { text, usage, num_turns, total_cost_usd, ... }
            if "text" in msg:
                text = msg.get("text") or ""
                usage = msg.get("usage") or {}
                stats = {
                    "input_tokens": usage.get("input_tokens", 0) or 0,
                    "output_tokens": usage.get("output_tokens", 0) or 0,
                    "cost_usd": msg.get("total_cost_usd", 0) or 0,
                    "turns": msg.get("num_turns", 0) or 0,
                }
                return text, stats
            # streaming-json style end event
            if msg.get("type") == "end":
                usage = msg.get("usage") or {}
                stats = {
                    "input_tokens": usage.get("input_tokens", 0) or 0,
                    "output_tokens": usage.get("output_tokens", 0) or 0,
                    "cost_usd": msg.get("total_cost_usd", 0) or 0,
                    "turns": msg.get("num_turns", 0) or 0,
                }
                # text may have been earlier; keep raw for RESULT parse
                return raw, stats

        return raw, stats
