#!/usr/bin/env python3
"""Invoque Codex sur un dépôt cible puis contrôle le candidat observé."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


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


class ChangeError(RuntimeError):
    """Le parcours ne peut pas produire un résultat vérifié."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True) + "\n").encode()


def sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ChangeError("precondition", f"{label} absent : {path}") from error
    except (OSError, UnicodeError) as error:
        raise ChangeError("precondition", f"{label} illisible : {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ChangeError(
            "configuration", f"{label} contient un JSON invalide : {error}"
        ) from error


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
        if not isinstance(name, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
            raise ChangeError("configuration", "environment contient un nom invalide")
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
        if not all(isinstance(item, str) and item and "\x00" not in item for item in command):
            raise ChangeError("configuration", f"{field}.command contient un argument invalide")
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


def run_git(repository: Path, arguments: list[str], *, binary: bool = False) -> bytes | str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        text=not binary,
    )
    if completed.returncode != 0:
        stderr = completed.stderr
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        raise ChangeError("git", stderr.strip() or "commande Git en échec")
    return completed.stdout


def validate_repository(repository: Path) -> tuple[Path, str]:
    repository = repository.resolve()
    if not repository.is_dir():
        raise ChangeError("precondition", f"dépôt absent : {repository}")
    root = str(run_git(repository, ["rev-parse", "--show-toplevel"])).strip()
    if Path(root).resolve() != repository:
        raise ChangeError("precondition", f"le chemin doit être la racine Git : {root}")
    head = str(run_git(repository, ["rev-parse", "--verify", "HEAD"])).strip()
    status_output = run_git(
        repository,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        binary=True,
    )
    assert isinstance(status_output, bytes)
    if status_output:
        raise ChangeError("precondition", "le dépôt cible doit être propre")
    return repository, head


def _path_digest(path: Path) -> str | None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(mode):
        return sha256_bytes(os.fsencode(os.readlink(path)))
    if stat.S_ISREG(mode):
        return sha256_bytes(path.read_bytes())
    return None


def _nul_fields(value: bytes) -> list[bytes]:
    fields = value.split(b"\x00")
    if fields and fields[-1] == b"":
        fields.pop()
    return fields


def observe_candidate(repository: Path, baseline: str) -> dict[str, Any] | None:
    name_status = run_git(
        repository,
        ["diff", "--name-status", "-z", "--no-renames", baseline, "--"],
        binary=True,
    )
    untracked = run_git(
        repository,
        ["ls-files", "--others", "--exclude-standard", "-z"],
        binary=True,
    )
    patch = run_git(
        repository,
        ["diff", "--binary", "--full-index", "--no-ext-diff", "--no-renames", baseline, "--"],
        binary=True,
    )
    assert isinstance(name_status, bytes)
    assert isinstance(untracked, bytes)
    assert isinstance(patch, bytes)

    changed_fields = _nul_fields(name_status)
    if len(changed_fields) % 2:
        raise ChangeError("git", "sortie Git name-status inattendue")

    entries: list[dict[str, Any]] = []
    identity = hashlib.sha256()
    identity.update(baseline.encode())
    identity.update(b"\x00tracked\x00")
    identity.update(patch)

    for index in range(0, len(changed_fields), 2):
        status_value = os.fsdecode(changed_fields[index])
        relative = os.fsdecode(changed_fields[index + 1])
        digest = None if status_value == "D" else _path_digest(repository / relative)
        entries.append({"digest": digest, "path": relative, "status": status_value})

    identity.update(b"\x00untracked\x00")
    for raw_path in sorted(_nul_fields(untracked)):
        relative = os.fsdecode(raw_path)
        path = repository / relative
        digest = _path_digest(path)
        identity.update(raw_path)
        identity.update(b"\x00")
        identity.update((digest or "special").encode())
        identity.update(b"\x00")
        entries.append({"digest": digest, "path": relative, "status": "?"})

    if not entries:
        return None
    entries.sort(key=lambda entry: (entry["path"], entry["status"]))
    return {
        "baseline": baseline,
        "digest": "sha256:" + identity.hexdigest(),
        "files": entries,
    }


def terminate_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def execute_process(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: int,
    stdin: str | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except OSError as error:
        raise ChangeError("process", f"impossible de lancer {command[0]} : {error}") from error

    timed_out = False
    try:
        stdout, stderr = process.communicate(input=stdin, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        terminate_process_group(process)
        stdout, stderr = process.communicate()

    return {
        "command": command,
        "duration_seconds": round(time.monotonic() - started, 6),
        "exit_code": None if timed_out else process.returncode,
        "stderr": stderr,
        "stdout": stdout,
        "timed_out": timed_out,
    }


def inherited_environment(
    names: list[str], *, codex_home: Path, temporary_home: Path
) -> tuple[dict[str, str], dict[str, list[str]]]:
    present = sorted(name for name in names if name in os.environ)
    missing = sorted(name for name in names if name not in os.environ)
    environment = {name: os.environ[name] for name in present}
    environment.update(
        {
            "CODEX_HOME": str(codex_home),
            "HOME": str(temporary_home),
            "TMPDIR": str(temporary_home),
        }
    )
    return environment, {"inherited": present, "missing": missing}


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
            raise ChangeError("agent_events", f"événement incomplet à la ligne {line_number}")
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
        raise ChangeError("agent_events", "le client n’a produit aucun événement JSONL")
    if not turn_completed:
        raise ChangeError("agent_events", "le flux JSONL ne contient pas de fin de tour")
    return {"command_count": command_count, "event_count": count, "usage": usage}


def agent_prompt(request: str) -> str:
    return (
        "Réalise la demande ci-dessous dans le dépôt courant. Respecte les instructions "
        "et skills applicables du dépôt. Ne crée aucun commit et ne publie rien. "
        "Ta réponse finale doit respecter le JSON Schema fourni ; elle décrit ton "
        "intervention mais ne décide pas si le candidat est vérifié.\n\n"
        "Demande :\n"
        f"{request.rstrip()}\n"
    )


def validate_agent_response(path: Path) -> dict[str, Any]:
    value = load_json(path, "réponse de l’agent")
    try:
        Draft202012Validator(AGENT_RESPONSE_SCHEMA).validate(value)
    except (SchemaError, ValidationError) as error:
        raise ChangeError(
            "agent_response", f"réponse de l’agent non conforme : {error.message}"
        ) from error
    assert isinstance(value, dict)
    return value


def invoke_agent(
    *,
    codex: Path,
    repository: Path,
    request: str,
    environment: dict[str, str],
    artifacts: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    schema_path = artifacts / "agent-response-schema.json"
    response_path = artifacts / "agent-response.json"
    schema_path.write_bytes(canonical_bytes(AGENT_RESPONSE_SCHEMA))
    shell_names = sorted(
        name for name in environment if name not in {"CODEX_HOME"}
    )
    command = [
        str(codex),
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
            "workspace-write",
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
        stdin=agent_prompt(request),
    )
    event_summary: dict[str, Any] | None = None
    event_error: ChangeError | None = None
    try:
        event_summary = parse_events(process["stdout"])
    except ChangeError as error:
        event_error = error

    response: dict[str, Any] | None = None
    response_error: ChangeError | None = None
    if not process["timed_out"] and process["exit_code"] == 0:
        try:
            response = validate_agent_response(response_path)
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
            "la politique de lecture et les sources de contexte dépendent de la version de Codex",
            "les sorties des processus ne possèdent pas encore de limite de taille "
            "distincte du timeout",
        ],
        "response": response,
        "response_error": str(response_error) if response_error else None,
        "sandbox": {"filesystem": "workspace-write", "network_for_commands": "disabled"},
        "stderr": process["stderr"],
        "timed_out": process["timed_out"],
    }


def run_check(
    *,
    codex: Path,
    repository: Path,
    check: dict[str, Any],
    environment: dict[str, str],
) -> dict[str, Any]:
    profile = FILESYSTEM_PROFILES[check["filesystem"]]
    sandbox_environment = environment.copy()
    sandbox_home = Path(environment["HOME"]) / "codex-sandbox"
    sandbox_home.mkdir(exist_ok=True)
    sandbox_environment["CODEX_HOME"] = str(sandbox_home)
    command = [
        str(codex),
        "sandbox",
        "-P",
        profile,
        "--sandbox-state-disable-network",
        "-C",
        str(repository),
        "--",
        *check["command"],
    ]
    process = execute_process(
        command,
        cwd=repository,
        environment=sandbox_environment,
        timeout_seconds=check["timeout_seconds"],
    )
    return {
        "command": check["command"],
        "duration_seconds": process["duration_seconds"],
        "exit_code": process["exit_code"],
        "name": check["name"],
        "sandbox": {"filesystem": check["filesystem"], "network": "disabled"},
        "status": "PASS"
        if process["exit_code"] == 0 and not process["timed_out"]
        else "FAIL",
        "stderr": process["stderr"],
        "stdout": process["stdout"],
        "timed_out": process["timed_out"],
    }


def codex_version(codex: Path, environment: dict[str, str], cwd: Path) -> str:
    result = execute_process(
        [str(codex), "--version"],
        cwd=cwd,
        environment=environment,
        timeout_seconds=10,
    )
    if result["exit_code"] != 0 or result["timed_out"]:
        raise ChangeError("client", result["stderr"].strip() or "version de Codex indisponible")
    return result["stdout"].strip()


def validate_codex_login(codex: Path, environment: dict[str, str], cwd: Path) -> None:
    result = execute_process(
        [str(codex), "login", "status"],
        cwd=cwd,
        environment=environment,
        timeout_seconds=10,
    )
    if result["exit_code"] != 0 or result["timed_out"]:
        diagnostic = result["stderr"].strip() or result["stdout"].strip()
        raise ChangeError(
            "precondition",
            diagnostic or "le CODEX_HOME dédié n’est pas authentifié",
        )


def validate_control_sandboxes(
    codex: Path,
    repository: Path,
    contract: dict[str, Any],
    environment: dict[str, str],
) -> None:
    for filesystem in sorted({check["filesystem"] for check in contract["checks"]}):
        probe = {
            "command": [sys.executable, "-c", "pass"],
            "filesystem": filesystem,
            "name": f"sandbox-{filesystem}",
            "timeout_seconds": 10,
        }
        result = run_check(
            codex=codex,
            repository=repository,
            check=probe,
            environment=environment,
        )
        if result["status"] != "PASS":
            diagnostic = result["stderr"].strip() or result["stdout"].strip()
            raise ChangeError(
                "precondition",
                f"sandbox {filesystem} indisponible : {diagnostic or 'échec sans diagnostic'}",
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
        raise ChangeError("precondition", "CODEX_HOME et le dépôt cible doivent être disjoints")
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
                "CODEX_HOME contient des skills utilisateur : " + ", ".join(user_skills),
            )
    return codex_home


def run_change(
    *,
    repository: Path,
    contract_path: Path,
    request: str,
    codex_home: Path,
    agent_timeout_seconds: int,
) -> tuple[dict[str, Any], int]:
    repository, baseline = validate_repository(repository)
    contract = validate_contract(load_json(contract_path.resolve(), "contrat"))
    contract_digest = sha256_bytes(canonical_bytes(contract))
    codex_home = validate_codex_home(codex_home, repository)
    codex = find_codex()
    request_digest = sha256_bytes(request.encode())

    temporary_root = Path(tempfile.gettempdir()).resolve()
    if temporary_root.is_relative_to(repository):
        raise ChangeError(
            "precondition",
            "le répertoire temporaire doit être extérieur au dépôt cible",
        )

    with tempfile.TemporaryDirectory(prefix="495-run-") as directory:
        artifacts = Path(directory)
        temporary_home = artifacts / "home"
        temporary_home.mkdir()
        environment, environment_report = inherited_environment(
            contract["environment"],
            codex_home=codex_home,
            temporary_home=temporary_home,
        )
        version = codex_version(codex, environment, repository)
        validate_codex_login(codex, environment, repository)
        validate_control_sandboxes(codex, repository, contract, environment)
        agent = invoke_agent(
            codex=codex,
            repository=repository,
            request=request,
            environment=environment,
            artifacts=artifacts,
            timeout_seconds=agent_timeout_seconds,
        )

        candidate = observe_candidate(repository, baseline)
        result: dict[str, Any] = {
            "agent": agent,
            "baseline": baseline,
            "candidate": candidate,
            "checks": [],
            "client_version": version,
            "contract_digest": contract_digest,
            "environment": environment_report,
            "outcome": "agent_failed",
            "request_digest": request_digest,
            "version": 1,
            "violations": [],
        }

        response = agent["response"]
        agent_succeeded = (
            not agent["timed_out"]
            and agent["exit_code"] == 0
            and agent["events_error"] is None
            and agent["response_error"] is None
            and isinstance(response, dict)
            and response["status"] == "completed"
        )
        if not agent_succeeded or candidate is None:
            if agent["timed_out"]:
                result["violations"].append("timeout du client")
            elif agent["exit_code"] != 0:
                result["violations"].append("code de sortie défavorable du client")
            elif agent["events_error"] is not None:
                result["violations"].append("flux d’événements du client invalide")
            elif agent["response_error"] is not None:
                result["violations"].append("réponse de l’agent invalide")
            elif isinstance(response, dict) and response.get("status") == "blocked":
                result["violations"].append("agent bloqué")
            if candidate is None:
                result["violations"].append("aucun candidat observé")
            return result, 3

        expected_candidate_digest = candidate["digest"]
        all_passed = True
        for check in contract["checks"]:
            check_result = run_check(
                codex=codex,
                repository=repository,
                check=check,
                environment=environment,
            )
            result["checks"].append(check_result)
            if check_result["status"] != "PASS":
                all_passed = False
            current_candidate = observe_candidate(repository, baseline)
            current_digest = current_candidate["digest"] if current_candidate else None
            if current_digest != expected_candidate_digest:
                result["violations"].append(
                    f"le contrôle {check['name']} a modifié l’état Git visible"
                )
                all_passed = False
                result["candidate_after_checks"] = current_candidate
                break

        result["outcome"] = "candidate_verified" if all_passed else "candidate_failed"
        return result, 0 if all_passed else 1


def error_result(error: ChangeError) -> dict[str, Any]:
    return {
        "error": {"kind": error.kind, "message": str(error)},
        "outcome": "execution_impossible",
        "version": 1,
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Invoque Codex sur un dépôt local et contrôle le candidat produit."
    )
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--request-file", required=True, type=Path)
    parser.add_argument("--codex-home", required=True, type=Path)
    parser.add_argument("--agent-timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        if arguments.agent_timeout_seconds <= 0:
            raise ChangeError("configuration", "le timeout de l’agent doit être positif")
        try:
            request = arguments.request_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise ChangeError(
                "precondition",
                f"demande illisible : {arguments.request_file}: {error}",
            ) from error
        if not request.strip():
            raise ChangeError("precondition", "la demande doit être non vide")
        result, exit_code = run_change(
            repository=arguments.repository,
            contract_path=arguments.contract,
            request=request,
            codex_home=arguments.codex_home,
            agent_timeout_seconds=arguments.agent_timeout_seconds,
        )
    except ChangeError as error:
        result = error_result(error)
        exit_code = 2
    sys.stdout.buffer.write(canonical_bytes(result))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
