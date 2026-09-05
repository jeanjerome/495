import unittest

from csap import CheckOutcome, ErrorCode, Operation, OperationStatus, PortName
from tests.enumeration.sealed_reference import coverage


class CsapEnumerationTest(unittest.TestCase):
    def test_operations(self):
        expected = {
            "describe", "prepare", "start_agent", "capture_candidate", "run_check",
            "get_operation", "cancel_operation", "release", "integrate", "request_approval",
        }
        coverage("csap_operations", {item.value for item in Operation}, expected, 10)

    def test_ports(self):
        coverage("csap_ports", {item.value for item in PortName}, {"agent", "execution", "repository", "approval"}, 4)

    def test_operation_statuses(self):
        expected = {"queued", "running", "succeeded", "failed", "cancelled", "unknown"}
        coverage("csap_operation_statuses", {item.value for item in OperationStatus}, expected, 6)

    def test_check_outcomes(self):
        coverage("csap_check_outcomes", {item.value for item in CheckOutcome}, {"PASS", "FAIL", "ERROR", "NOT_RUN"}, 4)

    def test_error_codes(self):
        expected = {
            "UNSUPPORTED_VERSION", "UNSUPPORTED_CAPABILITY", "UNSUPPORTED_PARAMETER",
            "INVALID_INPUT", "AUTHORIZATION_DENIED", "ENVIRONMENT_UNAVAILABLE", "TIMEOUT",
            "RESOURCE_LIMIT", "OUTPUT_INVALID", "INTEGRITY_MISMATCH", "CONFLICT",
            "OPERATION_UNKNOWN",
        }
        coverage("csap_error_codes", {item.value for item in ErrorCode}, expected, 12)
