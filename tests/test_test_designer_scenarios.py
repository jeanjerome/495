"""Scenarios of ``tests/features/test_designer.feature``: the tests to create are written by
a test designer before the producer, committed by the harness and protected from the change.

The run scenarios walk a change run with the scripted agents of ``conftest`` and read the
run, the prompts and the report back; the configuration scenarios build a ``HarnessConfig``
from TOML text or apply the command line's agent override. Nothing is asserted outside a
``Then``.
"""

from __future__ import annotations

import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core import git
from harness495.core.config import build_config
from harness495.core.models import (
    EvidenceKind,
    HarnessConfig,
    RequirementStatus,
    Role,
    RunMode,
    Sufficiency,
)
from harness495.core.report import render_markdown
from harness495.interfaces.cli import _apply_overrides
from tests.conftest import DESIGNED_TEST, SAMPLE_MODULE, Scenario, design_tests

scenarios("features/test_designer.feature")


@dataclass
class World:
    engine: Any = None
    run: Any = None
    config: HarnessConfig | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def world() -> World:
    return World()


def _names(text: str) -> list[str]:
    return [t.strip() for t in text.split(",") if t.strip()]


def implement(cwd: Path) -> None:
    """A producer that implements subtract and touches no test."""
    (cwd / "calc.py").write_text(
        SAMPLE_MODULE + "\n\ndef subtract(a: int, b: int) -> int:\n    return a - b\n",
        encoding="utf-8",
    )


def rewrite_the_designed_test(cwd: Path) -> None:
    """A producer that makes the designed test pass by rewriting it around a wrong subtract."""
    (cwd / "calc.py").write_text(
        SAMPLE_MODULE + "\n\ndef subtract(a: int, b: int) -> int:\n    return a + b\n",
        encoding="utf-8",
    )
    (cwd / "tests" / "test_subtract.py").write_text(
        "from calc import subtract\n\n\ndef test_subtract():\n    assert subtract(5, 3) == 8\n",
        encoding="utf-8",
    )


def implement_and_restore(cwd: Path) -> None:
    implement(cwd)
    (cwd / "tests" / "test_subtract.py").write_text(DESIGNED_TEST, encoding="utf-8")


def design_with_a_stub(path: str) -> Callable[[Path], None]:
    def design(cwd: Path) -> None:
        design_tests(cwd)
        (cwd / path).write_text(
            SAMPLE_MODULE
            + "\n\ndef subtract(a: int, b: int) -> int:\n    raise NotImplementedError\n",
            encoding="utf-8",
        )

    return design


def design_nothing(cwd: Path) -> None:
    pass


# --------------------------------------------------------------------------- through the engine


@given("the sample project")
def the_sample_project(
    world: World, sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    world.extra["project"] = sample_project
    world.extra["config"] = config
    world.extra["scenario"] = scenario
    world.engine = engine_factory()


@given(parsers.parse('V1 runs "{path}"'))
def v1_runs(world: World, path: str) -> None:
    sc: Scenario = world.extra["scenario"]
    sc.spec["verifications"][0]["command"] = (
        f"{sys.executable} -m pytest -q -p no:cacheprovider {path}"
    )


@given("the producer implements the behaviour and writes no test")
def the_producer_implements(world: World) -> None:
    world.extra["scenario"].producers = [implement]


@given(
    "the producer first rewrites the designed test to pass whatever subtract does, then "
    "implements the behaviour and restores the test"
)
def the_producer_rewrites_then_restores(world: World) -> None:
    world.extra["scenario"].producers = [rewrite_the_designed_test, implement_and_restore]


@given(parsers.parse('the test designer writes the test and a stub of the behaviour in "{path}"'))
def the_designer_writes_a_stub(world: World, path: str) -> None:
    world.extra["scenario"].designers = [design_with_a_stub(path)]


@given("the test designer writes nothing")
def the_designer_writes_nothing(world: World) -> None:
    world.extra["scenario"].designers = [design_nothing]


@given("no test designer is configured")
def no_test_designer(world: World) -> None:
    world.extra["config"].roles.test_designer = None


@given("no verification is a test to create, R1 asking only that the suite go on passing")
def no_test_to_create(world: World) -> None:
    sc: Scenario = world.extra["scenario"]
    sc.spec["verifications"][0]["to_create"] = False
    sc.spec["verifications"][0]["command"] = sc.spec["verifications"][1]["command"]
    sc.spec["requirements"][0]["kind"] = "non_regression"


@when("a change run walks the workflow")
def a_change_run_walks_the_workflow(world: World) -> None:
    run = world.engine.create_run(
        "add subtract to calc", world.extra["project"], world.extra["config"], RunMode.change
    )
    world.run = world.engine.run(run.id)


@then(parsers.parse('the roles were called in the order "{names}"'))
def the_roles_were_called_in_order(world: World, names: str) -> None:
    calls = [t.role.value for t in world.extra["scenario"].calls]
    assert calls == _names(names), calls


def _prompt(world: World, role: Role) -> str:
    prompts = [t.prompt for t in world.extra["scenario"].calls if t.role is role]
    assert prompts, f"no {role.value} was called"
    return prompts[0]


@then(parsers.parse('the test designer\'s prompt says "{text}"'))
def the_designers_prompt_says(world: World, text: str) -> None:
    assert text in _prompt(world, Role.test_designer)


@then(parsers.parse('the producer\'s prompt says "{text}"'))
def the_producers_prompt_says(world: World, text: str) -> None:
    assert text in _prompt(world, Role.producer), _prompt(world, Role.producer)


@then(parsers.parse('the producer\'s prompt does not say "{text}"'))
def the_producers_prompt_does_not_say(world: World, text: str) -> None:
    assert text not in _prompt(world, Role.producer)


@then(parsers.parse('the "{perspective}" reviewer\'s prompt says "{text}"'))
def the_reviewers_prompt_says(world: World, perspective: str, text: str) -> None:
    marker = f"Review the change from the perspective: **{perspective}**"
    prompts = [
        t.prompt
        for t in world.extra["scenario"].calls
        if t.role is Role.reviewer and marker in t.prompt
    ]
    assert prompts, f"no {perspective} reviewer was called"
    assert text in prompts[0]


@then(parsers.parse('the test design holds "{path}"'))
def the_test_design_holds(world: World, path: str) -> None:
    assert world.run.test_design is not None
    assert world.run.test_design.files == [path], world.run.test_design


@then("the test design holds no file")
def the_test_design_holds_nothing(world: World) -> None:
    assert world.run.test_design is not None and world.run.test_design.files == []


@then("there is no test design")
def there_is_no_test_design(world: World) -> None:
    assert world.run.test_design is None


@then(parsers.parse('the test design discarded "{path}"'))
def the_test_design_discarded(world: World, path: str) -> None:
    assert world.run.test_design.discarded == [path]


@then("the test design is committed on top of the version the designer was given")
def the_test_design_is_committed(world: World) -> None:
    design = world.run.test_design
    wt = Path(world.run.worktree)
    assert design.commit != design.base_commit
    assert git.rev_parse(wt, f"{design.commit}~1") == design.base_commit
    assert git.diff_names(wt, design.base_commit, design.commit) == design.files


@then(parsers.parse('the file "{path}" at the test design\'s commit has no "{text}"'))
def the_file_at_the_commit_has_no(world: World, path: str, text: str) -> None:
    wt = Path(world.run.worktree)
    content = git.git(["show", f"{world.run.test_design.commit}:{path}"], wt)
    assert text not in content


@then(parsers.parse('a warning says "{text}"'))
def a_warning_says(world: World, text: str) -> None:
    assert any(text in w for w in world.run.warnings), world.run.warnings


@then("the run ends delivered")
def the_run_ends_delivered(world: World) -> None:
    assert world.run.status.value == "delivered", (world.run.stop_reason, world.run.warnings)


@then(parsers.parse("iteration {n:d} is rejected"))
def the_iteration_is_rejected(world: World, n: int) -> None:
    assert world.run.iterations[n - 1].outcome.value == "reject"


@then(parsers.parse('a correction request of iteration {n:d} says "{text}"'))
def a_correction_request_says(world: World, n: int, text: str) -> None:
    requests = world.run.iterations[n - 1].correction_requests
    assert any(text in c for c in requests), requests


def _scope_checks(world: World, n: int) -> list[Any]:
    it = world.run.iterations[n - 1]
    return [
        e
        for e in (world.run.evidence_by_id(x) for x in it.evidence_ids)
        if e is not None and e.kind is EvidenceKind.scope_check
    ]


@then(parsers.parse('the evidence of iteration {n:d} has a failed scope check saying "{text}"'))
def a_failed_scope_check_says(world: World, n: int, text: str) -> None:
    checks = _scope_checks(world, n)
    assert any(e.passed is False and text in e.summary for e in checks), checks


@then(parsers.parse('the evidence of iteration {n:d} has a passed scope check saying "{text}"'))
def a_passed_scope_check_says(world: World, n: int, text: str) -> None:
    checks = _scope_checks(world, n)
    assert any(e.passed is True and text in e.summary for e in checks), checks


@then(parsers.parse("the verification {vid} is {sufficiency}"))
def the_verification_is(world: World, vid: str, sufficiency: str) -> None:
    assert world.run.spec.verification(vid).sufficiency is Sufficiency(sufficiency)


@then(parsers.parse("the requirement {rid} is {status}"))
def the_requirement_is(world: World, rid: str, status: str) -> None:
    assert world.run.spec.requirement(rid).status is RequirementStatus(status)


@then(parsers.parse('the report says "{text}"'))
def the_report_says(world: World, text: str) -> None:
    assert text in render_markdown(world.run, world.engine.store)


# --------------------------------------------------------------------------- the configuration


@when("the configuration is built from")
def the_configuration_is_built(world: World, docstring: str) -> None:
    world.config = build_config(tomllib.loads(docstring))


@given(parsers.parse('a configuration with the test designer "{agent}"'))
def a_configuration_with_a_designer(world: World, agent: str) -> None:
    world.config = HarnessConfig()
    world.config.roles.test_designer = agent


@given("a configuration with no test designer")
def a_configuration_without_a_designer(world: World) -> None:
    world.config = HarnessConfig()
    world.config.roles.test_designer = None


@when(parsers.parse('the agent "{agent}" is set for every role'))
def the_agent_is_set_for_every_role(world: World, agent: str) -> None:
    assert world.config is not None
    world.config = _apply_overrides(
        world.config, agent, None, None, None, None, None, None, False, None, None
    )


@then("the configured test designer is none")
def the_configured_designer_is_none(world: World) -> None:
    assert world.config is not None and world.config.roles.test_designer is None


@then(parsers.parse('the configured test designer is "{agent}"'))
def the_configured_designer_is(world: World, agent: str) -> None:
    assert world.config is not None and world.config.roles.test_designer == agent
