"""Scenarios of ``tests/features/running.feature``: what ``core/engine/running.py`` records of
a verification it ran.

The steps take the produced version ``conftest`` builds — a real repository holding the base
and the head commit — run one command in it through the ordinary sandbox, and read the
evidence and the stored output back. Nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core import git
from harness495.core.engine.running import VersionMismatch, run_verification
from harness495.core.models import Evidence, Verification, VerificationKind
from harness495.sandbox import Sandbox
from tests.conftest import Region

scenarios("features/running.feature")


@dataclass
class World:
    region: Region | None = None
    outputs: dict[str, str] = field(default_factory=dict)
    evidence: Evidence | None = None
    refused: Exception | None = None

    def the_region(self) -> Region:
        assert self.region is not None, "no version was produced"
        return self.region

    def the_evidence(self) -> Evidence:
        assert self.evidence is not None, "no verification was run"
        return self.evidence

    def sink(self, evidence_id: str, text: str) -> str:
        self.outputs[evidence_id] = text
        return f"evidence/{evidence_id}/output.txt"


@pytest.fixture
def world() -> World:
    return World()


@given("a produced version")
def a_produced_version(world: World, produced_version: Callable[..., Region]) -> None:
    world.region = produced_version()


@when(
    parsers.parse('"{vid}" runs "{command}" on the evaluated version, expecting exit {expected:d}')
)
def it_runs_on_the_evaluated_version(world: World, vid: str, command: str, expected: int) -> None:
    region = world.the_region()
    world.evidence = run_verification(
        Verification(
            id=vid,
            kind=VerificationKind.command,
            description=vid,
            command=command,
            expected_exit_code=expected,
        ),
        region.root,
        region.head,
        Sandbox(),
        1,
        30,
        world.sink,
        None,
        ["R1"],
    )


@when(parsers.parse('"{vid}" runs "{command}" against a version the worktree is not at'))
def it_runs_against_another_version(world: World, vid: str, command: str) -> None:
    region = world.the_region()
    try:
        run_verification(
            Verification(id=vid, kind=VerificationKind.command, description=vid, command=command),
            region.root,
            "0" * 40,
            Sandbox(),
            1,
            30,
            world.sink,
        )
    except VersionMismatch as exc:
        world.refused = exc


@when(parsers.parse('"{vid}" has no command to run'))
def it_has_no_command(world: World, vid: str) -> None:
    region = world.the_region()
    world.evidence = run_verification(
        Verification(id=vid, kind=VerificationKind.manual, description=vid),
        region.root,
        region.head,
        Sandbox(),
        1,
        30,
        world.sink,
    )


@then("the evidence says the verification passed")
def the_evidence_says_it_passed(world: World) -> None:
    assert world.the_evidence().passed is True


@then("the evidence says nothing about the change")
def the_evidence_says_nothing(world: World) -> None:
    assert world.the_evidence().passed is None


@then(parsers.parse("the evidence records exit {code:d}"))
def the_evidence_records_exit(world: World, code: int) -> None:
    assert world.the_evidence().exit_code == code


@then(parsers.parse('the evidence names the requirement "{rid}"'))
def the_evidence_names_the_requirement(world: World, rid: str) -> None:
    assert world.the_evidence().requirement_ids == [rid]


@then(parsers.parse('the output stored under the evidence says "{text}"'))
def the_stored_output_says(world: World, text: str) -> None:
    assert text in world.outputs[world.the_evidence().id]


@then("the evidence carries the fingerprint of that output")
def the_evidence_carries_the_fingerprint(world: World) -> None:
    evidence = world.the_evidence()
    assert evidence.output_sha256 == git.sha256_text(world.outputs[evidence.id])


@then(parsers.parse('the evidence summary says "{text}"'))
def the_evidence_summary_says(world: World, text: str) -> None:
    assert text in world.the_evidence().summary


@then("the run is refused as a version mismatch")
def the_run_is_refused(world: World) -> None:
    assert isinstance(world.refused, VersionMismatch)
