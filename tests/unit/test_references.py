import unittest

from domain.outcomes import Accepted, RefusalCode, Refused
from domain.references import (
    ApprovalRegistry,
    approval_applies,
    approvals_for,
    build_approval,
    build_ref,
    record,
)
from domain.vocabulary import ApprovalDecision, ArtifactKind


class ReferencesTest(unittest.TestCase):
    def fields(self):
        return {
            "artifact_id": "A",
            "revision": 1,
            "kind": ArtifactKind.DESIGN,
            "schema_version": "1",
            "digest": "sha256:abc",
        }

    def test_reference_validation(self):
        accepted = build_ref(**self.fields())
        self.assertIsInstance(accepted, Accepted)
        for field in self.fields():
            values = self.fields()
            del values[field]
            refused = build_ref(**values)
            self.assertEqual((refused.code, refused.subject), (RefusalCode.MISSING_FIELD, field))
        self.assertEqual(build_ref(**(self.fields() | {"kind": "unknown"})).code, RefusalCode.UNKNOWN_KIND)
        for revision in ("latest", "1", True, None):
            refused = build_ref(**(self.fields() | {"revision": revision}))
            self.assertEqual((refused.code, refused.subject), (RefusalCode.SYMBOLIC_REVISION, "revision"))

    def test_approval_requires_and_revalidates_complete_target(self):
        invalid = build_approval(
            approval_id="P", actor="a", role="owner", target="file.json",
            scope="all", decision=ApprovalDecision.APPROVED,
        )
        self.assertEqual(invalid.code, RefusalCode.INVALID_APPROVAL_TARGET)
        target = build_ref(**self.fields()).value
        accepted = build_approval(
            approval_id="P", actor="a", role="owner", target=target,
            scope="all", decision=ApprovalDecision.APPROVED,
        )
        self.assertIsInstance(accepted, Accepted)

    def test_approval_applies_to_exact_five_fields_and_registry_is_append_only(self):
        target = build_ref(**self.fields()).value
        approval = build_approval(
            approval_id="P", actor="a", role="owner", target=target,
            scope="all", decision="approved",
        ).value
        self.assertTrue(approval_applies(approval, target))
        for field, replacement in (
            ("artifact_id", "B"), ("revision", 2), ("kind", ArtifactKind.CANDIDATE),
            ("schema_version", "2"), ("digest", "sha256:def"),
        ):
            values = self.fields() | {field: replacement}
            self.assertFalse(approval_applies(approval, build_ref(**values).value))
        registry = ApprovalRegistry()
        updated = record(registry, approval).value
        self.assertEqual(registry.entries, ())
        self.assertEqual(approvals_for(updated, target), (approval,))
