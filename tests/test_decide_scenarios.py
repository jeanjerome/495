"""Scenarios of ``tests/features/decide.feature``: the decision as a function of the evidence.

The steps build a specification, evidence and reviews from the scenario text, call
``core.reading.decide.assess`` once, and read the assessment; nothing is asserted outside a
``Then``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core.models import (
    Evidence,
    EvidenceKind,
    Finding,
    Requirement,
    RequirementKind,
    RequirementStatus,
    ReviewVerdict,
    Severity,
    Spec,
    Sufficiency,
    Verdict,
    Verification,
    VerificationKind,
)
from harness495.core.reading.decide import Assessment, assess

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

    def require(self, rid: str, vid: str, kind: RequirementKind) -> None:
        self.spec.requirements.append(
            Requirement(id=rid, statement=rid, kind=kind, verification_ids=[vid])
        )
        if self.spec.verification(vid) is None:
            self.spec.verifications.append(
                Verification(id=vid, kind=VerificationKind.test, description=vid, command="true")
            )

    def correction_for(self, rid: str) -> str:
        return next(c for c in self.result().correction_requests if c.startswith(f"[{rid}]"))


@pytest.fixture
def case() -> Case:
    return Case()


@given(parsers.parse("a requirement {rid} verified by the test {vid}"))
def a_requirement_verified_by_a_test(case: Case, rid: str, vid: str) -> None:
    case.require(rid, vid, RequirementKind.behaviour)


@given(parsers.parse("a non-regression requirement {rid} verified by the test {vid}"))
def a_non_regression_requirement(case: Case, rid: str, vid: str) -> None:
    case.require(rid, vid, RequirementKind.non_regression)


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


@given(parsers.parse('the verification {vid} is {sufficiency} because "{why}"'))
def the_verification_has_the_sufficiency(case: Case, vid: str, sufficiency: str, why: str) -> None:
    v = case.spec.verification(vid)
    assert v is not None, f"no verification {vid} in the specification"
    v.sufficiency = Sufficiency(sufficiency)
    v.rationale = why


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


@given(parsers.parse("a control run of {vid} on the base version exited {code:d}"))
def a_control_run_on_the_base_version(case: Case, vid: str, code: int) -> None:
    case.evidence.append(
        Evidence(
            id=f"ev-control-{vid}",
            kind=EvidenceKind.instrument_check,
            iteration=1,
            verification_id=vid,
            passed=None,
            summary=f"control run on the base version: exit {code}",
        )
    )


@given(parsers.parse('the scope check failed saying "{summary}"'))
def the_scope_check_failed(case: Case, summary: str) -> None:
    case.evidence.append(
        Evidence(
            id="ev-scope",
            kind=EvidenceKind.scope_check,
            iteration=1,
            passed=False,
            summary=summary,
        )
    )


@given("a reviewer accepted the change")
def a_reviewer_accepted(case: Case) -> None:
    case.reviews.append(
        ReviewVerdict(intervention_id="int-p", perspective="p", verdict=Verdict.accept)
    )


def _rejection(case: Case, findings: list[Finding], discarded: bool = False) -> None:
    review = ReviewVerdict(
        intervention_id=f"int-r{len(case.reviews)}",
        perspective=f"r{len(case.reviews)}",
        verdict=Verdict.reject,
        findings=findings,
    )
    review.discarded = discarded
    case.reviews.append(review)


@given(
    parsers.re(
        r"a reviewer rejected the change with a major finding on (?P<rid>\w+) "
        r'citing "(?P<observation>.*)"'
    )
)
def a_reviewer_rejected_with_a_major_finding(case: Case, rid: str, observation: str) -> None:
    _rejection(
        case,
        [Finding(severity=Severity.major, title="bad", requirement_id=rid, evidence=observation)],
    )


@given(
    parsers.parse(
        'a reviewer rejected the change with a major finding on {rid} titled "{title}" '
        'citing "{observation}"'
    )
)
def a_reviewer_rejected_with_a_titled_finding(
    case: Case, rid: str, title: str, observation: str
) -> None:
    _rejection(
        case,
        [Finding(severity=Severity.major, title=title, requirement_id=rid, evidence=observation)],
    )


@given(
    parsers.parse(
        'a reviewer rejected the change with a major finding on {rid} whose remedy is "{remedy}", '
        'title "{title}" and observation "{observation}"'
    )
)
def a_reviewer_rejected_explaining_the_remedy(
    case: Case, rid: str, remedy: str, title: str, observation: str
) -> None:
    _rejection(
        case,
        [
            Finding(
                severity=Severity.major,
                title=title,
                detail=remedy,
                requirement_id=rid,
                evidence=observation,
            )
        ],
    )


@given(
    parsers.parse('a reviewer rejected the change with a blocker titled "{title}" citing "{ev}"')
)
def a_reviewer_rejected_with_a_blocker(case: Case, title: str, ev: str) -> None:
    _rejection(case, [Finding(severity=Severity.blocker, title=title, evidence=ev)])


@given(
    parsers.parse(
        'a discarded reviewer rejected the change with a blocker titled "{title}" citing "{ev}"'
    )
)
def a_discarded_reviewer_rejected(case: Case, title: str, ev: str) -> None:
    _rejection(case, [Finding(severity=Severity.blocker, title=title, evidence=ev)], discarded=True)


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


@then(parsers.parse('a correction request says "{text}"'))
def a_correction_request_says(case: Case, text: str) -> None:
    assert any(text in c for c in case.result().correction_requests)


@then(parsers.parse('no correction request says "{text}"'))
def no_correction_request_says(case: Case, text: str) -> None:
    assert not any(text in c for c in case.result().correction_requests)


@then(parsers.parse('exactly one correction request says "{text}"'))
def exactly_one_correction_request_says(case: Case, text: str) -> None:
    assert len([c for c in case.result().correction_requests if text in c]) == 1


@then("there is no correction request")
def there_is_no_correction_request(case: Case) -> None:
    assert case.result().correction_requests == []


@then(parsers.parse('the correction request for {rid} says "{text}"'))
def the_correction_request_for_says(case: Case, rid: str, text: str) -> None:
    assert text in case.correction_for(rid)


@then(parsers.parse('the correction request for {rid} does not say "{text}"'))
def the_correction_request_for_does_not_say(case: Case, rid: str, text: str) -> None:
    assert text not in case.correction_for(rid)


@then(parsers.parse('the reason for {rid} says "{text}"'))
def the_reason_for_says(case: Case, rid: str, text: str) -> None:
    assert text in case.result().reasons[rid]


@then(parsers.parse('the reason for {rid} does not say "{text}"'))
def the_reason_for_does_not_say(case: Case, rid: str, text: str) -> None:
    assert text not in case.result().reasons[rid]


@then(parsers.parse("an instrument fault names {vid}"))
def an_instrument_fault_names(case: Case, vid: str) -> None:
    assert any(f.startswith(f"{vid}:") for f in case.result().instrument_faults)


@then(parsers.parse("{rid} is uncredited, naming {vid}"))
def the_requirement_is_uncredited(case: Case, rid: str, vid: str) -> None:
    assert any(u.startswith(f"{rid}: {vid}") for u in case.result().uncredited)


@then("nothing is uncredited")
def nothing_is_uncredited(case: Case) -> None:
    assert case.result().uncredited == []
