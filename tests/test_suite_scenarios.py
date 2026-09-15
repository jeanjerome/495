"""Scenarios of ``tests/features/suite.feature``: the existing test suite is measured on the
change, and a passing command on a weaker suite credits no non-regression requirement.

The diff and tally scenarios call the pure readers of ``core.suite``; the decision scenarios
call ``core.decide.assess`` once; the run scenarios walk a change run with the scripted agents
of ``conftest`` and read the run, the prompts and the report back. The last section reaches
``core.engine.checks.suite`` on its own, through a ``RunServices`` over a recording store that
holds what each version printed, so that which commands the check compares and which
requirements it names are measured without a run reaching ``produced``. Nothing is asserted
outside a ``Then``.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core.engine.checks.suite import check_suite
from harness495.core.models import (
    DecisionKind,
    Evidence,
    EvidenceKind,
    Finding,
    Requirement,
    RequirementKind,
    RequirementStatus,
    ReviewVerdict,
    Role,
    RunMode,
    RunStatus,
    Severity,
    Spec,
    Verdict,
    Verification,
    VerificationKind,
)
from harness495.core.reading.decide import Assessment, assess
from harness495.core.reading.suite import (
    CountComparison,
    SuiteChange,
    SuiteCount,
    SuiteReading,
    compare_counts,
    count_tests,
    read_suite_changes,
)
from harness495.core.report import render_markdown
from tests.conftest import SAMPLE_MODULE, SAMPLE_TEST, Measured, Region, Scenario, measure

scenarios("features/suite.feature")


@dataclass
class World:
    diff: str = ""
    changes: list[SuiteChange] = field(default_factory=list)
    count: SuiteCount | None = None
    base_output: str = ""
    change_output: str = ""
    comparison: CountComparison | None = None
    spec: Spec = field(default_factory=Spec)
    evidence: list[Evidence] = field(default_factory=list)
    reviews: list[ReviewVerdict] = field(default_factory=list)
    assessment: Assessment | None = None
    engine: Any = None
    run: Any = None
    extra: dict[str, Any] = field(default_factory=dict)

    def result(self) -> Assessment:
        assert self.assessment is not None, "the harness has not assessed the change yet"
        return self.assessment


@pytest.fixture
def world() -> World:
    return World()


def _unescape(text: str) -> str:
    return text.replace("\\n", "\n").replace("\\t", "\t")


def _diff(file: str, hunk: list[str], new_file: str | None = None, mode: str = "") -> str:
    target = new_file or file
    header = [f"diff --git a/{file} b/{target}"]
    if mode:
        header.append(mode)
    if new_file:
        header += [f"rename from {file}", f"rename to {new_file}"]
    header += ["index 0000000..1111111 100644", f"--- a/{file}", f"+++ b/{target}"]
    body = ["@@ -1,3 +1,3 @@", " import calc"] + hunk if hunk else []
    return "\n".join(header + body) + "\n"


# --------------------------------------------------------------------------- the diff


@given(parsers.parse('a diff of "{file}" that removes the line "{line}"'))
def a_diff_removing(world: World, file: str, line: str) -> None:
    world.diff = _diff(file, ["-" + _unescape(line)])


@given(parsers.parse('a diff of "{file}" that adds the line "{line}"'))
def a_diff_adding(world: World, file: str, line: str) -> None:
    world.diff = _diff(file, ["+" + _unescape(line)])


@given(parsers.parse('a diff of "{file}" that replaces the line "{old}" with "{new}"'))
def a_diff_replacing(world: World, file: str, old: str, new: str) -> None:
    world.diff = _diff(file, ["-" + _unescape(old), "+" + _unescape(new)])


@given(
    parsers.parse(
        'a diff of "{file}" that removes the line "{removed}" and adds the line "{added}"'
    )
)
def a_diff_removing_and_adding(world: World, file: str, removed: str, added: str) -> None:
    world.diff = _diff(file, ["-" + _unescape(removed), "+" + _unescape(added)])


@given(parsers.parse('a diff that creates "{file}" with the line "{line}"'))
def a_diff_creating(world: World, file: str, line: str) -> None:
    world.diff = _diff(file, ["+" + _unescape(line)], mode="new file mode 100644")


@given(parsers.parse('a diff that deletes "{file}"'))
def a_diff_deleting(world: World, file: str) -> None:
    world.diff = _diff(
        file, ["-def test_add():", "-    assert True"], mode="deleted file mode 100644"
    )


@given(parsers.parse('a diff that renames "{file}" to "{new_file}"'))
def a_diff_renaming(world: World, file: str, new_file: str) -> None:
    world.diff = _diff(file, [], new_file=new_file, mode="similarity index 100%")


@when("the harness reads the suite")
def the_harness_reads_the_suite(world: World) -> None:
    world.changes = read_suite_changes(world.diff)


@then("the suite is weakened")
def the_suite_is_weakened(world: World) -> None:
    assert SuiteReading(world.changes, []).weakened, world.changes


@then("the suite is not weakened")
def the_suite_is_not_weakened(world: World) -> None:
    assert not SuiteReading(world.changes, []).weakened, world.changes


@then(parsers.parse('the reading says "{text}"'))
def the_reading_says(world: World, text: str) -> None:
    rendered = SuiteReading(world.changes, []).render()
    assert _unescape(text) in rendered, rendered


@then("no existing test file is listed")
def no_existing_test_file_is_listed(world: World) -> None:
    assert world.changes == []


# --------------------------------------------------------------------------- the tally


@when(parsers.parse('the harness counts the tests in "{output}"'))
def the_harness_counts(world: World, output: str) -> None:
    world.count = count_tests(_unescape(output))


@then(parsers.parse('the tally is {ran:d} ran and {skipped:d} skipped by "{runner}"'))
def the_tally_is(world: World, ran: int, skipped: int, runner: str) -> None:
    assert world.count == SuiteCount(ran=ran, skipped=skipped, runner=runner), world.count


@then("no tally is read")
def no_tally_is_read(world: World) -> None:
    assert world.count is None


@given(parsers.parse('the base printed "{base}" and the change printed "{change}"'))
def the_versions_printed(world: World, base: str, change: str) -> None:
    world.base_output = _unescape(base)
    world.change_output = _unescape(change)


@when(parsers.parse("the harness compares the tallies for {vid}"))
def the_harness_compares(world: World, vid: str) -> None:
    world.comparison = compare_counts(vid, world.base_output, world.change_output)


@then("the comparison is weakened")
def the_comparison_is_weakened(world: World) -> None:
    assert world.comparison is not None and world.comparison.weakened, world.comparison


@then("the comparison is not weakened")
def the_comparison_is_not_weakened(world: World) -> None:
    assert world.comparison is not None and not world.comparison.weakened, world.comparison


@then(parsers.parse('the comparison says "{text}"'))
def the_comparison_says(world: World, text: str) -> None:
    assert world.comparison is not None and text in world.comparison.describe()


# --------------------------------------------------------------------------- the decision


@given(parsers.parse("a {kind} requirement {rid} verified by the test {vid}"))
def a_requirement_verified_by_a_test(world: World, kind: str, rid: str, vid: str) -> None:
    world.spec.requirements.append(
        Requirement(
            id=rid,
            statement=rid,
            kind=RequirementKind(kind.replace("-", "_")),
            verification_ids=[vid],
        )
    )
    world.spec.verifications.append(
        Verification(id=vid, kind=VerificationKind.test, description=vid, command="true")
    )


@given(parsers.parse("{vid} {result} on the change"))
def a_verification_ran_on_the_change(world: World, vid: str, result: str) -> None:
    world.evidence.append(
        Evidence(
            id=f"ev-{vid}-{result}",
            kind=EvidenceKind.command_result,
            iteration=1,
            verification_id=vid,
            passed=result == "passed",
            summary=result,
        )
    )


@given(parsers.parse('a failed suite check naming {rid} saying "{summary}"'))
def a_failed_suite_check(world: World, rid: str, summary: str) -> None:
    world.evidence.append(
        Evidence(
            id="ev-suite",
            kind=EvidenceKind.suite_check,
            iteration=1,
            requirement_ids=[] if rid == "no requirement" else [rid],
            passed=False,
            summary=summary,
        )
    )


@given(parsers.parse("a passed suite check naming {rid}"))
def a_passed_suite_check(world: World, rid: str) -> None:
    world.evidence.append(
        Evidence(
            id="ev-suite",
            kind=EvidenceKind.suite_check,
            iteration=1,
            requirement_ids=[rid],
            passed=True,
            summary="no existing test file modified",
        )
    )


@given("a reviewer accepted the change")
def a_reviewer_accepted(world: World) -> None:
    world.reviews.append(
        ReviewVerdict(intervention_id="int-p", perspective="p", verdict=Verdict.accept)
    )


@given(
    parsers.re(
        r"a reviewer rejected the change with a major finding on (?P<rid>\w+) "
        r'citing "(?P<observation>.*)"'
    )
)
def a_reviewer_rejected_with_a_major_finding(world: World, rid: str, observation: str) -> None:
    finding = Finding(
        severity=Severity.major, title="bad", requirement_id=rid, evidence=observation
    )
    world.reviews.append(
        ReviewVerdict(
            intervention_id="int-p", perspective="p", verdict=Verdict.reject, findings=[finding]
        )
    )


@when("the harness assesses the change")
def the_harness_assesses_the_change(world: World) -> None:
    world.assessment = assess(world.spec, world.evidence, world.reviews)


@then(parsers.parse("the outcome is {outcome}"))
def the_outcome_is(world: World, outcome: str) -> None:
    assert world.result().outcome is Verdict(outcome), world.result()


@then(parsers.parse('the reason for {rid} says "{text}"'))
def the_reason_says(world: World, rid: str, text: str) -> None:
    assert text in world.result().reasons[rid], world.result().reasons


@then(parsers.parse('a requirement was not credited: "{text}"'))
def a_requirement_was_not_credited(world: World, text: str) -> None:
    assert text in world.result().uncredited, world.result().uncredited


@then(parsers.parse('an undetermined reason says "{text}"'))
def an_undetermined_reason_says(world: World, text: str) -> None:
    assert any(text in r for r in world.result().undetermined_reasons), world.result()


# --------------------------------------------------------------------------- through the engine


def _subtract(cwd: Path) -> None:
    (cwd / "calc.py").write_text(
        SAMPLE_MODULE + "\n\ndef subtract(a: int, b: int) -> int:\n    return a - b\n",
        encoding="utf-8",
    )


def remove_test_add(cwd: Path) -> None:
    _subtract(cwd)
    (cwd / "tests" / "test_calc.py").write_text("from calc import add\n", encoding="utf-8")


def skip_test_add(cwd: Path) -> None:
    _subtract(cwd)
    (cwd / "tests" / "test_calc.py").write_text(
        "import pytest\n\nfrom calc import add\n\n\n@pytest.mark.skip(reason='later')\n"
        "def test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )


def edit_test_add(cwd: Path) -> None:
    _subtract(cwd)
    (cwd / "tests" / "test_calc.py").write_text(
        SAMPLE_TEST.replace("== 5", "== 5  # still five"), encoding="utf-8"
    )


@given("the sample project")
def the_sample_project(
    world: World, sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    world.extra["project"] = sample_project
    world.extra["config"] = config
    world.extra["scenario"] = scenario
    # V1 runs the designed test, so that it fails without the change and observes it with it.
    scenario.spec["verifications"][0]["command"] = (
        f"{sys.executable} -m pytest -q -p no:cacheprovider tests/test_subtract.py"
    )
    world.engine = engine_factory()


@given(
    parsers.parse('the producer implements the behaviour and removes the existing test "{name}"')
)
def the_producer_removes(world: World, name: str) -> None:
    assert name == "test_add"
    world.extra["scenario"].producers = [remove_test_add]


@given(parsers.parse('the producer implements the behaviour and skips the existing test "{name}"'))
def the_producer_skips(world: World, name: str) -> None:
    assert name == "test_add"
    world.extra["scenario"].producers = [skip_test_add]


@given(
    parsers.parse(
        'the producer implements the behaviour and edits the assertion of the existing test "{name}"'
    )
)
def the_producer_edits(world: World, name: str) -> None:
    assert name == "test_add"
    world.extra["scenario"].producers = [edit_test_add]


@when("a change run walks the workflow")
def a_change_run_walks_the_workflow(world: World) -> None:
    run = world.engine.create_run(
        "add subtract to calc", world.extra["project"], world.extra["config"], RunMode.change
    )
    world.run = world.engine.run(run.id)


@when(parsers.parse('the requester accepts the risk with the note "{note}"'))
def the_requester_accepts_the_risk(world: World, note: str) -> None:
    world.engine.decide(world.run.id, "accept_with_risk", note=note)
    world.run = world.engine.run(world.run.id)


def _suite_checks(world: World, n: int) -> list[Evidence]:
    it = world.run.iterations[n - 1]
    return [
        e
        for e in (world.run.evidence_by_id(x) for x in it.evidence_ids)
        if e is not None and e.kind is EvidenceKind.suite_check
    ]


@then(parsers.parse('the suite check of iteration {n:d} passed saying "{text}"'))
def the_suite_check_passed(world: World, n: int, text: str) -> None:
    checks = _suite_checks(world, n)
    assert len(checks) == 1 and checks[0].passed is True and text in checks[0].summary, checks


@then(parsers.parse('the suite check of iteration {n:d} failed saying "{text}"'))
def the_suite_check_failed(world: World, n: int, text: str) -> None:
    checks = _suite_checks(world, n)
    assert len(checks) == 1 and checks[0].passed is False and text in checks[0].summary, checks


@then(parsers.parse("the requirement {rid} is {status}"))
def the_requirement_is(world: World, rid: str, status: str) -> None:
    if world.run is not None:
        assert world.run.spec.requirement(rid).status is RequirementStatus(status)
    else:
        assert world.result().requirement_status[rid] is RequirementStatus(status)


@then(parsers.parse('the run\'s reason for {rid} says "{text}"'))
def the_reason_in_the_run_says(world: World, rid: str, text: str) -> None:
    reason = world.run.spec.requirement(rid).status_reason
    assert text in reason, reason


@then("the run awaits the requester on an undetermined verdict")
def the_run_awaits_the_requester(world: World) -> None:
    assert world.run.status is RunStatus.awaiting_decision, world.run.status
    assert world.run.pending_decision.kind is DecisionKind.undetermined


@then("the run ends delivered")
def the_run_ends_delivered(world: World) -> None:
    assert world.run.status is RunStatus.delivered, (world.run.stop_reason, world.run.warnings)


def _prompt(world: World, role: Role) -> str:
    prompts = [t.prompt for t in world.extra["scenario"].calls if t.role is role]
    assert prompts, f"no {role.value} was called"
    return prompts[0]


@then(parsers.parse('the producer\'s prompt says "{text}"'))
def the_producers_prompt_says(world: World, text: str) -> None:
    assert text in _prompt(world, Role.producer)


@then(parsers.parse('the "{perspective}" reviewer\'s prompt says "{text}"'))
def the_reviewers_prompt_says(world: World, perspective: str, text: str) -> None:
    marker = f"Review the change from the perspective: **{perspective}**"
    prompts = [
        t.prompt
        for t in world.extra["scenario"].calls
        if t.role is Role.reviewer and marker in t.prompt
    ]
    assert prompts, f"no {perspective} reviewer was called"
    assert text in prompts[0], prompts[0]


@then(parsers.parse('the report says "{text}"'))
def the_report_says(world: World, text: str) -> None:
    assert text in render_markdown(world.run, world.engine.store)


# --------------------------------------------------------------------- the check on its own


@given("a version under review", target_fixture="region")
def a_version_under_review(produced_version: Callable[..., Region]) -> Region:
    return produced_version()


@given(parsers.parse("a non-regression requirement {rid} resting on the test command {vid}"))
def a_non_regression_requirement_on_a_test(region: Region, rid: str, vid: str) -> None:
    region.verification(
        vid,
        command=f"run {vid}",
        kind=VerificationKind.test,
        requirement=rid,
        requirement_kind=RequirementKind.non_regression,
    )


@given(parsers.parse("a non-regression requirement {rid} resting on the linter {vid}"))
def a_non_regression_requirement_on_a_linter(region: Region, rid: str, vid: str) -> None:
    region.verification(
        vid,
        command=f"run {vid}",
        kind=VerificationKind.lint,
        requirement=rid,
        requirement_kind=RequirementKind.non_regression,
    )


@given(
    parsers.parse(
        '{vid} printed "{change}" on the version under review and was never run on the base'
    )
)
def a_command_with_no_baseline(region: Region, vid: str, change: str) -> None:
    region.ran_command(vid, output=change)


@given(
    parsers.parse('{vid} printed "{base}" on the base and "{change}" on the version under review')
)
def a_command_run_on_both_versions(region: Region, vid: str, base: str, change: str) -> None:
    region.baseline(f"run {vid}", base)
    region.ran_command(vid, output=change)


@when("the suite check measures the version", target_fixture="measured")
def the_suite_check_measures_the_version(region: Region) -> Measured:
    return measure(
        lambda: check_suite(
            region.services, region.run, region.iteration, list(region.run.evidence)
        )
    )


def _suite_check(measured: Measured) -> Evidence:
    assert len(measured.evidence) == 1, [e.summary for e in measured.evidence]
    return measured.evidence[0]


@then(parsers.parse('the suite check says "{text}"'))
def the_suite_check_says(measured: Measured, text: str) -> None:
    assert text in _suite_check(measured).summary, _suite_check(measured).summary


@then("the suite check passed")
def the_measured_suite_check_passed(measured: Measured) -> None:
    assert _suite_check(measured).passed is True, _suite_check(measured).summary


@then("the suite check failed")
def the_measured_suite_check_failed(measured: Measured) -> None:
    assert _suite_check(measured).passed is False, _suite_check(measured).summary


@then(parsers.parse("the suite check names {rid}"))
def the_suite_check_names(measured: Measured, rid: str) -> None:
    assert rid in _suite_check(measured).requirement_ids, _suite_check(measured).requirement_ids


@then(parsers.parse("the suite check does not name {rid}"))
def the_suite_check_does_not_name(measured: Measured, rid: str) -> None:
    assert rid not in _suite_check(measured).requirement_ids, _suite_check(measured).requirement_ids
