"""Registre borné des ports CSAP injectés dans l’application."""

from dataclasses import dataclass

from csap.model import ProtocolError, ProtocolOutcome, ProtocolRejected, Request
from csap.vocabulary import ErrorCode, PORT_OPERATIONS, PortName

from .model import (
    ApplicationAccepted,
    ApplicationErrorCode,
    ApplicationOutcome,
    ApplicationRefusal,
)


@dataclass(frozen=True, slots=True)
class PortRegistry:
    entries: tuple[tuple[PortName, object], ...] = ()

    def dispatch(self, port: PortName, request: Request) -> ProtocolOutcome[object]:
        if not isinstance(request, Request):
            return ProtocolRejected(ProtocolError(ErrorCode.INVALID_INPUT, "request"))
        try:
            resolved_port = PortName(port)
        except (TypeError, ValueError):
            return ProtocolRejected(
                ProtocolError(ErrorCode.UNSUPPORTED_CAPABILITY, "port")
            )
        adapter = dict(self.entries).get(resolved_port)
        if adapter is None or not callable(getattr(adapter, "dispatch", None)):
            return ProtocolRejected(
                ProtocolError(ErrorCode.ENVIRONMENT_UNAVAILABLE, resolved_port.value)
            )
        if request.operation not in PORT_OPERATIONS[resolved_port]:
            return ProtocolRejected(
                ProtocolError(ErrorCode.AUTHORIZATION_DENIED, request.operation.value)
            )
        return adapter.dispatch(request)


def build_port_registry(
    bindings: tuple[tuple[PortName | str, object], ...],
) -> ApplicationOutcome[PortRegistry]:
    entries: list[tuple[PortName, object]] = []
    seen: set[PortName] = set()
    for raw_port, adapter in bindings:
        try:
            port = PortName(raw_port)
        except (TypeError, ValueError):
            return ApplicationRefusal(ApplicationErrorCode.INVALID_INPUT, "port")
        if port in seen:
            return ApplicationRefusal(
                ApplicationErrorCode.INVALID_INPUT, "duplicate_port", details=(port.value,)
            )
        if not callable(getattr(adapter, "dispatch", None)):
            return ApplicationRefusal(
                ApplicationErrorCode.INVALID_INPUT, "adapter", details=(port.value,)
            )
        seen.add(port)
        entries.append((port, adapter))
    return ApplicationAccepted(
        PortRegistry(tuple(sorted(entries, key=lambda item: item[0].value)))
    )
