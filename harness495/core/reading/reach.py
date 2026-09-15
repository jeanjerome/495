"""Which lines of the change the verifications execute, and which they never reach.

The control run says a command reports something else without the change; the mutation check
says whether it reports a wrong version of one of its lines. Neither says anything about a
line no command ever runs: a branch the tests never take is passed over in silence by both,
since a command that never executes a line cannot report anything about it either way.

The measure exists in every technology the catalogue covers, and the project's own tool makes
it: coverage.py, @vitest/coverage-v8, cargo-llvm-cov, ``go test -coverprofile``, jacoco or
kover, kcov through shellspec. This module does two pure things around that tool. It rewrites
the project's own test command into one that writes a line-level report — by appending the
options the runner takes, or by putting the coverage driver in front of the runner, never by
restructuring the command — and it reads the report back, in the formats those tools write
(lcov, coverage.py's JSON, a Go coverage profile, Cobertura and JaCoCo XML). The engine runs
the rewritten command and crosses what comes back with the lines the change adds.

A line the report does not mention at all is not charged: the tools list the lines they
instrument, and a line absent from the report carries no statement the engine counts (a
closing brace, the continuation of a statement that starts higher up) or belongs to a file
the tool does not instrument. Only a line the report holds, with no hit on it, is a line the
verifications did not execute
(``docs/decisions/0023-the-lines-the-change-adds-are-crossed-with-what-the-verifications-execute.md``).
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from harness495.core.reading.diff import AddedLine

REPORT_DIR = ".495-coverage"
"""Where the instrumented command is told to write, inside the worktree: one directory, so
that ``git clean`` takes every artefact of the measure away with it."""

Hits = dict[str, dict[int, int]]
"""What a report says: per file as the report names it, the number of times each line ran."""


# --------------------------------------------------------------------------- the reports


def merge(into: Hits, found: Hits) -> None:
    """Add one report to another, a line counted as run when either says it ran."""
    for file, lines in found.items():
        target = into.setdefault(file, {})
        for number, hits in lines.items():
            target[number] = max(target.get(number, 0), hits)


def read_lcov(text: str) -> Hits:
    """LCOV: ``SF:<path>`` opens a file, ``DA:<line>,<hits>`` counts one line.

    Written by @vitest/coverage-v8, c8, nyc, jest and cargo-llvm-cov.
    """
    found: Hits = {}
    file = ""
    for line in text.splitlines():
        if line.startswith("SF:"):
            file = line[3:].strip()
        elif line.startswith("DA:") and file:
            number, _, hits = line[3:].partition(",")
            try:
                found.setdefault(file, {})[int(number)] = int(float(hits or 0))
            except ValueError:
                continue
        elif line.startswith("end_of_record"):
            file = ""
    return found


def read_coverage_json(text: str) -> Hits:
    """coverage.py's JSON: ``executed_lines`` and ``missing_lines`` per file.

    A line in neither list carries no statement coverage.py counts, and is left out here for
    the same reason.
    """
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    found: Hits = {}
    for file, entry in (data.get("files") or {}).items():
        lines = {int(n): 1 for n in entry.get("executed_lines") or []}
        lines.update({int(n): 0 for n in entry.get("missing_lines") or []})
        if lines:
            found[str(file)] = lines
    return found


_GO_BLOCK = re.compile(r"^(?P<file>.+):(?P<start>\d+)\.\d+,(?P<end>\d+)\.\d+ \d+ (?P<count>\d+)$")


def read_go_profile(text: str) -> Hits:
    """A Go coverage profile: one block per statement span, with the times it ran.

    The span is a range of lines, and every line of it is credited with the block's count:
    the profile says nothing finer, and ``go tool cover`` reads it the same way.
    """
    found: Hits = {}
    for line in text.splitlines():
        m = _GO_BLOCK.match(line.strip())
        if m is None:
            continue
        lines = found.setdefault(m.group("file"), {})
        count = int(m.group("count"))
        for number in range(int(m.group("start")), int(m.group("end")) + 1):
            lines[number] = max(lines.get(number, 0), count)
    return found


def read_xml_report(text: str) -> Hits:
    """Cobertura (kcov, gocover-cobertura) and JaCoCo (jacoco, kover) XML.

    Cobertura names a file on the class and counts a line with ``hits``; JaCoCo names a
    package and a source file and counts the instructions covered on a line with ``ci``.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return {}
    found: Hits = {}
    for element in root.iter("class"):
        file = element.get("filename")
        if not file:
            continue
        lines = found.setdefault(file, {})
        for line in element.iter("line"):
            number, hits = line.get("number"), line.get("hits")
            if number is not None and hits is not None:
                lines[int(number)] = max(lines.get(int(number), 0), int(hits))
    for package in root.iter("package"):
        prefix = (package.get("name") or "").strip("/")
        for source in package.iter("sourcefile"):
            name = source.get("name")
            if not name:
                continue
            lines = found.setdefault(f"{prefix}/{name}" if prefix else name, {})
            for line in source.iter("line"):
                number, covered = line.get("nr"), line.get("ci")
                if number is not None and covered is not None:
                    lines[int(number)] = max(lines.get(int(number), 0), int(covered))
    return {file: lines for file, lines in found.items() if lines}


READERS: dict[str, Callable[[str], Hits]] = {
    "lcov": read_lcov,
    "coverage.json": read_coverage_json,
    "go profile": read_go_profile,
    "xml": read_xml_report,
}


# --------------------------------------------------------------------------- the command


@dataclass(frozen=True)
class Instrumented:
    """A project's own test command, rewritten so that it writes a coverage report."""

    command: str
    report: str
    """Where the report lands, relative to the worktree; a pattern when the tool names the
    file itself (``coverage/<spec>/cobertura.xml``)."""
    reader: str
    tool: str
    env: dict[str, str] = field(default_factory=dict)
    """What the tool reads from the environment rather than from its options, so that every
    artefact of the measure lands under the report directory."""


def _token(name: str) -> str:
    """A command token, whatever directory names it: ``node_modules/.bin/vitest`` holds one,
    ``vitest-serializer`` does not."""
    return rf"(?<![\w.-]){name}(?![\w.-])"


def _python(tools: Sequence[str], command: str, directory: str) -> Instrumented | None:
    """coverage.py in front of the runner, then its JSON report.

    ``--source=.`` is what puts a module no test imports in the report, as a file whose lines
    all went unexecuted, rather than leaving it out of the measure altogether.
    """
    if "coverage.py" not in tools:
        return None
    options = "run --source=. -m"
    module = re.search(
        r"(?P<interpreter>\S+)\s+-m\s+(?P<runner>pytest|unittest)(?![\w.-])", command
    )
    if module is not None:
        # `python -m pytest` becomes `python -m coverage run -m pytest`, whatever the
        # interpreter is named, and the report is asked of that same interpreter.
        driver = f"{module.group('interpreter')} -m coverage"
        prefix, runner = command[: module.start()], module.group("runner")
        rest = command[module.end() :]
    else:
        # `pytest` and `<somewhere>/pytest` become the coverage driver next to it, so that a
        # command run through a wrapper (`uv run pytest`) keeps its wrapper.
        executable = re.search(r"(?:^|\s)(?P<exe>\S*pytest)(?![\w.-])", command)
        if executable is None:
            return None
        driver = executable.group("exe")[: -len("pytest")] + "coverage"
        prefix, runner = command[: executable.start("exe")], "pytest"
        rest = command[executable.end("exe") :]
    run = f"{prefix}{driver} {options} {runner}{rest}"
    reporter = f"{prefix}{driver}"
    report = f"{directory}/coverage.json"
    return Instrumented(
        command=f"{run} && {reporter} json -o {report}",
        report=report,
        reader="coverage.json",
        tool="coverage.py",
        env={"COVERAGE_FILE": f"{directory}/.coverage"},
    )


def _node(tools: Sequence[str], command: str, directory: str) -> Instrumented | None:
    """The runner's own coverage options, appended: both runners take an lcov reporter and a
    directory to write it in, and appending leaves whatever wrapper the command starts with."""
    if not {"@vitest/coverage-v8", "c8", "nyc"}.intersection(tools):
        return None
    report = f"{directory}/lcov.info"
    if re.search(_token("vitest"), command):
        options = f"--coverage --coverage.reporter=lcovonly --coverage.reportsDirectory={directory}"
    elif re.search(_token("jest"), command):
        options = f"--coverage --coverageReporters=lcovonly --coverageDirectory={directory}"
    else:
        return None
    return Instrumented(
        command=f"{command} {options}",
        report=report,
        reader="lcov",
        tool=next(t for t in ("@vitest/coverage-v8", "c8", "nyc") if t in tools),
    )


def _go(tools: Sequence[str], command: str, directory: str) -> Instrumented | None:
    """``go test`` writes the profile itself; ``-coverpkg`` extends the measure to the packages
    the tested one calls, so that a file no test package imports is still in the report."""
    if "go test -cover" not in tools or not re.search(r"(?<![\w.-])go\s+test(?![\w.-])", command):
        return None
    report = f"{directory}/cover.out"
    return Instrumented(
        command=f"{command} -coverprofile={report} -coverpkg=./...",
        report=report,
        reader="go profile",
        tool="go test -cover",
    )


def _rust(tools: Sequence[str], command: str, directory: str) -> Instrumented | None:
    """cargo-llvm-cov runs the tests itself, so it replaces ``cargo test`` rather than wrapping
    it; the arguments the project passes to the runner follow it unchanged."""
    if "cargo-llvm-cov" not in tools:
        return None
    m = re.search(r"(?<![\w.-])cargo\s+test(?![\w.-])", command)
    if m is None:
        return None
    report = f"{directory}/lcov.info"
    return Instrumented(
        command=command[: m.start()]
        + f"cargo llvm-cov --lcov --output-path {report}"
        + command[m.end() :],
        report=report,
        reader="lcov",
        tool="cargo-llvm-cov",
    )


def _jvm(tools: Sequence[str], command: str, _directory: str) -> Instrumented | None:
    """The build writes the report where its plugin puts it, which no option moves cheaply:
    the goal is appended to the project's own command and the report read where it lands."""
    if re.search(r"(?<![\w.-])(?:mvnw|mvn)(?![\w.-])", command) and "jacoco" in tools:
        return Instrumented(
            command=f"{command} org.jacoco:jacoco-maven-plugin:report",
            report="target/site/jacoco/jacoco.xml",
            reader="xml",
            tool="jacoco",
        )
    if not re.search(r"(?<![\w.-])(?:gradlew|gradle)(?![\w.-])", command):
        return None
    if "kover" in tools:
        return Instrumented(
            command=f"{command} koverXmlReport",
            report="build/reports/kover/report.xml",
            reader="xml",
            tool="kover",
        )
    if "jacoco" in tools:
        return Instrumented(
            command=f"{command} jacocoTestReport",
            report="build/reports/jacoco/test/jacocoTestReport.xml",
            reader="xml",
            tool="jacoco",
        )
    return None


def _shell(tools: Sequence[str], command: str, _directory: str) -> Instrumented | None:
    """kcov traces the shell shellspec sources the script in, and writes one report directory
    per spec. The descriptor it puts in a ``select()`` set fails above 1023, which is the
    default limit on macOS, so the limit is lowered before the run
    (``docs/studies/2026-09-13-shell-test-libraries.md``)."""
    if "kcov" not in tools or not re.search(_token("shellspec"), command):
        return None
    return Instrumented(
        command=f"ulimit -n 1024 2>/dev/null; {command} --kcov",
        report="coverage/*/cobertura.xml",
        reader="xml",
        tool="kcov",
    )


RECIPES: dict[str, Callable[[Sequence[str], str, str], Instrumented | None]] = {
    "python": _python,
    "javascript/typescript": _node,
    "go": _go,
    "rust": _rust,
    "java/kotlin": _jvm,
    "shell": _shell,
}
"""One rewriting per technology of the catalogue, keyed as ``core/coverage.py`` names them."""


def instrument(
    technology: str, tools: Sequence[str], command: str, directory: str = REPORT_DIR
) -> Instrumented | None:
    """The project's test command, rewritten to write a coverage report, or None.

    None when the project measures the ``coverage`` role with no tool this knows how to drive,
    or when the command runs a runner whose options are not those of the tool: the check is
    then not made, and the catalogue gap is what the requester is shown instead of a command
    the harness invented (``docs/decisions/0014``).
    """
    recipe = RECIPES.get(technology)
    return recipe(tools, command, directory) if recipe else None


# --------------------------------------------------------------------------- the crossing


def _normalise(path: str) -> str:
    return path.replace("\\", "/").removeprefix("./")


def same_file(reported: str, wanted: str) -> bool:
    """Whether a path in a report and a path in the diff name the same file.

    The tools write what they know: an absolute path (lcov from a runner), a path relative to
    the project (coverage.py), a module path (a Go profile) or a package and a file name
    (JaCoCo). All of them end with the file's own path, so one path naming the other's tail,
    on a segment boundary, is the match.
    """
    one, other = _normalise(reported), _normalise(wanted)
    return one == other or one.endswith(f"/{other}") or other.endswith(f"/{one}")


@dataclass(frozen=True)
class Unreached:
    """One line the change adds that the report holds, with no hit on it."""

    file: str
    line: int
    text: str

    def describe(self) -> str:
        return f"{self.file}:{self.line} `{self.text.strip()}`"


@dataclass
class Reading:
    """What the instrumented commands executed of the change, and what they did not."""

    measured_by: list[str] = field(default_factory=list)
    """The verifications whose instrumented command wrote a report."""
    tools: list[str] = field(default_factory=list)
    reached: int = 0
    unreached: list[Unreached] = field(default_factory=list)
    unmeasured: list[str] = field(default_factory=list)
    """Files the change touches that no report holds a single line of: the tool did not
    instrument them, and what the verifications do there is not known either way."""

    @property
    def missed(self) -> bool:
        return bool(self.unreached)

    def summary(self, first: int = 8) -> str:
        if not self.measured_by:
            return "no command could be measured for what it executes of the change"
        by = f"{', '.join(self.measured_by)} under {', '.join(dict.fromkeys(self.tools))}"
        total = self.reached + len(self.unreached)
        aside = (
            f"; not instrumented: {', '.join(self.unmeasured[:first])}" if self.unmeasured else ""
        )
        if not self.unreached:
            return f"{by} executed the {total} line(s) the change adds{aside}"
        named = ", ".join(u.describe() for u in self.unreached[:first])
        more = f", and {len(self.unreached) - first} more" if len(self.unreached) > first else ""
        return (
            f"{len(self.unreached)} of the {total} line(s) the change adds were executed by no "
            f"verification ({by}): {named}{more}{aside}"
        )

    def render(self) -> str:
        """The fact handed to the reviewers: one line per line of the change nothing ran."""
        return "\n".join(f"- {u.describe()}" for u in self.unreached) or "(none)"


def cross(
    lines: Iterable[AddedLine],
    hits: Hits,
    measured_by: Sequence[str] = (),
    tools: Sequence[str] = (),
) -> Reading:
    """The lines the change adds, against what the reports counted.

    A line the reports hold with no hit is unreached; one they hold with a hit is reached; one
    they do not hold is neither, since the engines list the lines they instrument and say
    nothing about the rest.
    """
    reading = Reading(measured_by=list(measured_by), tools=list(tools))
    by_file: dict[str, dict[int, int]] = {}
    for added in lines:
        if added.file not in by_file:
            merged: dict[int, int] = {}
            for reported, counted in hits.items():
                if same_file(reported, added.file):
                    for number, count in counted.items():
                        merged[number] = max(merged.get(number, 0), count)
            by_file[added.file] = merged
            if not merged and added.file not in reading.unmeasured:
                reading.unmeasured.append(added.file)
        counted_lines = by_file[added.file]
        if added.line not in counted_lines:
            continue
        if counted_lines[added.line] > 0:
            reading.reached += 1
        else:
            reading.unreached.append(Unreached(file=added.file, line=added.line, text=added.text))
    return reading
