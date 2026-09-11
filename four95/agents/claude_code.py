"""Claude Code adapter: ``claude -p`` with JSON output, restricted tools and the CLI sandbox."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from functools import lru_cache
from typing import Any

from four95.agents.base import Agent, AgentResult, AgentTask
from four95.core.models import (
    AgentIdentity,
    AgentKind,
    Capability,
    InterventionStatus,
    Role,
    SandboxInfo,
    Usage,
)
from four95.sandbox.base import run_process

READ_ONLY_BASH = [
    "Bash(ls *)",
    "Bash(ls)",
    "Bash(cat *)",
    "Bash(head *)",
    "Bash(tail *)",
    "Bash(wc *)",
    "Bash(find *)",
    "Bash(grep *)",
    "Bash(rg *)",
    "Bash(sed -n *)",
    "Bash(tree *)",
    "Bash(git diff *)",
    "Bash(git log *)",
    "Bash(git show *)",
    "Bash(git status *)",
    "Bash(git status)",
    "Bash(git blame *)",
    "Bash(git ls-files *)",
    "Bash(git ls-files)",
    "Bash(git rev-parse *)",
]

AUTOMATION_ENV = {
    "DISABLE_AUTOUPDATER": "1",
    "DISABLE_TELEMETRY": "1",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
}


@lru_cache(maxsize=1)
def cli_version() -> str | None:
    exe = shutil.which("claude")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip().split()[0] if out.stdout.strip() else None


class ClaudeCodeAgent(Agent):
    kind = AgentKind.claude_code.value

    def check(self) -> tuple[bool, str]:
        exe = shutil.which("claude")
        if not exe:
            return False, "claude CLI not found on PATH"
        version = cli_version()
        return True, f"claude {version or '?'} at {exe}"

    def tools_for(self, task: AgentTask) -> tuple[list[str], list[str], str]:
        """Return (--tools list, --allowedTools list, permission mode)."""
        if task.capability is Capability.write:
            tools = ["Bash", "Edit", "Write", "Read"]
            allowed = ["Bash", "Edit", "Write", "Read"]
            return tools, allowed, "acceptEdits"
        tools = ["Bash", "Read"]
        return tools, ["Read", *READ_ONLY_BASH], "dontAsk"

    def sandbox_settings(self, task: AgentTask) -> dict[str, Any]:
        return {
            "sandbox": {
                "enabled": True,
                "autoAllowBashIfSandboxed": False,
                "network": {"allowedDomains": []},
            },
            "permissions": {
                "defaultMode": "acceptEdits" if task.capability is Capability.write else "dontAsk"
            },
        }

    def build_argv(self, task: AgentTask) -> tuple[list[str], list[str]]:
        tools, allowed, mode = self.tools_for(task)
        argv = [
            "claude",
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            mode,
            "--permission-prompts",
            "none",
            "--no-session-persistence",
            "--setting-sources",
            "project",
            "--strict-mcp-config",
            "--tools",
            ",".join(tools),
            "--allowedTools",
            *allowed,
            "--disallowedTools",
            "WebFetch",
            "WebSearch",
            "Task",
            "Agent",
            "Skill",
            "--settings",
            json.dumps(self.sandbox_settings(task)),
            "--append-system-prompt",
            task.system_prompt,
        ]
        if self.spec.model:
            argv += ["--model", self.spec.model]
        if self.spec.effort:
            argv += ["--effort", self.spec.effort]
        if task.max_budget_usd is not None:
            argv += ["--max-budget-usd", f"{task.max_budget_usd:.4f}"]
        if task.output_schema is not None:
            argv += ["--json-schema", json.dumps(task.output_schema)]
        argv += list(self.spec.extra_args)
        return argv, allowed

    def run(self, task: AgentTask) -> AgentResult:
        argv, allowed = self.build_argv(task)
        env = os.environ.copy()
        env.update(AUTOMATION_ENV)
        env.update(task.env)
        identity = AgentIdentity(
            kind=AgentKind.claude_code,
            name=self.spec.name,
            model=self.spec.model,
            cli_version=cli_version(),
            effort=self.spec.effort,
        )
        sandbox = SandboxInfo(
            backend="claude-code-sandbox",
            network="denied (sandbox.network.allowedDomains=[]; API traffic excepted)",
            writable_paths=[str(task.cwd)] if task.capability is Capability.write else [],
            detail=(
                "Claude Code built-in sandbox, permission prompts disabled, tools restricted to "
                + ",".join(allowed)
            ),
        )
        res = run_process(
            argv,
            task.cwd,
            task.timeout_s,
            env,
            task.stop_check,
            display_command="claude -p ...",
            stdin_text=task.prompt,
        )
        if res.timed_out:
            return self._result(
                InterventionStatus.timed_out,
                res.output,
                None,
                identity,
                sandbox,
                allowed,
                res,
                "timeout",
            )
        if res.interrupted:
            return self._result(
                InterventionStatus.interrupted,
                res.output,
                None,
                identity,
                sandbox,
                allowed,
                res,
                "interrupted",
            )
        payload = _extract_json(res.output)
        if payload is None:
            return self._result(
                InterventionStatus.failed,
                res.output,
                None,
                identity,
                sandbox,
                allowed,
                res,
                f"claude exited {res.exit_code} without a JSON result",
            )
        usage = parse_usage(payload)
        peak, requests = peak_from_stream(res.output)
        if peak:
            usage.context_peak_tokens = peak
            usage.context_peak_is_upper_bound = False
            usage.requests = max(requests, 1)
        identity.session_id = payload.get("session_id")
        if not identity.model:
            models = list((payload.get("modelUsage") or {}).keys())
            identity.model = models[0] if models else None
        cost = payload.get("total_cost_usd")
        text = payload.get("result") or ""
        structured = payload.get("structured_output")
        status = InterventionStatus.completed
        error = None
        subtype = payload.get("subtype", "")
        if payload.get("is_error") or res.exit_code not in (0, None):
            status = InterventionStatus.failed
            error = f"claude reported {subtype or 'error'}: {text[:500]}"
        if "budget" in subtype or "max_budget" in subtype:
            status = InterventionStatus.budget_exceeded
            error = f"claude stopped: {subtype}"
        return AgentResult(
            status=status,
            text=text,
            structured=structured if isinstance(structured, dict) else None,
            usage=usage,
            cost_usd=float(cost) if isinstance(cost, int | float) else None,
            cost_reported=isinstance(cost, int | float),
            identity=identity,
            sandbox=sandbox,
            allowed_tools=allowed,
            transcript=res.output,
            exit_code=res.exit_code,
            error=error,
            duration_s=res.duration_s,
            argv=argv,
            activity=summarise_activity(res.output),
        )

    @staticmethod
    def _result(
        status: InterventionStatus,
        transcript: str,
        structured: dict[str, Any] | None,
        identity: AgentIdentity,
        sandbox: SandboxInfo,
        allowed: list[str],
        res: Any,
        error: str,
    ) -> AgentResult:
        return AgentResult(
            status=status,
            text="",
            structured=structured,
            usage=Usage(),
            cost_usd=None,
            cost_reported=False,
            identity=identity,
            sandbox=sandbox,
            allowed_tools=allowed,
            transcript=transcript,
            exit_code=res.exit_code,
            error=error,
            duration_s=res.duration_s,
        )


def _extract_json(output: str) -> dict[str, Any] | None:
    """The final ``result`` event is the last JSON line whose ``type`` is ``result``.

    ``stream-json`` prints one event per line (init, assistant, user, tool results...) which the
    transcript keeps in full; only the terminal event carries usage, cost and structured output.
    """
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("type") == "result":
            return obj
    return None


def parse_usage(payload: dict[str, Any]) -> Usage:
    usage = payload.get("usage") or {}
    model_usage = payload.get("modelUsage") or {}
    window: int | None = None
    for info in model_usage.values():
        if isinstance(info, dict) and info.get("contextWindow"):
            window = int(info["contextWindow"])
            break
    peak = 0
    iterations = usage.get("iterations") or []
    for it in iterations:
        if not isinstance(it, dict):
            continue
        size = (
            int(it.get("input_tokens", 0))
            + int(it.get("cache_read_input_tokens", 0))
            + int(it.get("cache_creation_input_tokens", 0))
        )
        peak = max(peak, size)
    if not iterations:
        peak = (
            int(usage.get("input_tokens", 0))
            + int(usage.get("cache_read_input_tokens", 0))
            + int(usage.get("cache_creation_input_tokens", 0))
        )
    return Usage(
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
        cache_read_tokens=int(usage.get("cache_read_input_tokens", 0)),
        cache_write_tokens=int(usage.get("cache_creation_input_tokens", 0)),
        requests=max(len(iterations), 1),
        context_window=window,
        context_peak_tokens=peak or None,
        context_peak_is_upper_bound=not iterations,
    )


def role_label(role: Role) -> str:
    return role.value


def summarise_activity(output: str) -> dict[str, int]:
    """Count tool uses per tool name and assistant turns in a stream-json transcript."""
    counts: dict[str, int] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or obj.get("type") != "assistant":
            continue
        counts["assistant_turns"] = counts.get("assistant_turns", 0) + 1
        for block in (obj.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = str(block.get("name", "tool"))
                counts[name] = counts.get(name, 0) + 1
    return counts


def peak_from_stream(output: str) -> tuple[int, int]:
    """Exact context peak and request count from the per-message usage of assistant events.

    Every request's usage is repeated on each assistant event of the same message, so events
    are grouped by message id before counting.
    """
    peak = 0
    seen: set[str] = set()
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or obj.get("type") != "assistant":
            continue
        message = obj.get("message") or {}
        usage = message.get("usage") or {}
        if not isinstance(usage, dict):
            continue
        size = (
            int(usage.get("input_tokens") or 0)
            + int(usage.get("cache_read_input_tokens") or 0)
            + int(usage.get("cache_creation_input_tokens") or 0)
        )
        peak = max(peak, size)
        seen.add(str(message.get("id") or len(seen)))
    return peak, len(seen)
