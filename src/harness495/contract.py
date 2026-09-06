"""Contrats d’entrée et de sortie du premier parcours applicatif."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from harness495.errors import ChangeError, ConfigurationError
from harness495.serialization import canonical_bytes, sha256_bytes


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
        raise ConfigurationError("le contrat doit être un objet JSON")
    expected = {"checks", "environment", "version"}
    if set(value) != expected:
        raise ConfigurationError(
            f"le contrat doit contenir exactement {sorted(expected)}",
        )
    if value["version"] != 1:
        raise ConfigurationError("version de contrat non prise en charge")

    environment = value["environment"]
    if not isinstance(environment, list):
        raise ConfigurationError("environment doit être une liste")
    if len(environment) != len(set(environment)):
        raise ConfigurationError("environment contient un nom dupliqué")
    for name in environment:
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None
        ):
            raise ConfigurationError(
                "environment contient un nom invalide"
            )
        if name in {"CODEX_HOME", "HOME", "TMPDIR"}:
            raise ConfigurationError(
                f"{name} est défini par 495 et ne peut pas être hérité",
            )
        if any(marker in name.upper() for marker in ("KEY", "SECRET", "TOKEN")):
            raise ConfigurationError(
                f"{name} ressemble à un secret et ne peut pas être transmis dans cet incrément",
            )

    checks = value["checks"]
    if not isinstance(checks, list) or not checks:
        raise ConfigurationError("checks doit être une liste non vide")
    names: set[str] = set()
    for index, check in enumerate(checks):
        field = f"checks[{index}]"
        if not isinstance(check, dict):
            raise ConfigurationError(f"{field} doit être un objet")
        check_fields = {"command", "filesystem", "name", "timeout_seconds"}
        if set(check) != check_fields:
            raise ConfigurationError(
                f"{field} doit contenir exactement {sorted(check_fields)}",
            )
        name = check["name"]
        if not isinstance(name, str) or not name:
            raise ConfigurationError(f"{field}.name doit être non vide")
        if name in names:
            raise ConfigurationError(f"nom de contrôle dupliqué : {name}")
        names.add(name)
        command = check["command"]
        if not isinstance(command, list) or not command:
            raise ConfigurationError(f"{field}.command doit être non vide")
        if not all(
            isinstance(item, str) and item and "\x00" not in item for item in command
        ):
            raise ConfigurationError(
                f"{field}.command contient un argument invalide"
            )
        filesystem = check["filesystem"]
        if filesystem not in FILESYSTEM_PROFILES:
            raise ConfigurationError(
                f"{field}.filesystem doit valoir read-only ou workspace-write",
            )
        timeout = check["timeout_seconds"]
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
            raise ConfigurationError(
                f"{field}.timeout_seconds doit être un entier positif",
            )
    return value


def load_contract(path: Path) -> tuple[dict[str, Any], str]:
    """Lit et valide le contrat de l’application cible, puis calcule son digest."""

    path = path.resolve()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ChangeError("precondition", f"contrat absent : {path}") from error
    except (OSError, UnicodeError) as error:
        raise ChangeError(
            "precondition", f"contrat illisible : {path}: {error}"
        ) from error
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigurationError(
            f"contrat contient un JSON invalide : {error}"
        ) from error
    contract = validate_contract(value)
    return contract, sha256_bytes(canonical_bytes(contract))
