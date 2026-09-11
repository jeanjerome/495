from __future__ import annotations

from harness495.core.decide import assess
from harness495.core.models import (
    Evidence,
    EvidenceKind,
    Finding,
    Requirement,
    RequirementStatus,
    ReviewVerdict,
    Severity,
    Spec,
    Sufficiency,
    Verdict,
    Verification,
    VerificationKind,
)
from harness495.core.scope import check_scope


def test_scope_globs() -> None:
    files = ["src/a.py", "tests/test_a.py", "README.md", ".github/workflows/ci.yml", "docs/x/y.md"]
    rep = check_scope(files, ["src/**", "tests/**"], [".github/**"])
    assert rep.violations == ["README.md", "docs/x/y.md"]
    assert rep.forbidden_hits == [".github/workflows/ci.yml"]
    assert not rep.ok
    assert check_scope(["src/a.py"], [], [".495/**"]).ok
    assert check_scope(["calc.py"], ["calc.py", "tests/**"], []).ok
    assert check_scope(["a/b/c.py"], ["a/**/c.py"], []).ok
    assert "forbidden" in check_scope([".495/runs/x"], [], [".495/**"]).summary()


def _spec() -> Spec:
    return Spec(
        requirements=[
            Requirement(id="R1", statement="one", verification_ids=["V1"]),
            Requirement(id="R2", statement="two", verification_ids=["V2"]),
        ],
        verifications=[
            Verification(id="V1", kind=VerificationKind.test, description="t", command="true"),
            Verification(
                id="V2",
                kind=VerificationKind.review,
                description="r",
                sufficiency=Sufficiency.insufficient,
            ),
        ],
    )


def _ev(vid: str, passed: bool | None, iteration: int = 1) -> Evidence:
    return Evidence(
        id=f"ev-{vid}-{passed}",
        kind=EvidenceKind.command_result,
        iteration=iteration,
        verification_id=vid,
        passed=passed,
        summary="x",
    )


def _review(
    perspective: str,
    verdict: Verdict,
    findings: list[Finding] | None = None,
    assessment: dict[str, RequirementStatus] | None = None,
) -> ReviewVerdict:
    return ReviewVerdict(
        intervention_id="int-" + perspective,
        perspective=perspective,
        verdict=verdict,
        findings=findings or [],
        requirement_assessment=assessment or {},
    )


def test_undetermined_without_sufficient_verification() -> None:
    spec = _spec()
    a = assess(spec, [_ev("V1", True)], [_review("p", Verdict.accept)])
    assert a.requirement_status["R1"] is RequirementStatus.satisfied
    assert a.requirement_status["R2"] is RequirementStatus.undetermined
    assert a.outcome is Verdict.undetermined


def test_failed_verification_rejects_with_correction() -> None:
    spec = _spec()
    spec.verifications[1] = Verification(
        id="V2", kind=VerificationKind.test, description="t", command="false"
    )
    a = assess(spec, [_ev("V1", True), _ev("V2", False)], [_review("p", Verdict.accept)])
    assert a.outcome is Verdict.reject
    assert a.requirement_status["R2"] is RequirementStatus.violated
    assert any("[R2]" in c for c in a.correction_requests)


def test_reviewer_violation_requires_evidence() -> None:
    spec = _spec()
    spec.verifications[1] = Verification(
        id="V2", kind=VerificationKind.test, description="t", command="true"
    )
    evidence = [_ev("V1", True), _ev("V2", True)]
    no_evidence = Finding(severity=Severity.major, title="bad", requirement_id="R1", evidence="")
    a = assess(spec, evidence, [_review("p", Verdict.reject, [no_evidence])])
    # A major finding without evidence does not make the requirement violated.
    assert a.requirement_status["R1"] is RequirementStatus.satisfied
    assert a.outcome is Verdict.accept
    with_evidence = Finding(
        severity=Severity.major, title="bad", requirement_id="R1", evidence="file.py:3"
    )
    a = assess(spec, evidence, [_review("p", Verdict.reject, [with_evidence])])
    assert a.requirement_status["R1"] is RequirementStatus.violated
    assert a.outcome is Verdict.reject


def test_no_review_means_undetermined_and_discarded_ignored() -> None:
    spec = _spec()
    spec.verifications[1] = Verification(
        id="V2", kind=VerificationKind.test, description="t", command="true"
    )
    evidence = [_ev("V1", True), _ev("V2", True)]
    a = assess(spec, evidence, [])
    assert a.outcome is Verdict.undetermined
    discarded = _review(
        "p", Verdict.reject, [Finding(severity=Severity.blocker, title="x", evidence="y")]
    )
    discarded.discarded = True
    a = assess(spec, evidence, [discarded, _review("q", Verdict.accept)])
    assert a.outcome is Verdict.accept


def test_unattached_blocker_and_scope_block_acceptance() -> None:
    spec = _spec()
    spec.verifications[1] = Verification(
        id="V2", kind=VerificationKind.test, description="t", command="true"
    )
    evidence = [_ev("V1", True), _ev("V2", True)]
    blocker = Finding(severity=Severity.blocker, title="secret committed", evidence=".env:1")
    a = assess(spec, evidence, [_review("security", Verdict.reject, [blocker])])
    assert a.outcome is Verdict.reject and any("secret" in c for c in a.correction_requests)
    scope = Evidence(
        id="ev-scope",
        kind=EvidenceKind.scope_check,
        iteration=1,
        passed=False,
        summary="outside allowed paths: x",
    )
    a = assess(spec, [*evidence, scope], [_review("p", Verdict.accept)])
    assert a.outcome is Verdict.reject and any("[scope]" in c for c in a.correction_requests)


def test_correction_states_the_observation_not_the_remedy() -> None:
    """A reviewer's explanation is where the remedy hides; only its observation travels."""
    spec = _spec()
    spec.verifications[1] = Verification(
        id="V2", kind=VerificationKind.test, description="t", command="true"
    )
    finding = Finding(
        severity=Severity.major,
        title="subtract adds instead of subtracting",
        detail="change `return a + b` to `return a - b` on line 8",
        requirement_id="R1",
        evidence="calc.py:8 `return a + b`",
    )
    a = assess(spec, [_ev("V1", True), _ev("V2", True)], [_review("p", Verdict.reject, [finding])])
    correction = next(c for c in a.correction_requests if c.startswith("[R1]"))
    assert "subtract adds instead of subtracting" in correction
    assert "calc.py:8" in correction
    assert "return a - b" not in correction


def test_one_failing_verification_yields_one_correction_for_all_its_requirements() -> None:
    spec = Spec(
        requirements=[
            Requirement(id=f"R{n}", statement=f"r{n}", verification_ids=["V1"]) for n in range(1, 5)
        ],
        verifications=[
            Verification(id="V1", kind=VerificationKind.test, description="t", command="false")
        ],
    )
    a = assess(spec, [_ev("V1", False)], [_review("p", Verdict.accept)])
    failures = [c for c in a.correction_requests if "not demonstrated" in c]
    assert len(failures) == 1
    assert failures[0].startswith("[R1,R2,R3,R4]")
    assert "make verification pass" not in failures[0]


def test_a_verification_that_cannot_see_the_change_is_not_charged_to_the_change() -> None:
    spec = Spec(
        requirements=[
            Requirement(id="R1", statement="behaviour", verification_ids=["V1"]),
        ],
        verifications=[
            Verification(
                id="V1",
                kind=VerificationKind.test,
                description="t",
                command="false",
                sufficiency=Sufficiency.faulty,
                rationale="fails identically on the base version",
            )
        ],
    )
    a = assess(spec, [_ev("V1", False)], [_review("p", Verdict.accept)])
    assert a.requirement_status["R1"] is RequirementStatus.undetermined
    assert a.outcome is Verdict.undetermined
    assert a.correction_requests == []
    assert a.instrument_faults and a.instrument_faults[0].startswith("V1:")
    assert "does not observe the change" in a.reasons["R1"] or "base version" in a.reasons["R1"]


def test_finding_that_rests_on_a_blind_verification_is_set_aside() -> None:
    """A reviewer reads a failing command as a defect; the harness knows better by then."""
    spec = Spec(
        requirements=[Requirement(id="R1", statement="behaviour", verification_ids=["V1"])],
        verifications=[
            Verification(
                id="V1",
                kind=VerificationKind.test,
                description="t",
                command="false",
                sufficiency=Sufficiency.faulty,
                rationale="fails identically on the base version",
            )
        ],
    )
    finding = Finding(
        severity=Severity.major,
        title="the verification designated for R1 fails",
        requirement_id="R1",
        evidence="ev-1 [FAIL] for V1: exit 1 (expected 0)",
    )
    review = _review(
        "spec_compliance", Verdict.reject, [finding], {"R1": RequirementStatus.violated}
    )
    a = assess(spec, [_ev("V1", False)], [review])
    assert a.requirement_status["R1"] is RequirementStatus.undetermined
    assert a.correction_requests == []
    assert "set aside" in a.reasons["R1"]
    # A finding standing on the code itself is unaffected.
    real = Finding(
        severity=Severity.major,
        title="wrong operator",
        requirement_id="R1",
        evidence="calc.py:8 `return a + b`",
    )
    a = assess(spec, [_ev("V1", False)], [_review("correctness", Verdict.reject, [real])])
    assert a.requirement_status["R1"] is RequirementStatus.violated
    assert any("wrong operator" in c for c in a.correction_requests)


def test_a_control_run_never_stands_in_for_the_verification_it_checks() -> None:
    """The control is measured on the base version; it says nothing about the change."""
    spec = Spec(
        requirements=[Requirement(id="R1", statement="behaviour", verification_ids=["V1"])],
        verifications=[
            Verification(id="V1", kind=VerificationKind.test, description="t", command="cmd")
        ],
    )
    control = Evidence(
        id="ev-control",
        kind=EvidenceKind.instrument_check,
        iteration=1,
        verification_id="V1",
        passed=None,
        summary="control run on the base version: exit 1",
    )
    passing = _ev("V1", True)
    a = assess(spec, [passing, control], [_review("p", Verdict.accept)])
    assert a.requirement_status["R1"] is RequirementStatus.satisfied, a.reasons["R1"]
    assert "not executed" not in a.reasons["R1"]

    failing = _ev("V1", False)
    a = assess(spec, [failing, control], [_review("p", Verdict.accept)])
    assert a.requirement_status["R1"] is RequirementStatus.violated
    assert any("not demonstrated" in c for c in a.correction_requests)
