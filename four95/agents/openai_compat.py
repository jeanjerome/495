"""Minimal bash-only agent loop for models behind an OpenAI-compatible chat API.

The loop follows the mini-swe-agent pattern: linear message history, exactly one fenced
``bash`` block per assistant turn, every command executed as an independent subprocess in the
harness sandbox, and an explicit submit marker. It needs no tool-calling support from the
model, so any local model served by Ollama, llama.cpp, vLLM or LM Studio works.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import httpx

from four95.agents.base import Agent, AgentResult, AgentTask
from four95.core import pricing
from four95.core.models import (
    AgentIdentity,
    AgentKind,
    Capability,
    InterventionStatus,
    Usage,
)
from four95.sandbox import Sandbox
from four95.sandbox.base import ExecRequest

SUBMIT_MARKER = "FOUR95_SUBMIT"
ACTION_RE = re.compile(r"```bash\s*\n(.*?)\n```", re.DOTALL)
FINAL_RE = re.compile(r"```(?:json|final)\s*\n(.*?)\n```", re.DOTALL)
MAX_OBS = 12_000

LOOP_INSTRUCTIONS = """
## How you operate

You work by issuing shell commands. Each of your replies must contain exactly one fenced block
tagged `bash` containing the command to run; the harness executes it in a fresh subshell in the
working directory and shows you its exit code and output. Directory changes and variables do not
persist between commands. Keep commands short and observable. Do not use interactive programs.

{write_rules}

When you are done, reply with a single fenced block tagged `final` (not `bash`) containing your
final answer{schema_hint}. Nothing may follow the final block.
"""

WRITE_RULES = (
    "You may create and modify files inside the working directory (use heredocs or `python -c`). "
    "Do not touch anything outside it. Do not use git commands that rewrite history."
)
READ_RULES = (
    "The working directory is read-only for you: inspect files with cat, sed -n, grep, find, "
    "git diff, git log. Do not attempt to modify anything."
)


class OpenAICompatAgent(Agent):
    kind = AgentKind.openai_compat.value

    def __init__(self, spec: Any, sandbox: Sandbox) -> None:
        super().__init__(spec)
        self.sandbox = sandbox
        self.base_url = (
            spec.base_url or os.environ.get("OPENAI_BASE_URL") or "http://localhost:11434/v1"
        ).rstrip("/")
        key_env = spec.api_key_env or "OPENAI_API_KEY"
        self.api_key = os.environ.get(key_env, "") or "not-needed"

    def check(self) -> tuple[bool, str]:
        try:
            r = httpx.get(f"{self.base_url}/models", headers=self._headers(), timeout=5.0)
        except httpx.HTTPError as exc:
            return False, f"{self.base_url} unreachable: {exc}"
        if r.status_code >= 400:
            return False, f"{self.base_url}/models returned {r.status_code}"
        try:
            ids = [m.get("id") for m in r.json().get("data") or []]
        except (ValueError, AttributeError):
            ids = []
        if self.spec.model and ids and self.spec.model not in ids:
            return (
                False,
                f"model {self.spec.model!r} not served; available: {', '.join(map(str, ids[:10]))}",
            )
        return True, f"{self.base_url} model {self.spec.model or '?'}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _complete(self, messages: list[dict[str, str]], timeout: float) -> tuple[str, Usage]:
        body = {"model": self.spec.model, "messages": messages, "temperature": 0.0, "stream": False}
        r = httpx.post(
            f"{self.base_url}/chat/completions", headers=self._headers(), json=body, timeout=timeout
        )
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"].get("content") or ""
        u = data.get("usage") or {}
        prompt_tokens = int(u.get("prompt_tokens", 0))
        cached = int((u.get("prompt_tokens_details") or {}).get("cached_tokens", 0))
        usage = Usage(
            input_tokens=prompt_tokens - cached,
            output_tokens=int(u.get("completion_tokens", 0)),
            cache_read_tokens=cached,
            requests=1,
            context_peak_tokens=prompt_tokens + int(u.get("completion_tokens", 0)),
        )
        return content, usage

    def run(self, task: AgentTask) -> AgentResult:
        writable = task.capability is Capability.write
        req_proto = ExecRequest(
            command="true",
            cwd=task.cwd,
            timeout_s=min(300, task.timeout_s),
            writable=writable,
            network=False,
            scratch_dir=task.scratch_dir,
            stop_check=task.stop_check,
        )
        sandbox_info = self.sandbox.describe(req_proto)
        identity = AgentIdentity(
            kind=AgentKind.openai_compat, name=self.spec.name, model=self.spec.model
        )
        window = pricing.context_window(self.spec.model, self.spec.context_window)
        schema_hint = ""
        if task.output_schema is not None:
            schema_hint = " as a JSON object matching this JSON schema:\n" + json.dumps(
                task.output_schema
            )
        system = task.system_prompt + LOOP_INSTRUCTIONS.replace(
            "{write_rules}", WRITE_RULES if writable else READ_RULES
        ).replace("{schema_hint}", schema_hint)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": task.prompt},
        ]
        transcript: list[dict[str, Any]] = list(messages)
        usage = Usage(context_window=window)
        start = time.monotonic()
        status = InterventionStatus.failed
        error: str | None = "loop ended without a final answer"
        final_text = ""
        structured: dict[str, Any] | None = None
        format_errors = 0
        steps = 0
        recent_commands: list[str] = []
        while True:
            if task.stop_check is not None and task.stop_check():
                status, error = InterventionStatus.interrupted, "interrupted"
                break
            elapsed = time.monotonic() - start
            if elapsed > task.timeout_s:
                status, error = InterventionStatus.timed_out, "timeout"
                break
            if steps >= task.max_steps:
                status, error = InterventionStatus.failed, f"step limit {task.max_steps} reached"
                break
            if task.max_budget_usd is not None:
                cost = pricing.estimate(self.spec.model, usage)
                if cost.usd is not None and cost.usd > task.max_budget_usd:
                    status, error = InterventionStatus.budget_exceeded, "budget exceeded"
                    break
            if window and usage.context_peak_tokens and usage.context_peak_tokens > 0.95 * window:
                status, error = InterventionStatus.failed, "context window nearly exhausted"
                break
            try:
                content, step_usage = self._complete(
                    messages, timeout=min(600.0, task.timeout_s - elapsed)
                )
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                status, error = InterventionStatus.failed, f"model call failed: {exc}"
                break
            steps += 1
            usage = usage.add(step_usage)
            usage.context_window = window
            messages.append({"role": "assistant", "content": content})
            transcript.append(
                {"role": "assistant", "content": content, "usage": step_usage.model_dump()}
            )
            finals = FINAL_RE.findall(content)
            actions = ACTION_RE.findall(content)
            if finals and not actions:
                final_text = finals[-1].strip()
                if task.output_schema is not None:
                    try:
                        parsed = json.loads(final_text)
                    except json.JSONDecodeError as exc:
                        format_errors += 1
                        if format_errors > 2:
                            status, error = (
                                InterventionStatus.failed,
                                "final answer is not valid JSON",
                            )
                            break
                        obs = f"Your final block is not valid JSON ({exc}). Reply again with a valid JSON final block."
                        messages.append({"role": "user", "content": obs})
                        transcript.append({"role": "user", "content": obs})
                        continue
                    structured = parsed if isinstance(parsed, dict) else None
                status, error = InterventionStatus.completed, None
                break
            if len(actions) != 1:
                format_errors += 1
                if format_errors > 3:
                    status, error = InterventionStatus.failed, "repeated format errors"
                    break
                obs = (
                    f"Format error: expected exactly one fenced `bash` block (found {len(actions)}) "
                    "or one `final` block. Reply again."
                )
                messages.append({"role": "user", "content": obs})
                transcript.append({"role": "user", "content": obs})
                continue
            format_errors = 0
            command = actions[0].strip()
            if command in ("final", "FINAL") or command.startswith("final "):
                obs = (
                    "`final` is not a shell command. To finish, reply with a fenced block tagged "
                    "`final` (```final ... ```) containing your answer, and no `bash` block."
                )
                messages.append({"role": "user", "content": obs})
                transcript.append({"role": "user", "content": obs})
                continue
            recent_commands.append(command)
            if len(recent_commands) >= 3 and len(set(recent_commands[-3:])) == 1:
                status, error = InterventionStatus.failed, "model repeated the same command 3 times"
                break
            req = ExecRequest(
                command=command,
                cwd=task.cwd,
                timeout_s=min(300, max(5, int(task.timeout_s - elapsed))),
                writable=writable,
                network=False,
                scratch_dir=task.scratch_dir,
                stop_check=task.stop_check,
            )
            res = self.sandbox.run(req)
            out = res.output
            if len(out) > MAX_OBS:
                out = out[: MAX_OBS // 2] + "\n[... elided by 495 ...]\n" + out[-MAX_OBS // 2 :]
            obs = json.dumps(
                {
                    "exit_code": res.exit_code,
                    "timed_out": res.timed_out,
                    "output": out,
                },
                ensure_ascii=False,
            )
            messages.append({"role": "user", "content": obs})
            transcript.append({"role": "user", "content": obs, "command": command})
        cost = pricing.estimate(self.spec.model, usage)
        return AgentResult(
            status=status,
            text=final_text,
            structured=structured,
            usage=usage,
            cost_usd=cost.usd,
            cost_reported=False,
            identity=identity,
            sandbox=sandbox_info,
            allowed_tools=["bash (harness sandbox)" + (" write" if writable else " read-only")],
            transcript=json.dumps(transcript, indent=1, ensure_ascii=False),
            exit_code=0 if status is InterventionStatus.completed else 1,
            error=error,
            duration_s=round(time.monotonic() - start, 3),
            argv=[self.base_url, self.spec.model or ""],
            activity={"bash": len(recent_commands), "model_requests": steps},
        )
