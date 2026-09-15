from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from harness495.core.models import AgentSpec, HarnessConfig


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
        answer = render.prompt_decision(run, pending)
        assert answer is not None and (answer.choice, answer.note) == ("proceed", "")
    assert asked == [True]
