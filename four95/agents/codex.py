"""Codex adapter: ``codex exec --json`` with the CLI sandbox (read-only or workspace-write)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from four95.agents.base import Agent, AgentResult, AgentTask
from four95.core import pricing
from four95.core.models import (
    AgentIdentity,
    AgentKind,
    Capability,
    InterventionStatus,
    SandboxInfo,
    Usage,
)
from four95.sandbox.base import run_process


@lru_cache(maxsize=1)
def cli_version() -> str | None:
    exe = shutil.which("codex")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    parts = out.stdout.strip().split()
    return parts[-1] if parts else None


class CodexAgent(Agent):
    kind = AgentKind.codex.value

    def check(self) -> tuple[bool, str]:
        exe = shutil.which("codex")
        if not exe:
            return False, "codex CLI not found on PATH"
        return True, f"codex {cli_version() or '?'} at {exe}"

    def build_argv(
        self, task: AgentTask, last_message: Path, schema_file: Path | None
    ) -> list[str]:
        sandbox = "workspace-write" if task.capability is Capability.write else "read-only"
        argv = [
            "codex",
            "exec",
            "--json",
            "--color",
            "never",
            "--skip-git-repo-check",
            "--ephemeral",
            "-s",
            sandbox,
            "-C",
            str(task.cwd),
            "-c",
            "sandbox_workspace_write.network_access=false",
            "-o",
            str(last_message),
        ]
        if self.spec.model:
            argv += ["-m", self.spec.model]
        if self.spec.effort:
            argv += ["-c", f'model_reasoning_effort="{self.spec.effort}"']
        if schema_file is not None:
            argv += ["--output-schema", str(schema_file)]
        argv += list(self.spec.extra_args)
        argv.append("-")
        return argv

    def run(self, task: AgentTask) -> AgentResult:
        identity = AgentIdentity(
            kind=AgentKind.codex,
            name=self.spec.name,
            model=self.spec.model,
            cli_version=cli_version(),
            effort=self.spec.effort,
        )
        writable = task.capability is Capability.write
        sandbox = SandboxInfo(
            backend="codex-sandbox",
            network="denied (sandbox_workspace_write.network_access=false; API traffic excepted)",
            writable_paths=[str(task.cwd)] if writable else [],
            detail=f"codex --sandbox {'workspace-write' if writable else 'read-only'}",
        )
        allowed = ["shell (workspace-write)" if writable else "shell (read-only)"]
        with tempfile.TemporaryDirectory(prefix="495-codex-") as tmp:
            last = Path(tmp) / "last_message.txt"
            schema_file: Path | None = None
            if task.output_schema is not None:
                schema_file = Path(tmp) / "schema.json"
                schema_file.write_text(json.dumps(task.output_schema), encoding="utf-8")
            argv = self.build_argv(task, last, schema_file)
            env = os.environ.copy()
            env.update(task.env)
            prompt = f"{task.system_prompt}\n\n{task.prompt}"
            res = run_process(
                argv,
                task.cwd,
                task.timeout_s,
                env,
                task.stop_check,
                display_command="codex exec ...",
                stdin_text=prompt,
            )
            final_text = last.read_text(encoding="utf-8") if last.exists() else ""
        events = parse_events(res.output)
        usage = usage_from_events(
            events, self.spec.model or _configured_model(), self.spec.context_window
        )
        thread_id = next(
            (e.get("thread_id") for e in events if e.get("type") == "thread.started"), None
        )
        identity.session_id = thread_id if isinstance(thread_id, str) else None
        if not identity.model:
            identity.model = _configured_model()
        if not final_text:
            final_text = _last_agent_message(events)
        status = InterventionStatus.completed
        error = None
        if res.timed_out:
            status, error = InterventionStatus.timed_out, "timeout"
        elif res.interrupted:
            status, error = InterventionStatus.interrupted, "interrupted"
        else:
            failure = next(
                (e for e in events if e.get("type") in ("turn.failed", "error")),
                None,
            )
            if failure is not None:
                status = InterventionStatus.failed
                error = f"codex reported {failure.get('type')}: {json.dumps(failure)[:500]}"
            elif res.exit_code != 0:
                status = InterventionStatus.failed
                error = f"codex exited {res.exit_code}: {res.output[-500:]}"
        structured: dict[str, Any] | None = None
        if task.output_schema is not None and final_text:
            try:
                parsed = json.loads(final_text)
                structured = parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                structured = None
        cost = pricing.estimate(identity.model, usage)
        return AgentResult(
            status=status,
            text=final_text,
            structured=structured,
            usage=usage,
            cost_usd=cost.usd,
            cost_reported=False,
            identity=identity,
            sandbox=sandbox,
            allowed_tools=allowed,
            transcript=res.output,
            exit_code=res.exit_code,
            error=error,
            duration_s=res.duration_s,
            argv=argv,
            activity=summarise_activity(events),
        )


def summarise_activity(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in events:
        item = e.get("item")
        if e.get("type") == "item.completed" and isinstance(item, dict):
            kind = str(item.get("type", "item"))
            counts[kind] = counts.get(kind, 0) + 1
    return counts


@lru_cache(maxsize=1)
def _configured_model() -> str | None:
    cfg = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser() / "config.toml"
    if not cfg.exists():
        return None
    for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("model ") or line.startswith("model="):
            _, _, value = line.partition("=")
            return value.strip().strip('"').strip("'") or None
    return None


def parse_events(output: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            events.append(obj)
    return events


def usage_from_events(events: list[dict[str, Any]], model: str | None, window: int | None) -> Usage:
    total = Usage()
    turns = 0
    for e in events:
        if e.get("type") == "turn.completed" and isinstance(e.get("usage"), dict):
            u = e["usage"]
            turns += 1
            total = total.add(
                Usage(
                    input_tokens=int(u.get("input_tokens", 0)),
                    output_tokens=int(u.get("output_tokens", 0)),
                    cache_read_tokens=int(u.get("cached_input_tokens", 0)),
                    cache_write_tokens=int(u.get("cache_write_input_tokens", 0)),
                    requests=1,
                )
            )
    # Codex reports input tokens summed over the turn's requests; the peak context is bounded by it.
    total.context_window = pricing.context_window(model, window)
    total.context_peak_tokens = total.input_tokens or None
    total.context_peak_is_upper_bound = True
    total.requests = max(turns, 1)
    return total


def _last_agent_message(events: list[dict[str, Any]]) -> str:
    text = ""
    for e in events:
        item = e.get("item")
        if (
            e.get("type") == "item.completed"
            and isinstance(item, dict)
            and item.get("type") == "agent_message"
        ):
            text = str(item.get("text", ""))
    return text
