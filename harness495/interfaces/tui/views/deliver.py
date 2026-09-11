"""7 · deliver — what you got, and the commands that act on it."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from harness495.core.models import IntegrationCheck, RunStatus
from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.stages import STAGE_INDEX, STAGES, stage_of
from harness495.interfaces.tui.theme import VERDICT_STYLE
from harness495.interfaces.tui.views.base import StageContent, ViewContext
from harness495.interfaces.tui.widgets import commands, field_pairs, panel, short


def build_deliver(ctx: ViewContext) -> StageContent:
    run = ctx.run
    res = run.result
    it = run.current_iteration
    v = it.version if it else None
    project = run.project_root

    if run.status is not RunStatus.delivered:
        remaining = [s.name for s in STAGES if STAGE_INDEX[s.name] >= STAGE_INDEX[stage_of(run)]][
            :-1
        ]
        body: list[RenderableType] = [
            Text(
                "495 delivers a patch, a branch and a report — and merges nothing. None of it "
                "exists yet for this run.",
                style="h.value",
            ),
            Text(),
        ]
        if run.status in {RunStatus.failed, RunStatus.aborted, RunStatus.rejected}:
            body += [
                Text(f"The run {run.status.value}.", style="attn.dead"),
                Text(run.stop_reason or res.summary or "", style="h.value"),
                Text(),
                Text("what is kept anyway", style="h.key"),
                commands(
                    (f"495 report {run.id}", "the Markdown report of everything observed"),
                    (f"495 export {run.id}", "archive the whole run directory"),
                    (f"495 cleanup {run.id}", "remove the worktree; the evidence stays"),
                ),
            ]
        else:
            body += [
                Text("still to happen", style="h.key"),
                *[Text(f"  ○ {name}", style="tab.name.todo") for name in remaining],
            ]
        for w in run.warnings:
            body += [Text(), Text(f"⚠ {w}", style="gauge.warn")]
        return StageContent(Group(*body))

    artefacts = field_pairs(
        [
            (
                "outcome",
                Text(
                    res.outcome.value if res.outcome else "—",
                    style=VERDICT_STYLE.get(res.outcome, "h.value") if res.outcome else "h.value",
                ),
            ),
            ("summary", Text(res.summary or "—", style="h.value")),
            ("branch", Text(res.branch or "—", style="h.ref")),
            ("commit", Text(res.head_commit or "—", style="h.ref")),
            ("patch", Text(res.patch_ref or "—", style="h.ref")),
            ("sha256", Text(v.patch_sha256 if v and v.patch_sha256 else "—", style="h.meta")),
            ("report", Text(res.report_ref or "—", style="h.ref")),
            ("worktree", Text(run.worktree or "—", style="h.meta")),
        ],
        width=10,
    )
    acts = commands(
        (f"git -C {project} merge --no-ff {res.branch}", "take the branch as it is"),
        (f"git -C {project} am {res.patch_ref}", "or replay the patch on your own base"),
        (f"495 report {run.id} --format md", "read what was observed, requirement by requirement"),
        (
            f"495 check-integration {run.id} --ref main --rerun",
            "confirm it landed, and re-run the checks there",
        ),
        (f"495 cleanup {run.id}", "drop the worktree once you are done"),
    )
    body = [
        panel(
            Group(
                Text("nothing has been merged; that is your call", style="attn.done"),
                Text(),
                acts,
            ),
            ICON["deliver"],
            "what to do with it",
            tone="good",
        ),
        panel(artefacts, ICON["artefacts"], "what the run produced"),
    ]
    if res.integration is not None:
        body.append(_integration_panel(res.integration))
    return StageContent(Group(*body))


def _integration_panel(g: IntegrationCheck) -> Panel:
    ok = g.contains_commit and g.files_identical
    return panel(
        field_pairs(
            [
                ("target", Text(f"{g.target_ref} at {short(g.target_commit, 12)}", style="h.ref")),
                (
                    "contains",
                    Text(
                        "the delivered commit"
                        if g.contains_commit
                        else "not the delivered commit",
                        style="req.satisfied" if g.contains_commit else "req.violated",
                    ),
                ),
                (
                    "files",
                    Text(
                        "identical to the candidate"
                        if g.files_identical
                        else "differ from the candidate",
                        style="req.satisfied" if g.files_identical else "req.violated",
                    ),
                ),
                (
                    "checks there",
                    Text(
                        "not re-run"
                        if not g.verifications_rerun
                        else ("all pass" if g.verifications_passed else "some fail"),
                        style="h.meta"
                        if not g.verifications_rerun
                        else ("req.satisfied" if g.verifications_passed else "req.violated"),
                    ),
                ),
                ("detail", Text(g.detail or "—", style="h.meta")),
            ],
            width=13,
        ),
        ICON["integration"],
        "integration check",
        g.checked_at.astimezone().strftime("%Y-%m-%d %H:%M"),
        tone="good" if ok else "bad",
    )
