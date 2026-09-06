"""Observation indépendante d’un candidat dans un dépôt Git."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

from harness495.errors import ChangeError
from harness495.serialization import sha256_bytes


def _git(
    repository: Path, arguments: list[str], *, binary: bool = False
) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        text=not binary,
    )


def _stderr_text(completed: subprocess.CompletedProcess[Any]) -> str:
    stderr = completed.stderr
    if isinstance(stderr, bytes):
        stderr = stderr.decode(errors="replace")
    return stderr.strip()


def run_git(
    repository: Path, arguments: list[str], *, binary: bool = False
) -> bytes | str:
    completed = _git(repository, arguments, binary=binary)
    if completed.returncode != 0:
        raise ChangeError("git", _stderr_text(completed) or "commande Git en échec")
    return completed.stdout


def repository_root(repository: Path) -> Path:
    """Retourne le chemin résolu lorsqu’il désigne la racine d’un dépôt Git."""

    repository = repository.resolve()
    if not repository.is_dir():
        raise ChangeError("precondition", f"dépôt absent : {repository}")
    root = str(run_git(repository, ["rev-parse", "--show-toplevel"])).strip()
    if Path(root).resolve() != repository:
        raise ChangeError(
            "precondition", f"le chemin doit être la racine Git : {root}"
        )
    return repository


def require_clean(repository: Path) -> None:
    """Refuse tout fichier modifié, indexé ou non suivi et non ignoré."""

    status_output = run_git(
        repository,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        binary=True,
    )
    if status_output:
        raise ChangeError("precondition", "le dépôt cible doit être propre")


def resolve_baseline(repository: Path, reference: str = "HEAD") -> tuple[str, str]:
    """Résout la référence en commit et retourne ce commit avec celui de HEAD.

    La référence doit être HEAD ou un ancêtre de HEAD : le candidat représente
    ce que l’arbre de travail ajoute à la référence, commits intermédiaires
    compris, et non l’écart entre deux lignes de développement.
    """

    head = str(run_git(repository, ["rev-parse", "--verify", "HEAD"])).strip()
    resolved = _git(
        repository,
        ["rev-parse", "--verify", "--end-of-options", f"{reference}^{{commit}}"],
    )
    if resolved.returncode != 0:
        diagnostic = _stderr_text(resolved)
        raise ChangeError(
            "precondition",
            f"référence Git irrésoluble : {reference}"
            + (f" : {diagnostic}" if diagnostic else ""),
        )
    baseline = str(resolved.stdout).strip()
    if baseline != head:
        ancestry = _git(repository, ["merge-base", "--is-ancestor", baseline, head])
        if ancestry.returncode == 1:
            raise ChangeError(
                "precondition",
                f"la référence {reference} n’est pas un ancêtre de HEAD ; "
                "désigner la base de fusion, par exemple le résultat de "
                f"git merge-base {reference} HEAD",
            )
        if ancestry.returncode != 0:
            raise ChangeError(
                "git", _stderr_text(ancestry) or "commande Git en échec"
            )
    return baseline, head


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
        [
            "diff",
            "--binary",
            "--full-index",
            "--no-ext-diff",
            "--no-renames",
            baseline,
            "--",
        ],
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
