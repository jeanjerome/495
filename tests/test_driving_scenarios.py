"""Scenarios of ``tests/features/driving.feature``: what ``interfaces/tui/driving.py``,
``loops.py`` and ``views.py`` do to a run rather than say about it.

The steps build a ``StoreDriver`` over the sample project with the fake agents of
``tests/conftest.py`` behind it, press what the surface offers, wait for the driver to settle,
and read the store, the controls and the notice back. Nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

import io
import json
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from rich.console import Console

from harness495.core.models import HarnessConfig, Run, RunStatus
from harness495.core.store import DRIVER_FLAG, RunStore
from harness495.interfaces.tui import Shell, StoreSource
from harness495.interfaces.tui.attention import attention
from harness495.interfaces.tui.driving import StoreDriver
from harness495.interfaces.tui.loops import _wind_down
from harness495.interfaces.tui.stages import stage_of, stage_state
from harness495.interfaces.tui.theme import THEME
from harness495.interfaces.tui.views import ask_intent

scenarios("features/driving.feature")

WAIT = 120.0
"""Long enough for the fake agents and a real pytest run; a hung driver still fails the test."""


class BlockingEngine:
    """An engine that does nothing but hold the run until it is asked to stop."""

    def __init__(self, store: RunStore) -> None:
        self.store = store

    def run(self, run_id: str) -> None:
        while self.store.stop_requested(run_id) is None:
            time.sleep(0.01)


@dataclass
class Pilot:
    """A driver over the sample project, and the surface standing on the store it writes."""

    project: Path
    store: RunStore
    driver: StoreDriver
    config: HarnessConfig
    engines: Callable[..., Any]
    run_id: str = ""
    other_id: str = ""
    shell: Shell | None = None
    offered: list[tuple[str, str]] = field(default_factory=list)

    def settle(self, quiet: bool = True) -> None:
        assert self.driver.wait(WAIT), "the driver is still working"
        if quiet:
            assert self.driver.notice is None, self.driver.notice

    def open(self, run_id: str) -> Shell:
        console = Console(theme=THEME, file=io.StringIO(), width=150, highlight=False)
        shell = Shell(
            StoreSource(self.store), console, animated=False, driver=self.driver, selected=run_id
        )
        self.shell = shell
        return shell

    @property
    def surface(self) -> Shell:
        assert self.shell is not None, "no run is open on the surface"
        return self.shell

    @property
    def run(self) -> Run:
        return self.store.load(self.run_id)

    def refresh(self) -> Run:
        self.surface.source.refresh(force=True)
        return self.surface.run

    def create(self) -> str:
        return self.engines().create_run("add subtract to calc", self.project, self.config).id


@dataclass
class Typing:
    """A console the opening question is asked on, and what it came back with."""

    console: Console
    monkeypatch: pytest.MonkeyPatch
    taken: tuple[str, str] | None = None
    asked: str = ""

    def types(self, *typed: str) -> None:
        queue = iter(typed)
        self.monkeypatch.setattr("builtins.input", lambda *args, **kwargs: next(queue))
        self.taken = ask_intent(self.console)
        self.asked = self.console.export_text()


def _pilot(
    sample_project: Path,
    config: HarnessConfig,
    engine_factory: Callable[..., Any],
    engines: Callable[..., Any] | None = None,
) -> Pilot:
    """A run created here reads the project's own configuration from disk — that is the point of
    typing an intent into the surface rather than into a test — so the sample project gets the
    one setting that would otherwise stop every run at the gate."""
    (sample_project / ".495" / "config.toml").write_text("auto_approve = true\n", encoding="utf-8")
    store = RunStore(sample_project / ".495")
    build = engines or (lambda: engine_factory())
    return Pilot(
        sample_project,
        store,
        StoreDriver(store, project=sample_project, engine_factory=build),
        config,
        engine_factory,
    )


@given("a surface that may drive the sample project", target_fixture="world")
def a_surface_that_may_drive(
    sample_project: Path, config: HarnessConfig, engine_factory: Callable[..., Any]
) -> Pilot:
    return _pilot(sample_project, config, engine_factory)


@given(
    "a surface that may drive the sample project, where approval is not automatic",
    target_fixture="world",
)
def a_surface_where_approval_is_not_automatic(
    sample_project: Path, config: HarnessConfig, engine_factory: Callable[..., Any]
) -> Pilot:
    world = _pilot(sample_project, config, engine_factory)
    world.config.auto_approve = False
    return world


@given("a surface whose engine holds a run until it is asked to stop", target_fixture="world")
def a_surface_whose_engine_blocks(
    sample_project: Path, config: HarnessConfig, engine_factory: Callable[..., Any]
) -> Pilot:
    store = RunStore(sample_project / ".495")
    return _pilot(sample_project, config, engine_factory, engines=lambda: BlockingEngine(store))


@given("a console that answers what is typed at it", target_fixture="typing")
def a_console_that_answers(monkeypatch: pytest.MonkeyPatch) -> Typing:
    console = Console(theme=THEME, file=io.StringIO(), width=100, highlight=False, record=True)
    return Typing(console, monkeypatch)


@given("a run created but not started, open on the surface")
def a_run_created_but_not_started(world: Pilot) -> None:
    world.run_id = world.create()
    world.open(world.run_id)


@given("two runs created but not started")
def two_runs_created_but_not_started(world: Pilot) -> None:
    world.run_id = world.create()
    world.other_id = world.engines().create_run("something else", world.project, world.config).id


@given("another process holding the claim on it")
def another_process_holding_the_claim(world: Pilot) -> None:
    (world.store.run_dir(world.run_id) / DRIVER_FLAG).write_text(
        json.dumps({"pid": 1, "host": socket.gethostname(), "label": "495 run", "since": "now"}),
        encoding="utf-8",
    )


# ----------------------------------------------------------------- what is pressed


@when(parsers.parse('the intent "{intent}" is typed in'))
def the_intent_is_typed_in(world: Pilot, intent: str) -> None:
    world.run_id = world.driver.create(intent)
    world.settle()
    world.open(world.run_id)


@when(parsers.parse('the intent "{intent}" is typed in, over the working tree'))
def the_intent_is_typed_over_the_working_tree(world: Pilot, intent: str) -> None:
    world.run_id = world.driver.create(intent, "WORKTREE")
    world.settle()


@when("what the surface offers for it is read")
def what_the_surface_offers(world: Pilot) -> None:
    world.offered = world.surface.controls()


@when("the start control is pressed")
def the_start_control_is_pressed(world: Pilot) -> None:
    world.surface.act("control:start")
    world.driver.wait(WAIT)


@when("the run is asked to pause")
def the_run_is_asked_to_pause(world: Pilot) -> None:
    world.driver.pause(world.run_id)


@when("the run is started")
def the_run_is_started(world: Pilot) -> None:
    world.driver.start(world.run_id)
    world.driver.wait(WAIT)


@when("both of them are started")
def both_of_them_are_started(world: Pilot) -> None:
    world.driver.start(world.run_id)
    world.driver.start(world.other_id)


@when(parsers.parse('the question is answered "{choice}"'))
def the_question_is_answered(world: Pilot, choice: str) -> None:
    world.driver.decide(world.run_id, choice, "")
    world.settle()


@when("the run is started, and the surface is left")
def the_run_is_started_and_the_surface_is_left(world: Pilot) -> None:
    world.driver.start(world.run_id)
    for _ in range(500):
        if world.driver.working() is not None:
            break
        time.sleep(0.01)
    assert world.driver.working() is not None, "the driver never took the run up"
    _wind_down(world.surface, None, timeout=WAIT)


@when(parsers.parse('"{intent}" is typed, then enter'))
def an_intent_then_enter(typing: Typing, intent: str) -> None:
    typing.types(intent, "")


@when(parsers.parse('"{intent}" is typed, then "{second}", then enter'))
def an_intent_then_an_answer(typing: Typing, intent: str, second: str) -> None:
    typing.types(intent, second, "")


@when(parsers.parse('"{intent}" is typed, then "{second}", then "{third}", then "{ref}"'))
def an_intent_then_a_ref(typing: Typing, intent: str, second: str, third: str, ref: str) -> None:
    typing.types(intent, second, third, ref)


@when("nothing at all is typed")
def nothing_at_all_is_typed(typing: Typing) -> None:
    typing.types("")


# ----------------------------------------------------------------- what the store says


@then("the run is delivered")
def the_run_is_delivered(world: Pilot) -> None:
    run = world.run
    assert run.status is RunStatus.delivered, (run.stop_reason, run.warnings)


@then("the run records the surface as where the intent came from")
def the_run_records_the_surface(world: Pilot) -> None:
    assert world.run.intent.source == "surface"


@then("it stands at the integration, the stop the harness cannot walk alone")
def it_stands_at_the_integration(world: Pilot) -> None:
    assert stage_of(world.run) == "integration"


@then("there is nothing to answer, and nothing to start")
def nothing_to_answer_and_nothing_to_start(world: Pilot) -> None:
    assert "d" not in dict(world.surface.controls())
    assert world.surface.startable() is None


@then(parsers.parse('the run is an evaluate run of "{ref}"'))
def the_run_is_an_evaluate_run(world: Pilot, ref: str) -> None:
    run = world.run
    assert run.mode.value == "evaluate" and run.evaluate_ref == ref


@then(parsers.parse('it offers "{label}", as the key "{key}", and the band says so too'))
def it_offers_the_control_and_the_band_agrees(world: Pilot, label: str, key: str) -> None:
    assert world.surface.startable() == label
    assert (key, label) in world.offered
    assert attention(world.surface.run, can_drive=True).key == key


@then(parsers.parse('it offers "{label}", as the key "{key}", and there is nothing to start'))
def it_offers_the_control_and_nothing_to_start(world: Pilot, label: str, key: str) -> None:
    assert (key, label) in world.surface.controls()
    assert world.surface.startable() is None, (
        "a run stopped on a question is not started, it is answered"
    )


@then("a stop is on file for it")
def a_stop_is_on_file(world: Pilot) -> None:
    assert world.store.stop_requested(world.run_id) is not None


@then("the run is paused or delivered, the flag being read by whichever engine walks it next")
def the_run_is_paused_or_delivered(world: Pilot) -> None:
    assert world.run.status in {RunStatus.paused, RunStatus.delivered}


@then("the run stopped on a question")
def the_run_stopped_on_a_question(world: Pilot) -> None:
    assert world.refresh().status is RunStatus.awaiting_decision


@then(parsers.parse('the stop "{name}" is blocked'))
def the_stop_is_blocked(world: Pilot, name: str) -> None:
    assert stage_state(world.surface.run, name) == "blocked"


@then("the surface knows the run is held, and offers nothing to start")
def the_surface_knows_the_run_is_held(world: Pilot) -> None:
    assert world.surface.held is not None
    assert world.surface.startable() is None


@then(parsers.parse("the controls offered are: {controls}"))
def the_controls_offered_are(world: Pilot, controls: str) -> None:
    pairs = [item.strip().split(" ", 1) for item in controls.split(",")]
    assert world.surface.controls() == [(key, label) for key, label in pairs]


@then("the band says the run is being advanced elsewhere")
def the_band_says_elsewhere(world: Pilot) -> None:
    band = attention(world.surface.run, held=world.surface.held, can_drive=True)
    assert "elsewhere" in band.headline


@then("neither answering nor checking a ref is offered")
def neither_answering_nor_checking(world: Pilot) -> None:
    assert not world.surface.can("decide") and not world.surface.can("integrate")


@then("the stop is offered, which is how one terminal reaches another's run")
def the_stop_is_offered(world: Pilot) -> None:
    assert world.surface.can("control:pause")


@then("nothing was started, and the surface says to act on it there")
def nothing_was_started(world: Pilot) -> None:
    assert world.driver.working() is None
    assert world.driver.notice is not None and "act on it there" in world.driver.notice


@then("the run stands where it was")
def the_run_stands_where_it_was(world: Pilot) -> None:
    assert world.store.load(world.run_id).status is RunStatus.created


@then("the second was refused, the surface naming the first")
def the_second_was_refused(world: Pilot) -> None:
    assert world.driver.notice is not None and world.run_id in world.driver.notice


@then("the second run stands where it was")
def the_second_run_stands_where_it_was(world: Pilot) -> None:
    world.settle(quiet=False)
    assert world.store.load(world.other_id).status is RunStatus.created


@then("nothing is working any more")
def nothing_is_working_any_more(world: Pilot) -> None:
    assert world.driver.working() is None


# ----------------------------------------------------------------- what the question took


@then(parsers.parse('the intent taken is "{intent}", over "{ref}"'))
def the_intent_taken_is_over(typing: Typing, intent: str, ref: str) -> None:
    assert typing.taken == (intent, ref)


@then(parsers.parse('the intent taken is "{intent}", over nothing'))
def the_intent_taken_is_over_nothing(typing: Typing, intent: str) -> None:
    assert typing.taken == (intent, "")


@then(parsers.parse('the question said "{first}" and "{second}"'))
def the_question_said(typing: Typing, first: str, second: str) -> None:
    assert first in typing.asked and second in typing.asked


@then(parsers.parse('the question never showed "{text}", which the ordinary path never sees'))
def the_question_never_showed(typing: Typing, text: str) -> None:
    assert text not in typing.asked


@then("nothing is opened")
def nothing_is_opened(typing: Typing) -> None:
    assert typing.taken is None, "an empty intent opens nothing"
