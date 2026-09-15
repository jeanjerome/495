"""Execute one verification command, on the evaluated commit or on the base version.

The only part of the verification chain that runs anything. It puts a command in the sandbox,
checks before running on the change that the worktree is still at the version being evaluated,
and turns what came back into ``Evidence``. What the outcome *means* — whether a pair of runs
tells the change from its absence, whether a failure is an assertion or an execution error,
whether a verification is sufficient at all — is read by
:mod:`harness495.core.reading.verification`, which touches nothing and is handed these results.

Both functions are called from the checks region (``core/engine/checks/sequence.py`` runs the
verification, ``core/engine/checks/calibration.py`` the control run); this module is why
``core.engine`` is the one part of ``core`` that reaches ``sandbox`` (0006, 0011).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from harness495.core import git
from harness495.core.models import Evidence, EvidenceKind, Verification, new_id
from harness495.sandbox import Sandbox
from harness495.sandbox.base import CommandResult, ExecRequest


class VersionMismatch(RuntimeError):
    pass


def run_verification(
    v: Verification,
    worktree: Path,
    expected_head: str | None,
    sandbox: Sandbox,
    iteration: int,
    timeout_s: int,
    output_sink: Callable[[str, str], str],
    stop_check: Callable[[], bool] | None = None,
    requirement_ids: list[str] | None = None,
    network: bool = False,
) -> Evidence:
    """Execute one verification. ``output_sink(evidence_id, text)`` stores the output and returns a ref."""
    eid = new_id("ev")
    if v.command is None:
        return Evidence(
            id=eid,
            kind=EvidenceKind.command_result,
            iteration=iteration,
            subject_version=expected_head,
            verification_id=v.id,
            requirement_ids=requirement_ids or [],
            passed=None,
            summary=f"{v.id} has no command; not executed ({v.sufficiency.value})",
        )
    if expected_head is not None:
        actual = git.head_commit(worktree)
        if actual != expected_head:
            raise VersionMismatch(
                f"worktree HEAD {actual} differs from evaluated version {expected_head}"
            )
    req = ExecRequest(
        command=v.command,
        cwd=worktree,
        timeout_s=v.timeout_s or timeout_s,
        writable=True,  # test runners write caches; the version is protected by git, not by the sandbox
        network=network,
        stop_check=stop_check,
    )
    res: CommandResult = sandbox.run(req)
    ref = output_sink(eid, res.output)
    passed: bool | None
    if res.timed_out or res.interrupted:
        passed = None if res.interrupted else False
        summary = "timed out" if res.timed_out else "interrupted"
    else:
        passed = res.exit_code == v.expected_exit_code
        summary = f"exit {res.exit_code} (expected {v.expected_exit_code})"
    return Evidence(
        id=eid,
        kind=EvidenceKind.command_result,
        iteration=iteration,
        subject_version=expected_head,
        verification_id=v.id,
        requirement_ids=requirement_ids or [],
        command=v.command,
        exit_code=res.exit_code,
        expected_exit_code=v.expected_exit_code,
        passed=passed,
        summary=summary,
        output_ref=ref,
        output_sha256=git.sha256_text(res.output),
        duration_s=res.duration_s,
        sandbox=sandbox.describe(req),
    )


def run_control(
    v: Verification,
    base_worktree: Path,
    base_commit: str,
    sandbox: Sandbox,
    iteration: int,
    timeout_s: int,
    output_sink: Callable[[str, str], str],
    stop_check: Callable[[], bool] | None = None,
    network: bool = False,
    applied: list[str] | None = None,
    label: str | None = None,
) -> tuple[Evidence, CommandResult]:
    """Run a verification against the base version, where the change does not exist.

    The tree it runs in carries the change's own test files when they could be identified, so
    that the instrument is present and only the behaviour it measures is missing. What comes back
    is half of a pair: a command whose outcome is the same here and on the change is not
    observing the change, whatever it reports.
    """
    eid = new_id("ev")
    command = v.command
    assert command is not None
    req = ExecRequest(
        command=command,
        cwd=base_worktree,
        timeout_s=v.timeout_s or timeout_s,
        writable=True,
        network=network,  # the control must run under the conditions the subject ran under
        stop_check=stop_check,
    )
    res: CommandResult = sandbox.run(req)
    return (
        Evidence(
            id=eid,
            kind=EvidenceKind.instrument_check,
            iteration=iteration,
            subject_version=base_commit,
            verification_id=v.id,
            command=command,
            exit_code=res.exit_code,
            expected_exit_code=v.expected_exit_code,
            passed=None,  # a statement about the instrument, not about the change
            summary=f"{label or 'control run on the base version'}: exit {res.exit_code}"
            + (f", with {len(applied)} test file(s) of the change applied" if applied else ""),
            output_ref=output_sink(eid, res.output),
            output_sha256=git.sha256_text(res.output),
            duration_s=res.duration_s,
            sandbox=sandbox.describe(req),
        ),
        res,
    )
