import unittest

from csap import (
    CancellationAck,
    ErrorCode,
    InProcessAdapter,
    Operation,
    OperationAccepted,
    OperationSnapshot,
    OperationStatus,
    ProtocolAccepted,
    ProtocolRejected,
    build_request,
)
from tests.csap.support import check_result, description, request_document


class InProcessAdapterTest(unittest.TestCase):
    def setUp(self):
        self.adapter = InProcessAdapter(description())

    def dispatch(self, operation, *, request_id="request", key="key", payload=None):
        built = build_request(
            request_document(
                operation, request_id=request_id, key=key, payload=payload
            )
        )
        self.assertIsInstance(built, ProtocolAccepted)
        return self.adapter.dispatch(built.value)

    def start_check(self, key="check"):
        started = self.dispatch(Operation.RUN_CHECK, key=key)
        self.assertIsInstance(started, ProtocolAccepted)
        self.assertIsInstance(started.value, OperationAccepted)
        return started.value.operation_id

    def test_long_operation_returns_queued_and_idempotence_ignores_request_id(self):
        first = self.dispatch(Operation.START_AGENT, request_id="one", key="stable", payload={"x": 1})
        second = self.dispatch(Operation.START_AGENT, request_id="two", key="stable", payload={"x": 1})
        self.assertEqual(first.value.operation_id, second.value.operation_id)
        self.assertEqual(first.value.status, OperationStatus.QUEUED)
        self.assertFalse(first.value.replayed)
        self.assertTrue(second.value.replayed)
        conflict = self.dispatch(Operation.START_AGENT, request_id="three", key="stable", payload={"x": 2})
        self.assertEqual(conflict.error.code, ErrorCode.CONFLICT)

    def test_cancel_acknowledges_request_without_changing_status(self):
        operation_id = self.start_check()
        cancelled = self.dispatch(
            Operation.CANCEL_OPERATION,
            key="cancel",
            payload={"operation_id": operation_id, "reason": "user_request"},
        )
        self.assertIsInstance(cancelled.value, CancellationAck)
        self.assertTrue(cancelled.value.cancel_requested)
        self.assertEqual(cancelled.value.status, OperationStatus.QUEUED)
        snapshot = self.dispatch(
            Operation.GET_OPERATION,
            key="get",
            payload={"operation_id": operation_id, "cursor": 0},
        )
        self.assertEqual(snapshot.value.status, OperationStatus.QUEUED)

    def test_cursor_returns_only_later_events_and_unknown_cursor_is_refused(self):
        operation_id = self.start_check()
        self.adapter.advance(operation_id, OperationStatus.RUNNING)
        snapshot = self.dispatch(
            Operation.GET_OPERATION,
            key="cursor-one",
            payload={"operation_id": operation_id, "cursor": 1},
        ).value
        self.assertIsInstance(snapshot, OperationSnapshot)
        self.assertEqual(tuple(event.cursor for event in snapshot.events), (2,))
        unknown = self.dispatch(
            Operation.GET_OPERATION,
            key="cursor-unknown",
            payload={"operation_id": operation_id, "cursor": 99},
        )
        self.assertEqual(unknown.error.code, ErrorCode.OPERATION_UNKNOWN)

    def test_check_fail_is_a_succeeded_operation_and_terminal_is_final(self):
        operation_id = self.start_check()
        self.adapter.advance(operation_id, OperationStatus.RUNNING)
        completed = self.adapter.advance(
            operation_id, OperationStatus.SUCCEEDED, result=check_result("FAIL")
        )
        self.assertEqual(completed.value.status, OperationStatus.SUCCEEDED)
        second = self.adapter.advance(operation_id, OperationStatus.FAILED)
        self.assertEqual(second.error.code, ErrorCode.CONFLICT)

    def test_incomplete_pass_fails_with_output_invalid(self):
        operation_id = self.start_check()
        self.adapter.advance(operation_id, OperationStatus.RUNNING)
        incomplete = check_result("PASS") | {"evidence_refs": []}
        completed = self.adapter.advance(
            operation_id, OperationStatus.SUCCEEDED, result=incomplete
        )
        self.assertEqual(completed.value.status, OperationStatus.FAILED)
        self.assertEqual(completed.value.error.code, ErrorCode.OUTPUT_INVALID)

    def test_unsupported_version_operation_and_unknown_id_are_refused(self):
        request = build_request(request_document(Operation.DESCRIBE, version="9.0")).value
        self.assertEqual(self.adapter.dispatch(request).error.code, ErrorCode.UNSUPPORTED_VERSION)
        unknown = self.dispatch(
            Operation.GET_OPERATION,
            payload={"operation_id": "missing", "cursor": 0},
        )
        self.assertEqual(unknown.error.code, ErrorCode.OPERATION_UNKNOWN)

    def test_invalid_operation_transition_is_refused_without_state_change(self):
        operation_id = self.start_check()
        refusal = self.adapter.advance(operation_id, OperationStatus.SUCCEEDED, result=check_result())
        self.assertEqual(refusal.error.code, ErrorCode.CONFLICT)
        snapshot = self.dispatch(
            Operation.GET_OPERATION,
            key="still-queued",
            payload={"operation_id": operation_id, "cursor": 0},
        )
        self.assertEqual(snapshot.value.status, OperationStatus.QUEUED)
