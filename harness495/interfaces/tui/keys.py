"""Single keypresses, stdlib only.

A full-screen surface that blocks on ``input()`` cannot redraw while it waits, so the clock,
the pulse and anything the engine writes to the store all freeze between keys. Reading one key
at a time with a timeout is what lets the loop do both.
"""

from __future__ import annotations

import contextlib
import os
import select
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, TextIO

with contextlib.suppress(ImportError):  # Windows has no termios; the reader stays inert there.
    import termios
    import tty

ESCAPES = {
    "[A": "up",
    "[B": "down",
    "[C": "right",
    "[D": "left",
    "[5~": "pageup",
    "[6~": "pagedown",
    "[H": "home",
    "[F": "end",
    "[Z": "shifttab",
    "OA": "up",
    "OB": "down",
    "OC": "right",
    "OD": "left",
}
CONTROL = {"\r": "enter", "\n": "enter", "\t": "tab", "\x7f": "backspace", "\x1b": "escape"}


@dataclass(frozen=True)
class Binding:
    """One shortcut. ``scope`` is the view it belongs to, or ``global``."""

    key: str
    action: str
    label: str
    scope: str = "global"
    hidden: bool = False


class KeyReader:
    """Reads one key at a time without blocking the render loop.

    Used as a context manager: it puts the terminal in raw mode on entry and restores the
    previous settings on exit, including when the block raises, so a crash never leaves the
    user with a terminal that no longer echoes.
    """

    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdin
        # Whatever ``termios.tcgetattr`` returned: a list of modes whose last element is
        # itself a list. It is handed straight back to ``tcsetattr`` and never inspected.
        self._saved: list[Any] | None = None

    @property
    def interactive(self) -> bool:
        try:
            return bool(self.stream.isatty()) and "termios" in globals()
        except (ValueError, AttributeError):
            return False

    def __enter__(self) -> KeyReader:
        if self.interactive:
            fd = self.stream.fileno()
            self._saved = termios.tcgetattr(fd)
            tty.setcbreak(fd)
        return self

    def __exit__(self, *exc: object) -> None:
        self.restore()

    def restore(self) -> None:
        if self._saved is not None:
            termios.tcsetattr(self.stream.fileno(), termios.TCSADRAIN, self._saved)
            self._saved = None

    @contextlib.contextmanager
    def released(self) -> Iterator[None]:
        """Hand the terminal back for a prompt or a pager, then take it again."""
        saved, self._saved = self._saved, None
        if saved is not None:
            termios.tcsetattr(self.stream.fileno(), termios.TCSADRAIN, saved)
        try:
            yield
        finally:
            if saved is not None:
                fd = self.stream.fileno()
                self._saved = termios.tcgetattr(fd)
                tty.setcbreak(fd)

    def poll(self, timeout: float = 0.2) -> str | None:
        """The next key, or ``None`` if none arrived before ``timeout``.

        Escape sequences are read as a unit: an arrow key is three bytes, and returning them
        one by one would have the app act on a bare ``escape`` every time.
        """
        if not self.interactive:
            return None
        fd = self.stream.fileno()
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            return None
        first = os.read(fd, 1).decode(errors="ignore")
        if first != "\x1b":
            return CONTROL.get(first, first)
        rest = ""
        while select.select([fd], [], [], 0.02)[0] and len(rest) < 8:
            rest += os.read(fd, 1).decode(errors="ignore")
            if rest in ESCAPES:
                return ESCAPES[rest]
        return ESCAPES.get(rest, "escape")
