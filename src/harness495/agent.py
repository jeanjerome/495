"""Interface entre le parcours applicatif et un client d’agent de code."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class AgentClient(Protocol):
    """Capacités d’un client d’agent nécessaires au premier parcours."""

    def version(self, *, repository: Path, environment: dict[str, str]) -> str: ...

    def validate_ready(
        self, *, repository: Path, environment: dict[str, str]
    ) -> None: ...

    def invoke(
        self,
        *,
        repository: Path,
        request: str,
        environment: dict[str, str],
        artifacts: Path,
        timeout_seconds: int,
    ) -> dict[str, Any]: ...
