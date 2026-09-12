"""Git helpers: worktrees, exact version identification, diffs and integrity checks."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def git(args: list[str], cwd: Path, check: bool = True, timeout: int = 120) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=None,
    )
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def is_repo(path: Path) -> bool:
    try:
        return git(["rev-parse", "--is-inside-work-tree"], path).strip() == "true"
    except (GitError, OSError, subprocess.TimeoutExpired):
        return False


def repo_root(path: Path) -> Path:
    return Path(git(["rev-parse", "--show-toplevel"], path).strip())


def head_commit(path: Path) -> str:
    return git(["rev-parse", "HEAD"], path).strip()


def rev_parse(path: Path, ref: str) -> str:
    return git(["rev-parse", "--verify", f"{ref}^{{commit}}"], path).strip()


def current_branch(path: Path) -> str | None:
    out = git(["rev-parse", "--abbrev-ref", "HEAD"], path, check=False).strip()
    return out or None


def is_dirty(path: Path) -> bool:
    return bool(git(["status", "--porcelain", "--untracked-files=normal"], path).strip())


def has_uncommitted_changes(path: Path) -> bool:
    """Tracked files changed and not committed, staged or not — untracked files aside.

    The question a merge asks, as opposed to :func:`is_dirty`, which asks whether a worktree
    has been touched at all. A file of your own that git does not track is not in a merge's
    way unless the merge would write over it, and git says so itself when that happens.
    Refusing every stray file would make the control unusable in the tree people work in.
    """
    return bool(git(["status", "--porcelain", "--untracked-files=no"], path).strip())


def status_porcelain(path: Path) -> str:
    return git(["status", "--porcelain", "--untracked-files=normal"], path)


def ensure_excluded(root: Path, pattern: str) -> None:
    """Add ``pattern`` to ``.git/info/exclude`` without touching tracked files."""
    try:
        git_dir = Path(git(["rev-parse", "--git-common-dir"], root).strip())
    except GitError:
        return
    if not git_dir.is_absolute():
        git_dir = root / git_dir
    exclude = git_dir / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    if pattern not in existing.splitlines():
        with exclude.open("a", encoding="utf-8") as fh:
            if existing and not existing.endswith("\n"):
                fh.write("\n")
            fh.write(pattern + "\n")


def add_worktree(root: Path, dest: Path, branch: str, base: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise GitError(f"worktree path already exists: {dest}")
    existing = git(["branch", "--list", branch], root).strip()
    if existing:
        git(["worktree", "add", str(dest), branch], root)
    else:
        git(["worktree", "add", "-b", branch, str(dest), base], root)


def add_worktree_detached(root: Path, dest: Path, commit: str) -> None:
    """A throwaway checkout of ``commit``, on no branch, so nothing can move a branch pointer."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise GitError(f"worktree path already exists: {dest}")
    git(["worktree", "add", "--detach", str(dest), commit], root)


def remove_worktree(root: Path, dest: Path, force: bool = True) -> None:
    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(dest))
    git(args, root, check=False)
    git(["worktree", "prune"], root, check=False)


TRANSIENT_PATTERNS = (
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    ".tox",
    ".nox",
    ".coverage",
    "coverage.xml",
    "node_modules",
    ".DS_Store",
    "*.egg-info",
)


def commit_all(
    path: Path,
    message: str,
    author: str = "495 harness <495@localhost>",
    exclude: tuple[str, ...] = TRANSIENT_PATTERNS,
) -> str | None:
    """Stage everything except well-known build caches and commit as the harness.

    Returns the new SHA, or None when nothing changed.
    """
    pathspec = [".", *(f":(exclude,glob)**/{pat}" for pat in exclude)]
    git(["add", "-A", "--", *pathspec], path)
    if not git(["diff", "--cached", "--quiet"], path, check=False) and _staged_empty(path):
        return None
    git(
        [
            "-c",
            "user.name=495 harness",
            "-c",
            "user.email=495@localhost",
            "commit",
            "-q",
            "--no-verify",
            "--author",
            author,
            "-m",
            message,
        ],
        path,
    )
    return head_commit(path)


def _staged_empty(path: Path) -> bool:
    return not git(["diff", "--cached", "--name-only"], path).strip()


def diff(path: Path, base: str, head: str = "HEAD") -> str:
    return git(["diff", "--no-color", "--no-ext-diff", f"{base}..{head}"], path)


def diff_names(path: Path, base: str, head: str = "HEAD") -> list[str]:
    out = git(["diff", "--name-only", f"{base}..{head}"], path)
    return [line.strip() for line in out.splitlines() if line.strip()]


def diff_stat(path: Path, base: str, head: str = "HEAD") -> str:
    return git(["diff", "--stat", "--no-color", f"{base}..{head}"], path)


def format_patch(path: Path, base: str, head: str = "HEAD") -> str:
    return git(["format-patch", "--stdout", f"{base}..{head}"], path)


def worktree_diff(path: Path) -> str:
    """Diff of the working tree (staged and unstaged, untracked included) against HEAD."""
    git(["add", "-A", "--intent-to-add"], path, check=False)
    out = git(["diff", "--no-color", "--no-ext-diff", "HEAD"], path)
    return out


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def reset_hard_clean(path: Path, ref: str = "HEAD") -> None:
    git(["reset", "-q", "--hard", ref], path)
    git(["clean", "-fdq"], path)


def merge_no_ff(path: Path, branch: str, message: str) -> str:
    """Merge ``branch`` into the checked-out branch, keeping the merge commit.

    A merge that does not go through cleanly is undone rather than left half-made: a
    conflicted index is a state only the person at the keyboard can resolve, and it would be
    left behind by a thread they cannot see. Aborting puts the branch back where it was and
    hands the conflict back as a refusal, which is something a surface can say in one line.

    ``--no-ff`` because the merge commit is the record: it is what makes the delivered commit
    an ancestor of the branch under a name, so the check that follows can find it there and
    the history says where the change came from.
    """
    proc = subprocess.run(
        [
            "git",
            "-c",
            "user.name=495 harness",
            "-c",
            "user.email=495@localhost",
            "merge",
            "--no-ff",
            "-m",
            message,
            branch,
        ],
        cwd=str(path),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        git(["merge", "--abort"], path, check=False)
        detail = (proc.stdout + proc.stderr).strip().replace("\n", "; ")
        raise GitError(f"merging {branch} did not go through, nothing was changed: {detail}")
    return head_commit(path)


def is_ancestor(path: Path, commit: str, ref: str) -> bool:
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, ref],
        cwd=str(path),
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def blob_hash(path: Path, ref: str, file: str) -> str | None:
    out = git(["ls-tree", ref, "--", file], path, check=False)
    parts = out.split()
    return parts[2] if len(parts) >= 3 else None


def apply_check(path: Path, patch_file: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        ["git", "apply", "--check", str(patch_file)],
        cwd=str(path),
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0, (proc.stderr or proc.stdout).strip()


def top_level_listing(root: Path, max_entries: int = 200) -> list[str]:
    out = git(["ls-files"], root, check=False)
    files = [f for f in out.splitlines() if f.strip()]
    return files[:max_entries]
