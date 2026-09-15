"""Every module path the records name is a file that exists.

``AGENTS.md`` asks of a decision record that it "names every module and test that carries the
decision", and the invariants, ``docs/architecture.md`` and the catalogue name modules too. A
record whose path no longer resolves sends a reader to a file that moved, and nothing reports it:
the citation is prose, so neither ``ruff`` nor ``mypy`` nor ``lint-imports`` reads it.

A citation is read the way a reader reads it — as the tail of a path. ``core/reading/decide.py``,
``reading/decide.py`` and ``checks/sequence.py`` each name one file of the tree, and each fails
here the moment that file moves under another directory.

The documents read are those that state the tree as it stands. A dated one states what was
measured on its date — ``docs/studies/`` measures libraries, ``docs/architecture-review/``
measured the tree before it was rearranged — and ``docs/etude-harnais-495.md`` is the requester's
index of gaps, whose entries are the requester's to close. A path they name belongs to that
measurement, not to the tree.

A contract between the documents and the tree, not a behaviour: no scenario, but the
Given/When/Then shape (``docs/decisions/0013``). Hand-written: the catalogue
``docs/test-libraries.md`` has a role for forbidden dependencies (``architecture``,
import-linter) and none for what a document asserts about the tree, and no Python entry of it
reads prose (``docs/decisions/0012``).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SOURCE_TREES = ("harness495", "tests")
"""The directories whose files a document may name."""

DATED_DOCUMENTS = (
    ROOT / "docs" / "architecture-review",
    ROOT / "docs" / "studies",
    ROOT / "docs" / "etude-harnais-495.md",
)
"""Documents that record a measurement taken on a date, rather than the tree as it stands."""

HOST_PROJECT_EXAMPLES = frozenset(
    {
        "tests/test_calc.py",
        "tests/test_discounts.py",
        "tests/test_describe_clamp.py",
    }
)
"""Paths the prose gives as a host project's files, illustrating what a run does to one. They
name nothing of this repository and are not expected to exist here."""

CITATION = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*\.py")

CITATIONS_AT_LEAST = 100
"""A floor, not a tally: a pattern that stopped matching would otherwise leave the run green
with nothing checked. The documents named 126 distinct paths when this was written."""


def documents() -> list[Path]:
    """The documents that state the tree as it stands."""
    found = [ROOT / "AGENTS.md", *sorted(ROOT.glob("docs/**/*.md"))]
    return [
        document
        for document in found
        if not any(document.is_relative_to(dated) for dated in DATED_DOCUMENTS)
    ]


def tails_of_the_tree() -> set[str]:
    """Every path under the source trees, and every tail of one, on segment boundaries."""
    tails: set[str] = set()
    for tree in SOURCE_TREES:
        for module in (ROOT / tree).rglob("*.py"):
            parts = module.relative_to(ROOT).parts
            tails.update("/".join(parts[start:]) for start in range(len(parts)))
    return tails


def citations(document: Path) -> set[str]:
    """The module paths a document names: a citation with no separator names no directory."""
    cited = set(CITATION.findall(document.read_text(encoding="utf-8")))
    return {path for path in cited if "/" in path} - HOST_PROJECT_EXAMPLES


def test_given_the_documents_when_they_name_a_module_then_the_file_is_in_the_tree() -> None:
    # Given the documents that state the tree as it stands
    named: dict[str, set[str]] = {}
    for document in documents():
        for path in citations(document):
            named.setdefault(path, set()).add(str(document.relative_to(ROOT)))
    # When each path they name is looked for in the tree
    tails = tails_of_the_tree()
    stale = {path: sorted(where) for path, where in named.items() if path not in tails}
    # Then every one of them resolves, and enough were read for the check to mean something
    assert not stale, "module paths named by a document and absent from the tree: " + ", ".join(
        f"{path} ({', '.join(where)})" for path, where in sorted(stale.items())
    )
    assert len(named) >= CITATIONS_AT_LEAST, (
        f"only {len(named)} module paths read across {len(documents())} documents"
    )
