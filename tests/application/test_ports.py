import unittest

from application import ApplicationAccepted, build_port_registry
from csap import (
    ErrorCode,
    InProcessAdapter,
    Operation,
    PortName,
    ProtocolAccepted,
    build_request,
)
from csap.vocabulary import PORT_OPERATIONS
from tests.csap.support import description, request_document


class RecordingAdapter:
    def __init__(self):
        self.requests = []

    def dispatch(self, request):
        self.requests.append(request)
        return ProtocolAccepted(request.operation)


class PortRegistryTest(unittest.TestCase):
    def test_every_operation_routes_only_through_an_authorized_port(self):
        adapters = {port: RecordingAdapter() for port in PortName}
        registry = build_port_registry(tuple(adapters.items())).value
        for index, operation in enumerate(Operation):
            port = next(port for port in PortName if operation in PORT_OPERATIONS[port])
            request = build_request(
                request_document(
                    operation,
                    request_id=f"request-{index}",
                    key=f"key-{index}",
                )
            ).value
            result = registry.dispatch(port, request)
            self.assertEqual(result.value, operation)
            self.assertIs(adapters[port].requests[-1], request)

    def test_missing_port_cross_port_operation_and_duplicate_are_refused(self):
        adapter = RecordingAdapter()
        registry = build_port_registry(((PortName.EXECUTION, adapter),)).value
        approval = build_request(request_document(Operation.REQUEST_APPROVAL)).value
        denied = registry.dispatch(PortName.EXECUTION, approval)
        self.assertEqual(denied.error.code, ErrorCode.AUTHORIZATION_DENIED)
        self.assertEqual(adapter.requests, [])

        describe = build_request(request_document(Operation.DESCRIBE)).value
        missing = registry.dispatch(PortName.AGENT, describe)
        self.assertEqual(missing.error.code, ErrorCode.ENVIRONMENT_UNAVAILABLE)
        duplicate = build_port_registry(
            ((PortName.AGENT, adapter), (PortName.AGENT, adapter))
        )
        self.assertNotIsInstance(duplicate, ApplicationAccepted)

    def test_adapter_protocol_refusal_is_propagated_unchanged(self):
        adapter = InProcessAdapter(description())
        registry = build_port_registry(((PortName.EXECUTION, adapter),)).value
        request = build_request(
            request_document(Operation.RUN_CHECK, version="9.0")
        ).value
        result = registry.dispatch(PortName.EXECUTION, request)
        self.assertEqual(result.error.code, ErrorCode.UNSUPPORTED_VERSION)
