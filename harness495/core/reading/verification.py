"""What a verification command is worth, and what its runs mean, read and nothing else.

Three readings, none of which executes anything. Whether a specification's verifications can
carry its requirements at all (``assess_sufficiency``). What a pair of runs on two versions
says about the instrument rather than about the change (``measures_the_change``,
``classify_instrument``), and what two runs on the same version say about the command itself
(``reports_the_same_twice``). Which files of a change are the instrument rather than what it
delivers (``looks_like_a_test``), which is also what ``core/diff.py`` and ``core/suite.py``
read a diff with.

The results these functions are handed come from :mod:`harness495.core.engine.running`, the
only module that puts a verification command in the sandbox. Nothing here opens a file of the
project under test or runs a process, ``shutil.which`` on the machine's PATH excepted, which is
how the audit tells a command that cannot run from one that can.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Protocol

from harness495.core.catalogue import unmeasured_role
from harness495.core.models import (
    ProjectProfile,
    RequirementKind,
    Spec,
    Sufficiency,
    Verification,
    VerificationKind,
)

INTERPRETER_NAMES = ("python", "python3", "pytest", "node", "npm", "npx", "ruff", "mypy")

_VOLATILE = (
    (re.compile(r"\x1b\[[0-9;]*[A-Za-z]"), ""),  # ANSI colour
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\S*"), "<ts>"),
    (re.compile(r"\b\d{2}:\d{2}:\d{2}\b"), "<ts>"),
    (re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:ms|s|sec|secs|seconds|min)\b"), "<dur>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<addr>"),
    (re.compile(r"\b[0-9a-f]{7,40}\b"), "<hash>"),
    (re.compile(r"(?<![\w/])/(?:[\w.@+-]+/)*[\w.@+-]+"), "<path>"),
)

SIGNATURE_LINES = 40

_ASSERTION = re.compile(
    r"AssertionError|AssertionFailedError|ComparisonFailure|assertion `?left|"
    r"^\s*E\s+assert\b|\bassert\b.*(?:==|!=|is |in )|"  # pytest
    r"expect\(received\)|Expected:|Received:|toBe|toEqual|toStrictEqual|"  # jest, vitest
    r"^\s*--- FAIL:|Error Trace:|Not equal:|expected .* got|expected .* but was|"  # go, junit
    r"AssertionError:|expected:? <|\bexpected\b.*\bactual\b|"  # junit, spock
    r"^\s*(?:should|expected|but got)\b",  # shellspec, rspec, mocha
    re.IGNORECASE | re.MULTILINE,
)
"""What a test prints when it reaches an assertion and the assertion fails."""

_EXECUTION_ERROR = re.compile(
    r"^.*\b(?:"
    r"ImportError|ModuleNotFoundError|NameError|AttributeError|"  # python
    r"TypeError: .*(?:unexpected keyword|positional argument|not callable|is not a function|"
    r"is not a constructor)|"  # python, javascript
    r"ReferenceError|Cannot find module|Could not resolve|is not defined|is not exported|"  # node
    r"undefined: \S+|cannot find package|no required module|has no field or method|"
    r"too many arguments|not enough arguments|\[build failed\]|"  # go
    r"error\[E0\d{3}\]|unresolved import|cannot find (?:function|value|type|method)|"
    r"no method named|no function or associated item|"  # rust
    r"cannot find symbol|ClassNotFoundException|NoClassDefFoundError|NoSuchMethodError|"
    r"NoSuchMethodException|compilation failed|COMPILATION ERROR|"  # jvm
    r"command not found|No such file or directory|not found in PATH"  # shell
    r")\b.*$",
    re.MULTILINE,
)
"""What a run prints when the code a test needs is not there to run, so that the test never
reached what it was written to observe."""


def asserted(output: str) -> bool:
    """Whether the output shows a test reaching an assertion and failing it."""
    return _ASSERTION.search(output) is not None


def execution_error(output: str) -> str | None:
    """The first line of the output that reports an execution error, or None.

    An execution error is a failure that happened before any assertion could run: the module
    the test imports does not exist, the name it calls is not defined, the signature it uses
    is not the one in place. A test that fails this way without the change has shown that its
    target is absent, not that it observes the behaviour; a test that asserts anything at all
    on a target that exists would fail the same way. The families are those of the runners the
    catalogue names for Python, Node, Go, Rust, the JVM and the shell.
    """
    m = _EXECUTION_ERROR.search(output)
    if m is None:
        return None
    line = m.group(0).strip()
    return line[:200]


def failure_signature(output: str) -> str:
    """What failed, blind to when and where it ran.

    Two runs of the same command share a signature when they fail for the same reason. Timing,
    absolute paths, hashes and addresses differ between any two runs and carry no meaning here,
    so they are erased; everything else, counts included, is kept because a different count is a
    different failure.
    """
    text = output
    for pattern, replacement in _VOLATILE:
        text = pattern.sub(replacement, text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines[-SIGNATURE_LINES:])


def project_interpreters(executable_commands: set[str]) -> dict[str, str]:
    """Map bare tool names to the concrete executables the project's own commands use.

    ``/repo/.venv/bin/python -m pytest`` yields ``{"python": "/repo/.venv/bin/python",
    "python3": "/repo/.venv/bin/python"}`` so that proposed one-liners run in the same
    environment as the project's verified commands.
    """
    mapping: dict[str, str] = {}
    for command in executable_commands:
        tokens = command.split()
        if not tokens:
            continue
        head = tokens[0]
        base = Path(head).name
        if "/" not in head:
            continue
        if base.startswith("python"):
            mapping.setdefault("python", head)
            mapping.setdefault("python3", head)
        elif base in INTERPRETER_NAMES:
            mapping.setdefault(base, head)
    return mapping


def normalise_command(command: str, interpreters: dict[str, str]) -> tuple[str, str | None]:
    """Replace a bare interpreter name by the project's one; return (command, note)."""
    tokens = command.split(maxsplit=1)
    if not tokens:
        return command, None
    head = tokens[0]
    if head in interpreters and interpreters[head] != head:
        rest = tokens[1] if len(tokens) > 1 else ""
        replaced = interpreters[head] + (" " + rest if rest else "")
        return replaced, f"interpreter '{head}' replaced by the project's '{interpreters[head]}'"
    return command, None


def assess_sufficiency(
    spec: Spec,
    executable_commands: set[str] | None = None,
    passing_on_base: set[str] | None = None,
    profile: ProjectProfile | None = None,
) -> list[str]:
    """Flag verifications that are missing or insufficient. Mutates ``spec`` and returns the gaps.

    ``passing_on_base`` holds the commands that were run before the change existed and reported
    success. A requirement that states new behaviour cannot be carried by one of those alone: it
    already reports success on a tree where the behaviour is absent, so whatever it reports
    afterwards is the same and shows nothing.

    ``profile`` carries the role coverage: a verification that names a catalogue role the
    project does not measure is insufficient whatever its command, because the tool that
    measures the role is not in place and is the requester's to bring in, not the producer's;
    the rationale names what the catalogue recommends (``catalogue.unmeasured_role``).
    """
    gaps: list[str] = []
    interpreters = project_interpreters(executable_commands or set())
    for v in spec.verifications:
        v.sufficiency = Sufficiency.sufficient
        if v.command:
            v.command, note = normalise_command(v.command, interpreters)
            if note:
                v.rationale = note
        missing_role = (
            unmeasured_role(v.role, profile) if v.role is not None and profile is not None else None
        )
        if missing_role is not None:
            v.sufficiency = Sufficiency.insufficient
            v.rationale = missing_role
        elif v.kind in (VerificationKind.manual, VerificationKind.review):
            v.sufficiency = Sufficiency.insufficient
            v.rationale = v.rationale or "not automated: relies on human or reviewer judgement only"
        elif not v.command:
            v.sufficiency = Sufficiency.missing
            v.rationale = v.rationale or "no command to execute"
        elif v.kind is VerificationKind.test and v.to_create and not _has_scenario(v):
            v.sufficiency = Sufficiency.insufficient
            v.rationale = (
                "a test to create is stated as a scenario (given, when, then) so that the "
                "requester approves the text of the test and the producer writes it from that "
                "text; "
                + ("its scenario has no when or then step" if v.scenario else "none was given")
            )
        elif executable_commands is not None and not v.to_create:
            head = v.command.split()[0] if v.command.split() else ""
            if head and not _known_prefix(v.command, executable_commands):
                if shutil.which(head) is None and not Path(head).exists():
                    v.sufficiency = Sufficiency.insufficient
                    v.rationale = v.rationale or f"executable '{head}' not found on this machine"
                else:
                    v.rationale = v.rationale or (
                        f"'{head}' is not one of the project's verified commands but exists on PATH"
                    )
    for r in spec.requirements:
        vs: list[Verification] = [
            v for v in (spec.verification(vid) for vid in r.verification_ids) if v is not None
        ]
        if not vs:
            gaps.append(f"{r.id} has no verification")
            continue
        if all(v.sufficiency is not Sufficiency.sufficient for v in vs):
            reasons = "; ".join(f"{v.id}: {v.sufficiency.value} ({v.rationale})" for v in vs)
            gaps.append(f"{r.id} has no sufficient verification ({reasons})")
        elif (
            passing_on_base is not None
            and r.kind is RequirementKind.behaviour
            and all(not v.to_create and v.command in passing_on_base for v in vs)
        ):
            gaps.append(
                f"{r.id} states new behaviour, but "
                + ", ".join(v.id for v in vs)
                + " already passed on the base version and creates nothing: its outcome cannot "
                "tell the change from its absence"
            )
    spec.gaps = gaps
    return gaps


def _has_scenario(v: Verification) -> bool:
    return v.scenario is not None and v.scenario.complete


def _known_prefix(command: str, executable: set[str]) -> bool:
    return any(command.startswith(e.split()[0]) for e in executable if e.split())


_TEST_DIRS = frozenset({"test", "tests", "spec", "specs", "__tests__", "testing"})
_TEST_STEM = re.compile(r"(?:^|[._-])(?:tests?|specs?)(?:[._-]|$)", re.IGNORECASE)
_TEST_CAMEL = re.compile(r"[a-z0-9](?:Test|Tests|Spec|Specs|IT)$")
_TEST_SUFFIXES = frozenset({".feature"})
_TEST_NAMES = frozenset({"conftest.py"})


def looks_like_a_test(path: str) -> bool:
    """Whether a repository path is where a project keeps its tests.

    A naming convention, not a fact: this is how the harness guesses which files of a change are
    the instrument rather than the thing measured. It spans the usual layouts (``tests/``,
    ``test_x.py``, ``x_test.go``, ``x.spec.ts``, ``XTest.java``, ``.feature``) and misses a
    project that follows none of them, which is why nothing is concluded from an empty result.
    """
    p = Path(path)
    if any(part.lower() in _TEST_DIRS for part in p.parts[:-1]):
        return True
    if p.suffix.lower() in _TEST_SUFFIXES or p.name in _TEST_NAMES:
        return True
    return bool(_TEST_STEM.search(p.stem) or _TEST_CAMEL.search(p.stem))


def instrument_files(files_changed: list[str]) -> list[str]:
    """The files of a change that are how it is measured rather than what it delivers."""
    return [f for f in files_changed if looks_like_a_test(f)]


class CommandOutcome(Protocol):
    """What reading a pair of runs needs of a run that happened, and no more.

    The engine hands in the result its sandbox produced; naming the four fields structurally
    rather than importing that class is what keeps this module free of the package that
    executes commands.
    """

    exit_code: int | None
    output: str
    timed_out: bool
    interrupted: bool


def measures_the_change(
    subject_exit: int | None,
    subject_output: str,
    control: CommandOutcome,
    subject_timed_out: bool = False,
) -> bool:
    """False when the command fails identically with and without the change.

    Conservative by construction: anything that prevents a clean comparison (a timeout on either
    side, an interrupted control run) counts as "the instrument is sound", because accusing the
    specification on thin evidence is worse than letting one more iteration run.
    """
    if subject_timed_out or control.timed_out or control.interrupted:
        return True
    if subject_exit != control.exit_code:
        return True
    return failure_signature(subject_output) != failure_signature(control.output)


def reported_success(expected_exit_code: int, exit_code: int | None, timed_out: bool) -> bool:
    """Whether one run of a command reported what the verification expects of it."""
    return not timed_out and exit_code == expected_exit_code


def reports_the_same_twice(
    expected_exit_code: int,
    first_exit: int | None,
    first_output: str,
    first_timed_out: bool,
    second: CommandOutcome,
) -> tuple[bool, str]:
    """Read two runs of one command on one version. Returns (stable, what the pair reported).

    Nothing about the tree changed between them, so a difference is the command's own: a test
    that depends on the order it runs in, on the clock, on the network, on a port or a
    directory another process holds. A command that reports one thing and then another is not
    measuring the change, and what it happened to report first decides nothing — neither that
    the requirement holds nor that it is violated.

    Two runs that both report success are the same reading, whatever they printed on the way:
    the verification's outcome is its exit code, and a passing run's output carries counts and
    orderings that differ between any two runs. Two runs that both fail are compared on their
    failure signature as well, since a command that fails for a different reason each time
    hands the producer an observation that will not be there when it looks.
    """
    first_passed = reported_success(expected_exit_code, first_exit, first_timed_out)
    second_passed = reported_success(expected_exit_code, second.exit_code, second.timed_out)
    first_state = "timed out" if first_timed_out else f"exit {first_exit}"
    second_state = "timed out" if second.timed_out else f"exit {second.exit_code}"
    if first_passed != second_passed:
        return (
            False,
            f"reported success once and failure once on the same version: {first_state} then "
            f"{second_state}",
        )
    if first_passed:
        return True, f"reported success twice on the same version ({first_state}, {second_state})"
    if failure_signature(first_output) != failure_signature(second.output):
        return (
            False,
            f"failed twice on the same version, for two different reasons: {first_state} then "
            f"{second_state}, and the two runs did not fail the same way",
        )
    return True, f"failed the same way twice on the same version ({first_state}, {second_state})"


def classify_instrument(
    v: Verification,
    subject_passed: bool | None,
    subject_exit: int | None,
    subject_output: str,
    subject_timed_out: bool,
    control: CommandOutcome,
    base_commit: str,
    applied: list[str],
) -> tuple[bool | None, Sufficiency, str]:
    """Read a verification's pair of runs. Returns (discriminates, sufficiency, rationale).

    Only a difference between the two runs carries information. When they agree, what the command
    reported says which kind of instrument it is: one that never reports success, or one that
    reports it whatever the tree contains.
    """
    where = base_commit[:12]
    if measures_the_change(subject_exit, subject_output, control, subject_timed_out):
        error = (
            execution_error(control.output)
            if subject_passed
            and not control.timed_out
            and control.exit_code != v.expected_exit_code
            and not asserted(control.output)
            else None
        )
        if error is not None:
            # It fails there and passes here, so it observes the change; but what it reports
            # there is that the code it needs does not exist, which any test that names the
            # new code would report, an assertion about nothing included. The pair shows the
            # target is absent without the change, not that the test observes its behaviour.
            return (
                True,
                Sufficiency.unconfirmed,
                f"fails without the change (base version {where}) by an execution error, not "
                f"by an assertion: `{error}`; the test was seen missing its target, not "
                "observing the behaviour",
            )
        return True, Sufficiency.sufficient, ""
    if subject_passed:
        if not applied:
            # The command was asked to run a test the change creates, and that test was not
            # carried over to the base version, so it had nothing to run there. Passing on both
            # sides is what that looks like, and it is also what a command that ignores the
            # change looks like; the two are not separable here.
            return (
                None,
                Sufficiency.sufficient,
                f"passes on the base version {where} too, where none of the change's test files "
                "could be identified to run: not enough to tell whether it observes the change",
            )
        return (
            False,
            Sufficiency.vacuous,
            f"passes on the base version {where} as well, with the change's test files applied "
            "and the behaviour they measure absent: it reports success either way",
        )
    return (
        False,
        Sufficiency.broken,
        f"fails identically on the base version {where} (exit {control.exit_code}), so no edit "
        "inside the change can make it report success",
    )
