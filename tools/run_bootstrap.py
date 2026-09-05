#!/usr/bin/env python3
"""Valide le contrat minimal et génère les rapports du bootstrap."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACT = ROOT / "bootstrap/contract.json"
RUN_COUNT_RE = re.compile(r"Ran (\d+) tests?")
IDENTIFIER_RE = re.compile(r"\((tests\.[^)]+)\)")
COVERAGE_RE = re.compile(r"\bCOVERAGE\s+(\S+)\s+(\d+)/(\d+)")
COUNTER_PATTERNS = {
    "skipped": re.compile(r"skipped=(\d+)"),
    "expected failures": re.compile(r"expected failures=(\d+)"),
    "unexpected successes": re.compile(r"unexpected successes=(\d+)"),
}


class ContractError(ValueError):
    """Le contrat ne peut pas gouverner une exécution."""


def sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def relative_path(value: str, field: str, *, allow_dot: bool = False) -> Path:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{field} doit être une chaîne non vide")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or (path == Path(".") and not allow_dot):
        raise ContractError(f"{field} doit être un chemin relatif borné : {value}")
    return path


def require_type(value: Any, expected: type, field: str) -> None:
    if not isinstance(value, expected):
        raise ContractError(f"{field} doit être de type {expected.__name__}")


def reject_indeterminate(value: Any, field: str = "contract") -> None:
    if value is None:
        raise ContractError(f"{field} contient une valeur nulle")
    if isinstance(value, str) and value.strip().upper() == "UNBOUND":
        raise ContractError(f"{field} contient UNBOUND")
    if isinstance(value, dict):
        for key, child in value.items():
            reject_indeterminate(child, f"{field}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_indeterminate(child, f"{field}[{index}]")


def required_python_version(requirement: str) -> tuple[int, int]:
    match = re.fullmatch(r">=(\d+)\.(\d+)", requirement)
    if not match:
        raise ContractError("runtime.python_requires doit suivre la forme >=X.Y")
    return int(match.group(1)), int(match.group(2))


def load_contract(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        contract = json.loads(raw)
    except FileNotFoundError as error:
        raise ContractError(f"contrat absent : {path}") from error
    except json.JSONDecodeError as error:
        raise ContractError(f"JSON invalide : {error}") from error

    require_type(contract, dict, "contract")
    reject_indeterminate(contract)
    if raw != canonical_bytes(contract):
        raise ContractError(
            "le contrat doit utiliser les clés triées, une indentation de deux espaces "
            "et un retour à la ligne final"
        )
    validate_contract(contract)
    return contract, raw


def validate_contract(contract: dict[str, Any]) -> None:
    required = {
        "candidate",
        "checks",
        "environment",
        "objective",
        "permissions",
        "report",
        "runtime",
        "schema_version",
        "security",
        "stop_on",
        "work_document",
    }
    missing = required - set(contract)
    if missing:
        raise ContractError(f"champs racine manquants : {sorted(missing)}")
    if contract["schema_version"] != "bootstrap-1":
        raise ContractError("schema_version non prise en charge")
    if not isinstance(contract["objective"], str) or not contract["objective"].strip():
        raise ContractError("objective doit être une chaîne non vide")

    runtime = contract["runtime"]
    require_type(runtime, dict, "runtime")
    if runtime.get("command_token") != "{python}":
        raise ContractError("runtime.command_token doit valoir {python}")
    required_version = required_python_version(runtime.get("python_requires", ""))
    if sys.version_info[:2] < required_version:
        raise ContractError(
            f"Python {required_version[0]}.{required_version[1]} ou ultérieur requis"
        )

    candidate = contract["candidate"]
    require_type(candidate, dict, "candidate")
    require_type(candidate.get("roots"), list, "candidate.roots")
    require_type(candidate.get("include"), list, "candidate.include")
    if not candidate["roots"] or not candidate["include"]:
        raise ContractError("candidate.roots et candidate.include ne peuvent pas être vides")
    for index, root in enumerate(candidate["roots"]):
        require_type(root, str, f"candidate.roots[{index}]")
        relative_path(root, f"candidate.roots[{index}]")
    for index, pattern in enumerate(candidate["include"]):
        require_type(pattern, str, f"candidate.include[{index}]")
        relative_path(pattern, f"candidate.include[{index}]")
    if not isinstance(candidate.get("symlinks"), bool):
        raise ContractError("candidate.symlinks doit être booléen")

    permissions = contract["permissions"]
    require_type(permissions, dict, "permissions")
    for name in ("network", "secrets", "external_effects"):
        if not isinstance(permissions.get(name), bool):
            raise ContractError(f"permissions.{name} doit être booléen")
    for access in ("read", "write"):
        require_type(permissions.get(access), list, f"permissions.{access}")
        for index, value in enumerate(permissions[access]):
            require_type(value, str, f"permissions.{access}[{index}]")
            relative_path(value, f"permissions.{access}[{index}]")

    checks = contract["checks"]
    require_type(checks, list, "checks")
    if not checks:
        raise ContractError("au moins un contrôle est requis")
    identifiers: set[str] = set()
    for index, check in enumerate(checks):
        field = f"checks[{index}]"
        require_type(check, dict, field)
        identifier = check.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ContractError(f"{field}.id doit être une chaîne non vide")
        if identifier in identifiers:
            raise ContractError(f"identifiant de contrôle dupliqué : {identifier}")
        identifiers.add(identifier)
        argv = check.get("argv")
        require_type(argv, list, f"{field}.argv")
        if not argv or not all(isinstance(arg, str) and arg for arg in argv):
            raise ContractError(f"{field}.argv doit contenir des chaînes non vides")
        tokens = {token for arg in argv for token in re.findall(r"\{[^{}]+\}", arg)}
        if tokens - {"{python}"}:
            raise ContractError(f"{field}.argv contient des jetons inconnus : {tokens}")
        if not isinstance(check.get("required"), bool):
            raise ContractError(f"{field}.required doit être booléen")
        if not isinstance(check.get("timeout_seconds"), int) or check["timeout_seconds"] <= 0:
            raise ContractError(f"{field}.timeout_seconds doit être un entier positif")
        relative_path(
            check.get("working_directory", ""),
            f"{field}.working_directory",
            allow_dot=True,
        )
        expected = check.get("expected")
        require_type(expected, dict, f"{field}.expected")
        if expected.get("exit_code") != 0:
            raise ContractError(f"{field}.expected.exit_code doit valoir 0")
        if not isinstance(expected.get("minimum_test_count"), int):
            raise ContractError(f"{field}.expected.minimum_test_count doit être un entier")
        require_type(expected.get("zero_counters"), list, f"{field}.expected.zero_counters")
        unknown = set(expected["zero_counters"]) - set(COUNTER_PATTERNS)
        if unknown:
            raise ContractError(f"{field} contient des compteurs inconnus : {sorted(unknown)}")

    environment = contract["environment"]
    require_type(environment, dict, "environment")
    require_type(environment.get("inherit"), list, "environment.inherit")
    require_type(environment.get("set"), dict, "environment.set")
    if "TMPDIR" not in environment["set"]:
        raise ContractError("environment.set.TMPDIR est requis")
    relative_path(environment["set"]["TMPDIR"], "environment.set.TMPDIR")

    report = contract["report"]
    require_type(report, dict, "report")
    report_directory = relative_path(report.get("directory", ""), "report.directory")
    if report.get("qualification_without_enforcement") != "progress":
        raise ContractError(
            "report.qualification_without_enforcement doit valoir progress"
        )
    write_paths = [relative_path(value, "permissions.write") for value in permissions["write"]]
    if not any(path_contains(path, report_directory) for path in write_paths):
        raise ContractError("report.directory doit appartenir aux chemins inscriptibles")

    security = contract["security"]
    require_type(security, dict, "security")
    for name in ("candidate_immutability", "network_restriction", "write_restriction"):
        mechanism = security.get(name)
        require_type(mechanism, dict, f"security.{name}")
        if not isinstance(mechanism.get("mechanism"), str) or not mechanism["mechanism"]:
            raise ContractError(f"security.{name}.mechanism doit être renseigné")
        if not isinstance(mechanism.get("qualified"), bool):
            raise ContractError(f"security.{name}.qualified doit être booléen")
        if mechanism["qualified"] and mechanism["mechanism"] == "none":
            raise ContractError(
                f"security.{name} ne peut pas être qualifié sans mécanisme"
            )

    relative_path(contract["work_document"], "work_document")


def path_contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def contract_authorized(contract: dict[str, Any], digest: str) -> bool:
    work_document = ROOT / relative_path(contract["work_document"], "work_document")
    if not work_document.is_file():
        return False
    pattern = re.compile(
        rf"^AUTORISÉ — contrat {re.escape(digest)} — .+ — \d{{4}}-\d{{2}}-\d{{2}}$",
        re.MULTILINE,
    )
    return pattern.search(work_document.read_text(encoding="utf-8")) is not None


def candidate_manifest(contract: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    candidate = contract["candidate"]
    patterns = candidate["include"]
    allow_symlinks = candidate["symlinks"]
    files: dict[str, Path] = {}
    violations: list[str] = []

    for root_value in candidate["roots"]:
        root = ROOT / root_value
        if not root.is_dir():
            violations.append(f"racine candidate absente : {root_value}")
            continue
        if root.is_symlink() and not allow_symlinks:
            violations.append(f"lien symbolique interdit : {root_value}")
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(ROOT).as_posix()
            if path.is_symlink():
                if not allow_symlinks:
                    violations.append(f"lien symbolique interdit : {relative}")
                continue
            if not path.is_file():
                continue
            if not any(fnmatch.fnmatchcase(relative, pattern) for pattern in patterns):
                violations.append(f"fichier candidat hors périmètre : {relative}")
                continue
            files[relative] = path

    manifest = [
        {
            "digest": sha256_file(path),
            "path": relative,
            "size": path.stat().st_size,
        }
        for relative, path in sorted(files.items())
    ]
    if not manifest:
        violations.append("aucun fichier candidat découvert")
    return manifest, sorted(set(violations))


def manifest_digest(manifest: list[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_bytes(manifest))


def workspace_snapshot() -> dict[str, str]:
    ignored_roots = {".git", "bootstrap/runs"}
    snapshot: dict[str, str] = {}
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT).as_posix()
        if any(relative == root or relative.startswith(root + "/") for root in ignored_roots):
            continue
        if path.is_symlink():
            snapshot[relative] = "symlink:" + os.readlink(path)
        elif path.is_file():
            snapshot[relative] = sha256_file(path)
    return snapshot


def changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(
        path
        for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    )


def allowed_write(path: str, contract: dict[str, Any]) -> bool:
    child = Path(path)
    return any(
        path_contains(relative_path(parent, "permissions.write"), child)
        for parent in contract["permissions"]["write"]
    )


def git_value(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return "indisponible"
    return completed.stdout.strip()


def effective_environment(contract: dict[str, Any]) -> dict[str, str]:
    environment: dict[str, str] = {}
    for name in contract["environment"]["inherit"]:
        if name in os.environ:
            environment[name] = os.environ[name]
    for name, value in contract["environment"]["set"].items():
        if name in {"TMPDIR", "PYTHONPATH"}:
            environment[name] = str((ROOT / value).resolve())
        else:
            environment[name] = value
    return environment


def counter_values(output: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for name, pattern in COUNTER_PATTERNS.items():
        matches = [int(value) for value in pattern.findall(output)]
        values[name] = max(matches, default=0)
    return values


def execute_check(check: dict[str, Any], environment: dict[str, str]) -> dict[str, Any]:
    argv = [
        str(Path(sys.executable).resolve()) if value == "{python}" else value
        for value in check["argv"]
    ]
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            argv,
            cwd=ROOT / check["working_directory"],
            env=environment,
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

    duration = round(time.monotonic() - started, 6)
    combined = stdout + "\n" + stderr
    counts = [int(value) for value in RUN_COUNT_RE.findall(combined)]
    test_count = counts[-1] if counts else 0
    counters = counter_values(combined)
    identifiers = sorted(set(IDENTIFIER_RE.findall(combined)))
    coverage = [
        {
            "covered": int(covered),
            "declared": int(declared),
            "domain": domain,
        }
        for domain, covered, declared in COVERAGE_RE.findall(combined)
    ]

    expected = check["expected"]
    reasons: list[str] = []
    if timed_out:
        reasons.append("timeout")
    if exit_code != expected["exit_code"]:
        reasons.append(f"code de sortie {exit_code}")
    if test_count < expected["minimum_test_count"]:
        reasons.append(f"{test_count} test découvert")
    for name in expected["zero_counters"]:
        if counters[name] != 0:
            reasons.append(f"{name}={counters[name]}")
    if expected.get("coverage_equality"):
        if not coverage:
            reasons.append("aucune ligne COVERAGE")
        elif any(item["covered"] != item["declared"] for item in coverage):
            reasons.append("couverture d’énumération incomplète")

    return {
        "argv": argv,
        "coverage": coverage,
        "duration_seconds": duration,
        "exit_code": exit_code,
        "id": check["id"],
        "identifiers": identifiers,
        "required": check["required"],
        "status": "PASS" if not reasons else "FAIL",
        "status_reasons": reasons,
        "stderr": stderr,
        "stdout": stdout,
        "test_count": test_count,
        "timed_out": timed_out,
        "zero_counters": counters,
    }


def interpreter_record() -> dict[str, Any]:
    executable = Path(sys.executable).resolve()
    return {
        "architecture": platform.machine(),
        "digest": sha256_file(executable),
        "implementation": platform.python_implementation(),
        "path": str(executable),
        "platform": platform.platform(),
        "version": platform.python_version(),
    }


def write_report(contract: dict[str, Any], report: dict[str, Any]) -> Path:
    directory = ROOT / relative_path(contract["report"]["directory"], "report.directory")
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = directory / f"{timestamp}.json"
    with path.open("xb") as stream:
        stream.write(canonical_bytes(report))
    return path


def validate_command(contract_path: Path) -> int:
    contract, raw = load_contract(contract_path)
    digest = sha256_bytes(raw)
    authorized = contract_authorized(contract, digest)
    print("Contrat valide.")
    print(f"Digest : {digest}")
    print(f"Python : {platform.python_version()} ({Path(sys.executable).resolve()})")
    print(f"Autorisation du candidat : {'présente' if authorized else 'absente'}")
    if not authorized:
        print(f"Ligne d’autorisation attendue : AUTORISÉ — contrat {digest}")
    return 0


def run_command(contract_path: Path) -> int:
    contract, raw = load_contract(contract_path)
    contract_digest = sha256_bytes(raw)
    if not contract_authorized(contract, contract_digest):
        print(
            "Exécution refusée : docs/implementation.md ne contient pas "
            f"l’autorisation du contrat {contract_digest}.",
            file=sys.stderr,
        )
        return 2

    output_directory = ROOT / contract["environment"]["set"]["TMPDIR"]
    output_directory.mkdir(parents=True, exist_ok=True)

    git_commit = git_value("rev-parse", "HEAD")
    git_status_before = git_value("status", "--short")
    before_workspace = workspace_snapshot()
    before_manifest, scope_violations = candidate_manifest(contract)
    before_candidate_digest = manifest_digest(before_manifest)
    contract_before = sha256_file(contract_path)
    results: list[dict[str, Any]] = []

    if not scope_violations:
        environment = effective_environment(contract)
        for check in contract["checks"]:
            results.append(execute_check(check, environment))

    after_manifest, after_scope_violations = candidate_manifest(contract)
    after_candidate_digest = manifest_digest(after_manifest)
    after_workspace = workspace_snapshot()
    git_status_after = git_value("status", "--short")
    workspace_changes = changed_paths(before_workspace, after_workspace)
    forbidden_writes = [
        path for path in workspace_changes if not allowed_write(path, contract)
    ]

    violations = sorted(set(scope_violations + after_scope_violations))
    if contract_before != sha256_file(contract_path):
        violations.append("contrat modifié pendant l’exécution")
    if before_candidate_digest != after_candidate_digest:
        violations.append("candidat modifié pendant l’exécution")
    violations.extend(f"écriture hors périmètre : {path}" for path in forbidden_writes)
    violations = sorted(set(violations))

    required_checks_passed = all(
        result["status"] == "PASS"
        for result in results
        if result["required"]
    ) and all(
        any(result["id"] == check["id"] for result in results)
        for check in contract["checks"]
        if check["required"]
    )
    security_qualified = all(
        item["qualified"] for item in contract["security"].values()
    )
    acceptance_eligible = (
        required_checks_passed and not violations and security_qualified
    )
    functional_status = (
        "PASS" if required_checks_passed and not violations else "FAIL"
    )

    report = {
        "acceptance_eligible": acceptance_eligible,
        "candidate": {
            "digest": after_candidate_digest,
            "manifest": after_manifest,
        },
        "checks": results,
        "contract_digest": contract_digest,
        "git": {
            "commit": git_commit,
            "status_after": git_status_after,
            "status_before": git_status_before,
        },
        "interpreter": interpreter_record(),
        "objective": contract["objective"],
        "qualification": (
            "acceptance" if acceptance_eligible
            else contract["report"]["qualification_without_enforcement"]
        ),
        "run_id": datetime.now(timezone.utc).isoformat(),
        "schema_version": "bootstrap-run-1",
        "security": contract["security"],
        "status": functional_status,
        "violations": violations,
        "workspace_changes": workspace_changes,
    }
    report_path = write_report(contract, report)
    report_digest = sha256_file(report_path)
    print(f"Rapport : {report_path.relative_to(ROOT)}")
    print(f"Digest : {report_digest}")
    print(f"Résultat fonctionnel : {functional_status}")
    print(f"Qualification : {report['qualification']}")
    print(f"Acceptation possible : {'oui' if acceptance_eligible else 'non'}")
    return 0 if functional_status == "PASS" else 1


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valide ou exécute le contrat du bootstrap minimal."
    )
    parser.add_argument(
        "command",
        choices=("validate", "run"),
        help="valider le contrat ou exécuter ses contrôles",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=DEFAULT_CONTRACT,
        help="chemin du contrat (bootstrap/contract.json par défaut)",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    contract_path = arguments.contract
    if not contract_path.is_absolute():
        contract_path = ROOT / contract_path
    try:
        if arguments.command == "validate":
            return validate_command(contract_path)
        return run_command(contract_path)
    except ContractError as error:
        print(f"Contrat invalide : {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
