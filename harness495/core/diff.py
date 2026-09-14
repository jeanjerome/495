"""The lines the change adds, and which of them hold code a measure can be made about.

Two checks of the verify phase read the diff line by line: the mutation check writes a wrong
version of one added line at a time (``core/mutation.py``), and the coverage check asks which
added lines the verifications execute (``core/reach.py``). Both need the same reading — the
number a line has in the version under review, and whether that line is code of a technology
the catalogue covers rather than a comment, a blank, or the instrument itself — so the reading
lives here once and neither owns it.

Everything is textual: the diff comes in as git printed it, the lines go out. No language is
parsed, and the filters say so where they are loose.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from harness495.core.verification import looks_like_a_test

SOURCE_SUFFIXES = frozenset(
    {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".scala",
        ".groovy",
        ".rb",
        ".sh",
        ".bash",
        ".zsh",
    }
)
"""Where a line means something to these checks: the languages the catalogue covers. A line of
Markdown, of JSON or of a lock file is altered by no mutation operator and executed by no
coverage engine, and would be reported for reasons that say nothing about the tests."""


@dataclass(frozen=True)
class AddedLine:
    """A line the change adds, at its number in the version under review."""

    file: str
    line: int
    text: str


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_NEW_PATH = re.compile(r"^\+\+\+ (?:b/)?(.+?)\s*$")
_COMMENT = re.compile(r"^\s*(?:#|//|/\*|\*|\"\"\"|''')")


def added_lines(diff: str) -> list[AddedLine]:
    """Every line the diff adds, with the path and line number it has in the new version.

    The hunk header states how many lines the new version holds, and that count is what tells
    a header apart from a line of content that happens to start with ``+``.
    """
    out: list[AddedLine] = []
    path: str | None = None
    number = 0
    remaining = 0
    for line in diff.splitlines():
        if remaining <= 0:
            header = _NEW_PATH.match(line)
            if header:
                found = header.group(1)
                path = None if found == "/dev/null" else found
                continue
            hunk = _HUNK.match(line)
            if hunk:
                number = int(hunk.group(1))
                remaining = int(hunk.group(2) or 1)
            continue
        if line.startswith("+"):
            if path is not None:
                out.append(AddedLine(file=path, line=number, text=line[1:]))
            number += 1
            remaining -= 1
        elif line.startswith("-") or line.startswith("\\"):
            continue
        else:  # a context line, with or without its leading space
            number += 1
            remaining -= 1
    return out


def is_comment(text: str) -> bool:
    """Whether the line opens with a comment marker of one of the catalogue's languages.

    A comment marker further along the line is not read as one: what matters is that the line
    carries no statement of its own, and a line of code with a trailing comment does.
    """
    return bool(_COMMENT.match(text))


def names_the_file(file: str, commands: Sequence[str]) -> bool:
    """Whether one of the test commands names this file, by path or by file name.

    A project whose tests are a script the commands run (``./scripts/check.sh shout``) follows
    no test-naming convention, and ``looks_like_a_test`` reads that script as ordinary source.
    What the harness does know is which file a command that runs the tests names: that file is
    the instrument, whatever it is called. Only the commands of a ``test`` verification are
    read this way — a linter, a build or a type checker names the source it reads, which is
    the very thing these checks are about.

    The name is matched whole: a command running ``tests/test_calc.py`` names that file and
    not ``calc.py``, whose name it happens to hold, and reading it otherwise would leave the
    source of every project whose tests are named after it out of both checks.
    """
    name = Path(file).name
    return any(
        re.search(rf"(?<![\w.-]){re.escape(candidate)}(?![\w.-])", command) is not None
        for candidate in dict.fromkeys((file, name))
        for command in commands
    )


def code_lines(diff: str, commands: Sequence[str] = ()) -> list[AddedLine]:
    """The lines the change adds that carry code of a technology the catalogue covers.

    The instrument is left out — a file the naming convention reads as a test, or one a test
    command names — since a measure made on it is a measure of itself; so are the files of a
    language no operator and no coverage engine here reads, the blank lines and the comments.
    """
    kept: list[AddedLine] = []
    for added in added_lines(diff):
        if looks_like_a_test(added.file) or names_the_file(added.file, commands):
            continue
        if Path(added.file).suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if not added.text.strip() or is_comment(added.text):
            continue
        kept.append(added)
    return kept
