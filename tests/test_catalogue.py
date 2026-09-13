"""The catalogue ``docs/test-libraries.md`` and the profile's notion of roles agree.

A contract between a document and the code, not a behaviour: no scenario, but the
Given/When/Then shape (``docs/decisions/0013``). The catalogue has no entry for a document
parser, so the tables are read by hand here (``docs/decisions/0012``, point 1).
"""

from __future__ import annotations

import re
from pathlib import Path

from harness495.core.models import CatalogueRole
from harness495.core.profile import ROLES_BY_TECHNOLOGY

CATALOGUE = Path(__file__).resolve().parent.parent / "docs" / "test-libraries.md"


def _first_column(table_lines: list[str]) -> list[str]:
    rows = [line for line in table_lines if line.startswith("|")]
    return [line.split("|")[1].strip() for line in rows[2:]]  # header and separator skipped


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
        name.lower().replace(" ", ""): _first_column(lines)
        for name, lines in sections.items()
        if name in ("Python", "JavaScript / TypeScript", "Rust", "Go", "Java / Kotlin", "Shell")
    }
    # When the technologies the profile has markers for are looked up
    covered = {tech: [r.value for r in roles] for tech, roles in ROLES_BY_TECHNOLOGY.items()}
    # Then each has a table, and reports exactly the roles that table lists
    for tech, roles in covered.items():
        assert tech in tables, f"{tech} has markers but no table in the catalogue"
        assert set(roles) == set(tables[tech]), f"{tech}: roles differ from the catalogue's"
