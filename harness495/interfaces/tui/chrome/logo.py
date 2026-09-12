"""The 495 mark with a satin highlight, rendered with Rich.

A soft cyan highlight with a narrow white core crosses the unchanged mark
from left to right for 1.8 seconds, followed by 8.2 seconds at rest. The mark
always occupies exactly 11 columns and two rows; no glyph is replaced, so
nothing in the header moves but the colour.

Frames are pure functions of elapsed time. LogoMark can be rebuilt on every
redraw without restarting the animation. By default, instances share the
module's monotonic time origin. Pass a shared ``started_at`` value to start
the animation with a particular screen instead.

The existing h.logo theme style remains the resting style. A blue-grey
fallback is used if the theme does not define it. Non-terminal output and
LogoMark(animated=False) are static: one frame of a sweep, captured on its
own, reads as a colour picked at random, where the mark at rest reads as the
mark.
"""

from __future__ import annotations

import math
import time

from rich.console import Console, ConsoleOptions, RenderResult
from rich.style import Style
from rich.text import Text

Digit = tuple[str, str]
RGB = tuple[int, int, int]

DIGITS: tuple[Digit, ...] = (
    ("█ █", "▀▀█"),  # 4
    ("█▀█", "▀▀█"),  # 9
    ("█▀▀", "▀▀█"),  # 5
)

WIDTH = sum(len(d[0]) for d in DIGITS) + len(DIGITS) - 1

BASE_RGB: RGB = (145, 163, 178)
CYAN_RGB: RGB = (106, 217, 241)
WHITE_RGB: RGB = (236, 248, 255)
DEFAULT_STYLE = Style(color="#91a3b2")

SWEEP_DURATION = 1.8
INITIAL_PAUSE = 1.0
FINAL_PAUSE = 8.2
CYCLE = INITIAL_PAUSE + SWEEP_DURATION + FINAL_PAUSE
# The two pauses meet across the cycle boundary: 9.2 s of rest between sweeps.

HALO_WIDTH = 1.25
CORE_WIDTH = 0.55
EDGE_FADE = 0.12
LIGHT_FLOOR = 0.04
"""How much light a column needs before it is painted at all.

Below it the mix lands within a few units of the resting colour — invisible as light, and not
free: a painted column is an explicit ``#rrggbb``, while the resting style is whatever the
theme says, which a terminal may well draw brighter than any resolution of it. Painting all
eleven columns therefore dimmed the whole mark for the length of the pass. Columns the light
has not reached are left alone instead, so the mark away from the highlight is not merely the
same colour, it is the same style."""
STARTED_AT = time.monotonic()


def _smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def _mix(start: RGB, end: RGB, amount: float) -> RGB:
    red, green, blue = (round(a + (b - a) * amount) for a, b in zip(start, end, strict=True))
    return red, green, blue


def frame(elapsed: float, base_rgb: RGB = BASE_RGB) -> tuple[Style | None, ...] | None:
    """One overlay per column — ``None`` where the light has not reached — or ``None`` at rest.

    A frame is colour and nothing else: the digits are never redrawn, and both
    character rows take the same column colours, so the highlight crosses the
    mark as one vertical band rather than as two rows sliding on their own.
    """
    t = elapsed % CYCLE - INITIAL_PAUSE
    if t < 0.0 or t >= SWEEP_DURATION:
        return None

    progress = _smoothstep(t / SWEEP_DURATION)
    center = -3.0 + (WIDTH + 6.0) * progress
    envelope = _smoothstep(t / EDGE_FADE) * _smoothstep((SWEEP_DURATION - t) / EDGE_FADE)
    styles: list[Style | None] = []
    for column in range(WIDTH):
        distance = column + 0.5 - center
        halo = math.exp(-0.5 * (distance / HALO_WIDTH) ** 2) * envelope
        if halo < LIGHT_FLOOR:
            styles.append(None)
            continue
        core = math.exp(-0.5 * (distance / CORE_WIDTH) ** 2) * envelope * 0.8
        colour = _mix(_mix(base_rgb, CYAN_RGB, halo), WHITE_RGB, core)
        styles.append(Style(color="#{:02x}{:02x}{:02x}".format(*colour)))
    return tuple(styles)


def render(
    digits: tuple[Digit, ...],
    active: int | None = None,
    active_style: str = "h.logo",
    *,
    column_styles: tuple[Style | None, ...] | None = None,
    base_style: str | Style = "h.logo",
) -> Text:
    """The two rows of the mark, as one ``Text`` with a newline between them.

    Left-aligned, never justified: the header puts the mark in a fixed column
    beside the run id, and a centred mark would drift by a cell whenever the
    column did. ``column_styles`` paints the sweep over the glyphs, leaving the
    holes in the digits and the columns the light has not reached in the
    resting style; ``active`` draws one whole digit in another style, which is
    a still emphasis rather than a moving one.
    """
    out = Text(no_wrap=True)
    for row in range(2):
        column = 0
        for index, digit in enumerate(digits):
            style = active_style if index == active else base_style
            for character in digit[row]:
                start = len(out)
                out.append(character, style=style)
                lit = column_styles[column] if column_styles is not None else None
                if lit is not None and character != " ":
                    out.stylize(lit, start, start + 1)
                column += 1
            if index < len(digits) - 1:
                out.append(" ")
                column += 1
        if row == 0:
            out.append("\n")
    return out


def still(*, base_style: str | Style = "h.logo") -> Text:
    """The unchanged mark for print, export or a disabled animation."""
    return render(DIGITS, base_style=base_style)


class LogoMark:
    """A clock-driven renderable; no mutable frame counter or internal timer."""

    def __init__(self, animated: bool = True, *, started_at: float = STARTED_AT) -> None:
        self.animated = animated
        self.started_at = started_at

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        base_style = console.get_style("h.logo", default=DEFAULT_STYLE)
        if (
            not self.animated
            or not console.is_terminal
            or console.is_dumb_terminal
            or console.no_color
        ):
            yield still(base_style=base_style)
            return

        color = base_style.color
        if color is None or color.is_default:
            # Resolve a terminal-default foreground to an explicit resting
            # colour so the sweep can interpolate and return without a jump.
            base_style = base_style + DEFAULT_STYLE
            base_rgb = BASE_RGB
        else:
            red, green, blue = color.get_truecolor()
            base_rgb = (red, green, blue)

        styles = frame(time.monotonic() - self.started_at, base_rgb)
        yield render(DIGITS, column_styles=styles, base_style=base_style)
