"""Scenarios of ``tests/features/decide.feature``: the decision as a function of the evidence.

The steps build a specification, evidence and reviews from the scenario text, call
``core.decide.assess`` once, and read the assessment; nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core.decide import Assessment, assess
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

scenarios("features/decide.feature")


@dataclass
class Case:
    spec: Spec = field(default_factory=Spec)
    evidence: list[Evidence] = field(default_factory=list)
    reviews: list[ReviewVerdict] = field(default_factory=list)
    assessment: Assessment | None = None

    def result(self) -> Assessment:
        assert self.assessment is not None, "the harness has not assessed the change yet"
        return self.assessment


@pytest.fixture
def case() -> Case:
    return Case()


@given(parsers.parse("a requirement {rid} verified by the test {vid}"))
def a_requirement_verified_by_a_test(case: Case, rid: str, vid: str) -> None:
    case.spec.requirements.append(Requirement(id=rid, statement=rid, verification_ids=[vid]))
    case.spec.verifications.append(
        Verification(id=vid, kind=VerificationKind.test, description=vid, command="true")
    )


@given(parsers.parse("the verification {vid} is a review marked insufficient"))
def the_verification_is_an_insufficient_review(case: Case, vid: str) -> None:
    for i, v in enumerate(case.spec.verifications):
        if v.id == vid:
            case.spec.verifications[i] = Verification(
                id=vid,
                kind=VerificationKind.review,
                description=vid,
                sufficiency=Sufficiency.insufficient,
            )


@given(parsers.parse("{vid} {result} on the change"))
def a_verification_ran_on_the_change(case: Case, vid: str, result: str) -> None:
    case.evidence.append(
        Evidence(
            id=f"ev-{vid}-{result}",
            kind=EvidenceKind.command_result,
            iteration=1,
            verification_id=vid,
            passed=result == "passed",
            summary=result,
        )
    )


@given("a reviewer accepted the change")
def a_reviewer_accepted(case: Case) -> None:
    case.reviews.append(
        ReviewVerdict(intervention_id="int-p", perspective="p", verdict=Verdict.accept)
    )


@given(
    parsers.re(
        r"a reviewer rejected the change with a major finding on (?P<rid>\w+) "
        r'citing "(?P<observation>.*)"'
    )
)
def a_reviewer_rejected_with_a_major_finding(case: Case, rid: str, observation: str) -> None:
    finding = Finding(
        severity=Severity.major, title="bad", requirement_id=rid, evidence=observation
    )
    case.reviews.append(
        ReviewVerdict(
            intervention_id="int-p", perspective="p", verdict=Verdict.reject, findings=[finding]
        )
    )


@given(
    parsers.re(
        r"a reviewer rejected the change assessing (?P<rid>\w+) as violated "
        r"(?:without any finding|with a major finding citing \"(?P<observation>.*)\")"
    )
)
def a_reviewer_rejected_assessing_violated(case: Case, rid: str, observation: str | None) -> None:
    findings = (
        []
        if observation is None
        else [
            Finding(severity=Severity.major, title="bad", requirement_id=rid, evidence=observation)
        ]
    )
    case.reviews.append(
        ReviewVerdict(
            intervention_id=f"int-q{len(case.reviews)}",
            perspective=f"q{len(case.reviews)}",
            verdict=Verdict.reject,
            findings=findings,
            requirement_assessment={rid: RequirementStatus.violated},
        )
    )


@when("the harness assesses the change")
def the_harness_assesses_the_change(case: Case) -> None:
    case.assessment = assess(case.spec, case.evidence, case.reviews)


@then(parsers.parse("the requirement {rid} is {status}"))
def the_requirement_has_the_status(case: Case, rid: str, status: str) -> None:
    assert case.result().requirement_status[rid] is RequirementStatus(status)


@then(parsers.parse("the outcome is {outcome}"))
def the_outcome_is(case: Case, outcome: str) -> None:
    assert case.result().outcome is Verdict(outcome)


@then(parsers.parse("a correction request names {rid}"))
def a_correction_request_names(case: Case, rid: str) -> None:
    assert any(f"[{rid}]" in c for c in case.result().correction_requests)


@then(parsers.parse("no correction request names {rid}"))
def no_correction_request_names(case: Case, rid: str) -> None:
    assert not any(f"[{rid}]" in c for c in case.result().correction_requests)
