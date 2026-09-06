"""Adaptation du client Codex CLI au parcours applicatif de 495."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from harness495.contract import FILESYSTEM_PROFILES
from harness495.errors import ChangeError
from harness495.process import OUTPUT_LIMIT_BYTES, execute_process
from harness495.serialization import canonical_bytes, load_json


DISABLED_CODEX_FEATURES = (
    "apps",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "computer_use",
    "goals",
    "hooks",
    "image_generation",
    "in_app_browser",
    "multi_agent",
    "plugins",
    "remote_plugin",
    "shell_snapshot",
    "tool_suggest",
    "view_image",
    "workspace_dependencies",
)


def find_codex() -> Path:
    executable = shutil.which("codex")
    if executable is None:
        raise ChangeError("precondition", "codex est absent de PATH")
    return Path(executable).resolve()


def validate_codex_home(codex_home: Path, repository: Path) -> Path:
    codex_home = codex_home.resolve()
    if not codex_home.is_dir():
        raise ChangeError("precondition", f"CODEX_HOME dédié absent : {codex_home}")
    if codex_home.is_relative_to(repository) or repository.is_relative_to(codex_home):
        raise ChangeError(
            "precondition", "CODEX_HOME et le dépôt cible doivent être disjoints"
        )
    skills = codex_home / "skills"
    if skills.is_dir():
        try:
            user_skills = sorted(
                path.name for path in skills.iterdir() if path.name != ".system"
            )
        except OSError as error:
            raise ChangeError(
                "precondition", f"skills de CODEX_HOME illisibles : {error}"
            ) from error
        if user_skills:
            raise ChangeError(
                "precondition",
                "CODEX_HOME contient des skills utilisateur : "
                + ", ".join(user_skills),
            )
    return codex_home


def parse_events(stdout: str) -> dict[str, Any]:
    usage: dict[str, Any] | None = None
    count = 0
    command_count = 0
    turn_completed = False
    for line_number, line in enumerate(stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ChangeError(
                "agent_events",
                f"événement JSONL invalide à la ligne {line_number} : {error}",
            ) from error
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise ChangeError(
                "agent_events", f"événement incomplet à la ligne {line_number}"
            )
        count += 1
        if event["type"] == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "command_execution":
                command_count += 1
        if event["type"] == "turn.completed":
            turn_completed = True
            if isinstance(event.get("usage"), dict):
                usage = event["usage"]
    if count == 0:
        raise ChangeError(
            "agent_events", "le client n’a produit aucun événement JSONL"
        )
    if not turn_completed:
        raise ChangeError(
            "agent_events", "le flux JSONL ne contient pas de fin de tour"
        )
    return {"command_count": command_count, "event_count": count, "usage": usage}


def validate_agent_response(path: Path, schema: dict[str, Any]) -> dict[str, Any]:
    value = load_json(path, "réponse de l’agent")
    try:
        Draft202012Validator(schema).validate(value)
    except (SchemaError, ValidationError) as error:
        raise ChangeError(
            "agent_response", f"réponse de l’agent non conforme : {error.message}"
        ) from error
    assert isinstance(value, dict)
    return value


@dataclass(frozen=True)
class CodexAgentClient:
    """Client d’agent reposant sur une installation locale de Codex CLI."""

    executable: Path

    def version(self, *, repository: Path, environment: dict[str, str]) -> str:
        result = execute_process(
            [str(self.executable), "--version"],
            cwd=repository,
            environment=environment,
            timeout_seconds=10,
        )
        if result["exit_code"] != 0 or result["timed_out"]:
            raise ChangeError(
                "client",
                result["stderr"].strip() or "version de Codex indisponible",
            )
        return result["stdout"].strip()

    def validate_ready(
        self, *, repository: Path, environment: dict[str, str]
    ) -> None:
        result = execute_process(
            [str(self.executable), "login", "status"],
            cwd=repository,
            environment=environment,
            timeout_seconds=10,
        )
        if result["exit_code"] != 0 or result["timed_out"]:
            diagnostic = result["stderr"].strip() or result["stdout"].strip()
            raise ChangeError(
                "precondition",
                diagnostic or "le CODEX_HOME dédié n’est pas authentifié",
            )

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
    ) -> dict[str, Any]:
        if filesystem not in FILESYSTEM_PROFILES:
            raise ChangeError("configuration", f"profil de fichiers inconnu : {filesystem}")
        schema_path = artifacts / "agent-response-schema.json"
        response_path = artifacts / "agent-response.json"
        schema_path.write_bytes(canonical_bytes(response_schema))
        shell_names = sorted(name for name in environment if name != "CODEX_HOME")
        command = [
            str(self.executable),
            "exec",
            "--json",
            "--ephemeral",
            "--ignore-user-config",
            "--strict-config",
        ]
        for feature in DISABLED_CODEX_FEATURES:
            command.extend(["--disable", feature])
        command.extend(
            [
                "--config",
                "skills.bundled.enabled=false",
                "--config",
                'approval_policy="never"',
                "--config",
                "shell_environment_policy.inherit=all",
                "--config",
                f"shell_environment_policy.include_only={json.dumps(shell_names)}",
                "--config",
                "shell_environment_policy.ignore_default_excludes=false",
                "--config",
                "sandbox_workspace_write.network_access=false",
                "--config",
                "sandbox_workspace_write.exclude_slash_tmp=true",
                "--config",
                "sandbox_workspace_write.exclude_tmpdir_env_var=false",
                "--sandbox",
                filesystem,
                "-C",
                str(repository),
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(response_path),
                "-",
            ]
        )
        process = execute_process(
            command,
            cwd=repository,
            environment=environment,
            timeout_seconds=timeout_seconds,
            stdin=prompt,
        )
        event_summary: dict[str, Any] | None = None
        event_error: ChangeError | None = None
        if process["stdout_truncated"]:
            # Un flux tronqué ne permet pas de confirmer la fin du tour.
            event_error = ChangeError(
                "agent_events",
                f"flux JSONL tronqué : {process['stdout_bytes']} octets émis pour "
                f"une borne de {OUTPUT_LIMIT_BYTES}",
            )
        else:
            try:
                event_summary = parse_events(process["stdout"])
            except ChangeError as error:
                event_error = error

        response: dict[str, Any] | None = None
        response_error: ChangeError | None = None
        if not process["timed_out"] and process["exit_code"] == 0:
            try:
                response = validate_agent_response(response_path, response_schema)
            except ChangeError as error:
                response_error = error

        return {
            "client": "codex",
            "command": command,
            "duration_seconds": process["duration_seconds"],
            "events": event_summary,
            "events_error": str(event_error) if event_error else None,
            "exit_code": process["exit_code"],
            "limitations": [
                "la politique de lecture et les sources de contexte dépendent "
                "de la version de Codex",
            ],
            "response": response,
            "response_error": str(response_error) if response_error else None,
            "sandbox": {
                "filesystem": filesystem,
                "network_for_commands": "disabled",
            },
            "stderr": process["stderr"],
            "stderr_bytes": process["stderr_bytes"],
            "stderr_truncated": process["stderr_truncated"],
            "stdout_bytes": process["stdout_bytes"],
            "stdout_truncated": process["stdout_truncated"],
            "timed_out": process["timed_out"],
        }
