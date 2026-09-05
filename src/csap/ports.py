"""Interfaces structurelles des quatre ports CSAP."""

from typing import Protocol

from .model import ProtocolOutcome, Request


class AgentPort(Protocol):
    def dispatch(self, request: Request) -> ProtocolOutcome[object]: ...


class ExecutionPort(Protocol):
    def dispatch(self, request: Request) -> ProtocolOutcome[object]: ...


class RepositoryPort(Protocol):
    def dispatch(self, request: Request) -> ProtocolOutcome[object]: ...


class ApprovalPort(Protocol):
    def dispatch(self, request: Request) -> ProtocolOutcome[object]: ...
