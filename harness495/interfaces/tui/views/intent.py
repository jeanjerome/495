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
from rich.text import Text

from harness495.interfaces.tui.asking import Answers, Question, Step, ask_in_prompt
from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.widgets import Choice

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


LEAD = Text(
    "A run opens on what the change must accomplish — not on how to do it. 495 turns that into "
    "requirements, each tied to something that checks it, and nothing is produced until you "
    "have approved them.",
    style="h.value",
)
"""What the question is for. The example belongs in the field itself, where the answer goes."""


def intent_question() -> Question:
    """What must be true afterwards, who writes it, and a ref only where one is needed."""

    def step(answers: Answers) -> Step | None:
        if "intent" not in answers:
            return Step(
                "intent",
                "what must be true once this run is done?",
                hint="the deploy command refuses to run on a dirty working tree",
                required=True,
            )
        if "who" not in answers:
            return Step("who", "who writes the change", options=WHO)
        if answers["who"] == "produce":
            return None
        if "which" not in answers:
            return Step("which", "which change", options=WHICH)
        if answers["which"] == "worktree":
            return None
        if "ref" not in answers:
            return Step("ref", "commit or range", default="HEAD")
        return None

    return Question(title="a new run", glyph=ICON["question"], next=step, lead=LEAD)


def intent_taken(answers: Answers) -> tuple[str, str]:
    """The intent, and the change to evaluate — empty when 495 is to produce it."""
    if answers.get("who") == "produce":
        return answers["intent"], ""
    if answers.get("which") == "worktree":
        return answers["intent"], "WORKTREE"
    return answers["intent"], answers.get("ref") or "WORKTREE"


def ask_intent(console: Console) -> tuple[str, str] | None:
    """The same question where there is no surface to draw it on."""
    console.print(LEAD)
    answers = ask_in_prompt(console, intent_question())
    return None if answers is None else intent_taken(answers)
