import unittest

from csap import (
    CheckOutcome,
    ErrorCode,
    Operation,
    PortName,
    ProtocolAccepted,
    ProtocolRejected,
    build_check_result,
    build_description,
    build_request,
    negotiate,
)
from tests.csap.support import check_result, description, request_document


class EnvelopeValidationTest(unittest.TestCase):
    def test_each_operation_has_a_valid_envelope(self):
        for operation in Operation:
            with self.subTest(operation=operation):
                built = build_request(request_document(operation))
                self.assertIsInstance(built, ProtocolAccepted)
                self.assertEqual(built.value.operation, operation)

    def test_unknown_fields_operations_urls_and_symbolic_references_are_refused(self):
        cases = []
        unknown_field = request_document(Operation.DESCRIBE) | {"unexpected": True}
        cases.append((unknown_field, ErrorCode.INVALID_INPUT))
        unknown_operation = request_document(Operation.DESCRIBE) | {"operation": "shell"}
        cases.append((unknown_operation, ErrorCode.UNSUPPORTED_CAPABILITY))
        url = request_document(Operation.DESCRIBE, payload={"blob": "https://example.test/object"})
        cases.append((url, ErrorCode.INVALID_INPUT))
        symbolic = request_document(Operation.RUN_CHECK)
        symbolic["contract_ref"] = symbolic["contract_ref"] | {"revision": "latest"}
        cases.append((symbolic, ErrorCode.INVALID_INPUT))
        for document, code in cases:
            refusal = build_request(document)
            self.assertIsInstance(refusal, ProtocolRejected)
            self.assertEqual(refusal.error.code, code)

    def test_extensions_are_qualified_and_required_extensions_must_be_understood(self):
        optional = request_document(
            Operation.DESCRIBE,
            extensions={"org.example.trace": {"required": False, "value": {"id": 1}}},
        )
        self.assertIsInstance(build_request(optional), ProtocolAccepted)
        required = request_document(
            Operation.DESCRIBE,
            extensions={"org.example.trace": {"required": True, "value": True}},
        )
        self.assertEqual(build_request(required).error.code, ErrorCode.UNSUPPORTED_CAPABILITY)
        self.assertIsInstance(
            build_request(required, understood_extensions=frozenset(("org.example.trace",))),
            ProtocolAccepted,
        )
        unqualified = request_document(
            Operation.DESCRIBE,
            extensions={"trace": {"required": False, "value": True}},
        )
        self.assertEqual(build_request(unqualified).error.code, ErrorCode.INVALID_INPUT)

    def test_description_enforces_port_operation_separation(self):
        invalid = build_description(
            {
                "identity": "agent-only",
                "adapter_version": "1",
                "protocol_versions": ["1.0"],
                "ports": [PortName.AGENT.value],
                "operations": [Operation.INTEGRATE.value],
            }
        )
        self.assertEqual(invalid.error.code, ErrorCode.AUTHORIZATION_DENIED)

    def test_negotiation_selects_highest_common_version(self):
        adapter = description()
        selected = negotiate(("1.0", "1.1", "1.2"), adapter)
        self.assertEqual(selected.value, "1.2")
        unsupported = negotiate(("2.0",), adapter)
        self.assertEqual(unsupported.error.code, ErrorCode.UNSUPPORTED_VERSION)

    def test_check_fail_is_usable_but_incomplete_pass_is_invalid(self):
        self.assertIsInstance(build_check_result(check_result("FAIL")), ProtocolAccepted)
        self.assertIsInstance(build_check_result(check_result("PASS")), ProtocolAccepted)
        incomplete = check_result("PASS") | {"evidence_refs": []}
        refusal = build_check_result(incomplete)
        self.assertEqual(refusal.error.code, ErrorCode.OUTPUT_INVALID)
        invalid = check_result("PASS") | {"outcome": "GREEN"}
        self.assertEqual(build_check_result(invalid).error.code, ErrorCode.OUTPUT_INVALID)

    def test_all_check_outcomes_are_recognized(self):
        self.assertEqual(
            {item.value for item in CheckOutcome},
            {"PASS", "FAIL", "ERROR", "NOT_RUN"},
        )
