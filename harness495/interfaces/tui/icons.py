"""What *kind* of thing a panel is — and nothing else.

An emoji answers one question: what kind of thing is this panel. It never says where the run
is, whether something passed, or how close a ceiling is. Those are states, and a state has to
take the colour of its meaning and fit a one-column cell — neither of which an emoji can do,
since it carries its own colours and two cells of width. So the geometric marks stay exactly
where they are: ● ◉ ○ ◆ ✕ on the pipeline and the ledger, ✓ ✕ ◐ on the checks, ▸ for the
cursor, █ ░ ▇ for the gauges, and the box characters for every frame.

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
