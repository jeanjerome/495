"""Running every demonstrating verification again on the base version, and reading the pair.

The pure reader is ``core/verification.py`` — ``run_control``, ``measures_the_change`` and
``classify_instrument``, which say what a pair of runs on two trees means; this module is what
prepares the base version carrying the change's test files, runs the commands on it, records
what the producer reported as a candidate replacement, and puts an instrument found blind to
the requester (``docs/decisions/0002``, ``0019``).
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from harness495.core import git
from harness495.core.engine.checks.stage import Reading
from harness495.core.engine.errors import EngineError
from harness495.core.engine.services import RunServices
from harness495.core.models import (
    ADMISSIBLE,
    NON_DISCRIMINATING,
    REPLACED_PREFIX,
    DecisionKind,
    DecisionOption,
    Evidence,
    EvidenceKind,
    Iteration,
    PendingDecision,
    RequirementKind,
    Run,
    Sufficiency,
    Verification,
)
from harness495.core.verification import (
    classify_instrument,
    instrument_files,
    measures_the_change,
    run_control,
)


def calibrate(services: RunServices, run: Run, it: Iteration, evidence: list[Evidence]) -> Reading:
    """Run every demonstrating verification again on the base version and read the pair.

    The tree it runs against is the base version carrying the change's own test files: the
    instrument is there, what it measures is not. A command whose outcome is the same on both
    trees is not looking at the change — it either never reports success, or reports it
    whatever the tree holds — and no edit the producer could make would alter that.

    Pass or fail, every verification that a behaviour requirement leans on is measured this
    way. Checking only the failing ones catches the loud half and credits the silent one.
    A command the second run did not agree with is left out: what it reported on the change
    is one of two readings, and comparing it with a third run on another tree would name an
    instrument at fault on the strength of a coin that came up heads.
    """
    assert run.profile is not None and run.profile.base_commit and it.version is not None
    assert it.version.head_commit
    # What the previous pass found blind is not carried over: the commands are measured again
    # on this version, and what they report now is what the question rests on.
    it.instrument_faults = []
    base = run.profile.base_commit
    head = it.version.head_commit
    leaned_on = {
        vid
        for r in run.spec.requirements
        if r.kind is RequirementKind.behaviour
        for vid in r.verification_ids
    }
    subjects = [
        (v, e)
        for e in evidence
        if e.kind is EvidenceKind.command_result and e.verification_id
        for v in [run.spec.verification(e.verification_id)]
        if v is not None
        and v.command
        and v.sufficiency in ADMISSIBLE
        and v.stable is not False
        and (v.to_create or v.id in leaned_on)
    ]
    if not subjects:
        return Reading([], {})
    produced: list[Evidence] = []
    proposals: dict[str, str] = {}
    control_wt = services.worktree(run).parent / f"{run.id}.control"
    root = Path(run.project_root)
    git.remove_worktree(root, control_wt)
    shutil.rmtree(control_wt, ignore_errors=True)
    try:
        git.add_worktree_detached(root, control_wt, base)
    except git.GitError as exc:
        services.warn(run, f"cannot check the verifications against the base version: {exc}")
        return Reading([], {})

    def sink(eid: str, text: str) -> str:
        return services.store.write_text(
            run.id, str(services.store.evidence_dir(run.id, eid) / "output.txt"), text
        )

    try:
        wanted = instrument_files(it.version.files_changed)
        applied = git.checkout_paths(control_wt, head, wanted) if wanted else []
        if wanted:
            services.emit(
                run,
                "control.prepared",
                f"base version {base[:12]} with {len(applied)} test file(s) of the change "
                "applied, so the commands have something to run",
                {"files": applied},
            )
        for v, ev in subjects:
            control_ev, control = run_control(
                v,
                control_wt,
                base,
                services.sandbox,
                it.n,
                run.budget.command_timeout_s,
                sink,
                services.stop_check(run),
                network=run.config.sandbox.allow_network,
                applied=applied,
            )
            if control.interrupted:
                raise KeyboardInterrupt
            produced.append(control_ev)
            subject_output = services.store.read_text(run.id, ev.output_ref or "")
            discriminates, sufficiency, rationale = classify_instrument(
                v,
                ev.passed,
                ev.exit_code,
                subject_output,
                ev.summary == "timed out",
                control,
                base,
                applied,
            )
            v.discriminates = discriminates
            v.sufficiency = sufficiency
            if rationale:
                v.rationale = rationale
            if discriminates:
                services.emit(
                    run,
                    "control.ended",
                    f"{v.id}: reports something else without the change, so what it reports "
                    "with it is about the change"
                    + (
                        f"; unconfirmed: {rationale}"
                        if sufficiency is Sufficiency.unconfirmed
                        else ""
                    ),
                    {
                        "verification": v.id,
                        "faulty": False,
                        "unconfirmed": sufficiency is Sufficiency.unconfirmed,
                    },
                )
                continue
            if sufficiency is Sufficiency.sufficient:
                services.warn(run, f"{v.id} could not be calibrated: {rationale}")
                continue
            it.instrument_faults.append(f"{v.id}: {v.rationale}")
            services.emit(
                run,
                "instrument.fault",
                f"{v.id} does not observe the change: {v.rationale}",
                {"verification": v.id, "cause": sufficiency.value},
            )
            proposal = measure_proposal(services, run, it, v, control_wt, applied, sink)
            if proposal is not None:
                proposals[v.id] = proposal[0]
                produced.extend(proposal[1])
    finally:
        git.remove_worktree(root, control_wt)
        shutil.rmtree(control_wt, ignore_errors=True)
    return Reading(produced, proposals)


def measure_proposal(
    services: RunServices,
    run: Run,
    it: Iteration,
    v: Verification,
    control_wt: Path,
    applied: list[str],
    sink: Callable[[str, str], str],
) -> tuple[str, list[Evidence]] | None:
    """Take the producer's word for a command, then check it the same way as the spec's.

    The producer runs the commands by hand and is the first to see one of them refuse to work;
    what it reports is a claim, and the only thing that turns a claim into a fact here is the
    harness running it itself, on both trees, and finding that the two disagree.
    """
    assert it.version is not None and it.version.head_commit and run.profile is not None
    assert run.profile.base_commit
    head = (v.command or "").split()[:1]
    candidate = next(
        (
            c.command
            for c in it.commands_reported
            if c.exit_code == 0 and c.command != v.command and c.command.split()[:1] == head
        ),
        None,
    )
    if candidate is None:
        return None
    probe = v.model_copy(update={"command": candidate})
    wt = services.worktree(run)
    on_change, change_res = run_control(
        probe,
        wt,
        it.version.head_commit,
        services.sandbox,
        it.n,
        run.budget.command_timeout_s,
        sink,
        services.stop_check(run),
        network=run.config.sandbox.allow_network,
        label=f"command reported by the producer, run on the change for {v.id}",
    )
    without, without_res = run_control(
        probe,
        control_wt,
        run.profile.base_commit,
        services.sandbox,
        it.n,
        run.budget.command_timeout_s,
        sink,
        services.stop_check(run),
        network=run.config.sandbox.allow_network,
        applied=applied,
        label=f"the same command run without the change for {v.id}",
    )
    if change_res.interrupted or without_res.interrupted:
        raise KeyboardInterrupt
    passes = change_res.exit_code == v.expected_exit_code
    differs = measures_the_change(
        change_res.exit_code, change_res.output, without_res, change_res.timed_out
    )
    verdict = (
        "reports success with the change and something else without it"
        if passes and differs
        else f"exits {change_res.exit_code} with the change and {without_res.exit_code} without it"
    )
    services.emit(
        run,
        "proposal.measured",
        f"{v.id}: `{candidate}` {verdict}",
        {"verification": v.id, "command": candidate, "usable": passes and differs},
    )
    if not (passes and differs):
        return None
    return candidate, [on_change, without]


def recalibrate(services: RunServices, run: Run, note: str) -> None:
    """Point a verification at another command, keeping the requirement it carries.

    The command is not adopted on anyone's say-so: the run goes back to verifying, and the
    replacement is measured on both versions exactly as the one it replaces was.
    """
    it = run.current_iteration
    faulty = [v for v in run.spec.verifications if v.sufficiency in NON_DISCRIMINATING]
    if not faulty:
        raise EngineError("no verification is at fault, so there is no command to replace")
    head, sep, tail = note.partition(":")
    named = head.strip()
    chosen = next((v for v in faulty if v.id == named), None)
    command = tail if chosen is not None else note
    if chosen is None:
        # A note that opens on the id of a verification is naming one, and naming the wrong
        # one is a mistake to report rather than a command that happens to start with `V2:`.
        if sep and any(v.id == named for v in run.spec.verifications):
            raise EngineError(
                f"{named} is not one of the verifications at fault: "
                + ", ".join(v.id for v in faulty)
            )
        if len(faulty) != 1:
            raise EngineError(
                "name the verification the command is for, as `" + faulty[0].id + ": <command>`"
            )
        chosen = faulty[0]
    command = command.strip()
    if not command:
        raise EngineError("the note must carry the command to use instead")
    previous = chosen.command
    chosen.command = command
    chosen.sufficiency = Sufficiency.sufficient
    chosen.discriminates = None
    chosen.rationale = f"{REPLACED_PREFIX}{previous}` on the requester's instruction"
    if it is not None:
        it.instrument_faults = [
            f for f in it.instrument_faults if not f.startswith(f"{chosen.id}:")
        ]
    run.spec.artifact_ref = services.store.write_json(
        run.id,
        str(services.store.artifacts_dir(run.id) / "spec.json"),
        run.spec.model_dump(mode="json"),
    )
    services.emit(
        run,
        "verification.replaced",
        f"{chosen.id}: `{command}` replaces `{previous}`; it is measured on both versions "
        "before it counts",
        {"verification": chosen.id},
    )


def instrument_fault_settled(run: Run) -> bool:
    return any(
        d.kind is DecisionKind.instrument_fault and d.outcome == "ignore" for d in run.decisions
    )


def instrument_decision(it: Iteration, proposals: dict[str, str]) -> PendingDecision:
    measured = "; ".join(f"{vid}: `{cmd}`" for vid, cmd in proposals.items())
    question = (
        "These verifications report the same thing with and without the change, so they "
        "cannot show whether the requirements they carry hold: "
        + "; ".join(it.instrument_faults)
        + "."
    )
    if measured:
        question += (
            " The producer reported another command, and it was run on both versions: "
            + measured
            + " reports success with the change and something else without it."
        )
    question += (
        " Replace the command, go back to the specification, keep them as no proof either "
        "way, or abort?"
    )
    return PendingDecision(
        kind=DecisionKind.instrument_fault,
        question=question,
        options=[
            DecisionOption(
                key="recalibrate",
                label="Use another command (note: the command, or `V2: the command`)",
                needs_note=True,
                consequence="The command replaces the one in the specification, and the "
                "change already produced is verified again with it, on both versions. "
                "Nothing is implemented again and no agent is called.",
            ),
            DecisionOption(
                key="respecify",
                label="Write a specification these commands can actually check",
                needs_note=True,
                consequence="The specifier runs again with your note and proposes new "
                "verifications. The work already produced stays on the branch but is "
                "judged afresh against the new specification.",
            ),
            DecisionOption(
                key="ignore",
                label="Leave them; accept that they prove nothing either way",
                consequence="The run continues and stops asking. The requirements these "
                "commands were meant to cover can only end undetermined, so the run will "
                "ask you once more before concluding.",
            ),
            DecisionOption(
                key="abort",
                label="Abort the run",
                consequence="The run stops for good. The branch and the patch stay on disk.",
            ),
        ],
        context={"faults": it.instrument_faults, "measured": proposals},
    )
