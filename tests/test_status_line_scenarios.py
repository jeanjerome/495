"""Scenarios of ``tests/features/status_line.feature``: what ``interfaces/render.py`` does with
its live region when a question has to be asked under it.

The steps open a real ``RunMonitor`` over a console writing into memory, keep it open across
the steps of a scenario, and read the state of the live region and the answer the prompt
returned. Nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

import io
from contextlib import ExitStack
from dataclasses import dataclass, field
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from rich.console import Console

from harness495.core.models import (
    DecisionAnswer,
    DecisionKind,
    DecisionOption,
    Intent,
    PendingDecision,
    Run,
)
from harness495.interfaces import render

scenarios("features/status_line.feature")


@dataclass
class Watched:
    """A terminal, the monitor drawing on it, and what a prompt put under it answered."""

    console: Console
    watching: ExitStack = field(default_factory=ExitStack)
    paused: ExitStack = field(default_factory=ExitStack)
    monitor: render.RunMonitor | None = None
    answer: DecisionAnswer | None = None
    down_when_asked: list[bool] = field(default_factory=list)

    @property
    def live(self) -> Any:
        assert self.monitor is not None and self.monitor._live is not None
        return self.monitor._live


@given("a terminal", target_fixture="world")
def a_terminal() -> Any:
    world = Watched(Console(file=io.StringIO(), force_terminal=True, width=100))
    try:
        yield world
    finally:
        world.paused.close()
        world.watching.close()


@given(parsers.parse('a requester that answers "{choice}"'))
def a_requester_that_answers(world: Watched, choice: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_ask(*args: Any, **kwargs: Any) -> str:
        active = render._ACTIVE_MONITOR
        world.down_when_asked.append(active is None or not active._live.is_started)
        return choice

    monkeypatch.setattr(render, "console", world.console)
    monkeypatch.setattr(render.Prompt, "ask", fake_ask)


@when("a run is watched on it")
def a_run_is_watched(world: Watched) -> None:
    world.monitor = render.RunMonitor(world.console)
    world.watching.enter_context(world.monitor)


@when("the display is paused")
def the_display_is_paused(world: Watched) -> None:
    world.paused.enter_context(render.paused_display())


@when("the pause ends")
def the_pause_ends(world: Watched) -> None:
    world.paused.close()


@when("the watching ends")
def the_watching_ends(world: Watched) -> None:
    world.watching.close()


@when("the display is paused outside a run")
def the_display_is_paused_outside_a_run(world: Watched) -> None:
    with render.paused_display():
        pass


@when("a readiness question is put to the requester")
def a_readiness_question_is_put(world: Watched) -> None:
    pending = PendingDecision(
        kind=DecisionKind.readiness,
        question="q",
        options=[DecisionOption(key="proceed", label="Proceed", consequence="The run continues.")],
    )
    run = Run(id="run-x", intent=Intent(text="t"), project_root=".")
    world.answer = render.prompt_decision(run, pending)


@then("the live region is drawing, and is the one that is active")
def the_live_region_is_drawing_and_active(world: Watched) -> None:
    assert world.live.is_started
    assert render._ACTIVE_MONITOR is world.monitor


@then("the live region has stopped, so what is printed reaches the terminal untouched")
def the_live_region_has_stopped(world: Watched) -> None:
    assert not world.live.is_started


@then("the live region is drawing again")
def the_live_region_is_drawing_again(world: Watched) -> None:
    assert world.live.is_started


@then("no monitor is active")
def no_monitor_is_active(world: Watched) -> None:
    assert render._ACTIVE_MONITOR is None


@then("nothing was suspended, and the call went through")
def nothing_was_suspended(world: Watched) -> None:
    assert render._ACTIVE_MONITOR is None


@then(parsers.parse('the answer is "{choice}", with no note'))
def the_answer_is(world: Watched, choice: str) -> None:
    assert world.answer is not None
    assert (world.answer.choice, world.answer.note) == (choice, "")


@then("the prompt was asked with the live region down")
def the_prompt_was_asked_with_the_region_down(world: Watched) -> None:
    assert world.down_when_asked == [True]
