"""The question that opens a run: what must be true afterwards, and who writes the change.

Every other question 495 asks names its answers and says what taking each one does — that is
what a decision panel is. The first question of all has no reason to be the exception, and it
was: it asked for "an existing change to evaluate (commit, <base>..<head>, WORKTREE)" in git
syntax, with an empty string standing for "no, produce it", which is a question you can only
answer if you already know what it is for.

So it is asked in two steps, and the second one only when it changes anything: what the run
must accomplish, then who writes the change. A run that produces its own change — the common
one — never sees a ref at all.
"""

from __future__ import annotations

from rich.console import Console
from rich.prompt import Prompt
from rich.text import Text

from harness495.interfaces.tui.widgets import Choice, choices

WHO = (
    Choice(
        "produce",
        "495 writes it",
        "a producer agent implements the change in an isolated worktree, and the run verifies "
        "and reviews what it wrote",
    ),
    Choice(
        "evaluate",
        "it already exists",
        "no producer runs: the run verifies and reviews a change that is already written",
    ),
)

WHICH = (
    Choice("worktree", "the working tree", "everything uncommitted in the project right now"),
    Choice("commit", "a commit", "one commit against its parent, or a range like main..my-branch"),
)


def ask_intent(console: Console) -> tuple[str, str] | None:
    """The intent, and the change to evaluate — empty when 495 is to produce it.

    ``None`` when the question is declined, which an empty intent says: there is nothing to
    open a run on, and a run with no intent has nothing to specify.
    """
    console.print(
        Text(
            "A run opens on what the change must accomplish — not on how to do it. 495 turns "
            "that into requirements, each tied to something that checks it, and nothing is "
            "produced until you have approved them.",
            style="h.value",
        )
    )
    console.print(
        Text(
            "   e.g.  the deploy command refuses to run on a dirty working tree",
            style="attn.hint",
        )
    )
    intent = Prompt.ask(
        "intent [dim](empty goes back)[/]", console=console, default="", show_default=False
    ).strip()
    if not intent:
        return None

    console.print()
    console.print(choices(WHO, console.width))
    if _pick(console, "who writes the change", WHO) == "produce":
        return intent, ""

    console.print()
    console.print(choices(WHICH, console.width))
    if _pick(console, "which change", WHICH) == "worktree":
        return intent, "WORKTREE"
    return intent, Prompt.ask(
        "commit or range", console=console, default="HEAD"
    ).strip() or "WORKTREE"


def _pick(console: Console, question: str, options: tuple[Choice, ...]) -> str:
    """The first option is the default: pressing enter takes the ordinary path."""
    return Prompt.ask(
        question,
        choices=[o.key for o in options],
        default=options[0].key,
        console=console,
        show_choices=False,
    )
