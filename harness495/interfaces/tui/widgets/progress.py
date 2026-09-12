"""Bars and marks, for wholes that are known and for work whose end is not.

Progress is determinate only where a whole is actually known — checks out of six, spend
against a ceiling. An agent intervention gets a pulsing bar, because no agent CLI reports a
completion fraction, and a bar claiming 60% would be inventing one.

Where there is no room for a bar there is still room for one cell that turns, which says the
same thing: the tab strip spends exactly one column on the state of each stop.
"""

from __future__ import annotations

import time

from rich.console import RenderableType
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.spinner import Spinner
from rich.text import Text

TURNING = "dots2"
"""Which Rich spinner a single cell turns with.

Braille, because every frame of it is one cell wide and carries the same amount of ink: it
turns without changing the weight of the line it sits in, and it lands in the column a static
glyph would have taken. Spinners whose frames are two or three cells wide — or whose ink comes
and goes — would make the strip breathe in and out around whichever stop is working.
"""


class WorkingBar:
    """A pulsing bar for work whose end is not known.

    Rich pulses a ``BarColumn`` whenever the task total is ``None``, and that is the honest
    rendering for an agent intervention: there is no percentage to show — but there is
    certainly something happening, and a frozen band says otherwise.

    Kept across frames on purpose. The pulse gradient is driven by the global monotonic clock
    and would animate either way, but ``SpinnerColumn`` measures from its own ``Spinner``'s
    construction time: rebuilt every frame it freezes on the first glyph.
    """

    def __init__(self, style: str = "attn.work", note: bool = False) -> None:
        columns: list[TextColumn | SpinnerColumn | BarColumn] = [
            SpinnerColumn(style=style),
            BarColumn(bar_width=None, pulse_style=style),
        ]
        if note:
            columns.append(TextColumn("[h.value]{task.fields[note]}"))
        self.progress = Progress(*columns, expand=True)
        self.task = self.progress.add_task("", total=None, note="")

    def renderable(self, note: str = "") -> RenderableType:
        self.progress.update(self.task, note=note)
        return self.progress.get_renderable()


_PULSES: dict[str, WorkingBar] = {}


def pulse(name: str, *, note: bool = False) -> WorkingBar:
    """A named pulsing bar that outlives the frame that drew it.

    A spinner rebuilt every frame freezes on its first glyph, so the object has to persist —
    and a view built as a pure function of a run has nowhere to keep one. Naming them here
    gives every caller the same bar without threading one through eight builders.
    """
    bar = _PULSES.get(name)
    if bar is None:
        bar = _PULSES[name] = WorkingBar(note=note)
    return bar


class WorkingMark:
    """One cell that turns, for a line with room for exactly one.

    The band can afford a bar; a tab cannot — it holds a glyph, a name and a count in a box
    that shares the width of the screen with seven others. So the same fact is said in the
    column the tab already spends on its state: the mark for "the run is here" turns while
    something is advancing it, and stands still when nothing is.

    Kept across frames for the reason a :class:`WorkingBar` is: a ``Spinner`` measures from
    its own construction time, so one rebuilt every frame never leaves its first glyph.
    """

    def __init__(self, kind: str = TURNING) -> None:
        self.spinner = Spinner(kind)

    def glyph(self, at: float | None = None) -> str:
        """The frame it is on at ``at``, or right now — one cell, off the monotonic clock.

        Off the clock rather than off a frame counter, so two surfaces refreshing at different
        rates draw the same frame at the same instant, and a redraw the keyboard asked for
        does not advance the animation by a frame it has not earned.
        """
        frame = self.spinner.render(time.monotonic() if at is None else at)
        # A spinner carrying no text of its own renders as the frame alone, which this one
        # always does: it is a single cell inside a line someone else is composing.
        return frame.plain if isinstance(frame, Text) else ""


_MARKS: dict[str, WorkingMark] = {}


def spin(name: str) -> WorkingMark:
    """A named turning mark that outlives the frame that drew it, like :func:`pulse`."""
    mark = _MARKS.get(name)
    if mark is None:
        mark = _MARKS[name] = WorkingMark()
    return mark
