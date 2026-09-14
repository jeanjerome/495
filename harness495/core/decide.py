"""Decision policy: conclude only from evidence, refuse to conclude without enough of it.

Correction requests state what is *not demonstrated* and what was *observed*. They never state
what to do about it: a request shaped as a remedy makes the next producer optimise the remedy,
and a request naming a command makes it optimise the command. The requirement is the target;
the verification is only how the harness looks at it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from harness495.core.models import (
    ADMISSIBLE,
    NON_DISCRIMINATING,
    Evidence,
    EvidenceKind,
    RequirementKind,
    RequirementStatus,
    ReviewVerdict,
    Severity,
    Spec,
    Sufficiency,
    Verdict,
)


@dataclass
class Assessment:
    outcome: Verdict
    requirement_status: dict[str, RequirementStatus]
    reasons: dict[str, str]
    correction_requests: list[str] = field(default_factory=list)
    undetermined_reasons: list[str] = field(default_factory=list)
    instrument_faults: list[str] = field(default_factory=list)
    """Verifications that cannot observe the change. The specification is at fault, not the change."""
    uncredited: list[str] = field(default_factory=list)
    """Requirements a passing command was not allowed to credit, and why."""
    summary: str = ""


def _set_aside_for(requirement_id: str, set_aside: list[str]) -> list[str]:
    notes = [x.split(": ", 1)[1] for x in set_aside if x.startswith(f"{requirement_id}: ")]
    return ["set aside: " + "; ".join(notes)] if notes else []


def assess(spec: Spec, evidence: list[Evidence], reviews: list[ReviewVerdict]) -> Assessment:
    # Only what the command reported on the evaluated version says anything about the change.
    # A control run carries the same verification id but was measured on the base version, and
    # a baseline run predates the change entirely; neither is evidence for or against it.
    by_verification: dict[str, list[Evidence]] = {}
    for e in evidence:
        if e.verification_id and e.kind is EvidenceKind.command_result:
            by_verification.setdefault(e.verification_id, []).append(e)
    active_reviews = [r for r in reviews if not r.discarded]
    statuses: dict[str, RequirementStatus] = {}
    reasons: dict[str, str] = {}
    corrections: list[str] = []
    undetermined: list[str] = []
    uncredited: list[str] = []

    # One failing verification usually carries several requirements; the observation is the same
    # for all of them, so it is stated once, against the set of requirements it concerns.
    failures_by_observation: dict[str, list[str]] = {}
    faulty_instruments: dict[str, str] = {}

    # A reviewer reads a failing verification as a defect of the change, because from where it
    # stands that is what a failure means. The harness has since run that command on a version
    # without the change and seen it report the same thing, so a finding resting on it is
    # reporting the instrument, and acting on it would send the producer after the wrong thing.
    blind = {v.id for v in spec.verifications if v.sufficiency in NON_DISCRIMINATING}
    tainted = set(blind) | {e.id for e in evidence if e.verification_id in blind}
    tainted_pattern = (
        re.compile(r"\b(" + "|".join(re.escape(t) for t in sorted(tainted)) + r")\b")
        if tainted
        else None
    )

    def rests_on_a_blind_instrument(finding: object) -> bool:
        if tainted_pattern is None:
            return False
        text = getattr(finding, "evidence", "")
        return bool(tainted_pattern.search(text))

    set_aside: list[str] = []

    # The existing suite is the instrument of a non-regression requirement, and the harness
    # has read what the change did to it. A command that passes on a suite smaller than the
    # base's (a test deleted, skipped, deselected) shows that what is left still passes, not
    # that what was there still holds: it credits nothing, and the requirement waits for the
    # requester to rule on what the reviewers say about the missing tests.
    weakened_suite: dict[str, list[str]] = {}
    for e in evidence:
        if e.kind is EvidenceKind.suite_check and e.passed is False:
            for rid in e.requirement_ids:
                weakened_suite.setdefault(rid, []).append(e.summary)

    # The harness has run every command that passed against wrong versions of the change,
    # each one line of the diff altered in a stated way. A version all of them reported
    # success on is one the evidence does not tell from the change itself, and what those
    # commands report on the change is then not enough to call the requirement demonstrated.
    # It is not a defect either — the alteration may leave the behaviour as it was — so the
    # requirement waits for the requester rather than going back to the producer.
    let_through: dict[str, list[str]] = {}
    for e in evidence:
        if e.kind is EvidenceKind.mutation_check and e.passed is False:
            for rid in e.requirement_ids:
                let_through.setdefault(rid, []).append(e.summary)

    # The same commands have also been run under the project's coverage tool, and the lines the
    # change adds crossed with what it reported. A line no command executed is a line the
    # evidence has nothing to say about: whatever those commands report, they report it without
    # ever running that line. As above, it is not a defect — the line may carry behaviour no
    # requirement states — so the requirement waits for the requester rather than the producer.
    unexecuted: dict[str, list[str]] = {}
    for e in evidence:
        if e.kind is EvidenceKind.coverage_check and e.passed is False:
            for rid in e.requirement_ids:
                unexecuted.setdefault(rid, []).append(e.summary)

    for r in spec.requirements:
        failed: list[str] = []
        passed: list[str] = []
        not_run: list[str] = []
        faulty: list[str] = []
        insufficient_only = True
        for vid in r.verification_ids:
            v = spec.verification(vid)
            if v is None:
                not_run.append(f"{vid} (unknown verification)")
                continue
            settled_either_way = (
                v.sufficiency is Sufficiency.vacuous and r.kind is RequirementKind.non_regression
            )
            if v.sufficiency in NON_DISCRIMINATING and not settled_either_way:
                # The command reports the same thing with and without the change: its result says
                # nothing about this requirement, so it is neither proof nor evidence of a defect.
                # The exception is a requirement that something went on holding: a command that
                # reports success on both versions is exactly what that means.
                if v.sufficiency is Sufficiency.vacuous:
                    uncredited.append(f"{r.id}: {vid} {v.rationale}")
                faulty.append(f"{vid}: {v.rationale or 'does not observe the change'}")
                faulty_instruments.setdefault(vid, v.rationale or "does not observe the change")
                continue
            if v.sufficiency in ADMISSIBLE or settled_either_way:
                insufficient_only = False
            evs = by_verification.get(vid, [])
            if not evs:
                not_run.append(vid)
                continue
            last = evs[-1]
            if last.passed is True:
                # An unconfirmed verification credits the requirement as a sufficient one does:
                # it passed on the change and reported something else without it. What the
                # reason keeps is that the something else was an execution error, so that the
                # reader knows the test was never seen asserting the behaviour.
                passed.append(
                    vid
                    + (
                        f" (unconfirmed: {v.rationale})"
                        if v.sufficiency is Sufficiency.unconfirmed
                        else ""
                    )
                )
            elif last.passed is False:
                failed.append(f"{vid}: {last.summary}")
                failures_by_observation.setdefault(f"{vid} {last.summary}", []).append(r.id)
            else:
                not_run.append(f"{vid}: {last.summary}")
        admissible = [
            (rv.perspective, f)
            for rv in active_reviews
            for f in rv.findings
            if f.requirement_id == r.id
            and f.severity in (Severity.blocker, Severity.major)
            and f.evidence.strip()
        ]
        violations = [(p, f) for p, f in admissible if not rests_on_a_blind_instrument(f)]
        for persp, f in admissible:
            if rests_on_a_blind_instrument(f):
                set_aside.append(
                    f"{r.id}: {persp} reviewer's '{f.title}' rests on {', '.join(sorted(blind))}"
                )
        # A reviewer's per-requirement assessment is a claim; only its findings carry an
        # observation. An assessment of `violated` therefore weighs exactly what the findings
        # behind it weigh: with an admissible finding on the requirement, the finding is what
        # violates it; with none, the reviewer has said "violated" without showing anything,
        # and that is read as "undetermined".
        observed_by = {persp for persp, _ in violations}
        unsupported = [
            rv.perspective
            for rv in active_reviews
            if rv.requirement_assessment.get(r.id) is RequirementStatus.violated
            and rv.perspective not in observed_by
        ]
        for persp in unsupported:
            set_aside.append(
                f"{r.id}: {persp} reviewer assessed {r.id} as violated without a cited observation"
            )
        review_undetermined = [
            rv.perspective
            for rv in active_reviews
            if rv.requirement_assessment.get(r.id) is RequirementStatus.undetermined
            or rv.perspective in unsupported
        ]
        if failed or violations:
            statuses[r.id] = RequirementStatus.violated
            why = []
            if failed:
                why.append("failed verifications: " + "; ".join(failed))
            for persp, f in violations:
                why.append(f"{persp} reviewer: {f.title} ({f.evidence[:200]})")
                # The finding's title is the claim and its evidence is the observation; the
                # reviewer's own explanation is left out so the producer diagnoses the cause
                # itself instead of applying someone else's conclusion.
                observed = f.evidence.strip().replace("\n", " ")[:400]
                corrections.append(f"[{r.id}] {f.title} — observed: {observed}")
            why.extend(_set_aside_for(r.id, set_aside))
            reasons[r.id] = "; ".join(why)
        elif not r.verification_ids or not_run or insufficient_only or not passed:
            statuses[r.id] = RequirementStatus.undetermined
            why = []
            if not r.verification_ids:
                why.append("no verification attached")
            if not_run:
                why.append("verifications not executed: " + ", ".join(not_run))
            if faulty:
                why.append("no verification that observes the change: " + "; ".join(faulty))
            why.extend(_set_aside_for(r.id, set_aside))
            if insufficient_only and r.verification_ids and not faulty:
                why.append("only insufficient verifications available")
            if review_undetermined:
                why.append("reviewers undetermined: " + ", ".join(review_undetermined))
            reasons[r.id] = "; ".join(why) or "no passing evidence"
            undetermined.append(f"{r.id}: {reasons[r.id]}")
        elif r.id in weakened_suite:
            statuses[r.id] = RequirementStatus.undetermined
            observed = "; ".join(dict.fromkeys(weakened_suite[r.id]))
            reasons[r.id] = "; ".join(
                [
                    "verifications passed: "
                    + ", ".join(passed)
                    + ", on a suite weaker than the base's: "
                    + observed,
                    *_set_aside_for(r.id, set_aside),
                ]
            )
            uncredited.append(f"{r.id}: {', '.join(passed)} ran a suite weaker than the base's")
            undetermined.append(f"{r.id}: {reasons[r.id]}")
        elif r.id in let_through:
            statuses[r.id] = RequirementStatus.undetermined
            observed = "; ".join(dict.fromkeys(let_through[r.id]))
            reasons[r.id] = "; ".join(
                [
                    "verifications passed: "
                    + ", ".join(passed)
                    + ", and so did every command watching the change, on a wrong version of "
                    "it: " + observed,
                    *_set_aside_for(r.id, set_aside),
                ]
            )
            uncredited.append(f"{r.id}: no command told the change from a wrong version of it")
            undetermined.append(f"{r.id}: {reasons[r.id]}")
        elif r.id in unexecuted:
            statuses[r.id] = RequirementStatus.undetermined
            observed = "; ".join(dict.fromkeys(unexecuted[r.id]))
            reasons[r.id] = "; ".join(
                [
                    "verifications passed: "
                    + ", ".join(passed)
                    + ", and did not run every line the change adds: "
                    + observed,
                    *_set_aside_for(r.id, set_aside),
                ]
            )
            uncredited.append(f"{r.id}: no verification executed every line the change adds")
            undetermined.append(f"{r.id}: {reasons[r.id]}")
        elif (
            review_undetermined
            and len(review_undetermined) == len(active_reviews)
            and active_reviews
        ):
            statuses[r.id] = RequirementStatus.undetermined
            reasons[r.id] = "; ".join(
                [
                    "all reviewers undetermined despite passing verifications",
                    *_set_aside_for(r.id, set_aside),
                ]
            )
            undetermined.append(f"{r.id}: {reasons[r.id]}")
        else:
            statuses[r.id] = RequirementStatus.satisfied
            reasons[r.id] = "; ".join(
                ["verifications passed: " + ", ".join(passed), *_set_aside_for(r.id, set_aside)]
            )

    # Stated once per distinct observation, ahead of the reviewers' claims: these are the
    # harness's own measurements, and the requirements they carry are named together rather
    # than repeated as one near-identical line each.
    grouped: list[str] = []
    for observation, req_ids in failures_by_observation.items():
        vid, _, summary = observation.partition(" ")
        ids = ",".join(dict.fromkeys(req_ids))
        grouped.append(f"[{ids}] behaviour not demonstrated: {vid} {summary}")
    corrections = grouped + corrections

    instrument_faults = [f"{vid}: {why}" for vid, why in faulty_instruments.items()]

    # A scope violation is a defect of the change; a broken review integrity is not.
    unattached_weakening = False
    for e in evidence:
        if e.kind is EvidenceKind.scope_check and e.passed is False:
            corrections.append(f"[scope] {e.summary}")
        elif e.kind is EvidenceKind.integrity and e.passed is False:
            undetermined.append(f"review integrity: {e.summary}")
        elif e.kind is EvidenceKind.suite_check and e.passed is False and not e.requirement_ids:
            # No requirement names the suite, so no status can carry the observation; the
            # outcome carries it instead, since a change that shrank the suite is not accepted
            # on the word of the commands that ran what was left.
            undetermined.append(f"suite check: {e.summary}")
            unattached_weakening = True

    # Blocking findings not tied to a requirement still block acceptance.
    unattached_blockers = [
        (rv.perspective, f)
        for rv in active_reviews
        for f in rv.findings
        if f.severity is Severity.blocker and f.evidence.strip() and not f.requirement_id
    ]
    for persp, f in unattached_blockers:
        observed = f.evidence.strip().replace("\n", " ")[:400]
        corrections.append(f"[{persp}] {f.title} — observed: {observed}")

    if any(s is RequirementStatus.violated for s in statuses.values()) or corrections:
        outcome = Verdict.reject
    elif (
        any(s is RequirementStatus.undetermined for s in statuses.values())
        or not spec.requirements
        or unattached_weakening
    ):
        outcome = Verdict.undetermined
        if not spec.requirements:
            undetermined.append("the specification has no requirement")
    else:
        outcome = Verdict.accept

    if not active_reviews and outcome is Verdict.accept:
        outcome = Verdict.undetermined
        undetermined.append("no independent review verdict available")

    counts = {s.value: sum(1 for x in statuses.values() if x is s) for s in RequirementStatus}
    summary = (
        f"{outcome.value}: {counts['satisfied']} satisfied, {counts['violated']} violated, "
        f"{counts['undetermined']} undetermined requirement(s); {len(corrections)} correction request(s)"
    )
    return Assessment(
        outcome=outcome,
        requirement_status=statuses,
        reasons=reasons,
        correction_requests=list(dict.fromkeys(corrections)),
        undetermined_reasons=undetermined,
        instrument_faults=instrument_faults,
        uncredited=uncredited,
        summary=summary,
    )
