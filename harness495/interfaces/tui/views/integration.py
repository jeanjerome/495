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
from harness495.interfaces.tui.asking import Answers, Question, Step
from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.views.base import StageContent, ViewContext
from harness495.interfaces.tui.widgets import (
    Choice,
    commands,
    field_pairs,
    panel,
    plural,
    short,
)

RERUN = (
    Choice(
        "no",
        "compare only",
        "the commit and the content of the files it changed are looked for in the ref",
    ),
    Choice(
        "yes",
        "run the checks there too",
        "the verification commands are run again on the ref, which takes as long as they do",
    ),
)


MERGE = (
    # Not the ``no``/``yes`` the other question uses: both answers here make the merge, and a
    # grid whose first key reads "no" under "merge it into main?" says the opposite of what
    # taking it does.
    Choice(
        "merge",
        "merge it, then compare",
        "the merge commit is made, and the commit and the file contents are looked for in it",
    ),
    Choice(
        "verify",
        "merge it, then run the checks too",
        "the same, and the verification commands are run again on the merged tree",
    ),
)


def merge_question(branch: str, into: str, head: str) -> Question:
    """Whether to merge the delivered branch into the tree you have checked out.

    The one question on this surface whose answer writes to the repository you work in, so the
    lead states the three facts you would otherwise have to go and check — what is merged,
    where it lands, and that the tree is clean enough for it — and both answers are the same
    merge. Leaving is ``escape``, on the panel with the rest.
    """

    def step(answers: Answers) -> Step | None:
        if "how" not in answers:
            return Step("how", f"merge {branch} into {into}?", options=MERGE)
        return None

    return Question(
        title="merge what was delivered",
        glyph=ICON["integration"],
        next=step,
        lead=Text.assemble(
            ("495 runs ", "h.value"),
            (f"git merge --no-ff {branch}", "h.ref"),
            (f" on {into}, which is clean and does not carry ", "h.value"),
            (short(head, 12), "h.ref"),
            (
                " yet. A merge that does not go through cleanly is aborted, and nothing changes.",
                "h.value",
            ),
        ),
    )


def integration_question(head: str) -> Question:
    """Which ref you merged into, and whether the checks are run again on it."""

    def step(answers: Answers) -> Step | None:
        if "ref" not in answers:
            return Step("ref", "which ref did you integrate into?", default="HEAD")
        if "rerun" not in answers:
            return Step("rerun", "and on that ref", options=RERUN)
        return None

    return Question(
        title="check what you merged",
        glyph=ICON["integration"],
        next=step,
        lead=Text(
            f"495 looks for {short(head, 12)} — and for the exact content of the files it "
            "changed — in the ref you name.",
            style="h.value",
        ),
    )


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

    state = run.integration_state()
    if res.integration is not None:
        blocks.append(_integration_panel(res.integration, state))

    blocks.append(
        panel(
            Group(
                Text(
                    "The check asks three things of the ref you name: does it contain the "
                    "delivered commit, are the changed files identical to the verified ones, "
                    "and — if you ask for it — do the verification commands still pass there. "
                    "495 can make the merge it then inspects, into the branch you have checked "
                    "out; everything else it does happens in a worktree of its own.",
                    style="h.value",
                ),
                Text(),
                *(
                    [
                        Text.assemble(
                            (" m ", "cursor"),
                            (
                                f"  merge {res.branch} into the branch you have checked out, "
                                "then check the result",
                                "attn.hint",
                            ),
                        ),
                        Text(),
                    ]
                    if ctx.can_drive and res.branch and state != "landed"
                    else []
                ),
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
                    (f"495 merge {run.id}", "the same merge, from any shell"),
                    (
                        f"495 check-integration {run.id} --ref main --rerun",
                        "the same check, from any shell",
                    ),
                ),
            ),
            ICON["integration"],
            "check what you merged",
            # Still the live frame after a ref that turned out to be unmerged: the thing
            # this panel offers has not been done yet, and asking about it did not do it.
            tone="live" if state in ("unchecked", "unmerged") else "quiet",
        )
    )
    return StageContent(Group(*blocks))


def _integration_panel(g: IntegrationCheck, state: str) -> Panel:
    """What the ref turned out to hold.

    A ref nobody merged into gets two lines rather than the breakdown: "contains: not the
    delivered commit, files: differ from the candidate" is true of it and says the wrong
    thing — the files do not differ, they were never brought over, and a blob pair per file is
    five lines of evidence for an event that did not happen.
    """
    rows: list[tuple[str, Text]] = [
        ("target", Text(f"{g.target_ref} at {short(g.target_commit, 12)}", style="h.ref"))
    ]
    if state == "unmerged":
        rows.append(
            (
                "merged",
                Text(
                    "nothing of this run — the ref is still the commit it started from",
                    style="attn.you",
                ),
            )
        )
    else:
        rows += [
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
        ]
    if state != "unmerged" or g.verifications_rerun:
        rows.append(
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
            )
        )
        rows.append(("detail", Text(g.detail or "—", style="h.meta")))
    return panel(
        field_pairs(rows, width=13),
        ICON["integration"],
        "integration check",
        g.checked_at.astimezone().strftime("%Y-%m-%d %H:%M"),
        tone="ask"
        if state == "unmerged"
        else ("good" if state == "landed" and g.verifications_passed is not False else "bad"),
    )
