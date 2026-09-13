"""The catalogue's recommendations (``docs/test-libraries.md``) and a project's gaps against them.

``RECOMMENDED`` mirrors the ``recommended`` entries of the document, per technology and role,
in the document's order, and ``ROLE_CONTRACTS`` what its Roles table says a test of each role
must show; ``tests/test_catalogue.py`` keeps them equal to the document. ``compare`` reads a
profile's role coverage and states, for each role whose measure can contradict the agent's
implementation (``CONTRADICTING_ROLES``), whether the project measures it with the entry that
applies to it; ``unmeasured_role`` says, for a verification that names a role, whether the
project can run it at all. The document stays the source: an entry is added here only once it
is in the document with its source
(``docs/decisions/0012-tests-use-proven-libraries-from-a-catalogue.md``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from harness495.core.models import (
    CatalogueGap,
    CatalogueRole,
    GapKind,
    ProjectProfile,
    RoleCoverage,
)

CONTRADICTING_ROLES: frozenset[CatalogueRole] = frozenset(
    {
        CatalogueRole.bdd,
        CatalogueRole.property,
        CatalogueRole.fuzzing,
        CatalogueRole.mutation,
        CatalogueRole.coverage,
        CatalogueRole.architecture,
        CatalogueRole.static,
        CatalogueRole.types,
        CatalogueRole.security,
        CatalogueRole.contract,
    }
)
"""The roles proposed to a host project: those whose verdict comes from outside the agent.

A scenario the requester approved, inputs the agent did not choose, a verdict on the agent's
own tests, rules the project set: each can contradict what the agent produced. The runner
carries the other roles' tests and holds no oracle of its own, a test double is a writing
discipline, a performance bound is the project's to set; those three stay in the catalogue
for 495's own tests and are never a gap. The column "Proposed to a host project" of the
document's Roles table says the same, and ``tests/test_catalogue.py`` keeps them equal.
"""

ROLE_CONTRACTS: dict[CatalogueRole, str] = {
    CatalogueRole.runner: "planned cases hold, through public interfaces",
    CatalogueRole.bdd: (
        "behaviour scenarios in Gherkin (Given/When/Then), readable by the requester, bound to "
        "steps and run by the runner"
    ),
    CatalogueRole.property: (
        "no counter-example to a stated invariant over a generated input range"
    ),
    CatalogueRole.fuzzing: "no crash, hang or unbounded consumption on malformed input",
    CatalogueRole.mutation: "the suite detects a deliberate alteration of the code it covers",
    CatalogueRole.coverage: "which changed lines the suite executes",
    CatalogueRole.architecture: "forbidden dependencies and layer crossings fail the build",
    CatalogueRole.static: "lint, formatting, complexity, duplication",
    CatalogueRole.types: "type contracts hold",
    CatalogueRole.security: "SAST findings, secrets, vulnerable dependencies",
    CatalogueRole.contract: "schemas and API descriptions match the implementation",
    CatalogueRole.performance: "latency, memory, throughput against a bound",
    CatalogueRole.doubles: "test doubles and fixtures with a known discipline",
}
"""What a test of each role must show: the column of that name in the document's Roles table.
Rendered to the specifier so that it picks the role by the contract a requirement needs."""


def _no_pytest_suite_or_standalone_features(profile: ProjectProfile) -> bool:
    runner = profile.coverage("python", CatalogueRole.runner)
    has_pytest = runner is not None and "pytest" in runner.tools
    return not has_pytest or (Path(profile.root) / "features" / "steps").is_dir()


@dataclass(frozen=True)
class Recommendation:
    """One ``recommended`` entry of the catalogue: the tools of the cell, and when it applies.

    ``applies`` is None for the first entry of a cell, the default; the entries after it
    apply when their predicate holds on the project, and ``condition`` says so in words.
    """

    technology: str
    role: CatalogueRole
    tools: tuple[str, ...]
    condition: str = ""
    applies: Callable[[ProjectProfile], bool] | None = None


RECOMMENDED: tuple[Recommendation, ...] = (
    Recommendation("python", CatalogueRole.runner, ("pytest",)),
    Recommendation("python", CatalogueRole.bdd, ("pytest-bdd",)),
    Recommendation(
        "python",
        CatalogueRole.bdd,
        ("behave",),
        "the project has no pytest suite, or keeps its scenarios in a standalone features/ tree",
        _no_pytest_suite_or_standalone_features,
    ),
    Recommendation("python", CatalogueRole.architecture, ("import-linter",)),
    Recommendation("python", CatalogueRole.static, ("ruff",)),
    Recommendation("python", CatalogueRole.types, ("mypy",)),
    Recommendation("python", CatalogueRole.property, ("hypothesis",)),
    Recommendation("python", CatalogueRole.fuzzing, ("atheris",)),
    Recommendation("python", CatalogueRole.mutation, ("mutmut",)),
    Recommendation("python", CatalogueRole.coverage, ("coverage.py", "diff-cover")),
    Recommendation("python", CatalogueRole.security, ("ruff", "pip-audit")),
    Recommendation("python", CatalogueRole.contract, ("schemathesis",)),
    Recommendation("python", CatalogueRole.performance, ("pytest-benchmark", "pytest-memray")),
    Recommendation("python", CatalogueRole.doubles, ("pytest-mock",)),
    Recommendation("shell", CatalogueRole.runner, ("bats",)),
    Recommendation("shell", CatalogueRole.bdd, ("cucumber", "aruba")),
    Recommendation("shell", CatalogueRole.static, ("shellcheck", "shfmt")),
    Recommendation("shell", CatalogueRole.security, ("shellcheck", "gitleaks")),
)
"""The document's ``recommended`` entries, in its order; a cell with several entries lists
its default first. A technology whose section of the document is empty has no entry here,
so that no gap is ever stated against a recommendation that does not exist."""


def applicable(
    technology: str, role: CatalogueRole, profile: ProjectProfile
) -> Recommendation | None:
    """The entry of the cell that applies to the project: the first conditional one whose
    condition holds, else the default; None when the catalogue has no entry for the cell."""
    entries = [r for r in RECOMMENDED if r.technology == technology and r.role is role]
    if not entries:
        return None
    for entry in entries[1:]:
        if entry.applies is not None and entry.applies(profile):
            return entry
    return entries[0]


def _gap(row: RoleCoverage, entry: Recommendation) -> CatalogueGap | None:
    in_place = list(row.tools)
    missing = [tool for tool in entry.tools if tool not in in_place]
    if not missing:
        return None
    if not in_place:
        kind = GapKind.unmeasured
    elif len(missing) == len(entry.tools):
        kind = GapKind.other_tool
    else:
        kind = GapKind.incomplete
    return CatalogueGap(
        technology=row.technology,
        role=row.role,
        kind=kind,
        in_place=in_place,
        recommended=list(entry.tools),
        missing=missing,
        condition=entry.condition,
    )


def compare(profile: ProjectProfile) -> list[CatalogueGap]:
    """The profile's gaps against the catalogue, in the order of its role coverage.

    A row is compared only when its role can contradict the agent's implementation and the
    catalogue has an entry for its technology and role; a row that measures every tool of the
    applicable entry is not a gap, whatever else it measures.
    """
    gaps: list[CatalogueGap] = []
    for row in profile.role_coverage:
        if row.role not in CONTRADICTING_ROLES:
            continue
        entry = applicable(row.technology, row.role, profile)
        if entry is None:
            continue
        gap = _gap(row, entry)
        if gap is not None:
            gaps.append(gap)
    return gaps


def unmeasured_role(role: CatalogueRole, profile: ProjectProfile) -> str | None:
    """Why a verification of ``role`` cannot run in the project, or None when it can.

    A role is measured when a coverage row of any technology names a tool for it. When every
    row of the role is empty, the sentence names the tool the catalogue recommends for each
    such technology, or says that the catalogue has no entry. When the profile has no row for
    the role at all (no technology with markers), nothing is known and None is returned: an
    unmeasured role always states a fact about the project, never a gap in the profile.
    """
    rows = [r for r in profile.role_coverage if r.role is role]
    if not rows or any(r.measured for r in rows):
        return None
    advice: list[str] = []
    declined = False
    for row in rows:
        entry = applicable(row.technology, role, profile)
        refusal = profile.declined(row.technology, role)
        if entry is None:
            advice.append(f"the catalogue has no entry for {row.technology}")
        elif refusal is not None:
            declined = True
            reason = f": {refusal.reason}" if refusal.reason else ""
            advice.append(
                f"the requester declined {', '.join(entry.tools)} for {row.technology}{reason}"
            )
        else:
            condition = f" ({entry.condition})" if entry.condition else ""
            advice.append(
                f"the catalogue recommends {', '.join(entry.tools)} for {row.technology}{condition}"
            )
    closing = (
        "; the decision stands, take a verification the project can run"
        if declined
        else "; putting the tool in place is a conformance proposal for the requester "
        "(495 proposals), not part of this change"
    )
    return (
        f"the project does not measure the {role.value} role ({ROLE_CONTRACTS[role]}); "
        + "; ".join(advice)
        + closing
    )
