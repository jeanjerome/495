"""The 495 mark, and the pulse that runs through it.

4, 9 and 5 drawn on a 3x4 pixel grid and folded onto two character rows with half-blocks. The
three digits share a bar at mid-height and a stem going down on the right, which is why their
lower halves come out identical — that is the shape of the numerals, not a shortcut.

The mark is the one thing in the chrome that carries no information, so it is also the only
thing that can afford to move. It dissolves one digit at a time — ▒ ░ · ░ ▒ — and puts it
back, left to right, then rests. That is the whole animation: it says the surface is live
without competing with the attention band, which is the part that actually has something to
say.

A frame is a pure function of the clock, never of how often the screen was redrawn. A Live
that refreshes at four frames a second, one that refreshes at twenty, and a single ``--print``
all read the same phase off ``time.monotonic()``, so the animation never depends on being
driven at a particular rate, and nothing has to hold mutable frame state to draw it.
"""

from __future__ import annotations

import time

from rich.console import Console, ConsoleOptions, RenderResult
from rich.text import Text

Digit = tuple[str, str]

DIGITS: tuple[Digit, ...] = (
    ("█ █", "▀▀█"),  # 4
    ("█▀█", "▀▀█"),  # 9
    ("█▀▀", "▀▀█"),  # 5
)

WIDTH = sum(len(d[0]) for d in DIGITS) + len(DIGITS) - 1
"""Cells the mark occupies. The header gives it up below a width where it costs the intent."""

#: How a digit dissolves and comes back: the character it is drawn with, and its colour.
STAGES: tuple[tuple[str, str], ...] = (
    ("▒", "bright_blue"),
    ("░", "blue"),
    ("·", "dim blue"),
    ("░", "blue"),
    ("▒", "bright_cyan"),
)

FRAME_DELAY = 0.12
"""Seconds one dissolution stage holds. Below ~0.1 the stages blur into a flicker."""
SETTLE = 2 * FRAME_DELAY
"""The beat where a digit is back in its exact shape, in white, before the next one goes."""
INITIAL_PAUSE = 1.0
FINAL_PAUSE = 2.0

PER_DIGIT = len(STAGES) * FRAME_DELAY + SETTLE
CYCLE = INITIAL_PAUSE + len(DIGITS) * PER_DIGIT + FINAL_PAUSE


def morph(digit: Digit, character: str) -> Digit:
    """The same digit drawn with another character, holes kept as holes."""
    top, bottom = (
        "".join(" " if original == " " else character for original in line) for line in digit
    )
    return top, bottom


def frame(elapsed: float) -> tuple[tuple[Digit, ...], int | None, str]:
    """The digits, the one being dissolved, and the style it is drawn in, at ``elapsed``.

    Outside the moving part of the cycle — the two pauses — no digit is active and the mark is
    the plain one, which is what a still capture gets.
    """
    t = elapsed % CYCLE - INITIAL_PAUSE
    if t < 0 or t >= len(DIGITS) * PER_DIGIT:
        return DIGITS, None, "h.logo"
    index = int(t // PER_DIGIT)
    within = t - index * PER_DIGIT
    digits = list(DIGITS)
    step = int(within // FRAME_DELAY)
    if step >= len(STAGES):
        # Restored to its exact shape, held bright for a beat: the digit coming *back* is the
        # readable half of the animation, and at one frame delay it is gone before it reads.
        return tuple(digits), index, "bold white"
    character, colour = STAGES[step]
    digits[index] = morph(DIGITS[index], character)
    return tuple(digits), index, f"bold {colour}"


def render(
    digits: tuple[Digit, ...], active: int | None = None, active_style: str = "h.logo"
) -> Text:
    """The two rows of the mark, as one ``Text`` with a newline between them.

    Left-aligned, never justified: the header puts the mark in a fixed column beside the run
    id, and a centred mark would drift by a cell whenever the column did.
    """
    out = Text(no_wrap=True)
    for row in range(2):
        for index, digit in enumerate(digits):
            out.append(digit[row], style=active_style if index == active else "h.logo")
            if index < len(digits) - 1:
                out.append(" ")
        if row == 0:
            out.append("\n")
    return out


def still() -> Text:
    """The mark at rest. What a print, an export or a non-terminal console gets."""
    return render(DIGITS)


class LogoMark:
    """The mark, animated off the clock.

    Constructed per frame — it holds no state of its own, so there is nothing to keep alive
    between redraws and nothing to reset when the surface is torn down and rebuilt.
    """

    def __init__(self, animated: bool = True) -> None:
        self.animated = animated

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        if not self.animated:
            yield still()
            return
        digits, active, style = frame(time.monotonic())
        yield render(digits, active, style)
