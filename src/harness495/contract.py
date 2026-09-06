"""Contrats d’entrée et de sortie du premier parcours applicatif."""

from __future__ import annotations

import re
from typing import Any

from harness495.errors import ChangeError


AGENT_RESPONSE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["completed", "blocked"]},
        "summary": {"type": "string"},
        "questions": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "summary", "questions", "limitations"],
    "additionalProperties": False,
}

FILESYSTEM_PROFILES = {
    "read-only": ":read-only",
    "workspace-write": ":workspace",
}


def validate_contract(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ChangeError("configuration", "le contrat doit être un objet JSON")
    expected = {"checks", "environment", "version"}
    if set(value) != expected:
        raise ChangeError(
            "configuration",
            f"le contrat doit contenir exactement {sorted(expected)}",
        )
    if value["version"] != 1:
        raise ChangeError("configuration", "version de contrat non prise en charge")

    environment = value["environment"]
    if not isinstance(environment, list):
        raise ChangeError("configuration", "environment doit être une liste")
    if len(environment) != len(set(environment)):
        raise ChangeError("configuration", "environment contient un nom dupliqué")
    for name in environment:
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None
        ):
            raise ChangeError(
                "configuration", "environment contient un nom invalide"
            )
        if name in {"CODEX_HOME", "HOME", "TMPDIR"}:
            raise ChangeError(
                "configuration",
                f"{name} est défini par 495 et ne peut pas être hérité",
            )
        if any(marker in name.upper() for marker in ("KEY", "SECRET", "TOKEN")):
            raise ChangeError(
                "configuration",
                f"{name} ressemble à un secret et ne peut pas être transmis dans cet incrément",
            )

    checks = value["checks"]
    if not isinstance(checks, list) or not checks:
        raise ChangeError("configuration", "checks doit être une liste non vide")
    names: set[str] = set()
    for index, check in enumerate(checks):
        field = f"checks[{index}]"
        if not isinstance(check, dict):
            raise ChangeError("configuration", f"{field} doit être un objet")
        check_fields = {"command", "filesystem", "name", "timeout_seconds"}
        if set(check) != check_fields:
            raise ChangeError(
                "configuration",
                f"{field} doit contenir exactement {sorted(check_fields)}",
            )
        name = check["name"]
        if not isinstance(name, str) or not name:
            raise ChangeError("configuration", f"{field}.name doit être non vide")
        if name in names:
            raise ChangeError("configuration", f"nom de contrôle dupliqué : {name}")
        names.add(name)
        command = check["command"]
        if not isinstance(command, list) or not command:
            raise ChangeError("configuration", f"{field}.command doit être non vide")
        if not all(
            isinstance(item, str) and item and "\x00" not in item for item in command
        ):
            raise ChangeError(
                "configuration", f"{field}.command contient un argument invalide"
            )
        filesystem = check["filesystem"]
        if filesystem not in FILESYSTEM_PROFILES:
            raise ChangeError(
                "configuration",
                f"{field}.filesystem doit valoir read-only ou workspace-write",
            )
        timeout = check["timeout_seconds"]
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
            raise ChangeError(
                "configuration",
                f"{field}.timeout_seconds doit être un entier positif",
            )
    return value
