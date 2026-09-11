"""Turning numbers and long strings into something a fixed-width cell can hold."""

from __future__ import annotations


def clip(text: object, limit: int = 120) -> str:
    """One line, at most ``limit`` cells, with an ellipsis where the rest went."""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def short(commit: str | None, n: int = 8) -> str:
    return commit[:n] if commit else "—"


def hms(seconds: float) -> str:
    s = int(seconds)
    if s >= 3600:
        return f"{s // 3600}h{(s % 3600) // 60:02d}m"
    return f"{s // 60}m{s % 60:02d}s"


def plural(n: int, one: str, many: str | None = None) -> str:
    return one if n == 1 else (many or one + "s")
