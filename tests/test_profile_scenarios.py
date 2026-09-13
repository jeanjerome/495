"""Scenarios of ``tests/features/profile.feature``, ``catalogue.feature`` and
``proposals.feature``: the role coverage of a host project, its gaps against the catalogue,
and the conformance proposals those gaps become.

The steps lay a project out in a temporary directory from the scenario text, profile it
(through the API or through the CLI), answer the proposals through the CLI, and read the
coverage, the gaps and the proposals back; nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from typer.testing import CliRunner

from harness495.core.context import render_profile
from harness495.core.models import (
    CatalogueGap,
    CatalogueRole,
    ProjectProfile,
    Proposal,
    RoleCoverage,
    Run,
)
from harness495.core.profile import ROLES_BY_TECHNOLOGY, detect_profile
from harness495.core.store import RunStore
from harness495.interfaces.cli import app

scenarios("features/profile.feature", "features/catalogue.feature", "features/proposals.feature")


@dataclass
class Project:
    root: Path
    dependencies: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    ruff_select: list[str] = field(default_factory=list)
    profile: ProjectProfile | None = None
    last_role: RoleCoverage | None = None
    last_gap: CatalogueGap | None = None
    last_proposal: Proposal | None = None
    output: str = ""
    exit_code: int = 0

    def write_pyproject(self) -> None:
        deps = ", ".join(f'"{d}"' for d in self.dependencies)
        text = f'[project]\nname = "x"\nversion = "0"\ndependencies = [{deps}]\n'
        for section in self.sections:
            text += f"\n{section}\n"
        if self.ruff_select:
            rules = ", ".join(f'"{r}"' for r in self.ruff_select)
            text += f"\n[tool.ruff.lint]\nselect = [{rules}]\n"
        (self.root / "pyproject.toml").write_text(text)

    def profiled(self) -> ProjectProfile:
        assert self.profile is not None, "the harness has not profiled the project yet"
        return self.profile

    def coverage(self, technology: str, role: str) -> RoleCoverage:
        row = self.profiled().coverage(technology, CatalogueRole(role))
        assert row is not None, f"no coverage row for {technology} {role}"
        self.last_role = row
        return row

    def gap(self, technology: str, role: str) -> CatalogueGap | None:
        for gap in self.profiled().catalogue_gaps:
            if gap.technology == technology and gap.role is CatalogueRole(role):
                return gap
        return None

    def the_gap(self) -> CatalogueGap:
        assert self.last_gap is not None, "no gap was looked up before"
        return self.last_gap

    def store(self) -> RunStore:
        return RunStore(self.root / ".495")

    def proposals(self, technology: str, role: str) -> list[Proposal]:
        return [
            p
            for p in self.store().load_proposals().proposals
            if p.technology == technology and p.role is CatalogueRole(role)
        ]

    def proposal(self, technology: str, role: str) -> Proposal:
        found = self.proposals(technology, role)
        assert len(found) == 1, f"expected one proposal on {technology} {role}, found {found}"
        self.last_proposal = found[0]
        return found[0]

    def the_proposal(self) -> Proposal:
        assert self.last_proposal is not None, "no proposal was looked up before"
        return self.last_proposal

    def run_cli(self, *arguments: str, monkeypatch: pytest.MonkeyPatch) -> None:
        # A wide terminal: the tables are read whole, a cell is never folded on two lines.
        monkeypatch.setenv("COLUMNS", "200")
        result = CliRunner().invoke(app, ["--project", str(self.root), *arguments])
        self.output = result.output
        self.exit_code = result.exit_code


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return Project(root=tmp_path)


@given("a Python project")
def a_python_project(project: Project) -> None:
    project.write_pyproject()


@given("a shell project")
def a_shell_project(project: Project) -> None:
    (project.root / "scripts").mkdir()
    (project.root / "scripts" / "deploy.sh").write_text("#!/bin/sh\necho deploying\n")


@given("a Rust project")
def a_rust_project(project: Project) -> None:
    (project.root / "Cargo.toml").write_text('[package]\nname = "x"\n')


@given(parsers.parse('its pyproject.toml lists the dependency "{name}"'))
@when(parsers.parse('its pyproject.toml lists the dependency "{name}"'))
def pyproject_lists_a_dependency(project: Project, name: str) -> None:
    project.dependencies.append(name)
    project.write_pyproject()


@given(parsers.parse('its pyproject.toml has the section "{section}"'))
def pyproject_has_a_section(project: Project, section: str) -> None:
    project.sections.append(section)
    project.write_pyproject()


@given(parsers.parse('its pyproject.toml selects the ruff rules "{rules}"'))
def pyproject_selects_ruff_rules(project: Project, rules: str) -> None:
    project.ruff_select = [r.strip() for r in rules.split(",")]
    project.write_pyproject()


@given(parsers.parse('the file "{path}" contains "{text}"'))
def a_file_contains(project: Project, path: str, text: str) -> None:
    target = project.root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text + "\n")


@when("the harness profiles the project")
def the_harness_profiles_the_project(project: Project) -> None:
    project.profile = detect_profile(project.root)


@given("the project is a git repository")
def the_project_is_a_git_repository(project: Project) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=project.root, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")


@given(parsers.parse('the requester has run "495 {arguments}"'))
@when(parsers.parse('the requester runs "495 {arguments}"'))
def the_requester_runs(project: Project, arguments: str, monkeypatch: pytest.MonkeyPatch) -> None:
    project.run_cli(*arguments.split(), monkeypatch=monkeypatch)
    assert project.exit_code == 0, project.output


@given(
    parsers.parse(
        'the requester has accepted the proposal on "{role}" of "{technology}" without starting it'
    )
)
@when(
    parsers.parse(
        'the requester accepts the proposal on "{role}" of "{technology}" without starting it'
    )
)
def the_requester_accepts(
    project: Project, role: str, technology: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = project.proposal(technology, role)
    project.run_cli("proposals", "accept", proposal.id, "--no-start", monkeypatch=monkeypatch)
    assert project.exit_code == 0, project.output


@when(
    parsers.parse(
        'the requester tries to accept the proposal on "{role}" of "{technology}" without starting it'
    )
)
def the_requester_tries_to_accept(
    project: Project, role: str, technology: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = project.proposal(technology, role)
    project.run_cli("proposals", "accept", proposal.id, "--no-start", monkeypatch=monkeypatch)


@given(
    parsers.parse(
        'the requester has declined the proposal on "{role}" of "{technology}" with the reason "{reason}"'
    )
)
@when(
    parsers.parse(
        'the requester declines the proposal on "{role}" of "{technology}" with the reason "{reason}"'
    )
)
def the_requester_declines(
    project: Project, role: str, technology: str, reason: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = project.proposal(technology, role)
    project.run_cli(
        "proposals", "decline", proposal.id, "--reason", reason, monkeypatch=monkeypatch
    )
    assert project.exit_code == 0, project.output


@when(
    parsers.parse(
        'the requester tries to decline the proposal on "{role}" of "{technology}" with the reason "{reason}"'
    )
)
def the_requester_tries_to_decline(
    project: Project, role: str, technology: str, reason: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = project.proposal(technology, role)
    project.run_cli(
        "proposals", "decline", proposal.id, "--reason", reason, monkeypatch=monkeypatch
    )


@when(
    parsers.parse(
        'the requester tries to decline the proposal on "{role}" of "{technology}" without a reason'
    )
)
def the_requester_tries_to_decline_without_a_reason(
    project: Project, role: str, technology: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = project.proposal(technology, role)
    project.run_cli("proposals", "decline", proposal.id, "--reason", "  ", monkeypatch=monkeypatch)


@given(parsers.parse('the requester has deferred the proposal on "{role}" of "{technology}"'))
def the_requester_has_deferred(
    project: Project, role: str, technology: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = project.proposal(technology, role)
    project.run_cli("proposals", "defer", proposal.id, monkeypatch=monkeypatch)
    assert project.exit_code == 0, project.output


@then(parsers.parse('the role "{role}" of "{technology}" is measured with "{tools}"'))
def the_role_is_measured_with(project: Project, role: str, technology: str, tools: str) -> None:
    assert project.coverage(technology, role).tools == [t.strip() for t in tools.split(",")]


@then(parsers.parse('the role "{role}" of "{technology}" is not measured'))
def the_role_is_not_measured(project: Project, role: str, technology: str) -> None:
    row = project.coverage(technology, role)
    assert not row.measured and row.tools == [] and row.markers == []


@then(parsers.parse('that role is recognised from "{marker}"'))
def that_role_is_recognised_from(project: Project, marker: str) -> None:
    assert project.last_role is not None and project.last_role.markers == [marker]


@then(parsers.parse('every role of the catalogue for "{technology}" is listed'))
def every_role_of_the_catalogue_is_listed(project: Project, technology: str) -> None:
    listed = [r.role for r in project.profiled().role_coverage if r.technology == technology]
    assert listed == list(ROLES_BY_TECHNOLOGY[technology])


@then(parsers.parse('no role coverage is listed for "{technology}"'))
def no_role_coverage_is_listed_for(project: Project, technology: str) -> None:
    assert all(r.technology != technology for r in project.profiled().role_coverage)


@then(parsers.parse('the tooling names "{tool}"'))
def the_tooling_names(project: Project, tool: str) -> None:
    assert tool in project.profiled().tooling


@then(parsers.parse('the profile rendered to the agents says "{line}"'))
def the_rendered_profile_says(project: Project, line: str) -> None:
    assert line in render_profile(project.profiled())


@then(parsers.parse('the gap on "{role}" of "{technology}" is "{kind}"'))
def the_gap_is(project: Project, role: str, technology: str, kind: str) -> None:
    gap = project.gap(technology, role)
    assert gap is not None, f"no gap on {technology} {role}"
    project.last_gap = gap
    assert gap.kind.value == kind


@then(parsers.parse('there is no gap on "{role}" of "{technology}"'))
def there_is_no_gap(project: Project, role: str, technology: str) -> None:
    assert project.gap(technology, role) is None


@then(parsers.parse('that gap recommends "{tools}"'))
def that_gap_recommends(project: Project, tools: str) -> None:
    assert project.the_gap().recommended == [t.strip() for t in tools.split(",")]


@then(parsers.parse('that gap reads "{text}"'))
def that_gap_reads(project: Project, text: str) -> None:
    assert project.the_gap().statement == text


@then("that gap states no condition")
def that_gap_states_no_condition(project: Project) -> None:
    assert project.the_gap().condition == ""


@then(parsers.parse('that gap states the condition "{text}"'))
def that_gap_states_the_condition(project: Project, text: str) -> None:
    assert project.the_gap().condition == text


@then(parsers.parse('the output shows "{text}"'))
def the_output_shows(project: Project, text: str) -> None:
    assert text in project.output, project.output


@then(parsers.parse('the JSON output lists a gap on "{role}" of "{technology}"'))
def the_json_output_lists_a_gap(project: Project, role: str, technology: str) -> None:
    gaps = json.loads(project.output)["catalogue_gaps"]
    assert any(g["technology"] == technology and g["role"] == role for g in gaps), gaps


@then(parsers.parse('the proposal on "{role}" of "{technology}" is "{status}"'))
def the_proposal_is(project: Project, role: str, technology: str, status: str) -> None:
    assert project.proposal(technology, role).status.value == status


@then(parsers.parse('there is one proposal on "{role}" of "{technology}"'))
def there_is_one_proposal(project: Project, role: str, technology: str) -> None:
    assert len(project.proposals(technology, role)) == 1


@then(parsers.parse('that proposal states "{text}"'))
def that_proposal_states(project: Project, text: str) -> None:
    assert project.the_proposal().gap.statement == text


@then(parsers.parse('that proposal carries the reason "{reason}"'))
def that_proposal_carries_the_reason(project: Project, reason: str) -> None:
    assert project.the_proposal().reason == reason


@then(parsers.parse('the intent of the proposal on "{role}" of "{technology}" says "{text}"'))
def the_intent_says(project: Project, role: str, technology: str, text: str) -> None:
    intent = project.proposal(technology, role).intent
    assert text in intent, intent


@then(parsers.parse('a run of mode "{mode}" exists with the intent of that proposal'))
def a_run_exists_with_the_intent(project: Project, mode: str) -> None:
    proposal = project.the_proposal()
    assert proposal.run_id is not None
    run: Run = project.store().load(proposal.run_id)
    assert run.mode.value == mode and run.intent.text == proposal.intent


@then(parsers.parse('the run\'s intent source is "{source}"'))
def the_runs_intent_source_is(project: Project, source: str) -> None:
    proposal = project.the_proposal()
    assert proposal.run_id is not None
    assert project.store().load(proposal.run_id).intent.source == source


@then(parsers.parse('the command is refused with "{text}"'))
def the_command_is_refused_with(project: Project, text: str) -> None:
    assert project.exit_code != 0 and text in project.output, project.output


@then(
    parsers.parse(
        'the JSON output lists a proposal on "{role}" of "{technology}" with the answer starting "{prefix}"'
    )
)
def the_json_output_lists_a_proposal(
    project: Project, role: str, technology: str, prefix: str
) -> None:
    proposals = json.loads(project.output)
    matching = [
        p for p in proposals if p["gap"]["technology"] == technology and p["gap"]["role"] == role
    ]
    assert len(matching) == 1 and matching[0]["answer"].startswith(prefix), proposals
