"""One sentence per stage, saying what that stage concluded.

The badge on the pipeline strip says where to look; this says what was found. Written as
sentences on purpose: a status word ("violated") states a result, a sentence states the result
*and* the reason, and the reason is what the user needs to decide anything. Every one of them
is derived from the run — none is a caption.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from rich.text import Text

from harness495.core.models import (
    EvidenceKind,
    RequirementStatus,
    Role,
    Run,
    RunMode,
    RunStatus,
    Severity,
    Verdict,
)
from harness495.interfaces.tui.reading import (
    latest_results,
    requirement_counts,
    running_intervention,
)
from harness495.interfaces.tui.stages import DECISION_STAGE
from harness495.interfaces.tui.widgets.text import clip, hms, plural, short


def headline(run: Run, name: str) -> Text:
    return HEADLINES[name](run)


def _profile(run: Run) -> Text:
    if not run.profile:
        return Text("Not profiled yet: 495 has not looked at this project.", style="h.meta")
    p = run.profile
    dead = [r for r in p.readiness if not r.executable]
    lead = Text()
    lead.append(", ".join(p.languages) or "no language detected", style="h.value")
    lead.append(f" · {', '.join(p.tooling)}" if p.tooling else "", style="h.meta")
    lead.append(
        f" · {len(p.commands)} verification {plural(len(p.commands), 'command')}", "h.value"
    )
    if not p.readiness:
        lead.append(", none tried yet.", style="h.meta")
        return lead
    if not dead:
        lead.append(", all runnable on the base version.", style="req.satisfied")
        return lead
    lead.append(
        f". {len(dead)} cannot run here — {', '.join(r.command_name for r in dead)} — so nothing "
        f"{plural(len(dead), 'it', 'they')} would report can be used as evidence.",
        style="req.violated",
    )
    return lead


def _spec(run: Run) -> Text:
    spec = run.spec
    if not spec.requirements:
        return Text("No specification yet: the specifier has not run.", style="h.meta")
    n = len(spec.requirements)
    orphans = [r.id for r in spec.requirements if not r.verification_ids]
    out = Text()
    if not spec.approved:
        out.append(
            f"{n} {plural(n, 'requirement')} and {len(spec.verifications)} checks proposed. "
            "Nothing is produced until you approve them.",
            style="attn.you",
        )
    else:
        out.append(
            f"{n} {plural(n, 'requirement')} sealed, approved by "
            f"{spec.approved_by.value if spec.approved_by else 'the harness'}.",
            style="req.satisfied",
        )
    if orphans:
        out.append(
            f" {', '.join(orphans)} {plural(len(orphans), 'is', 'are')} carried by nothing: no "
            "evidence can decide it.",
            style="req.violated",
        )
    for gap in spec.gaps:
        out.append(f" Gap: {clip(gap, 110)}", style="suf.insufficient")
    return out


def _change(run: Run) -> Text:
    if run.mode is RunMode.evaluate:
        return Text(
            f"Evaluating an existing change ({run.evaluate_ref or 'a patch'}); no producer runs.",
            style="h.value",
        )
    live = running_intervention(run)
    if live is not None and live.role is Role.producer:
        return Text(
            f"{live.agent.kind.value}:{live.agent.model or 'default'} is holding the worktree, "
            f"{hms((dt.datetime.now(dt.UTC) - live.started_at).total_seconds())} of a "
            f"{live.timeout_s // 60}m timeout.",
            style="attn.work",
        )
    it = run.current_iteration
    if not it or not it.version or not it.version.head_commit:
        return Text("Nothing produced yet.", style="h.meta")
    v = it.version
    n = len(v.files_changed)
    scope = [e for e in run.evidence if e.kind is EvidenceKind.scope_check]
    inside = not scope or bool(scope[-1].passed)
    out = Text()
    out.append(f"{n} {plural(n, 'file')} changed, ", style="h.value")
    out.append(
        "all inside the allowed paths" if inside else "some outside the allowed paths",
        style="req.satisfied" if inside else "req.violated",
    )
    out.append(
        f". Evaluated at {short(v.head_commit)} on {v.branch or 'a detached head'}.", "h.value"
    )
    if it.blocked_claims:
        out.append(
            f" The producer reports {len(it.blocked_claims)} thing it could not do.",
            style="suf.insufficient",
        )
    return out


def _checks(run: Run) -> Text:
    results = latest_results(run)
    if not any(results.values()):
        return Text("No check has run against the candidate yet.", style="h.meta")
    total = len(run.spec.verifications)
    passed = [vid for vid, e in results.items() if e and e.passed]
    failed = [vid for vid, e in results.items() if e and e.passed is False]
    it = run.current_iteration
    faults = [vid for vid in (it.instrument_faults if it else []) if vid in results]
    failed = [vid for vid in failed if vid not in faults]
    out = Text()
    # White for the count, colour for the exceptions. Painting the whole sentence red because
    # two checks failed leaves nothing to point at the two that did.
    out.append(
        f"{len(passed)} of {total} checks pass.",
        style="req.satisfied" if len(passed) == total else "h.value",
    )
    if failed:
        out.append(
            f" {', '.join(failed)} {plural(len(failed), 'fails', 'fail')} on the candidate.",
            style="req.violated",
        )
    if faults:
        out.append(
            f" {', '.join(faults)} {plural(len(faults), 'fails', 'fail')} the same way on the base "
            f"version, so nothing {plural(len(faults), 'it', 'they')} reports can be attributed to "
            "the change.",
            style="suf.faulty",
        )
    return out


def _review(run: Run) -> Text:
    if not run.reviews:
        live = running_intervention(run)
        if live is not None and live.role is Role.reviewer:
            return Text(
                f"The {live.perspective} reviewer is reading the change.", style="attn.work"
            )
        return Text("No reviewer has reported yet.", style="h.meta")
    kept = [r for r in run.reviews if not r.discarded]
    dropped = [r for r in run.reviews if r.discarded]
    blockers = [(r, f) for r in kept for f in r.findings if f.severity is Severity.blocker]
    rejects = [r.perspective for r in kept if r.verdict is Verdict.reject]
    out = Text()
    out.append(
        f"{len(kept)} of {len(run.reviews)} verdicts kept.",
        style="req.satisfied" if not dropped else "suf.insufficient",
    )
    if rejects:
        out.append(
            f" {', '.join(rejects)} {plural(len(rejects), 'rejects', 'reject')}"
            + (f" on {len(blockers)} {plural(len(blockers), 'blocker')}." if blockers else "."),
            style="req.violated",
        )
    elif kept:
        out.append(" No reviewer rejects the change.", style="req.satisfied")
    for r in dropped:
        out.append(
            f" The {r.perspective} verdict was discarded: {clip(r.discard_reason, 70)}.",
            "suf.faulty",
        )
    return out


def _verdict(run: Run) -> Text:
    out = _ledger(run)
    # The question the run is stopped on is rendered under this sentence, so the sentence has
    # to survive an empty ledger: a run can be stopped on a decision before a single
    # requirement has been weighed, and "nothing to decide" printed above the thing being
    # decided was the ledger talking about itself as if it were the run.
    pending = run.pending_decision
    if pending is not None and DECISION_STAGE.get(pending.kind, "verdict") == "verdict":
        out.append("  495 is waiting on your answer below.", style="attn.you")
    return out


def _ledger(run: Run) -> Text:
    counts = requirement_counts(run)
    bad = counts[RequirementStatus.violated]
    grey = counts[RequirementStatus.undetermined]
    good = counts[RequirementStatus.satisfied]
    if not run.spec.requirements:
        return Text("No requirement has been written yet.", style="h.meta")
    if counts[RequirementStatus.pending] == len(run.spec.requirements):
        return Text("No requirement has been assessed yet.", style="h.meta")
    out = Text()
    if bad or grey:
        parts = []
        if bad:
            parts.append(f"{bad} violated")
        if grey:
            parts.append(f"{grey} undetermined")
        out.append(
            " and ".join(parts).capitalize(),
            style="req.violated" if bad else "req.undetermined",
        )
        out.append(
            f", {good} satisfied. This run cannot be delivered as it stands.", style="h.value"
        )
    else:
        out.append(
            f"All {good} requirements are satisfied on the evidence collected.",
            style="req.satisfied",
        )
    return out


def _deliver(run: Run) -> Text:
    res = run.result
    if run.status is not RunStatus.delivered:
        if run.status in {RunStatus.failed, RunStatus.aborted, RunStatus.rejected}:
            return Text(
                f"Nothing delivered: the run {run.status.value}"
                + (f" — {clip(run.stop_reason, 90)}" if run.stop_reason else "."),
                style="attn.dead",
            )
        return Text("Nothing is delivered yet; the run has not reached a verdict.", style="h.meta")
    out = Text()
    out.append(f"Delivered: {res.summary or 'the change is ready to integrate'}.", "req.satisfied")
    out.append(
        f" Patch at {res.patch_ref}, branch {res.branch}. Nothing is merged — that is your call.",
        style="h.value",
    )
    if res.integration is not None:
        ok = res.integration.contains_commit and res.integration.files_identical
        out.append(
            f" Integration into {res.integration.target_ref}: "
            + ("confirmed." if ok else "not confirmed."),
            style="req.satisfied" if ok else "req.violated",
        )
    return out


def _integration(run: Run) -> Text:
    g = run.result.integration
    if g is None:
        if run.status is not RunStatus.delivered:
            return Text("Nothing to recognise yet: no version has been delivered.", style="h.meta")
        return Text(
            "Not checked yet. Merge the branch or apply the patch, then have 495 look at the "
            "ref you merged into.",
            style="attn.you",
        )
    when = g.checked_at.astimezone().strftime("%Y-%m-%d %H:%M")
    out = Text()
    if g.contains_commit and g.files_identical:
        out.append(
            f"{g.target_ref} at {short(g.target_commit)} carries the verified commit and the "
            "same files.",
            style="req.satisfied",
        )
    elif g.files_identical:
        out.append(
            f"{g.target_ref} does not contain the delivered commit, but every changed file is "
            "identical to the verified one — the change landed by another route.",
            style="h.value",
        )
    elif run.integration_state() == "unmerged":
        out.append(
            f"{g.target_ref} has not been merged into: it is still {short(g.target_commit)}, the "
            "commit the run started from. Merge the branch or apply the patch, then ask again.",
            style="attn.you",
        )
    else:
        out.append(
            f"What is in {g.target_ref} is not what was verified: {clip(g.detail, 120)}",
            style="req.violated",
        )
    if g.verifications_rerun:
        out.append(
            " The checks were re-run there and "
            + ("all pass." if g.verifications_passed else "some fail."),
            style="req.satisfied" if g.verifications_passed else "req.violated",
        )
    out.append(f" Checked {when}.", style="h.meta")
    return out


HEADLINES: dict[str, Callable[[Run], Text]] = {
    "profile": _profile,
    "spec": _spec,
    "change": _change,
    "checks": _checks,
    "review": _review,
    "verdict": _verdict,
    "deliver": _deliver,
    "integration": _integration,
}

__all__ = ["HEADLINES", "headline"]
