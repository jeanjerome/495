#!/usr/bin/env python3
"""Produce the run surface images used by the README.

The screenshots are of a real store: a throwaway shell project is created in a temporary
directory, four runs are walked through the engine, and the surface is rendered over the
result. What makes it cheap is the only thing that is not real — the specifier, the producer
and the reviewers are a local object returning fixed answers, so no agent is called and no
quota is spent. Everything around them happens for real: the worktrees, the git commits, the
verification commands, the control runs on the base version, the verdicts, the merge and the
integration check.

That matters because the surface reads a run, not a fixture. A mocked-up screen can show a
badge no state produces, a headline no verdict would write, or a ledger that disagrees with
the checks above it; this one cannot.

The same store is what the recording opens on: :mod:`demo` walks these chapters, leaves the
last one for the camera, and lets the real CLI drive them.

Two images are written by default:

``docs/assets/run-surface.svg``
    The verdict stop of the run the README's console blocks narrate — the walked pipeline,
    the ledger, and what one requirement rests on.
``docs/assets/store-page.svg``
    The store's own page, with the cursor on the run that is waiting for an answer.

``--all`` writes every stop of every run instead, which is how another one is chosen.

Usage::

    ./run.sh --help                              # 495 itself
    python tools/capture/surface.py              # the two README images
    python tools/capture/surface.py --all        # every stop of every run
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness495.agents.base import Agent, AgentResult, AgentTask
from harness495.core.engine import engine as engine_mod
from harness495.core.config import load_config
from harness495.core.engine import Engine
from harness495.core.models import (
    AgentIdentity,
    AgentKind,
    AgentSpec,
    HarnessConfig,
    InterventionStatus,
    ReviewerSpec,
    Role,
    SandboxInfo,
    Usage,
)
from harness495.core.store import RunStore
from harness495.sandbox import Sandbox

REPO = Path(__file__).resolve().parents[2]
ASSETS = REPO / "docs" / "assets"

WIDTH = 140
"""Columns to render at.

Wide enough for the pipeline strip to carry its counts and for every stage to put its detail
beside its list rather than under it, which is the arrangement the README describes.
"""

SHOWN_ROOT = "/Users/you/code/greeter"
"""What the header prints as the project root.

The capture is taken in a temporary directory, and the path it happens to get says nothing to
a reader except that this was a scratch run.
"""

STAGES = ("profile", "spec", "change", "checks", "review", "verdict", "deliver", "integration")


# --------------------------------------------------------------------------- the project

GREETER = """#!/bin/sh
# Print a greeting.
set -eu

name="world"
while [ $# -gt 0 ]; do
    case "$1" in
        -n|--name) name="$2"; shift 2 ;;
        *) echo "greeter: unknown option $1" >&2; exit 2 ;;
    esac
done

printf 'Hello, %s!\\n' "$name"
"""

GREETER_SHOUT = """#!/bin/sh
# Print a greeting.
set -eu

name="world"
shout=0
while [ $# -gt 0 ]; do
    case "$1" in
        -n|--name) name="$2"; shift 2 ;;
        --shout) shout=1; shift ;;
        *) echo "greeter: unknown option $1" >&2; exit 2 ;;
    esac
done

greeting=$(printf 'Hello, %s!' "$name")
if [ "$shout" -eq 1 ]; then
    greeting=$(printf '%s' "$greeting" | tr '[:lower:]' '[:upper:]')
fi
printf '%s\\n' "$greeting"
"""

GREETER_LANG = """#!/bin/sh
# Print a greeting.
set -eu

name="world"
lang="en"
while [ $# -gt 0 ]; do
    case "$1" in
        -n|--name) name="$2"; shift 2 ;;
        --lang) lang="$2"; shift 2 ;;
        *) echo "greeter: unknown option $1" >&2; exit 2 ;;
    esac
done

case "$lang" in
    en) printf 'Hello, %s!\\n' "$name" ;;
    fr) printf 'Bonjour, %s !\\n' "$name" ;;
    es) printf '\\302\\241Hola, %s!\\n' "$name" ;;
    *) echo "greeter: unknown language $lang" >&2; exit 2 ;;
esac
"""

GREETER_REPEAT = """#!/bin/sh
# Print a greeting.
set -eu

name="world"
repeat=1
while [ $# -gt 0 ]; do
    case "$1" in
        -n|--name) name="$2"; shift 2 ;;
        --repeat) repeat="$2"; shift 2 ;;
        *) echo "greeter: unknown option $1" >&2; exit 2 ;;
    esac
done

%s

i=0
while [ "$i" -lt "$repeat" ]; do
    printf 'Hello, %%s!\\n' "$name"
    i=$((i + 1))
done
"""

REPEAT_GUARD = """case "$repeat" in
    ''|*[!0-9]*) echo "greeter: --repeat needs a positive integer" >&2; exit 2 ;;
    0) echo "greeter: --repeat needs a positive integer" >&2; exit 2 ;;
esac"""

CHECK_HEAD = """#!/bin/sh
# The project's own checks. Each subcommand is one behaviour.
set -eu
cd "$(dirname "$0")/.."

expect() {
    got=$(eval "$1")
    if [ "$got" != "$2" ]; then
        echo "FAIL: $1" >&2
        echo "  expected: $2" >&2
        echo "  got:      $got" >&2
        exit 1
    fi
    echo "ok  $1"
}

greet() {
    expect "./scripts/greeter.sh" "Hello, world!"
    expect "./scripts/greeter.sh --name Ada" "Hello, Ada!"
}
"""

CHECK_TAIL = """
case "${1:-all}" in
%s
    *) echo "check: no such check '$1'" >&2; exit 2 ;;
esac
"""


def check_script(subcommand: str = "", body: str = "") -> str:
    """The check script, with one more behaviour covered than the base version has."""
    arms = "    greet) greet ;;\n"
    if subcommand:
        arms += f"    {subcommand}) {subcommand} ;;\n"
    arms += f"    all) greet{'; ' + subcommand if subcommand else ''} ;;"
    return CHECK_HEAD + body + CHECK_TAIL % arms


CHECK = check_script()

CHECK_SHOUT = check_script(
    "shout",
    """
shout() {
    expect "./scripts/greeter.sh --shout" "HELLO, WORLD!"
    expect "./scripts/greeter.sh --name Ada --shout" "HELLO, ADA!"
}
""",
)

CHECK_LANG = check_script(
    "lang",
    """
lang() {
    expect "./scripts/greeter.sh --lang fr" "Bonjour, world !"
    expect "./scripts/greeter.sh --lang es --name Ada" "¡Hola, Ada!"
}
""",
)

CHECK_REPEAT = check_script(
    "repeat",
    """
repeat() {
    expect "./scripts/greeter.sh --repeat 3 | wc -l | tr -d ' '" "3"
    expect "./scripts/greeter.sh --repeat 10 | wc -l | tr -d ' '" "10"
    expect "./scripts/greeter.sh --repeat two 2>/dev/null || echo \\$?" "2"
}
""",
)

PROJECT_TOML = """conventions = [
    "the greeter stays a POSIX shell script: no bashisms",
    "every behaviour has a subcommand in scripts/check.sh",
]
docs = ["README.md"]

[[commands]]
name = "check"
command = "./scripts/check.sh all"
kind = "test"

[[commands]]
name = "syntax"
command = "sh -n scripts/greeter.sh"
kind = "lint"

[scope]
allowed_paths = ["scripts/**", "README.md"]
"""

PROJECT_README = """# greeter

A one-command greeter, kept small on purpose.

```sh
./scripts/greeter.sh --name Ada
```

Conventions: POSIX shell only, and every behaviour gets a subcommand in `scripts/check.sh`.
"""


def git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.name=greeter", "-c", "user.email=greeter@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def make_project(root: Path) -> Path:
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "greeter.sh").write_text(GREETER, encoding="utf-8")
    (root / "scripts" / "check.sh").write_text(CHECK, encoding="utf-8")
    (root / "scripts" / "greeter.sh").chmod(0o755)
    (root / "scripts" / "check.sh").chmod(0o755)
    (root / "README.md").write_text(PROJECT_README, encoding="utf-8")
    (root / ".495").mkdir()
    (root / ".495" / "project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    git("init", "-q", "-b", "main", cwd=root)
    git("add", ".", cwd=root)
    git("commit", "-qm", "greeter: a name, a greeting, and a check for it", cwd=root)
    return root


# --------------------------------------------------------------------------- the scripted agent

Producer = Callable[[Path], tuple[str, list[str]]]

ACCEPT_REVIEW: dict[str, Any] = {
    "verdict": "accept",
    "summary": "nothing to report from this perspective",
    "confidence": 0.9,
    "requirement_assessment": [],
    "findings": [],
}
"""What a perspective the script does not answer for says: the test_quality reviewer a test
to create calls for, when the script only answers for the configured perspectives."""


class Script:
    """What the three roles answer, for one run.

    The producer steps and the reviews are queues: the nth production of a run takes the nth
    step, the nth review from a perspective takes the nth verdict, and the last entry repeats.
    That is enough to script a correction iteration without scripting the engine.
    """

    def __init__(
        self,
        spec: dict[str, Any],
        producers: list[Producer] | None = None,
        reviews: dict[str, list[dict[str, Any]]] | None = None,
        usage: tuple[int, int, int] = (96_400, 3_100, 11),
        cost: float = 0.07,
    ) -> None:
        self.spec = spec
        self.producers = producers or []
        self.reviews = reviews or {}
        self.usage = usage
        self.cost = cost
        self.produced = 0
        self.reviewed: dict[str, int] = {}


class ScriptedAgent(Agent):
    """An agent that answers from a script instead of calling anything."""

    kind = "claude_code"

    def __init__(self, spec: AgentSpec, script: Script, pace: float = 0.0) -> None:
        super().__init__(spec)
        self.script = script
        self.pace = pace
        """Seconds to hold before answering.

        A still needs none of it. A recording needs all of it: an intervention a real agent
        spends minutes on comes back from here in microseconds, and a pipeline that walks its
        eight stops between two frames is shown as a still of its last one.
        """

    def check(self) -> tuple[bool, str]:
        return True, "scripted"

    def run(self, task: AgentTask) -> AgentResult:
        time.sleep(self.pace)
        s = self.script
        structured: dict[str, Any] | None = None
        text = ""
        if task.role is Role.clarifier:
            # An intent the script leaves nothing open in: one read-only round, no stop.
            structured = {"questions": []}
        elif task.role is Role.specifier:
            structured = s.spec
        elif task.role is Role.test_designer:
            structured = {"summary": "", "files_written": [], "tests": [], "not_done": []}
        elif task.role is Role.producer:
            step = s.producers[min(s.produced, len(s.producers) - 1)]
            s.produced += 1
            text, files = step(task.cwd)
            structured = {
                "summary": text,
                "files_changed": files,
                "commands_run": [
                    {"command": "./scripts/check.sh all", "exit_code": 0, "purpose": "self-check"}
                ],
                "not_done": [],
            }
        elif task.role is Role.reviewer:
            perspective = task.prompt.split("Review the change from the perspective: **")[1].split(
                "**"
            )[0]
            n = s.reviewed.get(perspective, 0)
            s.reviewed[perspective] = n + 1
            queue = s.reviews.get(perspective) or [ACCEPT_REVIEW]
            structured = queue[min(n, len(queue) - 1)]
        inp, out, requests = s.usage
        return AgentResult(
            status=InterventionStatus.completed,
            text=text,
            structured=structured,
            usage=Usage(
                input_tokens=inp,
                output_tokens=out,
                requests=requests,
                context_window=200_000,
                context_peak_tokens=int(inp * 0.42),
            ),
            cost_usd=s.cost,
            cost_reported=True,
            identity=AgentIdentity(
                kind=self.spec.kind, name=self.spec.name, model=self.spec.model or "sonnet"
            ),
            sandbox=SandboxInfo(
                backend="seatbelt",
                network="denied",
                writable_paths=[str(task.cwd)],
                detail="macOS sandbox-exec: writes confined to the run worktree",
            ),
            allowed_tools=["Read", "Edit", "Write", "Bash"],
            transcript="(scripted)",
            exit_code=0,
            duration_s=41.0,
        )


# --------------------------------------------------------------------------- specifications


def requirement(
    rid: str, statement: str, kind: str, rationale: str, vids: list[str]
) -> dict[str, Any]:
    return {
        "id": rid,
        "statement": statement,
        "kind": kind,
        "rationale": rationale,
        "verification_ids": vids,
    }


def assessed(*rows: tuple[str, str, str]) -> list[dict[str, Any]]:
    return [{"requirement_id": r, "status": s, "reason": why} for r, s, why in rows]


def review(
    verdict: str,
    summary: str,
    rows: list[dict[str, Any]],
    findings: list[dict[str, Any]] | None = None,
    confidence: float = 0.9,
) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "summary": summary,
        "confidence": confidence,
        "requirement_assessment": rows,
        "findings": findings or [],
    }


SHOUT_SPEC: dict[str, Any] = {
    "requirements": [
        requirement(
            "R1",
            "greeter.sh --shout prints the greeting in uppercase",
            "behaviour",
            "the option the intent asks for",
            ["V1"],
        ),
        requirement(
            "R2",
            "without --shout the greeting is unchanged, with and without a name",
            "non_regression",
            "the option must not alter the default output",
            ["V2"],
        ),
        requirement(
            "R3",
            "greeter.sh remains a valid POSIX shell script",
            "non_regression",
            "the project's own convention",
            ["V3"],
        ),
    ],
    "verifications": [
        {
            "id": "V1",
            "kind": "test",
            "description": "the check script covers --shout on its own and with a name",
            "command": "./scripts/check.sh shout",
            "to_create": True,
            "scenario": {
                "given": ["the greeter as the project ships it"],
                "when": ["greeter.sh --shout is run, once with no name and once with --name Ada"],
                "then": [
                    "the run with no name prints HELLO, WORLD!",
                    "the run with --name Ada prints HELLO, ADA!",
                ],
            },
        },
        {
            "id": "V2",
            "kind": "test",
            "description": "the existing greeting checks, unchanged",
            "command": "./scripts/check.sh greet",
            "to_create": False,
        },
        {
            "id": "V3",
            "kind": "lint",
            "description": "the script still parses under a POSIX shell",
            "command": "sh -n scripts/greeter.sh",
            "to_create": False,
        },
    ],
    "out_of_scope": ["translating the greeting", "reading the name from stdin"],
    "assumptions": ["ASCII names only, which is what tr can upper-case"],
    "allowed_paths": ["scripts/**"],
}

SHOUT_ROWS = assessed(
    ("R1", "satisfied", "V1 exercises --shout alone and with --name, and fails without the change"),
    ("R2", "satisfied", "V2 is untouched and still passes"),
    ("R3", "satisfied", "sh -n parses the script"),
)

SHOUT_REVIEWS = {
    "spec_compliance": [
        review(
            "accept",
            "all three requirements are carried by a check that reports something else without "
            "the change",
            SHOUT_ROWS,
        )
    ],
    "correctness": [
        review(
            "accept",
            "the greeting is assembled once and upper-cased as a whole, so the name and the "
            "punctuation cannot diverge",
            SHOUT_ROWS,
            [
                {
                    "severity": "minor",
                    "title": "tr is byte-oriented",
                    "detail": "a name outside ASCII is passed through unchanged rather than "
                    "upper-cased. The specification assumes ASCII, so this sits inside the "
                    "assumptions rather than against R1.",
                    "file": "scripts/greeter.sh",
                    "line": 18,
                    "requirement_id": "R1",
                    "evidence": "scripts/greeter.sh:18  tr '[:lower:]' '[:upper:]'",
                }
            ],
        )
    ],
    "conventions": [
        review(
            "accept",
            "POSIX shell throughout, and the new behaviour has a check subcommand of its own",
            SHOUT_ROWS,
            [
                {
                    "severity": "info",
                    "title": "the option is not in the README",
                    "detail": "README.md still shows only --name. Documentation is outside the "
                    "allowed paths of this run.",
                    "file": "README.md",
                    "requirement_id": "",
                    "evidence": "README.md:7",
                }
            ],
        )
    ],
}

REPEAT_SPEC: dict[str, Any] = {
    "requirements": [
        requirement(
            "R1",
            "greeter.sh --repeat N prints the greeting N times",
            "behaviour",
            "the option the intent asks for",
            ["V1"],
        ),
        requirement(
            "R2",
            "--repeat rejects a value that is not a positive integer, with exit 2",
            "behaviour",
            "the intent asks for a count, and the script already exits 2 on bad input",
            ["V1"],
        ),
        requirement(
            "R3",
            "without --repeat the greeting is printed once",
            "non_regression",
            "the default must not move",
            ["V2"],
        ),
    ],
    "verifications": [
        {
            "id": "V1",
            "kind": "test",
            "description": "the check script covers a count, and a value that must be refused",
            "command": "./scripts/check.sh repeat",
            "to_create": True,
            "scenario": {
                "given": ["the greeter as the project ships it"],
                "when": ["greeter.sh --repeat 3 is run", "greeter.sh --repeat two is run"],
                "then": [
                    "the run with 3 prints the greeting on three lines",
                    "the run with two exits 2 without printing a greeting",
                ],
            },
        },
        {
            "id": "V2",
            "kind": "test",
            "description": "the existing greeting checks, unchanged",
            "command": "./scripts/check.sh greet",
            "to_create": False,
        },
    ],
    "out_of_scope": ["a delay between repetitions"],
    "assumptions": ["N fits in a shell integer"],
    "allowed_paths": ["scripts/**"],
}

REPEAT_ROWS_BAD = assessed(
    ("R1", "undetermined", "V1 carries R1 and R2 and fails as a whole, so it credits neither"),
    ("R2", "violated", "a count that is not a positive integer is not rejected"),
    ("R3", "satisfied", "one line out with no option"),
)
REPEAT_ROWS_GOOD = assessed(
    ("R1", "satisfied", "three lines out for --repeat 3"),
    ("R2", "satisfied", "a non-numeric count exits 2 before the loop"),
    ("R3", "satisfied", "one line out with no option"),
)

REPEAT_REVIEWS = {
    "spec_compliance": [
        review(
            "reject",
            "R2 is not demonstrated: nothing in the change rejects a count that is not a "
            "positive integer",
            REPEAT_ROWS_BAD,
            [
                {
                    "severity": "blocker",
                    "title": "--repeat takes any string",
                    "detail": "the loop compares $repeat with -lt, so a value that is not a "
                    "number leaves the loop unentered and the script exits 0 rather than with "
                    "the 2 R2 asks for.",
                    "file": "scripts/greeter.sh",
                    "line": 19,
                    "requirement_id": "R2",
                    "evidence": 'scripts/greeter.sh:19  while [ "$i" -lt "$repeat" ]',
                }
            ],
            confidence=0.95,
        ),
        review(
            "accept",
            "both behaviours are now carried by V1, which fails without the guard",
            REPEAT_ROWS_GOOD,
        ),
    ],
    "correctness": [
        review(
            "reject",
            "the guard R2 describes is absent, so the failure mode is the shell's rather than "
            "the script's",
            REPEAT_ROWS_BAD,
        ),
        review(
            "accept",
            "the count is validated once, before the loop, and zero is refused with the same "
            "message as a non-number",
            REPEAT_ROWS_GOOD,
        ),
    ],
    "conventions": [
        review(
            "accept", "POSIX shell throughout, with a check subcommand of its own", REPEAT_ROWS_BAD
        ),
        review(
            "accept", "POSIX shell throughout, with a check subcommand of its own", REPEAT_ROWS_GOOD
        ),
    ],
}

LANG_SPEC: dict[str, Any] = {
    "requirements": [
        requirement(
            "R1",
            "greeter.sh --lang fr prints the French greeting, --lang es the Spanish one",
            "behaviour",
            "the option the intent asks for",
            ["V1"],
        ),
        requirement(
            "R2",
            "each translation is what a native speaker would write",
            "behaviour",
            "the intent asks for a greeting, not for a word-for-word substitution",
            ["V2"],
        ),
        requirement(
            "R3",
            "without --lang the greeting is unchanged",
            "non_regression",
            "the default must not move",
            ["V3"],
        ),
    ],
    "verifications": [
        {
            "id": "V1",
            "kind": "test",
            "description": "the check script pins each language to its expected line",
            "command": "./scripts/check.sh lang",
            "to_create": True,
            "scenario": {
                "given": ["the greeter as the project ships it"],
                "when": ["greeter.sh --lang fr is run", "greeter.sh --lang es --name Ada is run"],
                "then": [
                    "the run in fr prints Bonjour, world !",
                    "the run in es prints ¡Hola, Ada!",
                ],
            },
        },
        {
            "id": "V2",
            "kind": "manual",
            "description": "a speaker of each language reads the greeting",
            "to_create": False,
        },
        {
            "id": "V3",
            "kind": "test",
            "description": "the existing greeting checks, unchanged",
            "command": "./scripts/check.sh greet",
            "to_create": False,
        },
    ],
    "out_of_scope": ["a locale file", "languages beyond the three asked for"],
    "assumptions": ["the three greetings fit on one line each"],
    "allowed_paths": ["scripts/**"],
}

LANG_ROWS = assessed(
    ("R1", "satisfied", "V1 pins each language to its expected line"),
    ("R2", "undetermined", "no command can decide how a greeting reads"),
    ("R3", "satisfied", "V3 is untouched and still passes"),
)

LANG_REVIEWS = {
    "spec_compliance": [
        review(
            "undetermined",
            "R1 and R3 hold; R2 rests on V2, which is a human reading and was never run",
            LANG_ROWS,
            confidence=0.8,
        )
    ],
    "correctness": [
        review(
            "accept",
            "the case arms are exhaustive and an unknown language exits 2 rather than falling "
            "through to the default",
            LANG_ROWS,
        )
    ],
    "conventions": [
        review(
            "accept",
            "POSIX shell throughout; the non-ASCII characters are written as octal escapes "
            "rather than pasted in",
            LANG_ROWS,
            [
                {
                    "severity": "minor",
                    "title": "the French space before ! is a plain space",
                    "detail": "typography asks for a narrow no-break space there. Whether that "
                    "matters is exactly what V2 was meant to answer.",
                    "file": "scripts/greeter.sh",
                    "line": 17,
                    "requirement_id": "R2",
                    "evidence": "scripts/greeter.sh:17  printf 'Bonjour, %s !\\n'",
                }
            ],
        )
    ],
}

STDIN_SPEC: dict[str, Any] = {
    "requirements": [
        requirement(
            "R1",
            "with no --name and a name on stdin, greeter.sh greets that name",
            "behaviour",
            "the behaviour the intent asks for",
            ["V1"],
        ),
        requirement(
            "R2",
            "with no --name and nothing on stdin, the greeting stays Hello, world!",
            "non_regression",
            "an empty pipe must not change the default",
            ["V1", "V2"],
        ),
    ],
    "verifications": [
        {
            "id": "V1",
            "kind": "test",
            "description": "the check script pipes a name in, and pipes nothing in",
            "command": "./scripts/check.sh stdin",
            "to_create": True,
            "scenario": {
                "given": ["the greeter as the project ships it"],
                "when": [
                    "greeter.sh is run with no --name and a name piped in",
                    "greeter.sh is run with no --name and nothing piped in",
                ],
                "then": [
                    "the piped name is the one greeted",
                    "the run with nothing piped in prints the default greeting",
                ],
            },
        },
        {
            "id": "V2",
            "kind": "test",
            "description": "the existing greeting checks, unchanged",
            "command": "./scripts/check.sh greet",
            "to_create": False,
        },
    ],
    "out_of_scope": ["reading more than one name"],
    "assumptions": ["the first line of stdin is the whole name"],
    "allowed_paths": ["scripts/**"],
}


# --------------------------------------------------------------------------- what each run does


def write_change(greeter: str, check: str) -> Producer:
    def produce(cwd: Path) -> tuple[str, list[str]]:
        (cwd / "scripts" / "greeter.sh").write_text(greeter, encoding="utf-8")
        (cwd / "scripts" / "check.sh").write_text(check, encoding="utf-8")
        return "", ["scripts/greeter.sh", "scripts/check.sh"]

    return produce


def summarised(producer: Producer, summary: str) -> Producer:
    def produce(cwd: Path) -> tuple[str, list[str]]:
        _, files = producer(cwd)
        return summary, files

    return produce


SHOUT_PRODUCER = summarised(
    write_change(GREETER_SHOUT, CHECK_SHOUT),
    "added --shout to greeter.sh, upper-casing the assembled greeting, and a shout subcommand "
    "to check.sh covering it with and without a name",
)
LANG_PRODUCER = summarised(
    write_change(GREETER_LANG, CHECK_LANG),
    "added --lang with en, fr and es branches to greeter.sh, and a lang subcommand to check.sh "
    "pinning each one to its expected line",
)
REPEAT_PRODUCER_BAD = summarised(
    write_change(GREETER_REPEAT % "", CHECK_REPEAT),
    "added --repeat to greeter.sh, looping over the printf, and a repeat subcommand to check.sh",
)
REPEAT_PRODUCER_GOOD = summarised(
    write_change(GREETER_REPEAT % REPEAT_GUARD, CHECK_REPEAT),
    "refused a --repeat value that is not a positive integer before the loop, with exit 2, as "
    "R2 requires",
)


@dataclass(frozen=True)
class Chapter:
    """One run the store holds, and what it took to leave it where it stands.

    A chapter is the whole of a run: the intent that opened it, what the three roles answer
    while it walks, the gate it is left standing at or the answer that let it past, and
    whether it was taken into the branch it was cut from. The images and the recording read
    the same four, so a screenshot and a frame are of the same store.
    """

    run_id: str
    intent: str
    spec: dict[str, Any]
    producers: list[Producer]
    reviews: dict[str, list[dict[str, Any]]]
    usage: tuple[int, int, int] = (96_400, 3_100, 11)
    cost: float = 0.07
    gated: bool = False
    """The specification gate is left on for this one, so it stops there and stays."""
    decision: tuple[str, str] | None = None
    """An answer given mid-walk, with the note recorded beside it."""
    merged: bool = False

    def script(self) -> Script:
        """A script of its own: the queues one holds are spent as the run walks."""
        return Script(self.spec, self.producers, self.reviews, self.usage, self.cost)


SHOUT = Chapter(
    "run-15ebe4f8ec",
    "Add a --shout option to the greeter: it prints the greeting in uppercase. "
    "Extend the check script to cover the option, both on its own and with a name.",
    SHOUT_SPEC,
    [SHOUT_PRODUCER],
    SHOUT_REVIEWS,
    merged=True,
)

REPEAT = Chapter(
    "run-9c02b7a41d",
    "Add a --repeat N option printing the greeting N times. A value that is not a positive "
    "integer must be refused with exit 2.",
    REPEAT_SPEC,
    [REPEAT_PRODUCER_BAD, REPEAT_PRODUCER_GOOD],
    REPEAT_REVIEWS,
    usage=(88_700, 4_200, 13),
    cost=0.09,
)

# R2 rests on a human reading, which is a gap the gate raises whatever auto-approve says.
LANG = Chapter(
    "run-4e7fd1a8b3",
    "Add a --lang option choosing the language of the greeting: en, fr or es, defaulting to "
    "en. Keep the default output exactly as it is.",
    LANG_SPEC,
    [LANG_PRODUCER],
    LANG_REVIEWS,
    usage=(102_300, 3_600, 12),
    cost=0.08,
    decision=("approve_with_gaps", "the translations are mine to read"),
)

STDIN = Chapter(
    "run-b81c60d52f",
    "When no --name is given and something is piped in, greet the name read from stdin.",
    STDIN_SPEC,
    [],
    {},
    usage=(71_500, 2_800, 9),
    cost=0.05,
    gated=True,
)

CHAPTERS = (SHOUT, REPEAT, LANG, STDIN)
"""One of each thing a store holds: one delivered and merged, one delivered and waiting to be
taken, one stopped on a requirement no command can decide, one waiting at the gate."""

RUN_IDS = tuple(c.run_id for c in CHAPTERS)

AGES: dict[str, tuple[dt.timedelta, dt.timedelta]] = {
    SHOUT.run_id: (dt.timedelta(hours=3, minutes=12), dt.timedelta(hours=2, minutes=48)),
    REPEAT.run_id: (dt.timedelta(hours=1, minutes=55), dt.timedelta(hours=1, minutes=6)),
    LANG.run_id: (dt.timedelta(minutes=41), dt.timedelta(minutes=9)),
    STDIN.run_id: (dt.timedelta(minutes=6), dt.timedelta(minutes=4)),
}


def pin_ids(ids: Iterable[str]) -> None:
    """Hand out these run ids before the engine invents its own.

    Fixed ids are what lets a capture and the console block quoted beside it name the same
    run. Anything past the list, and anything that is not a run, is named as usual.
    """
    queue = iter(ids)
    invented: Callable[[str], str] = engine_mod.new_id  # type: ignore[attr-defined]

    def new_id(prefix: str) -> str:
        return next(queue, invented(prefix)) if prefix == "run" else invented(prefix)

    engine_mod.new_id = new_id  # type: ignore[attr-defined]


def scripted(held: dict[str, Script], pace: float = 0.0) -> Callable[[AgentSpec, Sandbox], Agent]:
    """An agent factory reading whichever script is held right now.

    The engine asks for an agent per intervention and says which role it is for, never which
    run it is walking, so the chapter being walked is held beside the factory rather than
    passed to it.
    """

    def factory(spec: AgentSpec, sandbox: Sandbox) -> Agent:
        return ScriptedAgent(spec, held["script"], pace)

    return factory


def build(
    project: Path,
    cfg: HarnessConfig,
    store: RunStore,
    chapters: Sequence[Chapter] = CHAPTERS,
    pace: float = 0.0,
) -> None:
    """Walk the chapters into the store, each one to where it is meant to stand."""
    held: dict[str, Script] = {}
    engine = Engine(store, sandbox=Sandbox(), agent_factory=scripted(held, pace))
    pin_ids(c.run_id for c in chapters)

    for chapter in chapters:
        held["script"] = chapter.script()
        config = cfg
        if chapter.gated:
            config = cfg.model_copy(deep=True)
            config.auto_approve = False
        run = engine.create_run(chapter.intent, project, config)
        engine.run(run.id)
        if chapter.decision is not None:
            engine.decide(run.id, *chapter.decision)
            engine.run(run.id)
        if chapter.merged:
            engine.merge_delivery(run.id, how="fast-forward", rerun_verifications=True)
        report(store, run.id)


def report(store: RunStore, run_id: str) -> None:
    run = store.load(run_id)
    pending = run.pending_decision.kind.value if run.pending_decision else "-"
    print(
        f"{run.id}  {run.status.value:18} outcome={str(run.result.outcome or '-'):13} "
        f"iteration {run.iteration_number}  pending {pending:14} {run.consumption.cost_usd:.2f} USD"
    )
    for warning in run.warnings:
        print(f"   warning: {warning}")


def dress(store: RunStore, root: str | None = SHOWN_ROOT) -> None:
    """Give the store an age, and a plausible project root, in place, before rendering.

    The listing answers "how long since this moved" and the header prints where the project
    is. Four runs created in the same second under a temporary path answer both with noise.

    A recording keeps the root it was built at: what is only read can be told where it lives,
    but a run that is about to be advanced, merged and checked has to say where it really is.
    """
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    for run_dir in sorted(store.runs_dir.iterdir()):
        path = run_dir / "run.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        created, updated = AGES.get(str(data["id"]), (dt.timedelta(0), dt.timedelta(0)))
        data["created_at"] = (now - created).isoformat().replace("+00:00", "Z")
        data["updated_at"] = (now - updated).isoformat().replace("+00:00", "Z")
        if root is not None:
            data["project_root"] = root
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- rendering


def renderer(store: RunStore, project: Path, out: Path, width: int) -> Callable[..., None]:
    """A function that renders one view and writes it out.

    The shell is built here rather than through :func:`harness495.interfaces.tui.watch`
    because a still render is read-only by construction — every control would drop off the
    screen — and because a capture of the listing has to say which row the cursor is on.
    """
    from harness495.interfaces.tui import Shell, StoreDriver, build_console
    from harness495.interfaces.tui.source import StoreSource

    out.mkdir(parents=True, exist_ok=True)

    def render(name: str, run_id: str | None, view: str, cursor: int = 0) -> None:
        console = build_console(width, record=True)
        shell = Shell(
            StoreSource(store),
            console,
            animated=False,
            driver=StoreDriver(store, project=project),
        )
        if run_id is not None:
            shell.select(run_id)
        shell.view = view
        shell.cursor = cursor
        console.print(shell.flow(console.width))
        subject = run_id or "the store"
        console.save_svg(str(out / f"{name}.svg"), title=f"495 {subject} · {view}")
        print(f"wrote {out / f'{name}.svg'}")

    return render


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all",
        action="store_true",
        help="write every stop of every run, instead of the two README images",
    )
    parser.add_argument("--out", type=Path, default=ASSETS, help="where to write the SVGs")
    parser.add_argument("--width", type=int, default=WIDTH, help="columns to render at")
    args = parser.parse_args()

    work = Path(tempfile.mkdtemp(prefix="495-capture-"))
    try:
        os.environ["HARNESS495_WORKTREES_DIR"] = str(work / "worktrees")
        project = make_project(work / "greeter")

        cfg = load_config(project)
        cfg.agents["default"] = AgentSpec(
            name="default", kind=AgentKind.claude_code, model="sonnet"
        )
        cfg.roles.reviewers = [
            ReviewerSpec(perspective="spec_compliance"),
            ReviewerSpec(perspective="correctness"),
            ReviewerSpec(perspective="conventions"),
        ]
        cfg.roles.test_designer = None  # the scripted producer writes the tests it is given
        cfg.budget.max_cost_usd = 5.0
        cfg.budget.max_iterations = 3
        cfg.sandbox.backend = "seatbelt"
        cfg.auto_approve = True

        store = RunStore(project / ".495")
        build(project, cfg, store)
        dress(store)

        render = renderer(store, project, args.out, args.width)
        if args.all:
            for run_id in RUN_IDS:
                for stage in STAGES:
                    render(f"{run_id}-{stage}", run_id, stage)
            for index in range(len(RUN_IDS)):
                render(f"store-page-{index}", None, "runs", index)
        else:
            render("run-surface", RUN_IDS[0], "verdict")
            render("store-page", None, "runs", cursor=RUN_IDS.index("run-4e7fd1a8b3"))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
