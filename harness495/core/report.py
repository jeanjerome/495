"""Human-readable restitution of a run (Markdown) built from the persisted state only."""

from __future__ import annotations

from typing import TYPE_CHECKING

from harness495.core.models import (
    NON_DISCRIMINATING,
    EvidenceKind,
    RequirementStatus,
    Run,
    Sufficiency,
    Verdict,
    Verification,
)

if TYPE_CHECKING:
    from harness495.core.store import RunStore

STATUS_ICON = {
    RequirementStatus.satisfied: "PASS",
    RequirementStatus.violated: "FAIL",
    RequirementStatus.undetermined: "UNDETERMINED",
    RequirementStatus.pending: "PENDING",
}


def _cost(run: Run) -> str:
    c = run.consumption
    if c.cost_basis.value == "unknown" and c.cost_usd == 0:
        return "unknown"
    label = f"{c.cost_usd:.4f} USD ({c.cost_basis.value})"
    if c.cost_unknown_interventions:
        label += f", {c.cost_unknown_interventions} intervention(s) without pricing"
    return label


def _observed(run: Run, ver: Verification) -> str:
    """What the verification reported on the evaluated commit, read as the decision reads it.

    Only a command result of the current iteration says anything about the change: a control
    run on the base version and a baseline run carry the same verification id and are left
    out, as ``decide.assess`` leaves them out. A verification that reports the same with and
    without the change is stated as such, since its result is neither proof nor defect, and so
    is one that reported something else when it was run a second time on this same commit:
    what it reported first was withdrawn from the decision, and the row says so rather than
    showing it as the check's result.
    """
    if ver.sufficiency in NON_DISCRIMINATING:
        return (
            "reports the same with and without the change: "
            f"{ver.rationale or 'does not observe the change'}"
        )
    it = run.current_iteration
    unstable = [
        e
        for e in (run.evidence_by_id(x) for x in (it.evidence_ids if it else []))
        if e
        and e.kind is EvidenceKind.stability_check
        and e.passed is False
        and e.verification_id == ver.id
    ]
    if unstable:
        return f"withdrawn ({unstable[-1].id}): {_cell(unstable[-1].summary)}"
    results = [
        e
        for e in (run.evidence_by_id(x) for x in (it.evidence_ids if it else []))
        if e and e.kind is EvidenceKind.command_result and e.verification_id == ver.id
    ]
    if not results:
        return "not run on the evaluated commit"
    last = results[-1]
    if last.passed is True:
        unconfirmed = (
            f"; unconfirmed: {_cell(ver.rationale)}"
            if ver.sufficiency is Sufficiency.unconfirmed
            else ""
        )
        return f"PASS on the evaluated commit ({last.id}){unconfirmed}"
    if last.passed is False:
        return f"FAIL on the evaluated commit ({last.id}): {_cell(last.summary)}"
    return f"no result on the evaluated commit ({last.id}): {_cell(last.summary)}"


def _scenario_sections(run: Run) -> list[str]:
    """One section per requirement that leans on a verification stated as a scenario.

    The scenario is the text the requester approved (0016); under the requirement it verifies,
    next to what its command reported, the reader checks the behaviour asked for against the
    behaviour observed without opening the specification or the evidence. A requirement none
    of whose verifications carries a scenario has no section: its table row says all there is.
    """
    lines: list[str] = []
    for r in run.spec.requirements:
        carried = [
            v for v in (run.spec.verification(x) for x in r.verification_ids) if v and v.scenario
        ]
        if not carried:
            continue
        lines += [f"### {r.id} {STATUS_ICON[r.status]}: {_cell(r.statement)}", ""]
        for v in carried:
            assert v.scenario is not None
            flag = ", to create" if v.to_create else ""
            role = f" / {v.role.value}" if v.role else ""
            lines += [
                f"{v.id} ({v.kind.value}{role}{flag}): {_observed(run, v)}",
                "",
                "```gherkin",
                f"Scenario: {v.description.strip()}",
                *(f"  {step}" for step in v.scenario.lines()),
                "```",
                "",
            ]
    return lines


def _clarification_section(run: Run) -> list[str]:
    """The decisions the specification was written under, and who took each.

    What the requester chose and what the harness took on their behalf are not the same record,
    so the table says which; a question nobody was asked is listed apart, because an assumption
    standing on it is not a decision.
    """
    clarification = run.clarification
    if not clarification.rounds:
        return []
    lines = ["## Decisions taken before the specification", ""]
    if clarification.answers:
        lines += [
            "| round | question | decided | by |",
            "|---|---|---|---|",
        ]
        for round_ in clarification.rounds:
            for answer in round_.answers:
                chosen = answer.label or answer.option
                if answer.note:
                    chosen += f" — {answer.note}"
                if answer.recommended:
                    chosen += " (the clarifier's recommendation)"
                lines.append(
                    f"| {round_.n} | {_cell(answer.question)} | {_cell(chosen)} | "
                    f"{answer.taken_by.value} |"
                )
        lines.append("")
    else:
        lines += ["The clarifier returned no question: nothing was left to decide.", ""]
    if clarification.open_questions:
        lines += [
            "Left unanswered when the clarification reached its round cap; what the "
            "specification does about them is an assumption, not a decision:",
            "",
        ]
        lines += [f"- {_cell(q.title)}" for q in clarification.open_questions]
        lines.append("")
    dropped = [d for r in clarification.rounds for d in r.dropped]
    if dropped:
        lines += ["Questions the harness did not put to you:", ""]
        lines += [f"- {_cell(d)}" for d in dropped]
        lines.append("")
    return lines


def render_markdown(run: Run, store: RunStore | None = None) -> str:
    lines: list[str] = []
    outcome = run.result.outcome.value if run.result.outcome else run.status.value
    lines += [
        f"# 495 run {run.id}",
        "",
        f"- **Outcome**: {outcome}",
        f"- **Status**: {run.status.value}",
        f"- **Mode**: {run.mode.value}",
        f"- **Project**: {run.project_root}",
        f"- **Created**: {run.created_at.isoformat()}",
        f"- **Updated**: {run.updated_at.isoformat()}",
        f"- **Interventions**: {run.consumption.interventions}",
        f"- **Tokens**: {run.consumption.usage.total_tokens} (in {run.consumption.usage.input_tokens}, out {run.consumption.usage.output_tokens}, cache read {run.consumption.usage.cache_read_tokens})",
        f"- **Cost**: {_cost(run)}",
        "",
        "## Intent",
        "",
        run.intent.text.strip(),
        "",
    ]
    if run.result.summary:
        lines += ["## Summary", "", run.result.summary, ""]
    lines += _clarification_section(run)
    it = run.current_iteration
    if it and it.version:
        v = it.version
        lines += [
            "## Version evaluated",
            "",
            f"- base commit: `{v.base_commit}`",
            f"- head commit: `{v.head_commit}`",
            f"- branch: `{v.branch}`",
            f"- patch: `{v.patch_ref or 'none'}` (sha256 `{v.patch_sha256}`)",
            f"- files changed: {len(v.files_changed)}",
        ]
        lines += [f"  - `{f}`" for f in v.files_changed[:100]]
        design = run.test_design
        if design is not None and design.files:
            lines.append(
                f"- tests written by the test designer before the producer, committed as "
                f"`{design.commit}` (intervention {design.intervention_id}), protected from the "
                f"change: {len(design.files)}"
            )
            lines += [f"  - `{f}`" for f in design.files[:100]]
        lines.append("")
    lines += [
        "## Requirements",
        "",
        "| id | status | statement | verifications | reason |",
        "|---|---|---|---|---|",
    ]
    for r in run.spec.requirements:
        lines.append(
            f"| {r.id} | {STATUS_ICON[r.status]} | {_cell(r.statement)} | {', '.join(r.verification_ids)} | {_cell(r.status_reason)} |"
        )
    lines.append("")
    lines += _scenario_sections(run)
    if run.spec.verifications:
        lines += [
            "## Verifications",
            "",
            "| id | kind | sufficiency | command | description |",
            "|---|---|---|---|---|",
        ]
        for ver in run.spec.verifications:
            cmd = _cell("`" + ver.command + "`") if ver.command else ""
            flag = " (to create)" if ver.to_create else ""
            role = f" / {ver.role.value}" if ver.role else ""
            lines.append(
                f"| {ver.id} | {ver.kind.value}{role}{flag} | {ver.sufficiency.value} | {cmd} | "
                f"{_cell(ver.description)} |"
            )
        lines.append("")
    if run.spec.gaps:
        lines += ["### Verification gaps", ""] + [f"- {g}" for g in run.spec.gaps] + [""]
    if run.iterations:
        lines += ["## Iterations", ""]
        for iteration in run.iterations:
            head = iteration.version.head_commit if iteration.version else "n/a"
            lines.append(
                f"### Iteration {iteration.n}: {iteration.outcome.value if iteration.outcome else 'in progress'} (head `{head}`)"
            )
            lines.append("")
            evidence = [e for e in (run.evidence_by_id(x) for x in iteration.evidence_ids) if e]
            if evidence:
                lines += [
                    "| evidence | kind | target | result | summary |",
                    "|---|---|---|---|---|",
                ]
                for e in evidence:
                    result = {True: "PASS", False: "FAIL", None: "n/a"}[e.passed]
                    lines.append(
                        f"| {e.id} | {e.kind.value} | {e.verification_id or ''} | {result} | {_cell(e.summary)} |"
                    )
                lines.append("")
            reviews = [r for r in run.reviews if r.intervention_id in iteration.review_ids]
            for rv in reviews:
                tag = " (discarded: " + rv.discard_reason + ")" if rv.discarded else ""
                lines.append(f"- **{rv.perspective}**: {rv.verdict.value}{tag}. {rv.summary}")
                for f in rv.findings:
                    where = f" `{f.file}:{f.line}`" if f.file else ""
                    req = (
                        f" [{f.requirement_id or f.verification_id}]"
                        if (f.requirement_id or f.verification_id)
                        else ""
                    )
                    lines.append(f"  - {f.severity.value}{req}: {f.title}{where}. {f.detail}")
                    if f.evidence:
                        lines.append(f"    - evidence: {f.evidence}")
            if iteration.instrument_faults:
                lines += ["", "Verifications that do not observe the change:"] + [
                    f"- {f}" for f in iteration.instrument_faults
                ]
            if iteration.blocked_claims:
                lines += [
                    "",
                    "Reported by the producer as not done (its own claim, unverified):",
                ] + [f"- {c}" for c in iteration.blocked_claims]
            if iteration.correction_requests:
                lines += ["", "Correction requests:"] + [
                    f"- {c}" for c in iteration.correction_requests
                ]
            lines.append("")
    if run.interventions:
        lines += [
            "## Interventions",
            "",
            "| id | it. | role | agent | model | status | duration | tokens | context | cost | isolation | activity |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for i in run.interventions:
            util = i.usage.context_utilization
            ctx = (
                "n/a"
                if util is None
                else f"{util:.0%}{'≤' if i.usage.context_peak_is_upper_bound else ''}"
            )
            cost = "unknown" if i.cost.usd is None else f"{i.cost.usd:.4f} ({i.cost.basis.value})"
            role = i.role.value + (f" ({i.perspective})" if i.perspective else "")
            activity = ", ".join(f"{k} {v}" for k, v in i.activity.items()) or "-"
            lines.append(
                f"| {i.id} | {i.iteration} | {role} | {i.agent.kind.value} | {i.agent.model or 'default'} | {i.status.value} | {i.duration_s or 0:.0f}s | {i.usage.total_tokens} | {ctx} | {cost} | {i.sandbox.backend} | {activity} |"
            )
        lines.append("")
    if run.decisions:
        lines += [
            "## Decisions",
            "",
            "| id | kind | by | outcome | rationale |",
            "|---|---|---|---|---|",
        ]
        for d in run.decisions:
            lines.append(
                f"| {d.id} | {d.kind.value} | {d.made_by.value} | {d.outcome} | {_cell(d.rationale)} |"
            )
        lines.append("")
    if run.result.integration:
        ic = run.result.integration
        lines += [
            "## Integration check",
            "",
            f"- target: `{ic.target_ref}` (`{ic.target_commit}`)",
            f"- outcome: {run.integration_state()}",
            f"- contains evaluated commit: {ic.contains_commit}",
            f"- touched files identical: {ic.files_identical}",
            f"- verifications re-run: {ic.verifications_rerun}"
            + (f" (passed: {ic.verifications_passed})" if ic.verifications_rerun else ""),
            f"- detail: {ic.detail}",
            "",
        ]
    if run.warnings:
        lines += ["## Warnings", ""] + [f"- {w}" for w in run.warnings] + [""]
    if (
        run.status.value == "delivered"
        and it
        and it.version
        and run.result.outcome is Verdict.accept
    ):
        lines += [
            "## Next step: integration (left to you)",
            "",
            "The change is on a branch of your repository; nothing has been merged. For example:",
            "",
            "```bash",
            f"git merge --no-ff {it.version.branch}",
            "```",
            "",
            "or apply the patch, then let 495 verify the integrated result:",
            "",
            "```bash",
            f"495 check-integration {run.id} --ref HEAD --rerun",
            "```",
            "",
        ]
    return "\n".join(lines)


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()
