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


WAYS = {
    "fast-forward": Choice(
        "fast-forward",
        "move your branch onto it",
        "nothing is added at all: your branch becomes the verified commit itself",
    ),
    "rebase": Choice(
        "rebase",
        "replay its commits on top",
        "linear, and the commits arrive under new hashes, so the verified one is not in it",
    ),
    "squash": Choice(
        "squash",
        "one commit on top",
        "linear, and everything the run changed arrives as a single commit of its own",
    ),
    "merge": Choice(
        "merge",
        "a merge commit",
        "not linear, and the only one that keeps the verified commit itself as an ancestor",
    ),
}
"""What one act can look like in a history, in the order the history stays flattest.

Four rather than one because the shape of the history is a matter of taste that the harness
has no business settling, and it is settled for good once the commit is written. The three
linear ones copy the change rather than move it, which the check that follows reads as
delivered-commit-absent, every-file-identical — the same thing it reads off a hand-made
cherry-pick, and why that was never treated as a failure."""

AFTER = (
    Choice(
        "no",
        "compare only",
        "the commit and the content of the files it changed are looked for in the result",
    ),
    Choice(
        "yes",
        "run the checks there too",
        "the verification commands are run again on the result, which takes as long as they do",
    ),
)


def merge_question(branch: str, into: str, head: str, ways: tuple[str, ...]) -> Question:
    """How to bring the delivered branch into the tree you have checked out, and what then.

    The one question on this surface whose answer writes to the repository you work in, so the
    lead states the facts you would otherwise have to go and check — what is integrated, where
    it lands, and that the tree is clean enough for it. ``ways`` is what this repository can
    actually do right now: a branch that has moved cannot be fast-forwarded onto, and an
    answer that would refuse itself is not offered. Leaving is ``escape``, on the panel.
    """

    def step(answers: Answers) -> Step | None:
        if "how" not in answers:
            return Step(
                "how",
                f"how should {branch} go into {into}?",
                options=tuple(WAYS[w] for w in ways),
            )
        if "checks" not in answers:
            return Step("checks", "and on the result", options=AFTER)
        return None

    return Question(
        title="integrate what was delivered",
        glyph=ICON["integration"],
        next=step,
        lead=Text.assemble(
            (f"{into} is clean and does not carry ", "h.value"),
            (short(head, 12), "h.ref"),
            (
                " yet. Whichever way you pick, an attempt that does not go through cleanly puts "
                "the branch back where it was and nothing is written.",
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
        blocks.append(_integration_panel(res.integration, state, res.integrated_as))

    blocks.append(
        panel(
            Group(
                Text(
                    "The check asks three things of the ref you name: does it contain the "
                    "delivered commit, are the changed files identical to the verified ones, "
                    "and — if you ask for it — do the verification commands still pass there. "
                    "495 can make the integration it then inspects, into the branch you have "
                    "checked out; everything else it does happens in a worktree of its own.",
                    style="h.value",
                ),
                Text(),
                *(
                    [
                        Text.assemble(
                            (" m ", "cursor"),
                            (
                                f"  bring {res.branch} into the branch you have checked out — "
                                "fast-forward, rebase, squash or merge — then check the result",
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
                    (
                        f"495 merge {run.id} --how squash",
                        "the same, from any shell; also fast-forward, rebase, merge",
                    ),
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


def _integration_panel(g: IntegrationCheck, state: str, how: str | None) -> Panel:
    """What the ref turned out to hold.

    A ref nobody merged into gets two lines rather than the breakdown: "contains: not the
    delivered commit, files: differ from the candidate" is true of it and says the wrong
    thing — the files do not differ, they were never brought over, and a blob pair per file is
    five lines of evidence for an event that did not happen.
    """
    rows: list[tuple[str, Text]] = [
        ("target", Text(f"{g.target_ref} at {short(g.target_commit, 12)}", style="h.ref"))
    ]
    if how:
        rows.append(("integrated", Text(f"by 495, as a {how}", style="h.value")))
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
                # A copy is the point of a rebase and a squash, not a shortfall of one: the
                # row says what was asked for rather than reporting its own instruction back
                # as a failure.
                Text(
                    "the delivered commit"
                    if g.contains_commit
                    else (
                        f"a copy of it, from the {how}"
                        if how in ("rebase", "squash")
                        else "not the delivered commit"
                    ),
                    style="req.satisfied"
                    if g.contains_commit or how in ("rebase", "squash")
                    else "req.violated",
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
