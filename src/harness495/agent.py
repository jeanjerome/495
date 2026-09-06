"""Interface entre le parcours applicatif et un client d’agent de code."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class AgentClient(Protocol):
    """Capacités d’un client d’agent nécessaires aux opérations disponibles.

    Chaque opération compose son propre prompt, son schéma de réponse et le
    profil de fichiers accordé à l’agent ; le client se borne à les appliquer.
    """

    def version(self, *, repository: Path, environment: dict[str, str]) -> str: ...

    def validate_ready(
        self, *, repository: Path, environment: dict[str, str]
    ) -> None: ...

    def invoke(
        self,
        *,
        repository: Path,
        prompt: str,
        response_schema: dict[str, Any],
        filesystem: str,
        environment: dict[str, str],
        artifacts: Path,
        timeout_seconds: int,
    ) -> dict[str, Any]: ...


def agent_completed(agent: dict[str, Any]) -> bool:
    """Vrai lorsque le client a terminé et remis une réponse `completed` conforme."""

    response = agent["response"]
    return (
        not agent["timed_out"]
        and agent["exit_code"] == 0
        and agent["events_error"] is None
        and agent["response_error"] is None
        and isinstance(response, dict)
        and response["status"] == "completed"
    )


def agent_failure_violations(agent: dict[str, Any]) -> list[str]:
    """Décrit la première cause pour laquelle l’intervention n’est pas exploitable."""

    response = agent["response"]
    if agent["timed_out"]:
        return ["timeout du client"]
    if agent["exit_code"] != 0:
        return ["code de sortie défavorable du client"]
    if agent["events_error"] is not None:
        return ["flux d’événements du client invalide"]
    if agent["response_error"] is not None:
        return ["réponse de l’agent invalide"]
    if isinstance(response, dict) and response.get("status") == "blocked":
        return ["agent bloqué"]
    return []
