"""Human-readable restitution of a run (Markdown) built from the persisted state only."""

from __future__ import annotations

from typing import TYPE_CHECKING

from harness495.core.models import RequirementStatus, Run, Verdict

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
            lines.append(
                f"| {ver.id} | {ver.kind.value}{flag} | {ver.sufficiency.value} | {cmd} | "
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
                    req = f" [{f.requirement_id}]" if f.requirement_id else ""
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
