"""Whether the change left the existing test suite as it found it.

The suite is the instrument of every non-regression requirement: a command that passes on the
change credits "the existing tests still pass" only if the tests it ran are the tests that
passed on the base. A change can remove a test, skip it, or deselect it, and the command still
reports success; nothing in the exit code says the suite got smaller. This module reads two
things the harness already has: the diff of the change, restricted to the test files that
existed on the base, and the count of tests each runner prints on the base and on the change.
Both readings are pure; the engine turns them into one ``suite_check`` evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from harness495.core.verification import looks_like_a_test

# --------------------------------------------------------------------------- the diff


@dataclass
class SuiteChange:
    """What the change did to one test file that existed on the base, read from the diff."""

    file: str
    deleted: bool = False
    renamed_to: str | None = None
    """The new path when the file was renamed to one the naming convention does not read as a
    test: the file is still there, the runner no longer collects it."""
    tests_removed: list[str] = field(default_factory=list)
    """Test definitions on removed lines whose name is on no added line of the same file, or
    ``N unnamed`` when the language marks tests with an attribute rather than a name."""
    tests_added: int = 0
    skips_added: list[str] = field(default_factory=list)
    """Lines the change adds that skip, ignore, disable or focus tests."""
    hunks: int = 0

    @property
    def weakened(self) -> bool:
        return bool(self.deleted or self.renamed_to or self.tests_removed or self.skips_added)

    def describe(self) -> str:
        if self.deleted:
            return f"{self.file}: deleted"
        if self.renamed_to:
            return f"{self.file}: renamed to {self.renamed_to}, which the runner does not collect"
        parts: list[str] = []
        if self.tests_removed:
            parts.append("test(s) removed: " + ", ".join(self.tests_removed))
        if self.skips_added:
            parts.append("skip(s) added: " + "; ".join(self.skips_added))
        if self.tests_added:
            parts.append(f"{self.tests_added} test(s) added")
        if not parts:
            parts.append(f"modified ({self.hunks} hunk(s))")
        return f"{self.file}: " + "; ".join(parts)


@dataclass
class SuiteCount:
    """What a runner printed as its tally: tests that ran, tests it set aside."""

    ran: int
    skipped: int
    runner: str


@dataclass
class CountComparison:
    verification_id: str
    base: SuiteCount
    change: SuiteCount

    @property
    def weakened(self) -> bool:
        return self.change.ran < self.base.ran or self.change.skipped > self.base.skipped

    def describe(self) -> str:
        return (
            f"{self.verification_id} ({self.base.runner}): {self.base.ran} ran and "
            f"{self.base.skipped} skipped on the base, {self.change.ran} ran and "
            f"{self.change.skipped} skipped on the change"
        )


@dataclass
class SuiteReading:
    changes: list[SuiteChange]
    counts: list[CountComparison]

    @property
    def weakened(self) -> bool:
        return any(c.weakened for c in self.changes) or any(c.weakened for c in self.counts)

    def summary(self) -> str:
        weak = [c.describe() for c in self.changes if c.weakened]
        weak += [c.describe() for c in self.counts if c.weakened]
        if weak:
            return "the suite is weaker than on the base: " + " | ".join(weak)
        parts: list[str] = []
        if self.changes:
            parts.append(
                f"{len(self.changes)} existing test file(s) modified, none deleted, no test "
                "removed or skipped"
            )
        else:
            parts.append("no existing test file modified")
        if self.counts:
            parts.append(
                "; ".join(
                    f"{c.verification_id} ran {c.change.ran} test(s) on the change for "
                    f"{c.base.ran} on the base"
                    for c in self.counts
                )
            )
        else:
            parts.append("no test tally read on both versions")
        return "; ".join(parts)

    def render(self) -> str:
        """The fact handed to the reviewers: every existing test file the change touched."""
        lines = [c.describe() for c in self.changes] + [c.describe() for c in self.counts]
        return "\n".join(f"- {ln}" for ln in lines) or "(none)"


_PY_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(test\w*)\s*\(")
_JS_DEF = re.compile(r"""^\s*(?:it|test)(?:\.\w+)*\s*\(\s*['"`](.+?)['"`]""")
_GO_DEF = re.compile(r"^func\s+(Test\w+)\s*\(")
_RUST_DEF = re.compile(r"^\s*#\[\s*(?:\w+::)*(?:test|rstest|proptest|quickcheck)\b")
_JVM_DEF = re.compile(r"^\s*@(?:Test|ParameterizedTest|RepeatedTest|TestFactory|Property)\b")
_SHELLSPEC_DEF = re.compile(r"""^\s*(?:It|Example|Specify)\s+['"](.+?)['"]""")
_BATS_DEF = re.compile(r"""^@test\s+['"](.+?)['"]""")
_GHERKIN_DEF = re.compile(r"^\s*(?:Scenario Outline|Scenario|Example)\s*:\s*(.+?)\s*$")
_RUBY_DEF = re.compile(r"""^\s*(?:it|specify|scenario)\s+['"](.+?)['"]|^\s*def\s+(test_\w*)""")

_DEFINITIONS: dict[str, re.Pattern[str]] = {
    ".py": _PY_DEF,
    ".js": _JS_DEF,
    ".jsx": _JS_DEF,
    ".ts": _JS_DEF,
    ".tsx": _JS_DEF,
    ".mjs": _JS_DEF,
    ".cjs": _JS_DEF,
    ".go": _GO_DEF,
    ".rs": _RUST_DEF,
    ".java": _JVM_DEF,
    ".kt": _JVM_DEF,
    ".scala": _JVM_DEF,
    ".groovy": _JVM_DEF,
    ".sh": _SHELLSPEC_DEF,
    ".bash": _SHELLSPEC_DEF,
    ".bats": _BATS_DEF,
    ".feature": _GHERKIN_DEF,
    ".rb": _RUBY_DEF,
}
"""How each language declares a test: a named definition, or an attribute (Rust, JVM) that
carries no name and is only counted."""

_PY_SKIP = re.compile(
    r"pytest\.mark\.(?:skip|skipif|xfail)|pytest\.(?:skip|xfail|importorskip)\(|"
    r"unittest\.skip|@skip(?:If|Unless)?\b|\.skipTest\(|pytestmark\s*=|"
    r"collect_ignore|__test__\s*=\s*False"
)
_JS_SKIP = re.compile(
    r"\b(?:it|test|describe|suite|context)\.(?:skip|only|todo)\s*\(|"
    r"\b(?:xit|xtest|xdescribe|xcontext|fit|fdescribe|ftest)\s*\(|\bthis\.skip\(\)"
)
_GO_SKIP = re.compile(r"\bt\.Skip(?:f|Now)?\(|\btesting\.Short\(\)")
_RUST_SKIP = re.compile(r"#\[\s*ignore\b")
_JVM_SKIP = re.compile(
    r"@(?:Disabled|Ignore|DisabledIf\w*|EnabledIf\w*|Skip)\b|\bassume(?:True|False|That)\("
)
_SHELL_SKIP = re.compile(r"^\s*(?:Skip|Pending|xIt|xExample|xSpecify|xDescribe|xContext|skip)\b")
_GHERKIN_SKIP = re.compile(r"@(?:skip|wip|ignore|pending|disabled)\b")
_RUBY_SKIP = re.compile(r"^\s*(?:skip|pending|xit|xspecify|xdescribe|xcontext)\b")

_SKIPS: dict[str, re.Pattern[str]] = {
    ".py": _PY_SKIP,
    ".js": _JS_SKIP,
    ".jsx": _JS_SKIP,
    ".ts": _JS_SKIP,
    ".tsx": _JS_SKIP,
    ".mjs": _JS_SKIP,
    ".cjs": _JS_SKIP,
    ".go": _GO_SKIP,
    ".rs": _RUST_SKIP,
    ".java": _JVM_SKIP,
    ".kt": _JVM_SKIP,
    ".scala": _JVM_SKIP,
    ".groovy": _JVM_SKIP,
    ".sh": _SHELL_SKIP,
    ".bash": _SHELL_SKIP,
    ".bats": _SHELL_SKIP,
    ".feature": _GHERKIN_SKIP,
    ".rb": _RUBY_SKIP,
}
"""What a language writes to keep a test from running or to run only some of them."""


def _definition(path: str, line: str) -> str | None:
    """The name a test line declares, ``""`` for an unnamed marker, None for any other line."""
    pattern = _DEFINITIONS.get(Path(path).suffix.lower())
    if pattern is None:
        return None
    m = pattern.match(line)
    if m is None:
        return None
    return next((g for g in m.groups() if g), "")


def _skip(path: str, line: str) -> bool:
    pattern = _SKIPS.get(Path(path).suffix.lower())
    return pattern is not None and pattern.search(line) is not None


_FILE_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+)$")


def read_suite_changes(diff: str) -> list[SuiteChange]:
    """What the diff does to the test files that were there before it.

    A file the diff creates is the change's own instrument and is left to the control run; a
    file that existed is part of the suite the base passed, and this reads whether the diff
    deleted it, renamed it out of the runner's reach, removed a test from it, added a skip to
    it, or merely edited it. A definition on a removed line whose name is on no added line of
    the file is a test removed, whatever else the file gains: the test that passed on the base
    no longer runs, and a renamed test reads the same way until the reviewer accounts for it.
    """
    changes: list[SuiteChange] = []
    current: SuiteChange | None = None
    removed: list[str] = []
    added: list[str] = []
    new_file = False

    def close() -> None:
        nonlocal current
        if current is None:
            return
        if not new_file and (looks_like_a_test(current.file) or current.renamed_to):
            named_added = {n for n in added if n}
            current.tests_removed = [n for n in removed if n and n not in named_added]
            unnamed_removed = sum(1 for n in removed if not n)
            unnamed_added = sum(1 for n in added if not n)
            if unnamed_removed > unnamed_added:
                current.tests_removed.append(f"{unnamed_removed - unnamed_added} unnamed")
            current.tests_added = max(
                len(named_added - {n for n in removed if n}) + unnamed_added - unnamed_removed, 0
            )
            changes.append(current)
        current = None

    for line in diff.splitlines():
        header = _FILE_HEADER.match(line)
        if header:
            close()
            old, new = header.group(1), header.group(2)
            current = SuiteChange(file=old)
            removed, added, new_file = [], [], False
            if old != new and looks_like_a_test(old) and not looks_like_a_test(new):
                current.renamed_to = new
            continue
        if current is None:
            continue
        if line.startswith("new file mode"):
            new_file = True
        elif line.startswith("deleted file mode"):
            current.deleted = True
        elif line.startswith("rename to "):
            new = line[len("rename to ") :].strip()
            if looks_like_a_test(current.file) and not looks_like_a_test(new):
                current.renamed_to = new
        elif line.startswith("@@"):
            current.hunks += 1
        elif line.startswith("+") and not line.startswith("+++"):
            body = line[1:]
            d = _definition(current.file, body)
            if d is not None:
                added.append(d)
            if _skip(current.file, body):
                current.skips_added.append(body.strip()[:120])
        elif line.startswith("-") and not line.startswith("---"):
            d = _definition(current.file, line[1:])
            if d is not None:
                removed.append(d)
    close()
    return changes


# --------------------------------------------------------------------------- the tally


def _ints(pattern: str, text: str) -> int:
    return sum(int(m) for m in re.findall(pattern, text, re.MULTILINE))


def _pytest(output: str) -> SuiteCount | None:
    lines = [
        ln
        for ln in output.splitlines()
        if re.search(
            r"\b(?:passed|failed|errors?|skipped|xfailed|xpassed|deselected|no tests ran)\b", ln
        )
        and re.search(r"\bin \d+(?:\.\d+)?s\b", ln)
    ]
    if not lines:
        return None
    last = lines[-1]
    ran = _ints(r"(\d+) (?:passed|failed|xpassed)\b", last) + _ints(r"(\d+) errors?\b", last)
    skipped = _ints(r"(\d+) (?:skipped|xfailed|deselected)\b", last)
    return SuiteCount(ran=ran, skipped=skipped, runner="pytest")


def _unittest(output: str) -> SuiteCount | None:
    m = list(re.finditer(r"^Ran (\d+) tests? in", output, re.MULTILINE))
    if not m:
        return None
    skipped = _ints(r"skipped=(\d+)", output)
    return SuiteCount(ran=int(m[-1].group(1)) - skipped, skipped=skipped, runner="unittest")


def _jest(output: str) -> SuiteCount | None:
    m = list(re.finditer(r"^\s*Tests:\s+(.*?)(\d+) total", output, re.MULTILINE))
    if not m:
        return None
    parts = m[-1].group(1)
    skipped = _ints(r"(\d+) (?:skipped|todo)\b", parts)
    return SuiteCount(ran=int(m[-1].group(2)) - skipped, skipped=skipped, runner="jest")


def _mocha(output: str) -> SuiteCount | None:
    if not re.search(r"^\s*\d+ passing\b", output, re.MULTILINE):
        return None
    ran = _ints(r"^\s*(\d+) (?:passing|failing)\b", output)
    skipped = _ints(r"^\s*(\d+) pending\b", output)
    return SuiteCount(ran=ran, skipped=skipped, runner="mocha")


def _go(output: str) -> SuiteCount | None:
    marks = re.findall(r"^\s*--- (PASS|FAIL|SKIP):", output, re.MULTILINE)
    if not marks:
        return None
    skipped = marks.count("SKIP")
    return SuiteCount(ran=len(marks) - skipped, skipped=skipped, runner="go test")


def _cargo(output: str) -> SuiteCount | None:
    results = re.findall(
        r"^test result: \w+\. (\d+) passed; (\d+) failed; (\d+) ignored", output, re.MULTILINE
    )
    if not results:
        return None
    ran = sum(int(p) + int(f) for p, f, _ in results)
    return SuiteCount(ran=ran, skipped=sum(int(i) for _, _, i in results), runner="cargo test")


def _examples(output: str) -> SuiteCount | None:
    m = list(
        re.finditer(
            r"^(\d+) examples?, (\d+) failures?(?:, (\d+) (?:pending|skipped))?",
            output,
            re.MULTILINE,
        )
    )
    if not m:
        return None
    total, _, pending = m[-1].groups()
    skipped = int(pending or 0)
    return SuiteCount(ran=int(total) - skipped, skipped=skipped, runner="shellspec/rspec")


def _surefire(output: str) -> SuiteCount | None:
    m = list(
        re.finditer(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)", output)
    )
    if not m:
        return None
    total, _, _, skipped = (int(x) for x in m[-1].groups())
    return SuiteCount(ran=total - skipped, skipped=skipped, runner="junit")


def _gradle(output: str) -> SuiteCount | None:
    m = list(re.finditer(r"(\d+) tests completed, (\d+) failed(?:, (\d+) skipped)?", output))
    if not m:
        return None
    total, _, skipped = m[-1].groups()
    return SuiteCount(
        ran=int(total) - int(skipped or 0), skipped=int(skipped or 0), runner="gradle"
    )


def _behave(output: str) -> SuiteCount | None:
    m = list(
        re.finditer(
            r"^(\d+) scenarios? passed, (\d+) failed,(?: \d+ error,)? (\d+) skipped",
            output,
            re.MULTILINE,
        )
    )
    if not m:
        return None
    passed, failed, skipped = (int(x) for x in m[-1].groups())
    return SuiteCount(ran=passed + failed, skipped=skipped, runner="behave")


def _cucumber(output: str) -> SuiteCount | None:
    m = list(re.finditer(r"^(\d+) scenarios? \((.*?)\)", output, re.MULTILINE))
    if not m:
        return None
    total, parts = int(m[-1].group(1)), m[-1].group(2)
    skipped = _ints(r"(\d+) (?:skipped|pending|undefined)\b", parts)
    return SuiteCount(ran=total - skipped, skipped=skipped, runner="cucumber")


_READERS = (
    _pytest,
    _unittest,
    _jest,
    _mocha,
    _go,
    _cargo,
    _examples,
    _surefire,
    _gradle,
    _behave,
    _cucumber,
)


def count_tests(output: str) -> SuiteCount | None:
    """The tally a runner prints at the end of its output, or None when no runner is recognised.

    The families are those of the runners the catalogue names for Python, Node, Go, Rust, the
    JVM and the shell. ``ran`` counts the tests that were exercised, whatever they reported;
    ``skipped`` counts the ones the runner set aside (skipped, ignored, pending, deselected,
    expected to fail). A ``go test`` without ``-v`` prints no tally, and reads as None.
    """
    for reader in _READERS:
        count = reader(output)
        if count is not None:
            return count
    return None


def compare_counts(
    verification_id: str, base_output: str, change_output: str
) -> CountComparison | None:
    """The tally on both versions, or None when either output prints none or they come from
    different runners."""
    base = count_tests(base_output)
    change = count_tests(change_output)
    if base is None or change is None or base.runner != change.runner:
        return None
    return CountComparison(verification_id=verification_id, base=base, change=change)
