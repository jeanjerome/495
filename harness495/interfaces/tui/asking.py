"""A question answered on the surface itself, one step at a time.

Rich draws; it does not read. Its prompt is ``input()`` underneath, which wants the terminal
in cooked mode and writes exactly where the live region is about to paint — so a question had
to take the screen down, print itself into the scrollback and put the surface back afterwards.
For the length of the answer the run was gone: the clock stopped, the pulse stopped, the
decision panel that had just stated the question was replaced by the same question in plain
text, and anything another process wrote to the store arrived unseen.

Nothing here asks Rich to read. The surface already owns the keyboard — it polls raw keys to
stay alive between them — so a question is one more thing on screen, and the run keeps moving
behind it.

A question is a sequence of steps that the answers decide: what the change must accomplish,
then who writes it, then a ref only on the branch that needs one. :attr:`Question.next` is a
pure function of what has been answered so far, and everything else follows from that: going
back is dropping the last answer and asking the same function again, and the keyless path
walks the identical steps with a prompt, so the two ways of asking cannot drift.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from rich import box
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from harness495.interfaces.tui.theme import PAD
from harness495.interfaces.tui.widgets import Choice, choices, title_text

Answers = dict[str, str]


@dataclass(frozen=True)
class Step:
    """One thing asked at a time: a line to type, or one answer to take.

    ``options`` is what makes the difference. With them the step is picked from a grid — the
    same grid every question 495 asks uses, so an answer always comes with what taking it
    does. Without them it is a line of text.
    """

    name: str
    question: str
    options: tuple[Choice, ...] = ()
    default: str = ""
    hint: str = ""
    required: bool = False
    """An empty line is refused rather than taken. A note that says nothing is not a record."""

    @property
    def picking(self) -> bool:
        return bool(self.options)


@dataclass(frozen=True)
class Question:
    """What the surface asks, and what it asks next given what it has been told."""

    title: str
    glyph: str
    next: Callable[[Answers], Step | None]
    lead: RenderableType | None = None
    """What the question rests on, shown above the step: the facts behind a decision, the
    sentence that says what an intent is for."""


class LineEditor:
    """One line of text with a caret. Everything a question needs and nothing else.

    Not readline: there is no history to walk, no completion to offer and no second line to
    scroll to, so what is left is the handful of moves a person actually makes in a one-line
    field — type, rub out, jump to either end, throw the line or the last word away.
    """

    WORD_BREAK = " /.-_:"

    def __init__(self, text: str = "") -> None:
        self.text = text
        self.caret = len(text)

    def key(self, key: str) -> None:
        if key == "backspace":
            if self.caret:
                self.text = self.text[: self.caret - 1] + self.text[self.caret :]
                self.caret -= 1
        elif key == "left":
            self.caret = max(0, self.caret - 1)
        elif key == "right":
            self.caret = min(len(self.text), self.caret + 1)
        elif key == "home":
            self.caret = 0
        elif key == "end":
            self.caret = len(self.text)
        elif key == "\x15":  # ctrl-u
            self.text, self.caret = self.text[self.caret :], 0
        elif key == "\x17":  # ctrl-w
            cut = self.text[: self.caret].rstrip(self.WORD_BREAK)
            cut = cut[: max((cut.rfind(c) for c in self.WORD_BREAK), default=-1) + 1]
            self.text, self.caret = cut + self.text[self.caret :], len(cut)
        elif key.isprintable():
            # A whole burst at once: a pasted line arrives as one read, and inserting it a
            # character per frame would drip it onto the screen over several seconds.
            self.text = self.text[: self.caret] + key + self.text[self.caret :]
            self.caret += len(key)

    def render(self, hint: str = "") -> Text:
        """The line, with the caret standing on the character it is before."""
        if not self.text and hint:
            out = Text(no_wrap=True, overflow="ellipsis")
            out.append(" ", style="cursor")
            out.append(f" {hint}", style="attn.hint")
            return out
        out = Text(no_wrap=True, overflow="ellipsis")
        out.append(self.text[: self.caret], style="h.title")
        out.append(self.text[self.caret : self.caret + 1] or " ", style="cursor")
        out.append(self.text[self.caret + 1 :], style="h.title")
        return out


@dataclass
class Ask:
    """A question being answered right now: where it is, what it has, and what it refused.

    ``commit`` is what the answers are for — creating the run, recording the decision, running
    the integration check. It is called by the loop rather than from a keystroke, so a failure
    lands on the surface's notice line like any other refusal.
    """

    question: Question
    commit: Callable[[Answers], None]
    answers: Answers = field(default_factory=dict)
    state: Literal["asking", "done", "cancelled"] = "asking"
    notice: str = ""
    step: Step | None = None
    editor: LineEditor = field(default_factory=LineEditor)
    cursor: int = 0
    trail: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._enter(self.question.next(self.answers))

    def _enter(self, step: Step | None, previous: str = "") -> None:
        self.step, self.notice = step, ""
        if step is None:
            self.state = "done"
            return
        self.editor = LineEditor(previous or "")
        keys = [o.key for o in step.options]
        self.cursor = keys.index(previous) if previous in keys else 0

    def key(self, key: str) -> None:
        """One keystroke. Everything that is not a move or a decision is text."""
        step = self.step
        if step is None:
            return
        if key == "escape":
            self._back()
        elif step.picking:
            self._picking(step, key)
        elif key == "enter":
            self._take(step, self.editor.text.strip() or step.default)
        else:
            self.notice = ""
            self.editor.key(key)

    def _picking(self, step: Step, key: str) -> None:
        if key in ("up", "k"):
            self.cursor = (self.cursor - 1) % len(step.options)
        elif key in ("down", "j", "tab"):
            self.cursor = (self.cursor + 1) % len(step.options)
        elif key == "enter":
            self._take(step, step.options[self.cursor].key)

    def _take(self, step: Step, value: str) -> None:
        if not value and step.required:
            self.notice = f"{step.name} cannot be empty"
            return
        self.answers[step.name] = value
        self.trail.append(step.name)
        self._enter(self.question.next(self.answers))

    def _back(self) -> None:
        """Escape undoes the last answer, or leaves the question if there is none.

        The steps are a function of the answers, so taking one back is dropping it: what to
        ask next is worked out again rather than remembered, and a branch of the question that
        an answer opened closes with it.
        """
        if not self.trail:
            self.state = "cancelled"
            return
        previous = self.answers.pop(self.trail.pop())
        self._enter(self.question.next(self.answers), previous)

    # ---- what the surface draws and offers

    def controls(self) -> list[tuple[str, str]]:
        step = self.step
        if step is None:
            return []
        moves = [("↑↓", "move"), ("enter", "take it")] if step.picking else [("enter", "accept")]
        return [*moves, ("esc", "go back" if self.trail else "cancel")]

    def panel(self, width: int) -> Panel:
        step = self.step
        body: list[RenderableType] = []
        if self.question.lead is not None:
            body += [self.question.lead, Text()]
        if step is not None:
            body.append(Text(step.question, style="h.title"))
            body.append(Text())
            if step.picking:
                body.append(choices(step.options, width, cursor=self.cursor))
            else:
                body.append(self.editor.render(step.hint or step.default))
            if self.notice:
                body += [Text(), Text(f"✕  {self.notice}", style="attn.dead")]
            body += [Text(), _keys_line(self.controls())]
        return Panel(
            Group(*body),
            title=title_text(self.question.glyph, self.question.title),
            title_align="left",
            box=box.HEAVY,
            border_style="frame.ask",
            padding=PAD,
        )


def _keys_line(keys: list[tuple[str, str]]) -> Text:
    out = Text()
    for key, label in keys:
        out.append(f" {key} ", style="cursor")
        out.append(f"  {label}   ", style="attn.hint")
    return out


def ask_in_prompt(console: Console, question: Question) -> Answers | None:
    """The same steps, asked where there is no terminal to draw them on.

    One question, two renderings, and the steps are the question: a prompted session takes the
    same branches and returns the same answers, which is the only way the two can stay the
    same question. Where the surface has ``escape``, this has the empty answer: nothing typed
    into something that must be answered leaves the question rather than asking it again.
    """
    answers: Answers = {}
    while (step := question.next(answers)) is not None:
        if step.picking:
            console.print(choices(step.options, console.width))
            value = Prompt.ask(
                step.question,
                choices=[o.key for o in step.options],
                default=step.options[0].key,
                console=console,
                show_choices=False,
            )
        else:
            typed = Prompt.ask(
                step.question,
                default=step.default,
                console=console,
                show_default=bool(step.default),
            )
            value = typed.strip()
            if not value and step.required:
                return None
        answers[step.name] = value
    return answers


__all__ = [
    "Answers",
    "Ask",
    "LineEditor",
    "Question",
    "Step",
    "ask_in_prompt",
]
