"""Scenarios of ``tests/features/scope.feature``: the paths a change is allowed to touch.

The steps hand ``core.reading.scope.check_scope`` the files and the two pattern lists the
scenario states, and read the report it returns; nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core.reading.scope import ScopeReport, check_scope

scenarios("features/scope.feature")


def _paths(text: str) -> list[str]:
    return [p.strip() for p in text.split(",") if p.strip()]


@dataclass
class Case:
    files: list[str]
    allowed: list[str]
    forbidden: list[str]
    report: ScopeReport | None = None

    def result(self) -> ScopeReport:
        assert self.report is not None, "the harness has not checked the scope yet"
        return self.report


@pytest.fixture
def case() -> Case:
    return Case(files=[], allowed=[], forbidden=[])


@given(parsers.parse('a change touching "{files}"'))
def a_change_touching(case: Case, files: str) -> None:
    case.files = _paths(files)


@given(parsers.parse('the allowed paths "{patterns}"'))
def the_allowed_paths(case: Case, patterns: str) -> None:
    case.allowed = _paths(patterns)


@given(parsers.parse('the forbidden paths "{patterns}"'))
def the_forbidden_paths(case: Case, patterns: str) -> None:
    case.forbidden = _paths(patterns)


@given("no allowed path is declared")
def no_allowed_path(case: Case) -> None:
    case.allowed = []


@given("no path is forbidden")
def no_forbidden_path(case: Case) -> None:
    case.forbidden = []


@when("the harness checks the scope")
def the_harness_checks_the_scope(case: Case) -> None:
    case.report = check_scope(case.files, case.allowed, case.forbidden)


@then(parsers.parse('the files outside the allowed paths are "{files}"'))
def the_files_outside_are(case: Case, files: str) -> None:
    assert case.result().violations == _paths(files)


@then(parsers.parse('the forbidden paths touched are "{files}"'))
def the_forbidden_paths_touched_are(case: Case, files: str) -> None:
    assert case.result().forbidden_hits == _paths(files)


@then("the change is within scope")
def the_change_is_within_scope(case: Case) -> None:
    assert case.result().ok


@then("the change is out of scope")
def the_change_is_out_of_scope(case: Case) -> None:
    assert not case.result().ok


@then(parsers.parse('the summary says "{text}"'))
def the_summary_says(case: Case, text: str) -> None:
    assert text in case.result().summary()
