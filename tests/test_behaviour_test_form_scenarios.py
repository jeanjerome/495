"""Scenarios of ``tests/features/behaviour_test_form.feature``: the form a test to create takes
follows the project's scenario runner, and the producer and the test_quality reviewer are told
the same form.

The engine scenarios walk a change run with the scripted agents of ``conftest`` and read the
prompts back; the renderer scenarios build a profile and render the sentence. Nothing is
asserted outside a ``Then``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core.context import render_behaviour_test_form
from harness495.core.models import (
    CatalogueRole,
    ProjectProfile,
    ReviewerSpec,
    Role,
    RoleCoverage,
    RunMode,
)
from tests.conftest import Scenario, git

scenarios("features/behaviour_test_form.feature")


@dataclass
class World:
    profile: ProjectProfile | None = None
    rendered: str = ""
    engine: Any = None
    extra: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def world() -> World:
    return World()


def _tools(text: str) -> list[str]:
    return [t.strip() for t in text.split(",") if t.strip()]


# --------------------------------------------------------------------------- through the engine


@given("the sample project")
def the_sample_project(
    world: World, sample_project: Path, config: Any, engine_factory: Any
) -> None:
    world.extra["project"] = sample_project
    world.extra["config"] = config
    world.engine = engine_factory()


@given(parsers.parse('its pyproject.toml lists the dependency "{name}"'))
def its_pyproject_lists_a_dependency(world: World, name: str) -> None:
    root: Path = world.extra["project"]
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "sample"\nversion = "0"\ndependencies = ["{name}"]\n',
        encoding="utf-8",
    )
    git("-c", "user.name=t", "-c", "user.email=t@t", "add", "pyproject.toml", cwd=root)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "deps", cwd=root)


@given(parsers.parse('the reviewers include "{perspective}"'))
def the_reviewers_include(world: World, perspective: str) -> None:
    world.extra["config"].roles.reviewers.append(ReviewerSpec(perspective=perspective))


@when("a change run walks the workflow")
def a_change_run_walks_the_workflow(world: World) -> None:
    run = world.engine.create_run(
        "add subtract to calc", world.extra["project"], world.extra["config"], RunMode.change
    )
    world.engine.run(run.id)


@then(parsers.parse('the producer\'s prompt says "{text}"'))
def the_producers_prompt_says(scenario: Scenario, text: str) -> None:
    prompts = [t.prompt for t in scenario.calls if t.role is Role.producer]
    assert prompts, "no producer was called"
    assert text in prompts[0], prompts[0]


@then(parsers.parse('the "{perspective}" reviewer\'s prompt says "{text}"'))
def the_reviewers_prompt_says(scenario: Scenario, perspective: str, text: str) -> None:
    marker = f"Review the change from the perspective: **{perspective}**"
    prompts = [t.prompt for t in scenario.calls if t.role is Role.reviewer and marker in t.prompt]
    assert prompts, f"no {perspective} reviewer was called"
    assert text in prompts[0], prompts[0]


# --------------------------------------------------------------------------- the renderer


@given(
    parsers.parse(
        'a profile measuring bdd with "{first}" for "{tech1}" and with "{second}" for "{tech2}"'
    )
)
def a_profile_measuring_bdd_twice(
    world: World, first: str, tech1: str, second: str, tech2: str
) -> None:
    world.profile = ProjectProfile(
        root=".",
        role_coverage=[
            RoleCoverage(technology=tech1, role=CatalogueRole.bdd, tools=_tools(first)),
            RoleCoverage(technology=tech2, role=CatalogueRole.bdd, tools=_tools(second)),
        ],
    )


@given(parsers.parse('a profile whose bdd row for "{technology}" is measured by nothing'))
def a_profile_with_an_unmeasured_bdd_row(world: World, technology: str) -> None:
    world.profile = ProjectProfile(
        root=".", role_coverage=[RoleCoverage(technology=technology, role=CatalogueRole.bdd)]
    )


@when("the form of a behaviour test is rendered")
def the_form_is_rendered(world: World) -> None:
    assert world.profile is not None
    world.rendered = render_behaviour_test_form(world.profile)


@then(parsers.parse('it says "{text}"'))
def it_says(world: World, text: str) -> None:
    assert text in world.rendered, world.rendered
