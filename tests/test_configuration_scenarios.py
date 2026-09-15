"""Scenarios of ``tests/features/configuration.feature``: what ``core/config.py::load_config``
makes of the two files a project carries under ``.495/``.

The steps write those two files into a temporary state directory from the scenario text, load
them, and read the configuration document back. Nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core.config import load_config
from harness495.core.models import AgentSpec, HarnessConfig

scenarios("features/configuration.feature")


@dataclass
class Project:
    """A project root with a state directory, and the configuration read out of it."""

    root: Path
    loaded: HarnessConfig | None = None

    @property
    def state(self) -> Path:
        directory = self.root / ".495"
        directory.mkdir(exist_ok=True)
        return directory

    @property
    def config(self) -> HarnessConfig:
        assert self.loaded is not None, "the configuration has not been loaded"
        return self.loaded


@pytest.fixture
def world(tmp_path: Path) -> Project:
    return Project(tmp_path)


@given(
    parsers.parse(
        'a config.toml naming the agent "{name}" as {kind} "{model}", a budget of {budget:f} '
        'dollars, the producer "{producer}" and the reviewer "{perspective}"'
    )
)
def a_config_toml(
    world: Project,
    name: str,
    kind: str,
    model: str,
    budget: float,
    producer: str,
    perspective: str,
) -> None:
    (world.state / "config.toml").write_text(
        f'[agents.{name}]\nkind = "{kind}"\nmodel = "{model}"\n'
        f"[budget]\nmax_cost_usd = {budget}\n"
        f'[roles]\nproducer = "{producer}"\n'
        f'reviewers = [{{perspective = "{perspective}", agent = "{name}"}}]\n'
    )


@given(
    parsers.parse(
        'a project.toml declaring the convention "{convention}", the command "{command}" as '
        '"{line}" and the allowed path "{path}"'
    )
)
def a_project_toml(world: Project, convention: str, command: str, line: str, path: str) -> None:
    (world.state / "project.toml").write_text(
        f'conventions = ["{convention}"]\n'
        f'[[commands]]\nname = "{command}"\ncommand = "{line}"\nkind = "{command}"\n'
        f'[scope]\nallowed_paths = ["{path}"]\n'
    )


@when("the configuration is loaded")
def the_configuration_is_loaded(world: Project) -> None:
    world.loaded = load_config(world.root, world.state)


@then(parsers.parse('the agent "{name}" is a {kind} agent'))
def the_agent_is_of_the_kind(world: Project, name: str, kind: str) -> None:
    agent = world.config.agents[name]
    assert isinstance(agent, AgentSpec) and agent.kind.value == kind


@then(parsers.parse("the budget allows {budget:f} dollars"))
def the_budget_allows(world: Project, budget: float) -> None:
    assert world.config.budget.max_cost_usd == budget


@then(parsers.parse('the producer is "{producer}", and the first reviewer looks at "{at}"'))
def the_roles_are(world: Project, producer: str, at: str) -> None:
    roles = world.config.roles
    assert roles.producer == producer and roles.reviewers[0].perspective == at


@then(parsers.parse('the project\'s first command is "{line}"'))
def the_first_command_is(world: Project, line: str) -> None:
    assert world.config.project.commands[0].command == line


@then(parsers.parse('a change may touch "{path}"'))
def a_change_may_touch(world: Project, path: str) -> None:
    assert world.config.project.scope.allowed_paths == [path]


@then(parsers.parse('the conventions are "{convention}"'))
def the_conventions_are(world: Project, convention: str) -> None:
    assert world.config.project.conventions == [convention]
