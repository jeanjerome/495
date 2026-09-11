"""The 495 run surface: the interface *is* the workflow.

Seven stops, in the order the engine walks them, named in the run's own vocabulary. A stop is
both "where the run is" and "the tab that shows what that stage produced", so there is no menu
to learn: you look for a fact at the stage that produced it.

Three things carry the design:

1.  **The navigation bar is the pipeline.** Each stop is a framed tab carrying its own key and
    its own count, so the strip is also a dashboard: you can see from it that checks are 4/6
    and that the review raised a blocker, without opening either. Colour says where the *run*
    is; a heavy frame says where *you* are.
2.  **One line always says what the run needs from you.** Working, waiting on you, or
    finished — on every view, with the key that answers it.
3.  **Every stage has the same shape: headline, list, detail.** The headline is one sentence
    stating what the stage concluded; the detail follows the cursor rather than replacing the
    list, so arrowing down a list of checks reads their outputs in place.

Two rules hold the surface together, and both are enforced in one place rather than by
discipline at four hundred call sites. **Colour**: six hues carry six meanings — it holds, it
is contradicted, it cannot say, it is happening now, it needs a human, it is not there — and
every style in :mod:`~harness495.interfaces.tui.theme` is built from one of them. **Frames**:
:func:`~harness495.interfaces.tui.widgets.panels.panel` takes the *reason* a border is loud
rather than a colour, so a stray blue cannot come back.

The package is laid out the way the screen is:

  ``theme`` ``icons``           the vocabulary: six hues, and what kind of thing a panel is
  ``reading`` ``stages``        what a view reads off a run, and the seven stops it walks
  ``headlines`` ``attention``   one sentence per stage, and the line that says what is needed
  ``widgets/``                  gauges, panels, tables — the parts every view is built from
  ``chrome/``                   identity and the animated mark, the band, the strip, the keys
  ``views/``                    one builder per stop, plus the log, the listing and the help
  ``keys`` ``shell`` ``loops``  input, state, and the two ways the shell is driven
  ``source`` ``logs`` ``app``   where runs come from, and the entry point over a store
"""

from harness495.interfaces.tui.app import build_console, watch
from harness495.interfaces.tui.shell import Shell
from harness495.interfaces.tui.source import StaticSource, StoreSource
from harness495.interfaces.tui.theme import THEME

__all__ = ["THEME", "Shell", "StaticSource", "StoreSource", "build_console", "watch"]
