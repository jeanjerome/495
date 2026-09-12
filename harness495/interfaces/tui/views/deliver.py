"""7 · deliver — what you got, and the commands that act on it."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.text import Text

from harness495.core.models import RunStatus
from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.stages import STAGE_INDEX, STAGES, stage_of
from harness495.interfaces.tui.theme import VERDICT_STYLE
from harness495.interfaces.tui.views.base import StageContent, ViewContext
from harness495.interfaces.tui.widgets import commands, field_pairs, panel


def build_deliver(ctx: ViewContext) -> StageContent:
    run = ctx.run
    res = run.result
    it = run.current_iteration
    v = it.version if it else None
    project = run.project_root

    if run.status is not RunStatus.delivered:
        remaining = [
            s.name
            for s in STAGES
            if STAGE_INDEX[stage_of(run)] <= STAGE_INDEX[s.name] < STAGE_INDEX["deliver"]
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
        (f"495 cleanup {run.id}", "drop the worktree once you are done"),
    )
    body = [
        panel(
            Group(
                Text("nothing has been merged; that is your call", style="attn.done"),
                Text(),
                acts,
                Text(),
                Text(
                    "once you have merged it, stop 8 asks whether what landed is what was verified",
                    style="attn.hint",
                ),
            ),
            ICON["deliver"],
            "what to do with it",
            tone="good",
        ),
        panel(artefacts, ICON["artefacts"], "what the run produced"),
    ]
    return StageContent(Group(*body))
