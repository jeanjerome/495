"""Running the test commands once more under the project's own coverage tool.

The pure reader is ``core/reading/reach.py`` — the recipe that puts a tool in front of a
command, the readers of the four report formats, and the crossing of a report with the lines
the change adds (``core/reading/diff.py``); this module is what runs the instrumented commands
and writes the ``coverage_check`` evidence (``docs/decisions/0023``).
"""

from __future__ import annotations

import shutil

from harness495.core import git
from harness495.core.engine.checks.stage import Reading
from harness495.core.engine.services import RunServices
from harness495.core.models import (
    ADMISSIBLE,
    CatalogueRole,
    Evidence,
    EvidenceKind,
    Iteration,
    RequirementKind,
    Run,
    Verification,
    VerificationKind,
    new_id,
)
from harness495.core.reading.diff import code_lines
from harness495.core.reading.reach import (
    READERS,
    REPORT_DIR,
    Hits,
    Instrumented,
    cross,
    instrument,
    merge,
)
from harness495.sandbox.base import ExecRequest


def coverage_watchers(run: Run, evidence: list[Evidence]) -> list[Verification]:
    """The commands worth running again under the project's coverage tool.

    A ``test`` verification that reported success on the evaluated commit and observes the
    change. Only a test is instrumented: a linter, a build or a type checker reads the
    source without executing it, and a coverage engine put in front of one would report
    that the change runs nowhere, which is about the command and not about the tests. A
    command already failing is being corrected, and one the calibration found blind, or
    one the second run did not agree with, describes itself. The cheapest goes first,
    since what bounds the check is a number of commands.
    """
    durations = {
        e.verification_id: e.duration_s or 0.0
        for e in evidence
        if e.kind is EvidenceKind.command_result and e.passed is True and e.verification_id
    }
    watchers = [
        v
        for v in run.spec.verifications
        if v.command
        and v.kind is VerificationKind.test
        and v.sufficiency in ADMISSIBLE
        and v.discriminates is not False
        and v.stable is not False
        and v.id in durations
    ]
    return sorted(watchers, key=lambda v: durations[v.id])


def instrumented_command(run: Run, command: str) -> Instrumented | None:
    """The command rewritten to write a coverage report, from the tool the profile found.

    The project's own tool makes the measure, and the profile says which one it is, per
    technology (``RoleCoverage`` of the ``coverage`` role). A project that measures the
    role with nothing, or with a tool this cannot drive, is not instrumented: the gap is
    the catalogue's to state and the requester's to close by a proposal, never the
    harness's to close by a command it invented (``docs/decisions/0014``).
    """
    assert run.profile is not None
    for row in run.profile.role_coverage:
        if row.role is not CatalogueRole.coverage or not row.tools:
            continue
        found = instrument(row.technology, row.tools, command, REPORT_DIR)
        if found is not None:
            return found
    return None


def reach(services: RunServices, run: Run, it: Iteration, evidence: list[Evidence]) -> Reading:
    """Measure which lines the change adds the verifications execute, and which they miss.

    The control run and the mutation check both ask what a command reports on another
    version of the tree; neither says anything about a line no command runs, since a
    command that never executes a line reports the same thing whatever that line says. The
    project's own coverage tool answers that, so the harness runs the test commands once
    more under it and crosses the report with the diff. A line the report holds with no
    hit leaves the behaviour requirements resting on those commands undetermined, for the
    same reason a surviving mutant does: the line may carry behaviour no requirement
    states, and only a reader tells that from a hole in the tests
    (``docs/decisions/0023``).
    """
    assert it.version is not None and it.version.head_commit
    limit = run.budget.max_coverage_commands
    watchers = coverage_watchers(run, evidence)[:limit] if limit > 0 else []
    pairs = [
        (v, recipe)
        for v in watchers
        if (recipe := instrumented_command(run, v.command or "")) is not None
    ]
    if not pairs:
        return Reading([])
    wt = services.worktree(run)
    head = it.version.head_commit
    test_commands = [
        v.command for v in run.spec.verifications if v.command and v.kind is VerificationKind.test
    ]
    lines = code_lines(git.diff(wt, it.version.base_commit, head), test_commands)
    if not lines:
        # The change adds no line a coverage engine counts (test files, documentation): a
        # run of the commands would measure nothing to cross.
        return Reading([])
    hits: Hits = {}
    measured: list[str] = []
    tools: list[str] = []
    last = ""
    try:
        for v, recipe in pairs:
            # The tool writes its data file where it is told and creates no directory for
            # it; a report left by the command before is not read as this one's.
            shutil.rmtree(wt / REPORT_DIR, ignore_errors=True)
            (wt / REPORT_DIR).mkdir(parents=True, exist_ok=True)
            res = services.sandbox.run(
                ExecRequest(
                    command=recipe.command,
                    cwd=wt,
                    timeout_s=run.budget.command_timeout_s,
                    writable=True,
                    network=run.config.sandbox.allow_network,
                    env=dict(recipe.env),
                    stop_check=services.stop_check(run),
                )
            )
            if res.interrupted:
                raise KeyboardInterrupt
            last = res.output
            found: Hits = {}
            for path in sorted(wt.glob(recipe.report)):
                text = path.read_text(encoding="utf-8", errors="replace")
                merge(found, READERS[recipe.reader](text))
            if not found:
                state = "timed out" if res.timed_out else f"exit {res.exit_code}"
                services.warn(
                    run,
                    f"{v.id} under {recipe.tool} wrote no coverage report ({state}): which "
                    "lines of the change it executes is not measured",
                )
                continue
            measured.append(v.id)
            tools.append(recipe.tool)
            merge(hits, found)
    finally:
        # The measure writes in the worktree; the reviewers read the version under review.
        git.reset_hard_clean(wt, head)
    reading = cross(lines, hits, measured, tools)
    # What an unexecuted line leaves undetermined: a requirement that states the change
    # makes something true, and rests on one of the commands that were measured.
    stakes = [
        r.id
        for r in run.spec.requirements
        if r.kind is RequirementKind.behaviour and set(measured).intersection(r.verification_ids)
    ]
    eid = new_id("ev")
    ev = Evidence(
        id=eid,
        kind=EvidenceKind.coverage_check,
        iteration=it.n,
        subject_version=head,
        requirement_ids=stakes if reading.missed else [],
        passed=None if not measured else not reading.missed,
        summary=reading.summary(),
    )
    if not measured or reading.missed:
        ev.output_ref = services.store.write_text(
            run.id, str(services.store.evidence_dir(run.id, eid) / "output.txt"), last
        )
        ev.output_sha256 = git.sha256_text(last)
    services.emit(
        run,
        "evidence",
        f"coverage: {'ok' if ev.passed else 'NOT EXECUTED' if ev.passed is False else 'not measured'}"
        f" - {ev.summary}",
        {"id": ev.id},
    )
    return Reading([ev])
