"""Bars, for wholes that are known and for work whose end is not.

Progress is determinate only where a whole is actually known — checks out of six, spend
against a ceiling. An agent intervention gets a pulsing bar, because no agent CLI reports a
completion fraction, and a bar claiming 60% would be inventing one.
"""

from __future__ import annotations

from rich.console import RenderableType
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn


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
