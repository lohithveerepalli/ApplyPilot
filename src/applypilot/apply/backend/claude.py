"""Claude Code backend — original ApplyPilot auto-apply agent."""

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
    make_playwright_mcp_config,
    parse_result_text,
)
from applypilot.apply.chrome import _kill_process_tree

logger = logging.getLogger(__name__)

# Gmail tools that must never be used by the apply agent
_GMAIL_DISALLOWED = (
    "mcp__gmail__draft_email,mcp__gmail__modify_email,"
    "mcp__gmail__delete_email,mcp__gmail__download_attachment,"
    "mcp__gmail__batch_modify_emails,mcp__gmail__batch_delete_emails,"
    "mcp__gmail__create_label,mcp__gmail__update_label,"
    "mcp__gmail__delete_label,mcp__gmail__get_or_create_label,"
    "mcp__gmail__list_email_labels,mcp__gmail__create_filter,"
    "mcp__gmail__list_filters,mcp__gmail__get_filter,"
    "mcp__gmail__delete_filter"
)


class ClaudeBackend(ApplyBackend):
    name = "claude"

    def is_available(self) -> bool:
        return shutil.which("claude") is not None

    def default_model(self) -> str:
        return os.environ.get("APPLY_CLAUDE_MODEL", "haiku")

    def describe(self) -> str:
        path = shutil.which("claude") or "claude (not found)"
        return f"claude ({path})"

    def run(self, ctx: AgentRunContext) -> AgentRunResult:
        mcp_config_path = config.APP_DIR / f".mcp-apply-{ctx.worker_id}.json"
        mcp_config_path.write_text(
            json.dumps(make_playwright_mcp_config(ctx.cdp_port, config.DEFAULTS["viewport"])),
            encoding="utf-8",
        )

        model = ctx.model or self.default_model()
        cmd = [
            "claude",
            "--model", model,
            "-p",
            "--mcp-config", str(mcp_config_path),
            "--permission-mode", "bypassPermissions",
            "--no-session-persistence",
            "--disallowedTools", _GMAIL_DISALLOWED,
            "--output-format", "stream-json",
            "--verbose",
            "-",
        ]

        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)

        start = time.time()
        text_parts: list[str] = []
        stats: dict = {}
        proc: subprocess.Popen | None = None

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                cwd=str(ctx.worker_dir),
            )
            assert proc.stdin and proc.stdout
            proc.stdin.write(ctx.prompt)
            proc.stdin.close()

            log_fh = open(ctx.log_path, "a", encoding="utf-8") if ctx.log_path else None
            try:
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        msg_type = msg.get("type")
                        if msg_type == "assistant":
                            for block in msg.get("message", {}).get("content", []):
                                bt = block.get("type")
                                if bt == "text":
                                    text_parts.append(block["text"])
                                    if log_fh:
                                        log_fh.write(block["text"] + "\n")
                                elif bt == "tool_use":
                                    name = (
                                        block.get("name", "")
                                        .replace("mcp__playwright__", "")
                                        .replace("mcp__gmail__", "gmail:")
                                    )
                                    inp = block.get("input", {})
                                    if "url" in inp:
                                        desc = f"{name} {inp['url'][:60]}"
                                    elif "ref" in inp:
                                        desc = f"{name} {inp.get('element', inp.get('text', ''))}"[:50]
                                    elif "fields" in inp:
                                        desc = f"{name} ({len(inp['fields'])} fields)"
                                    elif "paths" in inp:
                                        desc = f"{name} upload"
                                    else:
                                        desc = name
                                    if log_fh:
                                        log_fh.write(f"  >> {desc}\n")
                                    if ctx.on_action:
                                        ctx.on_action(desc[:35])
                        elif msg_type == "result":
                            stats = {
                                "input_tokens": msg.get("usage", {}).get("input_tokens", 0),
                                "output_tokens": msg.get("usage", {}).get("output_tokens", 0),
                                "cost_usd": msg.get("total_cost_usd", 0) or 0,
                                "turns": msg.get("num_turns", 0),
                            }
                            text_parts.append(msg.get("result", "") or "")
                    except json.JSONDecodeError:
                        text_parts.append(line)
                        if log_fh:
                            log_fh.write(line + "\n")
            finally:
                if log_fh:
                    log_fh.close()

            try:
                proc.wait(timeout=max(30, ctx.timeout_seconds))
            except subprocess.TimeoutExpired:
                _kill_process_tree(proc.pid)
                duration_ms = int((time.time() - start) * 1000)
                return AgentRunResult(
                    status="failed:timeout",
                    duration_ms=duration_ms,
                    raw_output="\n".join(text_parts),
                    backend=self.name,
                )

            returncode = proc.returncode
            proc = None
            duration_ms = int((time.time() - start) * 1000)
            output = "\n".join(text_parts)

            if returncode and returncode < 0:
                return AgentRunResult(
                    status="skipped",
                    duration_ms=duration_ms,
                    raw_output=output,
                    backend=self.name,
                )

            status = parse_result_text(output)
            return AgentRunResult(
                status=status,
                duration_ms=duration_ms,
                raw_output=output,
                cost_usd=float(stats.get("cost_usd") or 0),
                input_tokens=int(stats.get("input_tokens") or 0),
                output_tokens=int(stats.get("output_tokens") or 0),
                turns=int(stats.get("turns") or 0),
                backend=self.name,
            )
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.exception("Claude backend failed")
            return AgentRunResult(
                status=f"failed:{str(e)[:100]}",
                duration_ms=duration_ms,
                raw_output=str(e),
                backend=self.name,
            )
        finally:
            if proc is not None and proc.poll() is None:
                _kill_process_tree(proc.pid)
