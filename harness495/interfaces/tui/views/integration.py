"""8 · integration — whether what you merged is what was verified.

The one stop the harness cannot walk on its own. 495 delivers a patch and a branch and merges
nothing; until you have integrated it there is nothing to compare, and once you have, the
comparison is the only thing that ties the evidence to the tree people will actually work on.
So this stop is mostly a control: it names what will be compared, and ``i`` runs it.
"""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from harness495.core.models import IntegrationCheck, RunStatus
from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.views.base import StageContent, ViewContext
from harness495.interfaces.tui.widgets import commands, field_pairs, panel, plural, short


def build_integration(ctx: ViewContext) -> StageContent:
    run = ctx.run
    res = run.result
    it = run.current_iteration
    v = it.version if it else None
    blocks: list[RenderableType] = []

    if res.integration is None and run.status is not RunStatus.delivered:
        return StageContent(
            Group(
                Text(
                    "Nothing to check: the run has not delivered a version, so there is no "
                    "tree to recognise in yours.",
                    style="h.meta",
                ),
                Text(),
                Text(
                    "495 stops at the patch and the branch. Integrating them is your call, and "
                    "this stop is how you find out afterwards that what landed is what was "
                    "verified.",
                    style="h.value",
                ),
            )
        )

    if v is not None and v.head_commit:
        n = len(v.files_changed)
        blocks.append(
            panel(
                field_pairs(
                    [
                        ("verified", Text(short(v.head_commit, 12), style="h.ref")),
                        ("on branch", Text(res.branch or v.branch or "—", style="h.ref")),
                        (
                            "files",
                            Text(
                                f"{n} {plural(n, 'file')} whose content must be found again, "
                                "byte for byte",
                                style="h.value",
                            ),
                        ),
                    ],
                    width=10,
                ),
                ICON["artefacts"],
                "what is being looked for",
            )
        )

    if res.integration is not None:
        blocks.append(_integration_panel(res.integration))

    blocks.append(
        panel(
            Group(
                Text(
                    "The check asks three things of the ref you name: does it contain the "
                    "delivered commit, are the changed files identical to the verified ones, "
                    "and — if you ask for it — do the verification commands still pass there.",
                    style="h.value",
                ),
                Text(),
                *(
                    [
                        Text.assemble(
                            (" i ", "cursor"),
                            (
                                "  check a ref now; it asks which one, and whether to re-run "
                                "the checks",
                                "attn.hint",
                            ),
                        ),
                        Text(),
                    ]
                    if ctx.can_drive
                    else []
                ),
                commands(
                    (
                        f"495 check-integration {run.id} --ref main --rerun",
                        "the same check, from any shell",
                    )
                ),
            ),
            ICON["integration"],
            "check what you merged",
            tone="live" if res.integration is None else "quiet",
        )
    )
    return StageContent(Group(*blocks))


def _integration_panel(g: IntegrationCheck) -> Panel:
    ok = g.contains_commit and g.files_identical
    return panel(
        field_pairs(
            [
                ("target", Text(f"{g.target_ref} at {short(g.target_commit, 12)}", style="h.ref")),
                (
                    "contains",
                    Text(
                        "the delivered commit" if g.contains_commit else "not the delivered commit",
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
