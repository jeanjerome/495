"""Commands and captured output, rendered as what they are rather than as prose."""

from __future__ import annotations

from rich import box
from rich.console import RenderableType
from rich.panel import Panel
from rich.syntax import Syntax


def shell_block(command: str) -> Syntax:
    return Syntax(command, "bash", theme="ansi_dark", background_color="default", word_wrap=True)


def log_block(text: str) -> RenderableType:
    return Panel(
        Syntax(
            text.rstrip(),
            "console",
            theme="ansi_dark",
            background_color="default",
            word_wrap=True,
        ),
        box=box.MINIMAL,
        border_style="frame.quiet",
        padding=(0, 1),
    )
