"""Scenarios of ``tests/features/agent_answer.feature``: the object the harness reads out of an
agent's prose when the CLI returns no structured output.

``_parse_json_text`` is a pure function of a string — it reaches no engine, no store and no
worktree — so the scenarios call it on the text of the ``Given`` and read its return. Nothing is
asserted outside a ``Then``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest
from pytest_bdd import given, scenarios, then, when

from harness495.core.engine import _parse_json_text

scenarios("features/agent_answer.feature")


@dataclass
class World:
    text: str = ""
    answer: dict[str, Any] | None = None


@pytest.fixture
def world() -> World:
    return World()


@given("the agent answered")
def the_agent_answered(world: World, docstring: str) -> None:
    world.text = docstring


@given("the agent answered nothing at all")
def the_agent_answered_nothing(world: World) -> None:
    world.text = "   \n  "


@when("the harness reads the answer out of the text")
def the_harness_reads_the_answer(world: World) -> None:
    world.answer = _parse_json_text(world.text)


@then("the answer is")
def the_answer_is(world: World, docstring: str) -> None:
    assert world.answer == json.loads(docstring)


@then("there is no answer")
def there_is_no_answer(world: World) -> None:
    assert world.answer is None
