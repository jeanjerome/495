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


INTEGRATIONS = ("fast-forward", "rebase", "squash", "merge")
"""The four shapes one act can take, from the one that adds nothing to the one that adds a
commit of its own. Three of them leave a linear history; only ``merge`` does not."""


def can_fast_forward(path: Path, branch: str) -> bool:
    """Whether the checked-out branch is behind ``branch`` and has gone nowhere else."""
    return is_ancestor(path, head_commit(path), branch)


def _as_harness(args: list[str]) -> list[str]:
    return ["-c", "user.name=495 harness", "-c", "user.email=495@localhost", *args]


def integrate_branch(path: Path, branch: str, how: str, message: str, base: str) -> str:
    """Bring ``branch`` into the checked-out branch the way ``how`` says, or change nothing.

    What separates the four is what the history keeps. ``fast-forward`` moves the branch onto
    the delivered commit and adds nothing at all. ``rebase`` copies the commits the run made
    on top of yours, so they arrive under new hashes. ``squash`` puts everything the run
    changed into a single commit. ``merge`` keeps the delivered commit itself as an ancestor,
    under a commit that says where it came from — the only one of the four that is not linear,
    and the reason the other three exist.

    A copy is what makes ``rebase`` and ``squash`` differ from the other two for the check that
    follows: the delivered commit is not in the branch afterwards, and it is the content of the
    changed files, byte for byte, that says the right thing landed.

    Whatever fails, the branch goes back where it was. An uncommitted change to a tracked file
    was refused before this ran, so resetting to the commit it started from restores exactly
    what was there — untracked files included, which a reset does not touch.
    """
    if how not in INTEGRATIONS:
        raise GitError(f"unknown way to integrate: {how!r}")
    before = head_commit(path)
    try:
        if how == "fast-forward":
            git(["merge", "--ff-only", branch], path)
        elif how == "merge":
            git(_as_harness(["merge", "--no-ff", "-m", message, branch]), path)
        elif how == "rebase":
            git(_as_harness(["cherry-pick", f"{base}..{branch}"]), path)
        else:
            git(["merge", "--squash", branch], path)
            git(_as_harness(["commit", "-m", message]), path)
    except GitError as exc:
        _undo(path, before)
        detail = str(exc).split(": ", 1)[-1].replace("\n", "; ")
        raise GitError(
            f"{how} of {branch} did not go through, nothing was changed: {detail}"
        ) from exc
    return head_commit(path)


def _undo(path: Path, before: str) -> None:
    """Put the branch back, whichever half-made state the attempt left behind."""
    git(["merge", "--abort"], path, check=False)
    git(["cherry-pick", "--abort"], path, check=False)
    git(["reset", "-q", "--hard", before], path, check=False)


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
