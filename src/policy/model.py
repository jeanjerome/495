"""Construction sanctionnée de l'arbre immutable d'une politique."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from domain.outcomes import Accepted, Outcome, RefusalCode, Refused
from domain.references import ArtifactRef, build_ref
from domain.vocabulary import Gate


class PolicyOperator(StrEnum):
    ALL_OF = "all_of"
    ANY_OF = "any_of"
    CHECK_PASSED = "check_passed"
    APPROVAL_PRESENT = "approval_present"
    ARTIFACT_PRESENT = "artifact_present"
    DIGEST_MATCHES = "digest_matches"
    CAPABILITY_SATISFIED = "capability_satisfied"
    WITHIN_BUDGET = "within_budget"


@dataclass(frozen=True, slots=True)
class PolicyNode:
    operator: PolicyOperator
    obligation: str
    children: tuple["PolicyNode", ...] = ()
    key: str | None = None
    target: ArtifactRef | None = None
    expected_digest: str | None = None


@dataclass(frozen=True, slots=True)
class Policy:
    schema_version: str
    gate: Gate
    root: PolicyNode
    digest: str


_ROOT_FIELDS = frozenset(("schema_version", "gate", "root"))
_COMMON_NODE_FIELDS = frozenset(("operator", "obligation"))
_REFERENCE_FIELDS = frozenset(
    ("artifact_id", "revision", "kind", "schema_version", "digest")
)
_OPERATOR_FIELDS = {
    PolicyOperator.ALL_OF: frozenset(("children",)),
    PolicyOperator.ANY_OF: frozenset(("children",)),
    PolicyOperator.CHECK_PASSED: frozenset(("key",)),
    PolicyOperator.APPROVAL_PRESENT: frozenset(("target",)),
    PolicyOperator.ARTIFACT_PRESENT: frozenset(("target",)),
    PolicyOperator.DIGEST_MATCHES: frozenset(("key", "expected_digest")),
    PolicyOperator.CAPABILITY_SATISFIED: frozenset(("key",)),
    PolicyOperator.WITHIN_BUDGET: frozenset(("key",)),
}


def _refused(subject: str, *details: str) -> Refused[None]:
    return Refused(RefusalCode.PRECONDITION_UNSATISFIED, subject, None, tuple(details))


def _required(mapping: Mapping[str, Any], field: str, path: str) -> Refused[None] | None:
    if field not in mapping:
        return Refused(RefusalCode.MISSING_FIELD, f"{path}.{field}", None)
    return None


def _build_target(value: object, path: str) -> Outcome[ArtifactRef, None]:
    if not isinstance(value, Mapping) or set(value) != _REFERENCE_FIELDS:
        return _refused(path, "complete_artifact_reference")
    result = build_ref(**dict(value))
    if isinstance(result, Refused):
        return Refused(result.code, f"{path}.{result.subject}", None, result.details)
    return result


def _build_node(value: object, path: str) -> Outcome[PolicyNode, None]:
    if not isinstance(value, Mapping):
        return _refused(path, "object")
    for field in _COMMON_NODE_FIELDS:
        missing = _required(value, field, path)
        if missing is not None:
            return missing
    try:
        operator = PolicyOperator(value["operator"])
    except (TypeError, ValueError):
        return Refused(RefusalCode.UNKNOWN_KIND, f"{path}.operator", None)
    obligation = value["obligation"]
    if not isinstance(obligation, str) or not obligation:
        return _refused(f"{path}.obligation", "non_empty_string")
    expected_fields = _COMMON_NODE_FIELDS | _OPERATOR_FIELDS[operator]
    unknown = set(value) - expected_fields
    if unknown:
        return _refused(f"{path}.fields", *sorted(unknown))
    missing_fields = _OPERATOR_FIELDS[operator] - set(value)
    if missing_fields:
        field = sorted(missing_fields)[0]
        return Refused(RefusalCode.MISSING_FIELD, f"{path}.{field}", None)

    if operator in (PolicyOperator.ALL_OF, PolicyOperator.ANY_OF):
        children_value = value["children"]
        if not isinstance(children_value, (list, tuple)) or not children_value:
            return _refused(f"{path}.children", "non_empty_sequence")
        children: list[PolicyNode] = []
        for index, child_value in enumerate(children_value):
            child = _build_node(child_value, f"{path}.children[{index}]")
            if isinstance(child, Refused):
                return child
            children.append(child.value)
        return Accepted(PolicyNode(operator, obligation, tuple(children)))

    if operator in (PolicyOperator.APPROVAL_PRESENT, PolicyOperator.ARTIFACT_PRESENT):
        target = _build_target(value["target"], f"{path}.target")
        if isinstance(target, Refused):
            return target
        return Accepted(PolicyNode(operator, obligation, target=target.value))

    key = value["key"]
    if not isinstance(key, str) or not key:
        return _refused(f"{path}.key", "non_empty_string")
    if operator is PolicyOperator.DIGEST_MATCHES:
        expected_digest = value["expected_digest"]
        if not isinstance(expected_digest, str) or not expected_digest:
            return _refused(f"{path}.expected_digest", "non_empty_string")
        return Accepted(
            PolicyNode(operator, obligation, key=key, expected_digest=expected_digest)
        )
    return Accepted(PolicyNode(operator, obligation, key=key))


def build_policy(document: object) -> Outcome[Policy, None]:
    if not isinstance(document, Mapping):
        return _refused("policy", "object")
    missing = _ROOT_FIELDS - set(document)
    if missing:
        return Refused(RefusalCode.MISSING_FIELD, sorted(missing)[0], None)
    unknown = set(document) - _ROOT_FIELDS
    if unknown:
        return _refused("policy.fields", *sorted(unknown))
    if document["schema_version"] != "policy-1":
        return _refused("schema_version", "policy-1")
    try:
        gate = Gate(document["gate"])
    except (TypeError, ValueError):
        return Refused(RefusalCode.UNKNOWN_KIND, "gate", None)
    root = _build_node(document["root"], "root")
    if isinstance(root, Refused):
        return root
    try:
        canonical = json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        return _refused("policy", "json_value")
    digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return Accepted(Policy("policy-1", gate, root.value, digest))
