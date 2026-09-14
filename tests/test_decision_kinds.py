"""No member of ``DecisionKind`` or ``EvidenceKind`` is declared without the code that reaches it.

Two contracts between an enum and the code around it, not behaviours: no scenario, but the
Given/When/Then shape (``docs/decisions/0013``). The catalogue has no entry for a role that
reads a package's own sources for the enum members they name — ``import-linter`` states rules
over imports and ``ruff`` over a file's lint, neither expresses this — so the walk is written by
hand here (``docs/decisions/0012``, point 1).

A member the sources never name is constructed nowhere, so the second test measures the mentions:
it is the weaker of the two claims and the one an ``ast`` walk can settle without guessing which
call is a construction.
"""

from __future__ import annotations

import ast
from pathlib import Path

import harness495
from harness495.core.models import DecisionKind, EvidenceKind
from harness495.interfaces.tui.stages import DECISION_STAGE

PACKAGE = Path(harness495.__file__).resolve().parent


def _members_named(enum: str) -> set[str]:
    """Every ``<enum>.<member>`` an attribute access of the package names."""
    named: set[str] = set()
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == enum
            ):
                named.add(node.attr)
    return named


def test_every_decision_kind_has_a_stop_in_the_stage_table() -> None:
    # Given the table that sends a run awaiting a decision to the stage that asks the question
    stops = set(DECISION_STAGE)
    # When it is read against the kinds a pending decision can carry
    kinds = set(DecisionKind)
    # Then it holds one stop per kind, and no stop for a kind that no longer exists:
    # ``stage_of`` reads it through a default, so a missing kind lands on the wrong tab silently.
    assert stops == kinds


def test_every_evidence_kind_is_named_by_a_module_of_the_package() -> None:
    # Given the kinds of evidence a run can hold
    declared = {member.name for member in EvidenceKind}
    # When the package's sources are read for the members they name
    named = _members_named("EvidenceKind")
    # Then no kind is declared that nothing in the harness reaches
    assert declared - named == set()
