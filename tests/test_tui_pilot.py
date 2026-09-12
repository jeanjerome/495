"""Driving a run from the surface: an intent in, a decision answered, a merge checked.

The surface is the workflow, so what it can *do* is tested the way what it shows is tested —
against a real store walked by the fake agents, not against a mock of the engine.
"""

from __future__ import annotations

import io
import json
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from harness495.core.models import RunStatus
from harness495.core.store import DRIVER_FLAG, RunStore
from harness495.interfaces.tui import Shell, StoreSource
from harness495.interfaces.tui.attention import attention
from harness495.interfaces.tui.driving import StoreDriver
from harness495.interfaces.tui.loops import _wind_down
from harness495.interfaces.tui.stages import stage_of, stage_state
from harness495.interfaces.tui.theme import THEME
from harness495.interfaces.tui.views import ask_intent

WAIT = 120.0
"""Long enough for the fake agents and a real pytest run; a hung driver still fails the test."""


@pytest.fixture
def store(sample_project: Path) -> RunStore:
    return RunStore(sample_project / ".495")


@pytest.fixture
def pilot(store: RunStore, sample_project: Path, engine_factory: Any) -> StoreDriver:
    """A driver over the sample project, with the fake agents behind it.

    A run created here reads the project's own configuration from disk — that is the point of
    typing an intent into the surface rather than into a test — so the sample project gets the
    one setting that would otherwise stop every run at the gate.
    """
    (sample_project / ".495" / "config.toml").write_text("auto_approve = true\n", encoding="utf-8")
    return StoreDriver(store, project=sample_project, engine_factory=lambda: engine_factory())


def surface(store: RunStore, pilot: StoreDriver, width: int = 150) -> Shell:
    """A surface with the first run open, if the store holds one; the listing otherwise."""
    console = Console(theme=THEME, file=io.StringIO(), width=width, highlight=False)
    runs = store.list_runs()
    return Shell(
        StoreSource(store),
        console,
        animated=False,
        driver=pilot,
        selected=runs[0].id if runs else None,
    )


def render(shell: Shell, view: str, width: int = 150) -> str:
    shell.view = view
    out = io.StringIO()
    console = Console(theme=THEME, file=out, width=width, highlight=False, legacy_windows=False)
    console.print(shell.flow(width))
    return out.getvalue()


def settle(pilot: StoreDriver, quiet: bool = True) -> None:
    assert pilot.wait(WAIT), "the driver is still working"
    if quiet:
        assert pilot.notice is None, pilot.notice


# --------------------------------------------------------------------- from an intent


def test_an_intent_typed_here_becomes_a_run_that_walks_to_delivery(
    store: RunStore, pilot: StoreDriver
) -> None:
    run_id = pilot.create("add subtract to calc")
    settle(pilot)
    run = store.load(run_id)
    assert run.status is RunStatus.delivered, (run.stop_reason, run.warnings)
    assert run.intent.source == "surface"
    shell = surface(store, pilot)
    shell.select(run_id)
    # A delivered run stands at the last stop, which is the one the harness cannot walk alone.
    assert stage_of(run) == "integration"
    assert "d" not in dict(shell.controls()) and shell.startable() is None


def test_an_existing_change_can_be_evaluated_from_here(
    store: RunStore, pilot: StoreDriver, sample_project: Path
) -> None:
    run_id = pilot.create("subtract must work", "WORKTREE")
    settle(pilot)
    run = store.load(run_id)
    assert run.mode.value == "evaluate" and run.evaluate_ref == "WORKTREE"


def test_the_opening_question_states_what_each_answer_does(monkeypatch: Any) -> None:
    """Enter twice is the ordinary run; a ref is asked for only where one is meant."""
    console = Console(theme=THEME, file=io.StringIO(), width=100, highlight=False, record=True)

    def answers(*typed: str) -> None:
        queue = iter(typed)
        monkeypatch.setattr("builtins.input", lambda *a, **k: next(queue))

    answers("make the deploy command idempotent", "")
    assert ask_intent(console) == ("make the deploy command idempotent", "")
    asked = console.export_text()
    assert "495 writes it" in asked and "it already exists" in asked
    assert "<base>..<head>" not in asked, "the ordinary path never sees git syntax"

    answers("subtract must work", "evaluate", "")
    assert ask_intent(console) == ("subtract must work", "WORKTREE")

    answers("subtract must work", "evaluate", "commit", "main..mine")
    assert ask_intent(console) == ("subtract must work", "main..mine")

    answers("")
    assert ask_intent(console) is None, "an empty intent opens nothing"


# --------------------------------------------------------------------- start, pause, answer


def test_a_created_run_is_started_by_one_key(
    store: RunStore, pilot: StoreDriver, sample_project: Path, config: Any, engine_factory: Any
) -> None:
    run = engine_factory().create_run("add subtract to calc", sample_project, config)
    shell = surface(store, pilot)
    shell.select(run.id)
    assert shell.startable() == "start"
    assert ("s", "start") in shell.controls()
    assert attention(shell.run, can_drive=True).key == "s"
    shell.act("control:start")
    settle(pilot)
    shell.source.refresh(force=True)
    assert shell.run.status is RunStatus.delivered


def test_pausing_asks_the_run_to_stop_wherever_it_is_driven_from(
    store: RunStore, pilot: StoreDriver, sample_project: Path, config: Any, engine_factory: Any
) -> None:
    run = engine_factory().create_run("add subtract to calc", sample_project, config)
    pilot.pause(run.id)
    assert store.stop_requested(run.id) is not None
    # The flag is read by whichever engine walks the run next, and cleared when it starts.
    pilot.start(run.id)
    settle(pilot)
    assert store.load(run.id).status in {RunStatus.paused, RunStatus.delivered}


def test_a_question_answered_here_lets_the_run_carry_on(
    store: RunStore, pilot: StoreDriver, sample_project: Path, config: Any, engine_factory: Any
) -> None:
    config.auto_approve = False
    run = engine_factory().create_run("add subtract to calc", sample_project, config)
    pilot.start(run.id)
    settle(pilot)
    shell = surface(store, pilot)
    shell.select(run.id)
    assert shell.run.status is RunStatus.awaiting_decision
    assert ("d", "answer") in shell.controls()
    assert shell.startable() is None, "a run stopped on a question is not started, it is answered"
    assert stage_state(shell.run, "spec") == "blocked"
    pilot.decide(shell.run.id, "approve", "")
    settle(pilot)
    shell.source.refresh(force=True)
    assert shell.run.status is RunStatus.delivered


# --------------------------------------------------------------------- the eighth stop


def test_the_integration_check_runs_from_the_surface(
    store: RunStore, pilot: StoreDriver, sample_project: Path
) -> None:
    run_id = pilot.create("add subtract to calc")
    settle(pilot)
    run = store.load(run_id)
    assert run.result.branch
    _git(sample_project, "merge", "--no-ff", "-m", "merge", run.result.branch)

    shell = surface(store, pilot)
    shell.select(run_id)
    shell.view = "integration"
    assert ("i", "check a ref") in shell.controls()
    assert "not checked yet" in render(shell, "integration").lower()

    pilot.integrate(run_id, "HEAD", False)
    settle(pilot)
    shell.source.refresh(force=True)
    check = shell.run.result.integration
    assert check is not None and check.contains_commit and check.files_identical
    assert stage_state(shell.run, "integration") == "done"
    assert "integration check" in render(shell, "integration")


def test_a_ref_nobody_merged_into_is_not_a_failed_integration(
    store: RunStore, pilot: StoreDriver, sample_project: Path
) -> None:
    """Asking about a tree you have not merged into is answered "not yet", not "it broke".

    The check records two booleans and both are false here — which is also what they are when
    a merge went wrong. Told apart by the commit the run branched from, they are opposite
    facts, and only one of them is worth a red stop.
    """
    run_id = pilot.create("add subtract to calc")
    settle(pilot)
    shell = surface(store, pilot)
    shell.select(run_id)
    before = attention(shell.run, can_drive=True)

    pilot.integrate(run_id, "HEAD", False)  # nothing was merged
    settle(pilot)
    shell.source.refresh(force=True)

    check = shell.run.result.integration
    assert check is not None and not check.contains_commit and not check.files_identical
    assert shell.run.integration_state() == "unmerged"
    assert stage_state(shell.run, "integration") == "blocked", "the merge is still yours to make"
    after = attention(shell.run, can_drive=True)
    assert after.tone == before.tone == "good", "asking must not turn a delivered run red"
    assert "has not been merged into" in after.detail
    assert "nothing of this run has been merged into it" in check.detail
    assert "evaluated" not in check.detail, "nothing was integrated, so nothing can differ"


def test_a_tree_that_carries_something_else_is_named_as_such(
    store: RunStore, pilot: StoreDriver, sample_project: Path
) -> None:
    run_id = pilot.create("add subtract to calc")
    settle(pilot)
    _git(sample_project, "commit", "--allow-empty", "-m", "the branch moved on without it")
    pilot.integrate(run_id, "HEAD", False)
    settle(pilot)
    shell = surface(store, pilot)
    shell.select(run_id)
    check = shell.run.result.integration
    assert check is not None and not check.contains_commit and not check.files_identical
    assert shell.run.integration_state() == "differs"
    assert stage_state(shell.run, "integration") == "failed"
    assert attention(shell.run, can_drive=True).tone == "bad"


def test_the_check_is_offered_from_wherever_you_are_standing(
    store: RunStore, pilot: StoreDriver, sample_project: Path
) -> None:
    """The last thing left to do on a delivered run is not hidden behind the stop that owns it."""
    run_id = pilot.create("add subtract to calc")
    settle(pilot)
    shell = surface(store, pilot)
    shell.select(run_id)
    shell.view = "change"
    assert shell.resolve("i") == "integrate"
    assert ("i", "check a ref") in shell.controls()
    assert attention(shell.run, can_drive=True).key == "i", "the band names the key, not the stop"
    assert attention(shell.run, can_drive=False).key == "8", "and the stop where it cannot act"


# --------------------------------------------------------------------- two terminals


def test_a_run_advanced_elsewhere_is_watched_not_joined(
    store: RunStore, pilot: StoreDriver, sample_project: Path, config: Any, engine_factory: Any
) -> None:
    run = engine_factory().create_run("add subtract to calc", sample_project, config)
    (store.run_dir(run.id) / DRIVER_FLAG).write_text(
        json.dumps({"pid": 1, "host": socket.gethostname(), "label": "495 run", "since": "now"}),
        encoding="utf-8",
    )
    shell = surface(store, pilot)
    shell.select(run.id)
    assert shell.held is not None
    assert shell.startable() is None
    assert shell.controls() == [("p", "pause the run"), ("c", "new run")]
    band = attention(shell.run, held=shell.held, can_drive=True)
    assert "elsewhere" in band.headline
    # Answering a question here would write over the document the other engine is holding.
    assert not shell.can("decide") and not shell.can("integrate")
    # Except the stop: a flag in the run directory is how one terminal reaches another's run.
    assert shell.can("control:pause")
    shell.act("control:start")
    assert pilot.working() is None
    assert pilot.notice is not None and "act on it there" in pilot.notice
    assert store.load(run.id).status is RunStatus.created


def test_the_driver_does_one_thing_at_a_time(
    store: RunStore, pilot: StoreDriver, sample_project: Path, config: Any, engine_factory: Any
) -> None:
    first = engine_factory().create_run("add subtract to calc", sample_project, config)
    second = engine_factory().create_run("something else", sample_project, config)
    pilot.start(first.id)
    pilot.start(second.id)
    assert pilot.notice is not None and first.id in pilot.notice
    settle(pilot, quiet=False)
    assert store.load(second.id).status is RunStatus.created


# --------------------------------------------------------------------- leaving


class _BlockingEngine:
    """An engine that does nothing but hold the run until it is asked to stop."""

    def __init__(self, store: RunStore) -> None:
        self.store = store

    def run(self, run_id: str) -> None:
        while self.store.stop_requested(run_id) is None:
            time.sleep(0.01)


def test_leaving_the_surface_pauses_the_run_it_was_advancing(
    store: RunStore, sample_project: Path, config: Any, engine_factory: Any
) -> None:
    """The engine lives in this process: quitting without stopping it kills an agent mid-turn."""
    run = engine_factory().create_run("add subtract to calc", sample_project, config)
    pilot = StoreDriver(
        store, project=sample_project, engine_factory=lambda: _BlockingEngine(store)
    )
    shell = surface(store, pilot)
    shell.select(run.id)
    pilot.start(run.id)
    for _ in range(500):
        if pilot.working() is not None:
            break
        time.sleep(0.01)
    assert pilot.working() is not None
    _wind_down(shell, None, timeout=WAIT)
    assert pilot.working() is None
    assert store.stop_requested(run.id) is not None


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
