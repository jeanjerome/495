"""The catalogue ``docs/test-libraries.md`` and the profile's notion of roles agree.

A contract between a document and the code, not a behaviour: no scenario, but the
Given/When/Then shape (``docs/decisions/0013``). The catalogue has no entry for a document
parser, so the tables are read by hand here (``docs/decisions/0012``, point 1).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from harness495.core.catalogue import CONTRADICTING_ROLES, RECOMMENDED, ROLE_CONTRACTS
from harness495.core.coverage import ROLES_BY_TECHNOLOGY
from harness495.core.models import CatalogueRole

CATALOGUE = Path(__file__).resolve().parent.parent / "docs" / "test-libraries.md"


def _first_column(table_lines: list[str]) -> list[str]:
    rows = [line for line in table_lines if line.startswith("|")]
    return [line.split("|")[1].strip() for line in rows[2:]]  # header and separator skipped


def _rows(table_lines: list[str]) -> list[list[str]]:
    rows = [line for line in table_lines if line.startswith("|")]
    return [[cell.strip() for cell in line.split("|")[1:-1]] for line in rows[2:]]


def _tools(library_cell: str) -> list[str]:
    """The tool names of a Library cell: "ruff (rules `S`), pip-audit" -> ruff, pip-audit."""
    bare = re.sub(r"\s*\(.*?\)", "", library_cell)
    return [t.strip() for t in re.split(r",\s*(?:with\s+)?", bare) if t.strip()]


def _sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        m = re.match(r"^(#{2,3}) (.+)$", line)
        if m:
            current = m.group(2).strip()
            out[current] = []
        elif current:
            out[current].append(line)
    return out


def test_the_roles_of_the_catalogue_are_the_roles_of_the_profile() -> None:
    # Given the catalogue's Roles table
    sections = _sections(CATALOGUE.read_text(encoding="utf-8"))
    # When its first column is read
    documented = _first_column(sections["Roles"])
    # Then it names exactly the roles the profile reports
    assert documented == [role.value for role in CatalogueRole]


def test_a_technology_with_markers_has_the_catalogue_table_it_covers() -> None:
    # Given the per-technology tables of the catalogue
    sections = _sections(CATALOGUE.read_text(encoding="utf-8"))
    tables = {
        TABLES[name]: _first_column(lines) for name, lines in sections.items() if name in TABLES
    }
    # When the technologies the profile has markers for are looked up
    covered = {tech: [r.value for r in roles] for tech, roles in ROLES_BY_TECHNOLOGY.items()}
    # Then each has a table, and reports exactly the roles that table lists
    for tech, roles in covered.items():
        assert tech in tables, f"{tech} has markers but no table in the catalogue"
        assert set(roles) == set(tables[tech]), f"{tech}: roles differ from the catalogue's"


TABLES = {
    "Python": "python",
    "JavaScript / TypeScript": "javascript/typescript",
    "Rust": "rust",
    "Go": "go",
    "Java / Kotlin": "java/kotlin",
    "Shell": "shell",
}
"""The per-technology tables of the document, and the technology key the code uses."""


@pytest.mark.parametrize(("table", "technology"), TABLES.items())
def test_the_recommended_entries_of_the_catalogue_are_the_recommendations_of_the_code(
    table: str, technology: str
) -> None:
    # Given one technology's table of the catalogue
    sections = _sections(CATALOGUE.read_text(encoding="utf-8"))
    rows = _rows(sections[table])
    # When its recommended entries are read, in order, with the tools of each cell
    documented = [
        (role, _tools(library)) for role, library, status, *_ in rows if status == "recommended"
    ]
    # Then they are exactly the code's recommendations for the technology, in the same order
    coded = [(r.role.value, list(r.tools)) for r in RECOMMENDED if r.technology == technology]
    assert documented == coded


def test_a_recommendation_exists_only_for_a_technology_the_profile_has_markers_for() -> None:
    # Given the code's recommendations
    technologies = {r.technology for r in RECOMMENDED}
    # When they are compared with the technologies that have coverage rows
    # Then none recommends for a technology whose rows do not exist
    assert technologies <= set(ROLES_BY_TECHNOLOGY)


def test_the_roles_proposed_to_a_host_project_are_those_the_catalogue_marks() -> None:
    # Given the Roles table of the catalogue, with its "Proposed to a host project" column
    sections = _sections(CATALOGUE.read_text(encoding="utf-8"))
    rows = _rows(sections["Roles"])
    # When the roles marked yes are read
    marked = {role for role, *_, proposed in rows if proposed.split(":")[0].strip() == "yes"}
    # Then they are exactly the roles the comparison covers
    assert marked == {role.value for role in CONTRADICTING_ROLES}


def test_what_a_test_of_each_role_must_show_is_what_the_catalogue_says() -> None:
    # Given the Roles table of the catalogue, with its "What the test must show" column
    sections = _sections(CATALOGUE.read_text(encoding="utf-8"))
    rows = _rows(sections["Roles"])
    # When that column is read per role
    documented = {role: shows for role, _contract, shows, *_ in rows}
    # Then it is what the code renders to the specifier for each role
    assert documented == {role.value: text for role, text in ROLE_CONTRACTS.items()}
