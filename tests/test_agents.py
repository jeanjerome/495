from __future__ import annotations

import json
import os
import stat
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from four95.agents.base import AgentTask
from four95.agents.claude_code import (
    ClaudeCodeAgent,
    _extract_json,
    parse_usage,
    peak_from_stream,
    summarise_activity,
)
from four95.agents.codex import CodexAgent, parse_events, usage_from_events
from four95.agents.openai_compat import OpenAICompatAgent
from four95.core.models import AgentKind, AgentSpec, Capability, InterventionStatus, Role
from four95.sandbox import Sandbox

CLAUDE_RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": '{"answer":"OK"}',
    "structured_output": {"answer": "OK"},
    "session_id": "sess-1",
    "total_cost_usd": 0.0123,
    "num_turns": 2,
    "usage": {
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_input_tokens": 50,
        "cache_creation_input_tokens": 10,
        "iterations": [
            {
                "input_tokens": 40,
                "output_tokens": 10,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 10,
            },
            {
                "input_tokens": 60,
                "output_tokens": 10,
                "cache_read_input_tokens": 50,
                "cache_creation_input_tokens": 0,
            },
        ],
    },
    "modelUsage": {"claude-haiku-4-5-20251001": {"contextWindow": 200000, "costUSD": 0.0123}},
}


def _script(path: Path, body: str) -> None:
    path.write_text("#!/bin/bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _task(
    cwd: Path, capability: Capability = Capability.read, schema: dict[str, Any] | None = None
) -> AgentTask:
    return AgentTask(
        role=Role.reviewer,
        capability=capability,
        system_prompt="SYS",
        prompt="PROMPT",
        cwd=cwd,
        timeout_s=30,
        output_schema=schema,
    )


def test_claude_parse_usage_peaks_per_iteration() -> None:
    usage = parse_usage(CLAUDE_RESULT)
    assert (
        usage.input_tokens == 100
        and usage.cache_read_tokens == 50
        and usage.cache_write_tokens == 10
    )
    assert (
        usage.context_window == 200000 and usage.context_peak_tokens == 110 and usage.requests == 2
    )
    assert not usage.context_peak_is_upper_bound
    assert _extract_json("noise\n" + json.dumps(CLAUDE_RESULT) + "\n")["session_id"] == "sess-1"
    assert _extract_json("nothing here") is None


def test_claude_argv_restricts_tools_by_capability(tmp_path: Path) -> None:
    agent = ClaudeCodeAgent(
        AgentSpec(name="a", kind=AgentKind.claude_code, model="haiku", effort="low")
    )
    argv, allowed = agent.build_argv(_task(tmp_path, Capability.read, {"type": "object"}))
    assert "--permission-mode" in argv and argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "Bash,Read" in argv and "Bash(git diff *)" in allowed and "Edit" not in allowed
    assert "--json-schema" in argv and "--model" in argv and "--effort" in argv
    settings = json.loads(argv[argv.index("--settings") + 1])
    assert (
        settings["sandbox"]["enabled"] is True
        and settings["sandbox"]["network"]["allowedDomains"] == []
    )
    argv_w, allowed_w = agent.build_argv(_task(tmp_path, Capability.write))
    assert argv_w[argv_w.index("--permission-mode") + 1] == "acceptEdits" and "Edit" in allowed_w
    assert "--json-schema" not in argv_w


def test_claude_agent_runs_fake_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _script(
        bin_dir / "claude",
        f"""
if [ "$1" = "--version" ]; then echo "9.9.9 (Claude Code)"; exit 0; fi
cat > "{tmp_path}/prompt.txt"
printf '%s\\n' "$@" > "{tmp_path}/argv.txt"
echo '{json.dumps(CLAUDE_RESULT)}'
""",
    )
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    from four95.agents import claude_code

    claude_code.cli_version.cache_clear()
    agent = ClaudeCodeAgent(AgentSpec(name="a", kind=AgentKind.claude_code, model="haiku"))
    assert agent.check()[0]
    res = agent.run(_task(tmp_path, schema={"type": "object"}))
    assert res.status is InterventionStatus.completed
    assert res.structured == {"answer": "OK"} and res.cost_usd == 0.0123 and res.cost_reported
    assert res.identity.session_id == "sess-1" and res.identity.cli_version == "9.9.9"
    assert (tmp_path / "prompt.txt").read_text() == "PROMPT"
    argv_text = (tmp_path / "argv.txt").read_text()
    assert (
        "--permission-prompts" in argv_text
        and "stream-json" in argv_text
        and "--verbose" in argv_text
    )
    assert res.sandbox.backend == "claude-code-sandbox"


def test_claude_agent_reports_failure_and_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _script(
        bin_dir / "claude",
        'if [ "$1" = "--version" ]; then echo 1; exit 0; fi\necho "boom" 1>&2; exit 1\n',
    )
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    from four95.agents import claude_code

    claude_code.cli_version.cache_clear()
    agent = ClaudeCodeAgent(AgentSpec(name="a", kind=AgentKind.claude_code))
    res = agent.run(_task(tmp_path))
    assert res.status is InterventionStatus.failed and "without a JSON result" in (res.error or "")
    _script(bin_dir / "claude", 'if [ "$1" = "--version" ]; then echo 1; exit 0; fi\nsleep 20\n')
    task = _task(tmp_path)
    task.timeout_s = 1
    res = agent.run(task)
    assert res.status is InterventionStatus.timed_out


CODEX_EVENTS = [
    {"type": "thread.started", "thread_id": "thr-1"},
    {"type": "turn.started"},
    {
        "type": "item.completed",
        "item": {"id": "i0", "type": "command_execution", "command": "ls", "exit_code": 0},
    },
    {
        "type": "item.completed",
        "item": {"id": "i1", "type": "agent_message", "text": '{"verdict":"accept"}'},
    },
    {
        "type": "turn.completed",
        "usage": {"input_tokens": 300, "cached_input_tokens": 100, "output_tokens": 30},
    },
]


def test_codex_usage_is_upper_bound() -> None:
    events = parse_events("\n".join(json.dumps(e) for e in CODEX_EVENTS) + "\ngarbage\n")
    usage = usage_from_events(events, "gpt-5", None)
    assert (
        usage.input_tokens == 300 and usage.cache_read_tokens == 100 and usage.output_tokens == 30
    )
    assert usage.context_peak_is_upper_bound and usage.context_window == 400000


def test_codex_agent_runs_fake_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    events = "\n".join(json.dumps(e) for e in CODEX_EVENTS)
    _script(
        bin_dir / "codex",
        f"""
if [ "$1" = "--version" ]; then echo "codex-cli 1.2.3"; exit 0; fi
printf '%s\\n' "$@" > "{tmp_path}/argv.txt"
cat > "{tmp_path}/prompt.txt"
out=""
while [ $# -gt 0 ]; do if [ "$1" = "-o" ]; then out="$2"; fi; shift; done
printf '%s' '{{"verdict":"accept"}}' > "$out"
cat <<'EOF2'
{events}
EOF2
""",
    )
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    from four95.agents import codex

    codex.cli_version.cache_clear()
    agent = CodexAgent(AgentSpec(name="c", kind=AgentKind.codex, model="gpt-5-mini"))
    assert agent.check()[0]
    res = agent.run(_task(tmp_path, Capability.write, {"type": "object"}))
    assert res.status is InterventionStatus.completed and res.structured == {"verdict": "accept"}
    argv = (tmp_path / "argv.txt").read_text()
    assert (
        "workspace-write" in argv and "--output-schema" in argv and "network_access=false" in argv
    )
    assert (tmp_path / "prompt.txt").read_text().startswith("SYS")
    assert res.cost_usd is not None and not res.cost_reported and res.identity.session_id == "thr-1"
    assert res.identity.cli_version == "1.2.3"


class _FakeOpenAI(BaseHTTPRequestHandler):
    replies: list[str] = []
    seen: list[dict[str, Any]] = []

    def log_message(self, *a: Any) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        body = json.dumps({"data": [{"id": "fake-model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(length))
        type(self).seen.append(req)
        content = type(self).replies.pop(0) if type(self).replies else "```final\n{}\n```"
        body = json.dumps(
            {
                "choices": [
                    {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 50 + 10 * len(type(self).seen), "completion_tokens": 5},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def fake_openai() -> Any:
    _FakeOpenAI.replies = []
    _FakeOpenAI.seen = []
    server = HTTPServer(("127.0.0.1", 0), _FakeOpenAI)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    server.shutdown()


def test_openai_compat_loop_executes_commands_then_final(tmp_path: Path, fake_openai: str) -> None:
    _FakeOpenAI.replies = [
        "Let me look.\n```bash\necho hello > note.txt && cat note.txt\n```",
        "two blocks\n```bash\nls\n```\n```bash\nls\n```",
        '```final\n{"verdict": "accept", "seen": true}\n```',
    ]
    spec = AgentSpec(
        name="l",
        kind=AgentKind.openai_compat,
        model="fake-model",
        base_url=fake_openai,
        context_window=4096,
    )
    agent = OpenAICompatAgent(spec, Sandbox())
    assert agent.check()[0]
    res = agent.run(_task(tmp_path, Capability.write, {"type": "object"}))
    assert res.status is InterventionStatus.completed and res.structured == {
        "verdict": "accept",
        "seen": True,
    }
    assert (tmp_path / "note.txt").read_text() == "hello\n"
    # Observation of the command and the format error both reached the model.
    seen = _FakeOpenAI.seen
    assert len(seen) == 3
    assert (
        '"exit_code": 0' in seen[1]["messages"][-1]["content"]
        and "hello" in seen[1]["messages"][-1]["content"]
    )
    assert "Format error" in seen[2]["messages"][-1]["content"]
    assert (
        res.usage.requests == 3
        and res.usage.context_window == 4096
        and res.usage.context_peak_tokens
    )
    assert res.cost_usd is None  # fake-model has no pricing


def test_openai_compat_step_limit(tmp_path: Path, fake_openai: str) -> None:
    _FakeOpenAI.replies = [f"```bash\necho {i}\n```" for i in range(10)]
    spec = AgentSpec(
        name="l", kind=AgentKind.openai_compat, model="fake-model", base_url=fake_openai
    )
    agent = OpenAICompatAgent(spec, Sandbox())
    task = _task(tmp_path, Capability.read)
    task.max_steps = 3
    res = agent.run(task)
    assert res.status is InterventionStatus.failed and "step limit" in (res.error or "")
    assert res.usage.requests == 3


def test_openai_compat_detects_loops_and_final_misuse(tmp_path: Path, fake_openai: str) -> None:
    _FakeOpenAI.replies = [
        "```bash\nfinal\n```",
        "```bash\nls\n```",
        "```bash\nls\n```",
        "```bash\nls\n```",
    ]
    spec = AgentSpec(
        name="l", kind=AgentKind.openai_compat, model="fake-model", base_url=fake_openai
    )
    agent = OpenAICompatAgent(spec, Sandbox())
    res = agent.run(_task(tmp_path, Capability.read))
    assert res.status is InterventionStatus.failed and "repeated the same command" in (
        res.error or ""
    )
    assert "`final` is not a shell command" in _FakeOpenAI.seen[1]["messages"][-1]["content"]


def test_claude_activity_summary() -> None:
    stream = "\n".join(
        [
            json.dumps({"type": "system", "subtype": "init"}),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "tool_use", "name": "Bash"},
                            {"type": "text", "text": "hi"},
                        ]
                    },
                }
            ),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "tool_use", "name": "Edit"},
                            {"type": "tool_use", "name": "Bash"},
                        ]
                    },
                }
            ),
            json.dumps(CLAUDE_RESULT),
        ]
    )
    assert summarise_activity(stream) == {"assistant_turns": 2, "Bash": 2, "Edit": 1}
    assert (
        _extract_json(stream + "\n" + json.dumps({"type": "system", "subtype": "task_summary"}))[
            "session_id"
        ]
        == "sess-1"
    )


def test_claude_peak_from_stream_events() -> None:
    def ev(mid: str, inp: int, cached: int) -> str:
        return json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": mid,
                    "usage": {
                        "input_tokens": inp,
                        "cache_read_input_tokens": cached,
                        "cache_creation_input_tokens": 0,
                    },
                    "content": [],
                },
            }
        )

    stream = "\n".join(
        [ev("m1", 10, 100), ev("m1", 10, 100), ev("m2", 5, 3000), json.dumps(CLAUDE_RESULT)]
    )
    assert peak_from_stream(stream) == (3005, 2)
    assert peak_from_stream("nothing") == (0, 0)
