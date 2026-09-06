#!/usr/bin/env python3
"""Exécute les contrôles déclarés et produit éventuellement un rapport."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACT = ROOT / "bootstrap/contract.json"


class ContractError(ValueError):
    """La configuration ne décrit pas une exécution valide."""


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def relative_path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{field} doit être une chaîne non vide")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path == Path("."):
        raise ContractError(f"{field} doit être un chemin relatif borné : {value}")
    return path


def validate_contract(contract: Any) -> None:
    if not isinstance(contract, dict):
        raise ContractError("la racine doit être un objet JSON")

    fields = {"checks", "files", "report_directory", "version"}
    if set(contract) != fields:
        missing = sorted(fields - set(contract))
        unknown = sorted(set(contract) - fields)
        details = []
        if missing:
            details.append(f"champs manquants : {missing}")
        if unknown:
            details.append(f"champs inconnus : {unknown}")
        raise ContractError("; ".join(details))

    if contract["version"] != 1:
        raise ContractError("version de configuration non prise en charge")

    files = contract["files"]
    if not isinstance(files, list) or not files:
        raise ContractError("files doit être une liste non vide")
    if len(files) != len(set(files)):
        raise ContractError("files contient un motif dupliqué")
    for index, pattern in enumerate(files):
        relative_path(pattern, f"files[{index}]")

    checks = contract["checks"]
    if not isinstance(checks, list) or not checks:
        raise ContractError("checks doit être une liste non vide")
    names: set[str] = set()
    for index, check in enumerate(checks):
        field = f"checks[{index}]"
        if not isinstance(check, dict):
            raise ContractError(f"{field} doit être un objet")
        expected = {"command", "name", "timeout_seconds"}
        if set(check) != expected:
            raise ContractError(f"{field} doit contenir exactement {sorted(expected)}")
        name = check["name"]
        if not isinstance(name, str) or not name:
            raise ContractError(f"{field}.name doit être une chaîne non vide")
        if name in names:
            raise ContractError(f"nom de contrôle dupliqué : {name}")
        names.add(name)
        command = check["command"]
        if not isinstance(command, list) or not command:
            raise ContractError(f"{field}.command doit être une liste non vide")
        if not all(isinstance(argument, str) and argument for argument in command):
            raise ContractError(f"{field}.command contient un argument invalide")
        for argument in command:
            if "{" in argument or "}" in argument:
                if argument != "{python}":
                    raise ContractError(f"{field}.command contient un jeton inconnu")
        timeout = check["timeout_seconds"]
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
            raise ContractError(f"{field}.timeout_seconds doit être un entier positif")

    relative_path(contract["report_directory"], "report_directory")


def load_contract(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ContractError(f"configuration absente : {path}") from error
    except json.JSONDecodeError as error:
        raise ContractError(f"JSON invalide : {error}") from error
    validate_contract(contract)
    return contract, canonical_bytes(contract)


def candidate_manifest(contract: dict[str, Any]) -> list[dict[str, Any]]:
    files: dict[str, Path] = {}
    for index, pattern in enumerate(contract["files"]):
        matches = sorted(path for path in ROOT.glob(pattern) if path.is_file())
        if not matches:
            raise ContractError(f"files[{index}] ne correspond à aucun fichier : {pattern}")
        for path in matches:
            relative = path.relative_to(ROOT).as_posix()
            files[relative] = path

    return [
        {
            "digest": sha256_file(path),
            "path": relative,
            "size": path.stat().st_size,
        }
        for relative, path in sorted(files.items())
    ]


def manifest_digest(manifest: list[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_bytes(manifest))


def command_arguments(check: dict[str, Any]) -> list[str]:
    python = str(Path(sys.executable).resolve())
    return [python if argument == "{python}" else argument for argument in check["command"]]


def execute_check(check: dict[str, Any]) -> dict[str, Any]:
    command = command_arguments(check)
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=check["timeout_seconds"],
        )
        exit_code: int | None = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        exit_code = None
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")

    result: dict[str, Any] = {
        "command": command,
        "duration_seconds": round(time.monotonic() - started, 6),
        "exit_code": exit_code,
        "name": check["name"],
        "status": "PASS" if exit_code == 0 and not timed_out else "FAIL",
        "timed_out": timed_out,
    }
    if result["status"] == "FAIL":
        result["stdout"] = stdout
        result["stderr"] = stderr
    return result


def interpreter_record() -> dict[str, str]:
    return {
        "implementation": platform.python_implementation(),
        "path": str(Path(sys.executable).resolve()),
        "version": platform.python_version(),
    }


def write_report(contract: dict[str, Any], report: dict[str, Any]) -> Path:
    directory = ROOT / relative_path(contract["report_directory"], "report_directory")
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = directory / f"{timestamp}.json"
    path.write_bytes(canonical_bytes(report))
    return path


def validate_command(contract_path: Path) -> int:
    contract, raw = load_contract(contract_path)
    manifest = candidate_manifest(contract)
    print("Configuration valide.")
    print(f"Digest : {sha256_bytes(raw)}")
    print(f"Fichiers : {len(manifest)}")
    print(f"Contrôles : {len(contract['checks'])}")
    return 0


def run_command(contract_path: Path, *, save_report: bool = False) -> int:
    contract, raw = load_contract(contract_path)
    contract_digest = sha256_bytes(raw)
    before_manifest = candidate_manifest(contract)
    before_candidate_digest = manifest_digest(before_manifest)
    results = []

    for check in contract["checks"]:
        result = execute_check(check)
        results.append(result)
        print(
            f"{result['name']}: {result['status']} "
            f"({result['duration_seconds']:.3f}s)"
        )
        if result["status"] == "FAIL":
            if result["stdout"]:
                print(result["stdout"], end="", file=sys.stdout)
            if result["stderr"]:
                print(result["stderr"], end="", file=sys.stderr)

    violations: list[str] = []
    try:
        _, after_raw = load_contract(contract_path)
        after_contract_digest = sha256_bytes(after_raw)
    except ContractError:
        after_contract_digest = "indisponible"
    if after_contract_digest != contract_digest:
        violations.append("configuration modifiée pendant l’exécution")

    try:
        after_manifest = candidate_manifest(contract)
        after_candidate_digest = manifest_digest(after_manifest)
    except ContractError:
        after_manifest = []
        after_candidate_digest = "indisponible"
    if after_candidate_digest != before_candidate_digest:
        violations.append("fichiers contrôlés modifiés pendant l’exécution")

    status = (
        "PASS"
        if all(result["status"] == "PASS" for result in results) and not violations
        else "FAIL"
    )
    report = {
        "candidate": {
            "digest": after_candidate_digest,
            "manifest": after_manifest,
        },
        "checks": results,
        "contract_digest": contract_digest,
        "interpreter": interpreter_record(),
        "run_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "version": 1,
        "violations": violations,
    }

    if save_report:
        report_path = write_report(contract, report)
        print(f"Rapport : {report_path.relative_to(ROOT)}")
        print(f"Digest du rapport : {sha256_file(report_path)}")
    print(f"Résultat : {status}")
    for violation in violations:
        print(f"Violation : {violation}", file=sys.stderr)
    return 0 if status == "PASS" else 1


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valide ou exécute les contrôles du projet."
    )
    parser.add_argument("command", choices=("validate", "run"))
    parser.add_argument(
        "--contract",
        type=Path,
        default=DEFAULT_CONTRACT,
        help="configuration à utiliser",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="conserver le résultat sous forme de rapport JSON",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    contract_path = arguments.contract
    if not contract_path.is_absolute():
        contract_path = ROOT / contract_path
    try:
        if arguments.command == "validate":
            if arguments.report:
                raise ContractError("--report s’utilise uniquement avec run")
            return validate_command(contract_path)
        return run_command(contract_path, save_report=arguments.report)
    except ContractError as error:
        print(f"Configuration invalide : {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
