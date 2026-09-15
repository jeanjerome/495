"""Whether the verifications constrain the change, or only notice it.

The control run asks "does this command report something else without the change?"; it cannot
ask "would it report something else if the change were wrong?". It has one mutant to work
with, the absence of the change, and a test that fails there because the code it names does
not exist yet reports nothing about the assertions it makes once the code is there.

This module writes a few more mutants. Each takes one line the change added
(``core/reading/diff.py`` reads which lines those are), alters it the way a plausible mistake
would (a comparison inverted, an ``and`` turned into an ``or``, an operand sign flipped, a
constant moved, a call dropped, a return short-circuited) and hands the engine a version of the
change that is wrong
in a stated way. A verification that still reports success on it is passing over a wrong
implementation of the very line it is supposed to watch. Reading is pure here: the diff comes
in, the mutants and the mutated source go out, and the engine runs them.

Two limits are structural, not incidental. The operators are textual and read one line at a
time, so they fire only where an operator is surrounded by spaces and never look at the
grammar of the language; and a mutant may be equivalent to the line it replaces (a constant no
behaviour depends on, a call that only logs), in which case no test can kill it and the
survivor is about the mutant, not about the suite. Both are why a survivor leaves a
requirement undetermined for the requester to rule on rather than charging it as a defect
(``docs/decisions/0022-the-verifications-are-measured-against-wrong-versions-of-the-change.md``).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from harness495.core.reading.diff import AddedLine, code_lines

# --------------------------------------------------------------------------- the operators

_COMPARISON = {">=": ">", "<=": "<", "==": "!=", "!=": "==", ">": ">=", "<": "<="}
_COMPARISON_RE = re.compile(r"(?<=\s)(>=|<=|==|!=|>|<)(?=\s)")

_CONNECTOR = {"and": "or", "or": "and", "&&": "||", "||": "&&"}
_CONNECTOR_RE = re.compile(r"(?<=\s)(and|or|&&|\|\|)(?=\s)")

_ARITHMETIC = {"+": "-", "-": "+", "*": "/", "/": "*"}
_ARITHMETIC_RE = re.compile(r"(?<=\s)([+\-*/])(?=\s)")

_BOOLEAN = {"True": "False", "False": "True", "true": "false", "false": "true"}
_BOOLEAN_RE = re.compile(r"\b(True|False|true|false)\b")

_NUMBER_RE = re.compile(r"(?<![\w.])(\d+)(?![\w.])")

_CALL_RE = re.compile(
    r"^(\s*)(?!(?:if|elif|else|for|while|switch|case|return|yield|def|fn|func|function|"
    r"class|struct|impl|catch|with|assert|import|from|use|package|match|when|do|until|then|fi|"
    r"esac|done|end|raise|throw|new|export|module)\b)"
    r"(?:await\s+)?([A-Za-z_$][\w.$]*)\s*\(.*\)\s*;?\s*$"
)
"""A statement whose whole effect is one call: dropping it is the mutant."""

_QUIET_CALL = re.compile(
    r"log|print|debug|warn|info|trace|echo|puts|console\.|fmt\.Print|eprintln|println",
    re.IGNORECASE,
)
"""Calls a correct implementation may drop without changing what anything observes. Mutating
one produces a survivor that says nothing about the tests, so it is left alone."""

_RETURN_RE = re.compile(r"^(\s*)return\s+(\S.*?)\s*(;?)\s*$")

_NOOP = {".py": "pass", ".sh": ":", ".bash": ":", ".zsh": ":"}
"""What replaces a dropped call where a block may not be left empty."""

_NEUTRAL = {
    ".py": "None",
    ".js": "null",
    ".jsx": "null",
    ".ts": "null",
    ".tsx": "null",
    ".mjs": "null",
    ".cjs": "null",
    ".rb": "nil",
}
"""The value any function of the language may return, whatever it returns otherwise. A
language that types its returns (Go, Rust, the JVM) has no such value and gets no mutant of
this operator: the ones it would produce fail to compile and are killed by the compiler."""


def _swap(pattern: re.Pattern[str], table: dict[str, str], line: str) -> str | None:
    """Replace the first token of the table the pattern finds, or None when it finds none."""
    m = pattern.search(line)
    if m is None:
        return None
    return line[: m.start(1)] + table[m.group(1)] + line[m.end(1) :]


def _comparison(_suffix: str, line: str) -> tuple[str, str] | None:
    mutated = _swap(_COMPARISON_RE, _COMPARISON, line)
    return ("comparison", mutated) if mutated else None


def _connector(_suffix: str, line: str) -> tuple[str, str] | None:
    mutated = _swap(_CONNECTOR_RE, _CONNECTOR, line)
    return ("connector", mutated) if mutated else None


def _arithmetic(_suffix: str, line: str) -> tuple[str, str] | None:
    mutated = _swap(_ARITHMETIC_RE, _ARITHMETIC, line)
    return ("arithmetic", mutated) if mutated else None


def _boolean(_suffix: str, line: str) -> tuple[str, str] | None:
    mutated = _swap(_BOOLEAN_RE, _BOOLEAN, line)
    return ("boolean", mutated) if mutated else None


def _constant(_suffix: str, line: str) -> tuple[str, str] | None:
    m = _NUMBER_RE.search(line)
    if m is None:
        return None
    moved = str(int(m.group(1)) + 1)
    return ("constant", line[: m.start(1)] + moved + line[m.end(1) :])


def _call(suffix: str, line: str) -> tuple[str, str] | None:
    m = _CALL_RE.match(line)
    if m is None or _QUIET_CALL.search(m.group(2)):
        return None
    return ("call", m.group(1) + _NOOP.get(suffix, ""))


def _return(suffix: str, line: str) -> tuple[str, str] | None:
    neutral = _NEUTRAL.get(suffix)
    m = _RETURN_RE.match(line)
    if neutral is None or m is None or m.group(2) == neutral:
        return None
    return ("return", f"{m.group(1)}return {neutral}{m.group(3)}")


_OPERATORS = (_comparison, _connector, _arithmetic, _boolean, _constant, _call, _return)
"""Ordered by how much a survivor says: an inverted comparison that no test notices is a
stronger statement about the suite than a constant it never reads."""


def candidates(file: str, line: str) -> list[tuple[str, str]]:
    """Every mutant one line admits, as (operator, the line as the mutant writes it)."""
    suffix = Path(file).suffix.lower()
    found: list[tuple[str, str]] = []
    for operator in _OPERATORS:
        mutant = operator(suffix, line)
        if mutant is not None and mutant[1] != line:
            found.append(mutant)
    return found


# --------------------------------------------------------------------------- the plan


@dataclass(frozen=True)
class Mutant:
    """One wrong version of the change: a single line, altered in one stated way."""

    id: str
    file: str
    line: int
    operator: str
    original: str
    mutated: str

    def describe(self) -> str:
        return (
            f"{self.id} {self.file}:{self.line} ({self.operator}) "
            f"`{self.original.strip()}` -> `{self.mutated.strip() or '(line dropped)'}`"
        )


def plan_mutants(diff: str, limit: int, commands: Sequence[str] = ()) -> list[Mutant]:
    """The mutants to run, at most ``limit`` of them, over the lines the change added.

    The lines are the code the change adds, as ``core/reading/diff.py`` reads it: the
    instrument is left alone, since altering it measures nothing but itself. The cap is spread
    rather than spent on the first lines it meets — one mutant per changed line, taking the
    files in turn, then a second one per line, and so on — so that a change touching several
    files is measured in several places.
    """
    if limit <= 0:
        return []
    by_file: dict[str, list[tuple[AddedLine, list[tuple[str, str]]]]] = {}
    for added in code_lines(diff, commands):
        found = candidates(added.file, added.text)
        if found:
            by_file.setdefault(added.file, []).append((added, found))
    if not by_file:
        return []
    queues = list(by_file.values())
    depth = max(len(q) for q in queues)
    ordered = [q[i] for i in range(depth) for q in queues if i < len(q)]
    chosen = [
        (added, found[rank])
        for rank in range(max(len(found) for _, found in ordered))
        for added, found in ordered
        if rank < len(found)
    ][:limit]
    return [
        Mutant(
            id=f"m{n}",
            file=added.file,
            line=added.line,
            operator=operator,
            original=added.text,
            mutated=mutated,
        )
        for n, (added, (operator, mutated)) in enumerate(chosen, start=1)
    ]


def mutated_source(source: str, mutant: Mutant) -> str | None:
    """The file as the mutant writes it, or None when the line is not where it was.

    The line is checked against the text the diff showed before it is replaced: a mutant is
    applied to the version it was planned on, or it is not applied at all.
    """
    lines = source.splitlines(keepends=True)
    if not 0 < mutant.line <= len(lines):
        return None
    current = lines[mutant.line - 1]
    ending = current[len(current.rstrip("\r\n")) :]
    if current.rstrip("\r\n") != mutant.original:
        return None
    lines[mutant.line - 1] = mutant.mutated + ending
    return "".join(lines)
