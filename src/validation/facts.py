"""Faits explicites et qualification déterministe des observations."""

from dataclasses import dataclass
from enum import StrEnum

from domain.outcomes import Accepted, Outcome, RefusalCode, Refused
from domain.references import ArtifactRef


class FactState(StrEnum):
    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class Fact:
    fact_id: str
    state: FactState
    evidence: tuple[ArtifactRef, ...] = ()
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class BudgetFact:
    budget_id: str
    consumed: int
    limit: int


@dataclass(frozen=True, slots=True)
class Observation:
    observation_id: str
    fact_id: str
    result: bool | None
    evidence: tuple[ArtifactRef, ...] = ()
    target: ArtifactRef | None = None
    expected_target: ArtifactRef | None = None
    observed_digest: str | None = None
    expected_digest: str | None = None
    fresh: bool = True
    well_formed: bool = True


@dataclass(frozen=True, slots=True)
class FactBundle:
    checks: tuple[Fact, ...] = ()
    artifacts: tuple[ArtifactRef, ...] = ()
    digests: tuple[tuple[str, str], ...] = ()
    capabilities: tuple[str, ...] = ()
    budgets: tuple[BudgetFact, ...] = ()


def _unresolved(observation: Observation, detail: str) -> Fact:
    return Fact(observation.fact_id, FactState.UNRESOLVED, observation.evidence, detail)


def qualify_observation(observation: Observation) -> Fact:
    if not observation.well_formed:
        return _unresolved(observation, "malformed_observation")
    if not observation.fresh:
        return _unresolved(observation, "stale_observation")
    if any(not isinstance(item, ArtifactRef) for item in observation.evidence):
        return _unresolved(observation, "invalid_evidence_reference")
    if (
        observation.expected_target is not None
        and observation.target != observation.expected_target
    ):
        return _unresolved(observation, "inapplicable_target")
    if observation.expected_digest is not None:
        if observation.observed_digest is None:
            return _unresolved(observation, "missing_digest")
        if observation.observed_digest != observation.expected_digest:
            return Fact(
                observation.fact_id,
                FactState.VIOLATED,
                observation.evidence,
                "digest_mismatch",
            )
    if observation.result is None:
        return _unresolved(observation, "missing_result")
    return Fact(
        observation.fact_id,
        FactState.SATISFIED if observation.result else FactState.VIOLATED,
        observation.evidence,
        None if observation.result else "check_failed",
    )


def build_fact_bundle(
    *,
    checks: tuple[Fact, ...] = (),
    artifacts: tuple[ArtifactRef, ...] = (),
    digests: tuple[tuple[str, str], ...] = (),
    capabilities: tuple[str, ...] = (),
    budgets: tuple[BudgetFact, ...] = (),
) -> Outcome[FactBundle, None]:
    keyed_values = (
        ("checks", tuple(item.fact_id for item in checks)),
        ("digests", tuple(item[0] for item in digests)),
        ("budgets", tuple(item.budget_id for item in budgets)),
    )
    for subject, keys in keyed_values:
        if len(keys) != len(set(keys)):
            return Refused(RefusalCode.PRECONDITION_UNSATISFIED, f"unique_{subject}", None)
    if any(not isinstance(item, ArtifactRef) for item in artifacts):
        return Refused(RefusalCode.PRECONDITION_UNSATISFIED, "artifact_reference", None)
    bundle = FactBundle(
        checks=tuple(sorted(checks, key=lambda item: item.fact_id)),
        artifacts=tuple(
            sorted(
                artifacts,
                key=lambda item: (
                    item.artifact_id,
                    item.revision,
                    item.kind.value,
                    item.schema_version,
                    item.digest,
                ),
            )
        ),
        digests=tuple(sorted(digests)),
        capabilities=tuple(sorted(set(capabilities))),
        budgets=tuple(sorted(budgets, key=lambda item: item.budget_id)),
    )
    return Accepted(bundle)
