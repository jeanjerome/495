"""Running the verifications against wrong versions of the change.

The pure reader is ``core/mutation.py`` — which line of the diff to alter and how, and what the
altered source reads (``core/diff.py``); this module is what applies each mutant in a detached
worktree, runs the commands watching it and writes the ``mutation_check`` evidence
(``docs/decisions/0022``).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from harness495.core import git
from harness495.core.engine.checks.stage import Reading
from harness495.core.engine.services import RunServices
from harness495.core.models import (
    ADMISSIBLE,
    Evidence,
    EvidenceKind,
    Iteration,
    RequirementKind,
    Run,
    Verification,
    VerificationKind,
    new_id,
)
from harness495.core.mutation import Mutant, mutated_source, plan_mutants
from harness495.sandbox.base import ExecRequest


def mutation_watchers(
    services: RunServices, run: Run, evidence: list[Evidence]
) -> list[Verification]:
    """The commands worth running against a wrong version of the change.

    Every command that reported success on the evaluated commit twice and can say
    something else on another tree: a command already failing is being corrected, and what
    a command that does not repeat its own reading reports on an altered version of the
    same code is not a statement about anything. The
    set is not restricted to the requirement a mutated line belongs to, because the
    harness does not know which requirement a line belongs to: what a mutant asks is
    whether the evidence the run rests on, taken together, tells this version of the
    change from a wrong one. A command slower on the change than the budget allows is left
    out with a warning, since the check costs one run per mutant; the rest are ordered by
    what they took, so that the cheapest gets the chance to settle the mutant first.
    """
    durations = {
        e.verification_id: e.duration_s or 0.0
        for e in evidence
        if e.kind is EvidenceKind.command_result and e.passed is True and e.verification_id
    }
    watchers: list[Verification] = []
    slow: set[str] = set()
    for v in run.spec.verifications:
        if (
            v.command is None
            or v.sufficiency not in ADMISSIBLE
            or v.discriminates is False
            or v.stable is False
            or v.id not in durations
        ):
            continue
        if durations[v.id] > run.budget.mutant_command_max_s:
            slow.add(v.id)
            continue
        watchers.append(v)
    for vid in sorted(slow):
        services.warn(
            run,
            f"{vid} took {durations[vid]:.0f}s on the change, over the "
            f"{run.budget.mutant_command_max_s}s a mutant run is given: what it lets "
            "through is not measured",
        )
    return sorted(watchers, key=lambda v: durations[v.id])


def mutate(services: RunServices, run: Run, it: Iteration, evidence: list[Evidence]) -> Reading:
    """Measure what the verifications let through, on wrong versions of the change itself.

    The calibration says each command reports something else without the change; it cannot
    say the command would report something else if the change were wrong. So the harness
    writes a few wrong versions: one line of the diff altered in one stated way each, on a
    worktree of the evaluated commit. A wrong version every command reports success on is
    one the run's evidence does not tell from the change, and the behaviour requirements
    resting on those commands are left undetermined for the requester to rule on: a mutant
    may be equivalent to the line it replaces, and only a reader can tell that from a hole
    in the tests (``docs/decisions/0022``).
    """
    assert it.version is not None and it.version.head_commit
    watchers = mutation_watchers(services, run, evidence)
    # What a mutant nothing reports leaves undetermined: a requirement that states the
    # change makes something true, and rests on one of the commands that passed it.
    watched = {v.id for v in watchers}
    stakes = [
        r.id
        for r in run.spec.requirements
        if r.kind is RequirementKind.behaviour and watched.intersection(r.verification_ids)
    ]
    if not watchers or not stakes:
        return Reading([])
    wt = services.worktree(run)
    head = it.version.head_commit
    mutants = plan_mutants(
        git.diff(wt, it.version.base_commit, head),
        run.budget.max_mutants,
        [
            v.command
            for v in run.spec.verifications
            if v.command and v.kind is VerificationKind.test
        ],
    )
    if not mutants:
        return Reading([])
    produced: list[Evidence] = []
    mutant_wt = wt.parent / f"{run.id}.mutant"
    root = Path(run.project_root)
    git.remove_worktree(root, mutant_wt)
    shutil.rmtree(mutant_wt, ignore_errors=True)
    try:
        git.add_worktree_detached(root, mutant_wt, head)
    except git.GitError as exc:
        services.warn(run, f"cannot measure the verifications against wrong versions: {exc}")
        return Reading([])
    try:
        for mutant in mutants:
            produced.append(run_mutant(services, run, it, mutant, watchers, stakes, mutant_wt))
    finally:
        git.remove_worktree(root, mutant_wt)
        shutil.rmtree(mutant_wt, ignore_errors=True)
    return Reading(produced)


def run_mutant(
    services: RunServices,
    run: Run,
    it: Iteration,
    mutant: Mutant,
    watchers: list[Verification],
    stakes: list[str],
    mutant_wt: Path,
) -> Evidence:
    """Apply one mutant, run the commands watching it, and record what they reported.

    The first command that fails settles it: one report is enough to say the change is
    told from this wrong version of it, and the commands that would have run after it say
    nothing more. A mutant no command reports is charged to every behaviour requirement
    those commands carry, since which of them the altered line serves is exactly what the
    harness cannot read.
    """
    assert it.version is not None
    source = mutant_wt / mutant.file
    original = source.read_text(encoding="utf-8", errors="replace") if source.is_file() else ""
    written = mutated_source(original, mutant) if original else None
    eid = new_id("ev")
    if written is None:
        return Evidence(
            id=eid,
            kind=EvidenceKind.mutation_check,
            iteration=it.n,
            subject_version=it.version.head_commit,
            passed=None,
            summary=f"{mutant.describe()}: the line is not where the diff put it; not applied",
        )
    ran: list[str] = []
    killer: str | None = None
    last = ""
    state = ""
    source.write_text(written, encoding="utf-8")
    try:
        for v in watchers:
            assert v.command is not None
            res = services.sandbox.run(
                ExecRequest(
                    command=v.command,
                    cwd=mutant_wt,
                    timeout_s=run.budget.mutant_command_max_s * 2,
                    writable=True,
                    network=run.config.sandbox.allow_network,
                    stop_check=services.stop_check(run),
                )
            )
            if res.interrupted:
                raise KeyboardInterrupt
            ran.append(v.id)
            last = res.output
            # A command that times out on the mutant is counted as having reported it: it
            # did not report success, and calling that "let through" would be an
            # accusation resting on a run that did not finish.
            state = "timed out" if res.timed_out else f"exit {res.exit_code}"
            if res.timed_out or res.exit_code != v.expected_exit_code:
                killer = v.id
                break
    finally:
        source.write_text(original, encoding="utf-8")
    summary = f"{mutant.describe()}: " + (
        f"{killer} reported it ({state})"
        if killer is not None
        else f"passed by every command that watches the change ({', '.join(ran)})"
    )
    ev = Evidence(
        id=eid,
        kind=EvidenceKind.mutation_check,
        iteration=it.n,
        subject_version=it.version.head_commit,
        verification_id=killer,
        requirement_ids=[] if killer is not None else stakes,
        passed=killer is not None,
        summary=summary,
        output_ref=services.store.write_text(
            run.id, str(services.store.evidence_dir(run.id, eid) / "output.txt"), last
        ),
        output_sha256=git.sha256_text(last),
    )
    services.emit(
        run,
        "evidence",
        f"mutation: {'reported' if ev.passed else 'LET THROUGH'} - {ev.summary}",
        {"id": ev.id, "mutant": mutant.id},
    )
    return ev
