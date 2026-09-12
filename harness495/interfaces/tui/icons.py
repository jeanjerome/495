"""What *kind* of thing a panel is — and nothing else.

An emoji answers one question: what kind of thing is this. It never says where the run is,
whether something passed, or how close a ceiling is. Those are states, and a state has to take
the colour of its meaning and fit a one-column cell — neither of which an emoji can do, since
it carries its own colours and two cells of width. So the geometric marks stay exactly where
they are: ● ◉ ○ ◆ ✕ on the pipeline and the ledger, ✓ ✕ ◐ on the checks, ▸ for the cursor,
█ ░ ▇ for the gauges, and the box characters for every frame.

The attention band is the one surface that names a state here, and it is the exception that
proves the rule: a state is its whole subject, it is announced on a title rather than in a
measured cell, and the hue that says how bad it is lives on the frame around it. The emoji
there only has to be recognised — ❓ ✋ ❌ ✅ 💤 — while the colour keeps coming from the
theme. Working is the one state with no emoji: it is drawn with the mark that turns, because
that is the same fact the pipeline strip turns on, and a still picture of work is a
contradiction.

What they replace is the grab-bag that accumulates in panel titles — ``$`` for budget, ``!``
for findings, ``⊞`` for scope — symbols picked one at a time, each of which has to be decoded
from its own panel rather than recognised on sight. One pair earns its place twice over: 📋 is
always the list and 🔍 is always the detail beside it, so the master-detail relationship is
legible before a word is read.

Every code here is an emoji that is *already* two cells wide. That rules out the obvious picks
— ⚠ for findings, ⚖ for limits, ⌨ for keys — which are text characters one cell wide dressed
up with a variation selector, and which terminals therefore measure two different ways.
:func:`use_icons` refuses them outright rather than letting one back in.
"""

from __future__ import annotations

import os

from rich.cells import cell_len
from rich.emoji import Emoji

#: name: (the Rich shortcode, the mark it replaces)
ICON_SET: dict[str, tuple[str, str]] = {
    # One per stop, keyed by the stage's own name. The stage panel used to take the run's
    # state glyph for its title — which the strip three lines above was already drawing, in
    # the same colour. Naming the stop instead says the one thing the strip has no room for,
    # and the state is not lost: the panel's border carries it. Where a panel inside the stage
    # already named the same thing, it is the same emoji, so ``deliver`` and ``integration``
    # are not repeated below.
    "profile": ("toolbox", "1"),
    "spec": ("memo", "2"),
    "change": ("hammer", "3"),
    "checks": ("test_tube", "4"),
    "review": ("eyes", "5"),
    "verdict": ("ledger", "6"),
    # The states the band announces. ``delivered`` and ``decided`` share one emoji on purpose:
    # a decision taken and a run delivered are the same kind of fact, something settled.
    "paused": ("raised_hand", "‖"),
    "stopped": ("cross_mark", "✕"),
    "delivered": ("white_check_mark", "●"),
    "idle": ("zzz", "○"),
    "pipeline": ("compass", "◆"),
    "list": ("clipboard", "≣"),
    "detail": ("mag", "⤢"),
    "agent": ("robot", "▶"),
    "budget": ("money_bag", "$"),
    "limits": ("no_entry", "⚖"),
    "findings": ("exclamation", "!"),
    "attempts": ("repeat", "↻"),
    "claims": ("construction", "⚑"),
    "corrections": ("outbox_tray", "↩"),
    "artefacts": ("package", "▤"),
    "deliver": ("rocket", "→"),
    "integration": ("link", "⇲"),
    "project": ("file_folder", "◈"),
    "briefing": ("books", "▤"),
    "scope": ("triangular_ruler", "⊞"),
    "decided": ("white_check_mark", "✓"),
    "question": ("question", "?"),
    # What drives the run, as opposed to what walks you around it. Not the rocket: that one
    # is the delivery stop now, and an emoji that stands for two things stands for neither.
    "controls": ("video_game", "▶"),
    "keys": ("key", "⌨"),
    "legend": ("abc", "◈"),
}

ICON: dict[str, str] = {}

ENV_VAR = "HARNESS495_ICONS"


def use_icons(kind: str = "emoji") -> None:
    """Fill :data:`ICON`, either with emoji or with the marks they replace.

    Every icon has to be two cells wide *natively* — that is, its codepoint must already carry
    emoji presentation. ⚠ ⚖ ⌨ ↪ 🏷 do not: they are text characters one cell wide, and reaching
    two takes a variation selector (U+FE0F). Rich then counts two and a terminal that ignores
    the selector draws one, so those titles alone come out a column short while every other
    panel is square — which is what it looks like when two lines out of twenty are off.

    Padding them with an extra space would only move the defect: it would line those two up in
    a terminal that renders them narrow, and break them in one that renders them wide. The
    disagreement is what has to go, so a shortcode that needs the selector is refused here
    rather than quietly patched.
    """
    for name, (code, mark) in ICON_SET.items():
        if kind == "ascii":
            ICON[name] = mark
            continue
        glyph = str(Emoji(code))
        if cell_len(glyph) != 2:
            raise ValueError(
                f"icon {name!r}: :{code}: is {cell_len(glyph)} cell(s) wide without a variation "
                "selector, so terminals will disagree about it — pick an emoji that is already "
                "two cells"
            )
        ICON[name] = glyph


use_icons(os.environ.get(ENV_VAR, "emoji"))
