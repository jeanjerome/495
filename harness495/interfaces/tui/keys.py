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

BURST = 4096
"""Bytes taken from the terminal in one read. A pasted paragraph arrives in one."""


def take_key(data: bytes) -> tuple[str | None, bytes]:
    """The first key in ``data``, and what is left behind it.

    One key at a time, whatever the bytes look like: an escape sequence is consumed whole so a
    pressed arrow is never acted on as a bare ``escape``; a character outside ASCII is decoded
    from all of its bytes rather than one of them, which is the difference between typing
    ``é`` and typing nothing; and a byte that cannot start a character is dropped rather than
    held, so a stray one cannot stop the keyboard.

    ``None`` means the bytes held no whole key — the tail of a character the terminal has not
    finished sending — and they are kept for the next read.
    """
    if not data:
        return None, b""
    if data[:1] == b"\x1b":
        for sequence, name in ESCAPES.items():
            if data[1:].startswith(sequence.encode()):
                return name, data[1 + len(sequence) :]
        return "escape", data[1:]
    lead = data[0]
    if lead < 0x20 or lead == 0x7F:
        control = data[:1].decode()
        return CONTROL.get(control, control), data[1:]
    if lead < 0x80:
        return data[:1].decode(), data[1:]
    size = 2 if lead < 0xE0 else 3 if lead < 0xF0 else 4
    if lead < 0xC2 or lead > 0xF4:
        return None, data[1:]  # not the start of a character at all
    if len(data) < size:
        return None, data  # the rest of it has not arrived yet
    try:
        return data[:size].decode(), data[size:]
    except UnicodeDecodeError:
        return None, data[1:]


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
        self._pending = b""

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

        What arrives is a burst, not a keystroke: a pasted line is hundreds of bytes in one
        read, a character outside ASCII is two to four, an arrow key is three. So everything
        available is taken at once and handed out one key at a time, and the caller polls with
        no timeout until it runs dry — which is what lets a paste land in one frame instead of
        at ten characters a second, and what keeps two keys pressed together from becoming one
        key that matches nothing.
        """
        if not self.interactive:
            return None
        fd = self.stream.fileno()
        if not self._pending:
            if not select.select([fd], [], [], timeout)[0]:
                return None
            self._pending = os.read(fd, BURST)
            if self._pending == b"\x1b" and select.select([fd], [], [], 0.02)[0]:
                # A terminal may send an escape sequence in pieces. One more look, brief
                # enough not to be felt, is what tells a pressed escape from an arrow key.
                self._pending += os.read(fd, BURST)
        key, self._pending = take_key(self._pending)
        return key
