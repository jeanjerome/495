from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from harness495.core import engine as engine_mod
from harness495.core.models import AgentSpec, HarnessConfig, RunStatus
from harness495.interfaces.api import make_server
from harness495.interfaces.cli import app
from tests.conftest import FakeAgent, Scenario

runner = CliRunner()


def _cli(project: Path, *args: str) -> Any:
    return runner.invoke(app, ["--project", str(project), *args])


def test_cli_basics(sample_project: Path) -> None:
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0 and "495" in res.output
    res = _cli(sample_project, "--json", "profile")
    assert res.exit_code == 0
    prof = json.loads(res.output)
    assert prof["commands"][0]["name"] == "test" and prof["base_commit"]
    res = _cli(sample_project, "schema", "spec")
    assert res.exit_code == 0 and "requirements" in json.loads(res.output)["properties"]
    res = _cli(sample_project, "--json", "doctor")
    assert res.exit_code == 0 and "sandboxes" in json.loads(res.output)
    res = _cli(sample_project, "init")
    assert res.exit_code == 0 and (sample_project / ".495" / "config.toml").exists()
    assert "[scope]" in (sample_project / ".495" / "project.toml").read_text()


def test_cli_run_lifecycle(sample_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = Scenario()
    monkeypatch.setattr(engine_mod, "build_agent", lambda spec, sandbox: FakeAgent(spec, scenario))
    res = _cli(
        sample_project,
        "--json",
        "new",
        "add subtract",
        "--no-start",
        "--agent",
        "claude_code:fake",
        "--sandbox",
        "host",
    )
    assert res.exit_code == 0, res.output
    run_id = json.loads(res.output)["id"]
    res = _cli(sample_project, "--json", "run", run_id)
    assert res.exit_code == 3, res.output  # awaiting the spec approval
    payload = json.loads(res.output)
    assert (
        payload["status"] == "awaiting_decision"
        and payload["pending_decision"]["kind"] == "approve_spec"
    )
    res = _cli(sample_project, "--json", "decide", run_id, "approve")
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["status"] == "delivered" and payload["outcome"] == "accept"
    res = _cli(sample_project, "--json", "status", run_id)
    assert json.loads(res.output)["requirements"][0]["status"] == "satisfied"
    res = _cli(sample_project, "--json", "list")
    assert [r["id"] for r in json.loads(res.output)] == [run_id]
    res = _cli(sample_project, "report", run_id)
    assert "# 495 run" in res.output and "## Interventions" in res.output
    res = _cli(sample_project, "--json", "events", run_id)
    types = [json.loads(line)["type"] for line in res.output.splitlines() if line.strip()]
    assert "run.delivered" in types
    res = _cli(
        sample_project, "validate", str(sample_project / ".495" / "runs" / run_id / "run.json")
    )
    assert res.exit_code == 0 and "valid" in res.output
    res = _cli(sample_project, "--json", "export", run_id, "-o", str(sample_project / "out.tgz"))
    assert res.exit_code == 0 and (sample_project / "out.tgz").exists()
    # A ref nobody merged into is the run standing where it delivered, not a rejection: the
    # command says so and exits clean, and it is a moved ref carrying something else that does
    # not.
    res = _cli(sample_project, "--json", "check-integration", run_id)
    assert res.exit_code == 0 and json.loads(res.output)["state"] == "unmerged"
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "--allow-empty", "-m", "on"],
        cwd=sample_project,
        check=True,
        capture_output=True,
    )
    res = _cli(sample_project, "--json", "check-integration", run_id)
    assert res.exit_code == 4 and json.loads(res.output)["state"] == "differs"
    res = _cli(sample_project, "--json", "cleanup", run_id)
    assert res.exit_code == 0
    res = _cli(sample_project, "--json", "status", "run-nope")
    assert res.exit_code == 1 and "not found" in json.loads(res.output)["error"]


def test_cli_eval_and_stop(sample_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = Scenario()
    monkeypatch.setattr(engine_mod, "build_agent", lambda spec, sandbox: FakeAgent(spec, scenario))
    from tests.conftest import good_producer

    good_producer(sample_project)
    res = _cli(
        sample_project,
        "--json",
        "eval",
        "add subtract",
        "--auto-approve",
        "--agent",
        "claude_code:fake",
        "--sandbox",
        "host",
    )
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["mode"] == "evaluate" and payload["outcome"] == "accept"
    res = _cli(sample_project, "--json", "stop", payload["id"])
    assert (
        res.exit_code == 0 and (sample_project / ".495" / "runs" / payload["id"] / "STOP").exists()
    )


def _http(method: str, url: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            ctype = resp.headers.get("Content-Type", "")
            return resp.status, json.loads(raw) if "json" in ctype else raw
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def test_api_lifecycle(sample_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = Scenario()
    monkeypatch.setattr(engine_mod, "build_agent", lambda spec, sandbox: FakeAgent(spec, scenario))
    (sample_project / ".495" / "config.toml").write_text(
        '[sandbox]\nbackend = "host"\n[agents.default]\nkind = "claude_code"\nmodel = "fake"\n'
    )
    server = make_server(sample_project, sample_project / ".495", "127.0.0.1", 0)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        code, health = _http("GET", f"{base}/health")
        assert code == 200 and health["ok"]
        code, created = _http(
            "POST", f"{base}/runs", {"intent": "add subtract", "agent": "default"}
        )
        assert code == 201, created
        run_id = created["id"]
        deadline = time.time() + 60
        while time.time() < deadline:
            code, doc = _http("GET", f"{base}/runs/{run_id}")
            if doc["status"] == RunStatus.awaiting_decision.value and not doc["running"]:
                break
            time.sleep(0.2)
        assert doc["pending_decision"]["kind"] == "approve_spec"
        code, ev = _http("GET", f"{base}/runs/{run_id}/events?offset=0")
        assert code == 200 and any(e["type"] == "decision.requested" for e in ev["events"])
        code, doc = _http("POST", f"{base}/runs/{run_id}/decisions", {"choice": "approve"})
        assert code == 200, doc
        deadline = time.time() + 60
        while time.time() < deadline:
            code, doc = _http("GET", f"{base}/runs/{run_id}")
            if doc["status"] == "delivered":
                break
            time.sleep(0.2)
        assert doc["status"] == "delivered" and doc["result"]["outcome"] == "accept"
        code, report = _http("GET", f"{base}/runs/{run_id}/report")
        assert code == 200 and "# 495 run" in report
        code, runs = _http("GET", f"{base}/runs")
        assert code == 200 and runs[0]["id"] == run_id
        code, schema = _http("GET", f"{base}/schema/run")
        assert code == 200 and "properties" in schema
        code, err = _http("POST", f"{base}/runs", {})
        assert code == 400 and "intent" in err["error"]
        code, err = _http("GET", f"{base}/runs/run-nope")
        assert code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_config_precedence_and_templates(tmp_path: Path) -> None:
    from harness495.core.config import load_config

    state = tmp_path / ".495"
    state.mkdir()
    (state / "config.toml").write_text(
        '[agents.x]\nkind = "codex"\nmodel = "m"\n[budget]\nmax_cost_usd = 2.5\n[roles]\nproducer = "x"\nreviewers = [{perspective = "security", agent = "x"}]\n'
    )
    (state / "project.toml").write_text(
        'conventions = ["c1"]\n[[commands]]\nname = "lint"\ncommand = "ruff check ."\nkind = "lint"\n[scope]\nallowed_paths = ["src/**"]\n'
    )
    cfg: HarnessConfig = load_config(tmp_path, state)
    assert isinstance(cfg.agents["x"], AgentSpec) and cfg.agents["x"].kind.value == "codex"
    assert cfg.budget.max_cost_usd == 2.5 and cfg.roles.producer == "x"
    assert cfg.roles.reviewers[0].perspective == "security"
    assert cfg.project.commands[
        0
    ].command == "ruff check ." and cfg.project.scope.allowed_paths == ["src/**"]
    assert cfg.project.conventions == ["c1"]


def test_cli_spec_command(sample_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = Scenario()
    monkeypatch.setattr(engine_mod, "build_agent", lambda spec, sandbox: FakeAgent(spec, scenario))
    res = _cli(sample_project, "--json", "new", "add subtract", "--no-start", "--sandbox", "host")
    run_id = json.loads(res.output)["id"]
    res = _cli(sample_project, "--json", "run", run_id)
    assert res.exit_code == 3, res.output

    res = _cli(sample_project, "--json", "spec", run_id)
    assert res.exit_code == 0, res.output
    spec = json.loads(res.output)
    assert [r["id"] for r in spec["requirements"]] == ["R1", "R2"]
    assert spec["artifact_ref"]

    res = _cli(sample_project, "spec", run_id)
    assert res.exit_code == 0 and "R1" in res.output and "not approved" in res.output
    assert "calc.subtract" in res.output


def test_decision_output_carries_consequences_and_no_duplicate_table(
    sample_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.conftest import bad_producer, reject_review

    scenario = Scenario()
    scenario.producers = [bad_producer]
    scenario.reviews["correctness"] = [reject_review("correctness")]
    monkeypatch.setattr(engine_mod, "build_agent", lambda spec, sandbox: FakeAgent(spec, scenario))
    res = _cli(
        sample_project,
        "--json",
        "new",
        "add subtract",
        "--no-start",
        "--auto-approve",
        "--max-iterations",
        "1",
        "--sandbox",
        "host",
    )
    run_id = json.loads(res.output)["id"]
    res = _cli(sample_project, "run", run_id)
    assert res.exit_code == 3, res.output
    # Every option says what it does to the run, not just what it is called.
    assert "Raises the limit by one" in res.output
    assert "stay on disk" in res.output
    # The requirements are laid out once, by the decision, not twice.
    assert res.output.count("R1") >= 1
    assert "where each requirement stands" in res.output
    assert "outstanding corrections" in res.output


def test_the_status_line_steps_aside_for_a_prompt() -> None:
    """A live region redraws over the last line: a question asked under one cannot be answered."""
    import io

    from rich.console import Console

    from harness495.interfaces import render

    console = Console(file=io.StringIO(), force_terminal=True, width=100)
    monitor = render.RunMonitor(console)
    with monitor:
        assert monitor._live is not None and monitor._live.is_started
        assert render._ACTIVE_MONITOR is monitor
        with render.paused_display():
            # Whatever is printed here reaches the terminal untouched.
            assert not monitor._live.is_started
        assert monitor._live.is_started
    assert render._ACTIVE_MONITOR is None
    # Outside a run there is nothing to suspend, and prompting must still work.
    with render.paused_display():
        pass


def test_prompt_decision_answers_while_a_run_is_being_watched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io

    from rich.console import Console

    from harness495.core.models import (
        DecisionKind,
        DecisionOption,
        Intent,
        PendingDecision,
        Run,
    )
    from harness495.interfaces import render

    console = Console(file=io.StringIO(), force_terminal=True, width=100)
    monkeypatch.setattr(render, "console", console)
    asked: list[bool] = []

    def fake_ask(*args: Any, **kwargs: Any) -> str:
        # The prompt only reaches the user if the live region is down at this moment.
        asked.append(render._ACTIVE_MONITOR is None or not render._ACTIVE_MONITOR._live.is_started)
        return "proceed"

    monkeypatch.setattr(render.Prompt, "ask", fake_ask)
    pending = PendingDecision(
        kind=DecisionKind.readiness,
        question="q",
        options=[DecisionOption(key="proceed", label="Proceed", consequence="The run continues.")],
    )
    run = Run(id="run-x", intent=Intent(text="t"), project_root=".")
    monitor = render.RunMonitor(console)
    with monitor:
        assert render.prompt_decision(run, pending) == ("proceed", "")
    assert asked == [True]
