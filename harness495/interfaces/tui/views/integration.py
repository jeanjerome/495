"""8 · integration — whether what you merged is what was verified.

The one stop the harness cannot walk on its own. 495 delivers a patch and a branch and merges
nothing; until you have integrated it there is nothing to compare, and once you have, the
comparison is the only thing that ties the evidence to the tree people will actually work on.
So this stop opens on where it stands — whether anything carries the change, and what is left
for you to do about it — and the panels under that are the evidence for the answer and the
controls that change it.
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
        "a cherry-pick, so linear, under new hashes, and the delivered branch is left alone",
    ),
    "squash": Choice(
        "squash",
        "one commit on top",
        "linear, and everything the run changed arrives as a single commit of its own",
    ),
    "merge": Choice(
        "merge",
        "a merge commit",
        "not linear, and it keeps the verified commit itself rather than a copy",
    ),
}
"""What one act can look like in a history, in the order the history stays flattest.

Four rather than one because the shape of the history is a matter of taste that the harness
has no business settling, and it is settled for good once the commit is written. ``rebase``
and ``squash`` copy the change rather than move it, which the check that follows reads as
delivered-commit-absent, every-file-identical — the same thing it reads off a hand-made
cherry-pick, and why that was never treated as a failure.

``rebase`` names the shape of the result, not the command: it is run as a cherry-pick, because
the delivered branch is checked out in the run's own worktree and git refuses to move a branch
that is checked out elsewhere — and moving it is what a rebase would do, taking the verified
commit out of reach of the very name the check looks it up by."""

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


def _stands(ctx: ViewContext, state: str) -> Panel:
    """Where this stop stands, and what — if anything — is left for you to do about it.

    Always the first block, and always the same two things in the same order, because the
    question a reader arrives with is always the same one: is my change in, and is there
    anything left for me. Four states answer it, and the fourth answers "no". A screen that
    says so only through the colour of a border, or only in a row of a breakdown further down,
    is a screen that has to be decoded before it can be read.
    """
    run = ctx.run
    res = run.result
    g = res.integration
    branch = res.branch or "the delivered branch"
    lines: list[Text] = []
    # Landed with the checks failing there is the one state the four words do not separate:
    # the right files arrived and something around them does not hold, which is a finding
    # rather than a conclusion.
    faulted = state == "landed" and g is not None and g.verifications_passed is False
    tone = "bad" if faulted else {"landed": "good", "differs": "bad"}.get(state, "ask")

    if state == "landed" and g is not None:
        how = f" as a {res.integrated_as}" if res.integrated_as else ""
        lines.append(
            Text.assemble(
                (g.target_ref, "h.ref"),
                (f" carries the verified change{how}.", "req.satisfied"),
            )
        )
        if faulted:
            lines += [
                Text(),
                Text(
                    "The files are the ones that were verified, but the checks do not pass "
                    "there — something around the change, not the change itself.",
                    style="req.violated",
                ),
            ]
        else:
            lines += [
                Text(),
                Text("Nothing is left to do here.", style="attn.done"),
                Text(
                    f"{branch} and its worktree are still on disk, and nothing has been pushed.",
                    style="h.meta",
                ),
            ]
        if ctx.can_drive:
            # Not work still owed — the line above just said there is none. A question you may
            # want to ask again later, named as one, so that a key on a finished stop reads as
            # something available rather than something outstanding.
            lines += [
                Text(),
                Text.assemble(
                    (" i ", "cursor"),
                    (
                        "  asks again later — after other commits, whether the change is "
                        "still there",
                        "attn.hint",
                    ),
                ),
            ]
    elif state == "differs" and g is not None:
        lines += [
            Text.assemble(
                ("What is in ", "req.violated"),
                (g.target_ref, "h.ref"),
                (" is not what was verified.", "req.violated"),
            ),
            Text(),
            Text(
                "This is the one thing this stop exists to catch. Read what differs below, "
                f"then integrate {branch} again, or name the ref you actually merged into.",
                style="h.value",
            ),
        ]
        if ctx.can_drive:
            lines += [
                Text(),
                Text.assemble(
                    (" m ", "cursor"),
                    (f"  integrates {branch} and checks the result", "attn.hint"),
                ),
                Text.assemble((" i ", "cursor"), ("  checks another ref instead", "attn.hint")),
            ]
    else:
        if state == "unmerged" and g is not None:
            lines.append(
                Text.assemble(
                    ("Nothing has been merged. ", "attn.you"),
                    (g.target_ref, "h.ref"),
                    (
                        f" is still {short(g.target_commit, 12)}, the commit the run started from.",
                        "attn.you",
                    ),
                )
            )
        else:
            lines.append(
                Text(
                    "Nothing has been merged. Your working tree is exactly as you left it.",
                    style="attn.you",
                )
            )
        lines.append(Text())
        if ctx.can_drive and res.branch:
            lines.append(
                Text.assemble(
                    (" m ", "cursor"),
                    (
                        f"  is the next move: it brings {branch} into the branch you have "
                        "checked out, and checks the result.",
                        "attn.hint",
                    ),
                )
            )
        else:
            lines.append(
                Text(
                    f"Merging {branch} is yours to make; 495 never does it unasked.",
                    style="h.value",
                )
            )
        lines.append(
            Text.assemble(
                (" i ", "cursor"),
                ("  is for a merge you made yourself: it checks the ref you name.", "attn.hint"),
            )
            if ctx.can_drive
            else Text(
                "Once you have merged it yourself, the check below looks at the ref you name.",
                style="h.value",
            )
        )
    return panel(
        Group(*lines),
        ICON["integration"],
        "where this stands",
        tone=tone,
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

    state = run.integration_state()
    landed = state == "landed"
    blocks.append(_stands(ctx, state))

    # What will be looked for, while that is still ahead. Once something has been found, the
    # breakdown below holds the same three facts as answers, and a panel stating the question
    # above its answer is a panel the reader has to walk past twice.
    if not landed and v is not None and v.head_commit:
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
        blocks.append(_integration_panel(res.integration, state, res.integrated_as))

    # What the check is, and how to reach it from outside. The keys are named once, on the
    # panel that says what is left to do; naming them here as well was the same invitation
    # printed twice, three lines apart, which reads as two different things to do.
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
                commands(
                    *(
                        ()
                        if landed
                        else (
                            (
                                f"495 merge {run.id} --how squash",
                                "the same, from any shell; also fast-forward, rebase, merge",
                            ),
                        )
                    ),
                    (
                        f"495 check-integration {run.id} --ref main --rerun",
                        "the same check, from any shell",
                    ),
                ),
            ),
            ICON["integration"],
            "what the check asks",
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
                        f"a copy of it — the {how} replayed it under a new hash"
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
