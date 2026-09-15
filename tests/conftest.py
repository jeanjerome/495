from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from harness495.agents.base import Agent, AgentResult, AgentTask
from harness495.core.engine import Engine
from harness495.core.engine.checks import Reading
from harness495.core.engine.services import RunServices
from harness495.core.models import (
    AgentIdentity,
    AgentKind,
    AgentSpec,
    Event,
    Evidence,
    EvidenceKind,
    HarnessConfig,
    Intent,
    InterventionStatus,
    Iteration,
    Requirement,
    RequirementKind,
    ReviewerSpec,
    Role,
    Run,
    RunStatus,
    SandboxInfo,
    Usage,
    Verification,
    VerificationKind,
    Version,
    new_id,
)
from harness495.core.store import RunStore
from harness495.sandbox import Sandbox
from harness495.sandbox.base import CommandResult, ExecRequest

SAMPLE_MODULE = '''"""Tiny calculator module used by the tests."""


def add(a: int, b: int) -> int:
    return a + b
'''

SAMPLE_TEST = """from calc import add


def test_add():
    assert add(2, 3) == 5
"""


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def sample_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A git repository with a python module, a passing test and a project.toml."""
    monkeypatch.setenv("HARNESS495_WORKTREES_DIR", str(tmp_path / "worktrees"))
    root = tmp_path / "proj"
    root.mkdir()
    (root / "calc.py").write_text(SAMPLE_MODULE, encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_calc.py").write_text(SAMPLE_TEST, encoding="utf-8")
    (root / "tests" / "conftest.py").write_text(
        "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# sample\n\nConventions: keep functions typed.\n", encoding="utf-8"
    )
    (root / ".495").mkdir()
    (root / ".495" / "project.toml").write_text(
        f'''conventions = ["functions are type annotated"]

[[commands]]
name = "test"
command = "{sys.executable} -m pytest -q -p no:cacheprovider"
kind = "test"

[scope]
allowed_paths = ["calc.py", "tests/**"]
''',
        encoding="utf-8",
    )
    git("init", "-q", "-b", "main", cwd=root)
    git("-c", "user.name=t", "-c", "user.email=t@t", "add", ".", cwd=root)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init", cwd=root)
    return root


SPEC_JSON: dict[str, Any] = {
    "requirements": [
        {
            "id": "R1",
            "statement": "calc.subtract(a, b) returns a - b",
            "kind": "behaviour",
            "rationale": "requested",
            "verification_ids": ["V1"],
        },
        {
            "id": "R2",
            "statement": "existing tests still pass",
            "kind": "non_regression",
            "rationale": "non-regression",
            "verification_ids": ["V2"],
        },
    ],
    "verifications": [
        {
            "id": "V1",
            "kind": "test",
            "description": "a test exercising subtract with positive and negative values",
            "command": f"{sys.executable} -m pytest -q -p no:cacheprovider tests/test_calc.py",
            "to_create": True,
            "scenario": {
                "given": ["the calc module"],
                "when": ["subtract(5, 3) and subtract(3, 5) are called"],
                "then": ["they return 2 and -2"],
            },
        },
        {
            "id": "V2",
            "kind": "test",
            "description": "full test suite",
            "command": f"{sys.executable} -m pytest -q -p no:cacheprovider",
            "to_create": False,
        },
    ],
    "out_of_scope": ["multiplication"],
    "assumptions": ["integers only"],
    "allowed_paths": ["calc.py", "tests/**"],
}


def accept_review(perspective: str) -> dict[str, Any]:
    return {
        "verdict": "accept",
        "summary": f"{perspective}: looks good",
        "confidence": 0.9,
        "requirement_assessment": [
            {"requirement_id": "R1", "status": "satisfied", "reason": "test present"},
            {"requirement_id": "R2", "status": "satisfied", "reason": "suite passes"},
        ],
        "findings": [],
    }


def reject_review(perspective: str) -> dict[str, Any]:
    return {
        "verdict": "reject",
        "summary": f"{perspective}: subtract is wrong",
        "confidence": 0.8,
        "requirement_assessment": [
            {"requirement_id": "R1", "status": "violated", "reason": "returns a + b"},
            {"requirement_id": "R2", "status": "satisfied", "reason": "suite passes"},
        ],
        "findings": [
            {
                "severity": "major",
                "title": "subtract adds instead of subtracting",
                "detail": "use a - b",
                "file": "calc.py",
                "line": 8,
                "requirement_id": "R1",
                "evidence": "calc.py:8 `return a + b`",
            }
        ],
    }


DESIGNED_TEST = """from calc import subtract


def test_subtract():
    assert subtract(5, 3) == 2
    assert subtract(3, 5) == -2
"""


def design_tests(cwd: Path) -> None:
    """What the scripted test designer writes: the test of V1, and nothing else."""
    (cwd / "tests" / "test_subtract.py").write_text(DESIGNED_TEST, encoding="utf-8")


def good_producer(cwd: Path) -> None:
    (cwd / "calc.py").write_text(
        SAMPLE_MODULE + "\n\ndef subtract(a: int, b: int) -> int:\n    return a - b\n",
        encoding="utf-8",
    )
    (cwd / "tests" / "test_calc.py").write_text(
        SAMPLE_TEST
        + "\n\nfrom calc import subtract\n\n\ndef test_subtract():\n    assert subtract(5, 3) == 2\n    assert subtract(0, 4) == -4\n",
        encoding="utf-8",
    )


def bad_producer(cwd: Path) -> None:
    (cwd / "calc.py").write_text(
        SAMPLE_MODULE + "\n\ndef subtract(a: int, b: int) -> int:\n    return a + b\n",
        encoding="utf-8",
    )
    (cwd / "tests" / "test_calc.py").write_text(
        SAMPLE_TEST
        + "\n\nfrom calc import subtract\n\n\ndef test_subtract():\n    assert subtract(5, 5) == 10\n",
        encoding="utf-8",
    )


class Scenario:
    """Scripted behaviour for the fake agent, keyed by role/perspective and call count."""

    def __init__(self) -> None:
        self.spec: dict[str, Any] = json.loads(json.dumps(SPEC_JSON))
        self.clarify_rounds: list[dict[str, Any]] = [{"questions": []}]
        """One entry per clarification round; the default is an intent with nothing left to
        decide, so a scenario that says nothing about clarification pays one round and no stop."""
        self.clarifier_fails = False
        self.designers: list[Callable[[Path], None]] = [design_tests]
        self.designer_not_done: list[str] = []
        self.producers: list[Callable[[Path], None]] = [good_producer]
        self.reviews: dict[str, list[dict[str, Any]]] = {}
        self.default_review: Callable[[str], dict[str, Any]] = accept_review
        self.calls: list[AgentTask] = []
        self.producer_status = InterventionStatus.completed
        self.producer_not_done: list[str] = []
        self.producer_commands: list[dict[str, Any]] = []
        self.reviewer_hook: Callable[[AgentTask], None] | None = None
        self.usage = Usage(
            input_tokens=1000,
            output_tokens=200,
            requests=2,
            context_window=200000,
            context_peak_tokens=1200,
        )
        self.cost = 0.01

    def next_producer(self) -> Callable[[Path], None]:
        n = sum(1 for t in self.calls if t.role is Role.producer) - 1
        return self.producers[min(n, len(self.producers) - 1)]

    def next_designer(self) -> Callable[[Path], None]:
        n = sum(1 for t in self.calls if t.role is Role.test_designer) - 1
        return self.designers[min(n, len(self.designers) - 1)]

    def next_clarify(self) -> dict[str, Any]:
        n = sum(1 for t in self.calls if t.role is Role.clarifier) - 1
        if n >= len(self.clarify_rounds):
            return {"questions": []}
        return self.clarify_rounds[n]

    def next_review(self, perspective: str) -> dict[str, Any]:
        n = sum(1 for t in self.calls if t.role is Role.reviewer and perspective in t.prompt) - 1
        queue = self.reviews.get(perspective)
        if queue:
            return queue[min(n, len(queue) - 1)]
        return self.default_review(perspective)


class FakeAgent(Agent):
    kind = "fake"

    def __init__(self, spec: AgentSpec, scenario: Scenario) -> None:
        super().__init__(spec)
        self.scenario = scenario

    def check(self) -> tuple[bool, str]:
        return True, "fake"

    def run(self, task: AgentTask) -> AgentResult:
        sc = self.scenario
        sc.calls.append(task)
        structured: dict[str, Any] | None = None
        text = ""
        status = InterventionStatus.completed
        if task.role is Role.clarifier:
            structured = sc.next_clarify()
            if sc.clarifier_fails:
                status = InterventionStatus.failed
        elif task.role is Role.specifier:
            structured = sc.spec
        elif task.role is Role.test_designer:
            sc.next_designer()(task.cwd)
            text = "wrote tests/test_subtract.py; ran pytest: exit 1 (ImportError)"
            structured = {
                "summary": text,
                "files_written": ["tests/test_subtract.py"],
                "tests": [{"verification_id": "V1", "file": "tests/test_subtract.py"}],
                "not_done": list(sc.designer_not_done),
            }
        elif task.role is Role.producer:
            sc.next_producer()(task.cwd)
            text = "changed calc.py and tests/test_calc.py; ran pytest: exit 0"
            structured = {
                "summary": text,
                "files_changed": ["calc.py", "tests/test_calc.py"],
                "commands_run": list(sc.producer_commands),
                "not_done": list(sc.producer_not_done),
            }
            status = sc.producer_status
        elif task.role is Role.reviewer:
            perspective = task.prompt.split("Review the change from the perspective: **")[1].split(
                "**"
            )[0]
            if sc.reviewer_hook is not None:
                sc.reviewer_hook(task)
            structured = sc.next_review(perspective)
        return AgentResult(
            status=status,
            text=text,
            structured=structured,
            usage=sc.usage,
            cost_usd=sc.cost,
            cost_reported=True,
            identity=AgentIdentity(
                kind=self.spec.kind, name=self.spec.name, model=self.spec.model or "fake-model"
            ),
            sandbox=SandboxInfo(backend="fake"),
            allowed_tools=["fake"],
            transcript="fake transcript",
            exit_code=0,
        )


@pytest.fixture
def scenario() -> Scenario:
    return Scenario()


@pytest.fixture
def config(sample_project: Path) -> HarnessConfig:
    from harness495.core.config import load_config

    cfg = load_config(sample_project)
    cfg.agents["default"] = AgentSpec(
        name="default", kind=AgentKind.claude_code, model="fake-model"
    )
    cfg.roles.reviewers = [
        ReviewerSpec(perspective="spec_compliance"),
        ReviewerSpec(perspective="correctness"),
    ]
    cfg.budget.max_cost_usd = 5.0
    cfg.budget.intervention_timeout_s = 60
    cfg.budget.command_timeout_s = 120
    cfg.auto_approve = True
    return cfg


@pytest.fixture
def engine_factory(sample_project: Path, scenario: Scenario) -> Callable[..., Engine]:
    def make(**kwargs: Any) -> Engine:
        store = RunStore(sample_project / ".495")
        return Engine(
            store,
            sandbox=Sandbox(),
            agent_factory=lambda spec, sandbox: FakeAgent(spec, scenario),
            **kwargs,
        )

    return make


# ----------------------------------------------------- reaching a region without the engine


@dataclass
class Reply:
    """What the scripted sandbox answers for one command, and what running it leaves behind.

    ``writes`` are the files the command creates under its working directory — a coverage
    report, a build artefact — so that a region reading what a command wrote reads a real file
    it found itself rather than a value handed to it.
    """

    exit_code: int | None = 0
    output: str = ""
    timed_out: bool = False
    writes: dict[str, str] = field(default_factory=dict)


class FakeSandbox(Sandbox):
    """A sandbox answering from a script, keeping every request it was given.

    A stop the requester asked for is honoured the way the real one honours it: the request
    carries the check, and the result comes back interrupted. What a region does with an
    interrupted command is then measured rather than described.
    """

    name = "fake"

    def __init__(self, replies: list[Reply] | None = None) -> None:
        self.replies = list(replies or [])
        self.requests: list[ExecRequest] = []

    @property
    def commands(self) -> list[str]:
        return [r.command for r in self.requests]

    def run(self, req: ExecRequest) -> CommandResult:
        self.requests.append(req)
        if req.stop_check is not None and req.stop_check():
            return CommandResult(req.command, None, "", 0.1, interrupted=True)
        reply = self.replies.pop(0) if self.replies else Reply()
        for name, text in reply.writes.items():
            path = req.cwd / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return CommandResult(
            command=req.command,
            exit_code=None if reply.timed_out else reply.exit_code,
            output=reply.output,
            duration_s=0.1,
            timed_out=reply.timed_out,
        )


class RecordingStore(RunStore):
    """A run store that keeps what was written through it, under the reference it returned.

    A check records where it put a command's output; a test reads it back by that reference
    rather than by reconstructing the path, which is what the engine's surfaces do too.
    """

    def __init__(self, state_dir: Path) -> None:
        super().__init__(state_dir)
        self.written: dict[str, str] = {}

    def write_text(self, run_id: str, ref: str, text: str) -> str:
        out = super().write_text(run_id, ref, text)
        self.written[out] = text
        return out


class RecordingServices(RunServices):
    """The services a region of the engine works through, with what it did to the world kept.

    The store is real and the worktree is a real repository, so a region persists and reads
    back exactly as it does behind the engine; only the commands are scripted. The events, the
    warnings and the statuses are recorded rather than dispatched, since the region under
    measure is what raised them and no state machine is there to answer.
    """

    def __init__(self, state_dir: Path, worktree: Path, replies: list[Reply] | None = None) -> None:
        self.recording_store = RecordingStore(state_dir)
        self.fake_sandbox = FakeSandbox(replies)
        self.tree = worktree
        self.events: list[Event] = []
        self.warnings: list[str] = []
        self.statuses: list[RunStatus] = []
        self.stop_requested = False
        super().__init__(
            store=self.recording_store,
            sandbox=lambda: self.fake_sandbox,
            emit=self._emit,
            warn=self._warn,
            worktree=lambda run: self.tree,
            stop_check=lambda run: self._stopped,
            set_status=self._set_status,
        )

    def _emit(
        self, run: Run, type_: str, message: str = "", data: dict[str, Any] | None = None
    ) -> None:
        event = Event(run_id=run.id, type=type_, message=message, data=data or {})
        self.recording_store.append_event(event)
        self.events.append(event)

    def _warn(self, run: Run, message: str) -> None:
        if message not in run.warnings:
            run.warnings.append(message)
        self.warnings.append(message)
        self._emit(run, "warning", message)

    def _stopped(self) -> bool:
        return self.stop_requested

    def _set_status(self, run: Run, status: RunStatus) -> None:
        run.status = status
        self.recording_store.save(run)
        self.statuses.append(status)


@dataclass
class Measured:
    """What a check reported when it was reached on its own.

    A stop the requester asked for leaves a region by ``KeyboardInterrupt`` — the state machine
    is what decides where the run goes next — so it is an outcome recorded here rather than an
    error that escapes the scenario.
    """

    evidence: list[Evidence] = field(default_factory=list)
    proposals: dict[str, str] = field(default_factory=dict)
    interrupted: bool = False


def measure(check: Callable[[], Reading]) -> Measured:
    """Run one check and keep what it produced, the stop it raised included."""
    try:
        reading = check()
    except KeyboardInterrupt:
        return Measured(interrupted=True)
    return Measured(evidence=list(reading.evidence), proposals=dict(reading.proposals))


@dataclass
class Region:
    """A produced version, and what a check of ``core/engine/checks/`` measures it through.

    ``root`` is a git repository holding both commits, standing in for the run's worktree;
    ``run`` carries the iteration the version belongs to. What the engine hands a region once
    a version has been produced, with no phase having run to put it there.
    """

    root: Path
    run: Run
    services: RecordingServices

    @property
    def iteration(self) -> Iteration:
        it = self.run.current_iteration
        assert it is not None
        return it

    @property
    def head(self) -> str:
        assert self.iteration.version is not None
        return self.iteration.version.head_commit or ""

    @property
    def base(self) -> str:
        assert self.iteration.version is not None
        return self.iteration.version.base_commit

    def answers(self, *replies: Reply) -> None:
        """What the commands of this version report, in the order the region runs them."""
        self.services.fake_sandbox.replies.extend(replies)

    def ran_command(
        self,
        vid: str,
        *,
        passed: bool = True,
        seconds: float = 1.0,
        output: str = "",
        iteration: int | None = None,
    ) -> Evidence:
        """A command result of this run, as the verifications stage would have left it:
        the evidence on the run and under the iteration, and its output in the store."""
        v = self.run.spec.verification(vid)
        n = self.iteration.n if iteration is None else iteration
        eid = new_id("ev")
        ev = Evidence(
            id=eid,
            kind=EvidenceKind.command_result,
            iteration=n,
            subject_version=self.head,
            verification_id=vid,
            command=v.command if v is not None else None,
            exit_code=0 if passed else 1,
            passed=passed,
            summary=f"{vid} exit {0 if passed else 1}",
            duration_s=seconds,
            output_ref=self.services.store.write_text(
                self.run.id,
                str(self.services.store.evidence_dir(self.run.id, eid) / "output.txt"),
                output,
            ),
        )
        self.run.evidence.append(ev)
        self.run.iterations[n - 1].evidence_ids.append(ev.id)
        return ev

    def baseline(self, command: str, output: str) -> Evidence:
        """What the command printed on the base version, as the gate of the run left it."""
        eid = new_id("ev")
        ev = Evidence(
            id=eid,
            kind=EvidenceKind.baseline,
            iteration=0,
            command=command,
            passed=True,
            summary="baseline",
            output_ref=self.services.store.write_text(
                self.run.id,
                str(self.services.store.evidence_dir(self.run.id, eid) / "output.txt"),
                output,
            ),
        )
        self.run.evidence.append(ev)
        return ev

    def verification(
        self,
        vid: str,
        *,
        command: str | None = "python -m pytest -q",
        kind: VerificationKind = VerificationKind.test,
        requirement: str | None = None,
        requirement_kind: RequirementKind = RequirementKind.behaviour,
    ) -> Verification:
        """A verification of the specification, and the requirement leaning on it, if any."""
        v = Verification(id=vid, kind=kind, description=vid, command=command)
        self.run.spec.verifications.append(v)
        if requirement is not None:
            existing = self.run.spec.requirement(requirement)
            if existing is None:
                self.run.spec.requirements.append(
                    Requirement(
                        id=requirement,
                        statement=requirement,
                        kind=requirement_kind,
                        verification_ids=[vid],
                    )
                )
            else:
                existing.verification_ids.append(vid)
        return v


def _write_files(root: Path, files: dict[str, str | None]) -> None:
    for name, text in files.items():
        path = root / name
        if text is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


BASE_TREE: dict[str, str | None] = {"calc.py": SAMPLE_MODULE, "tests/test_calc.py": SAMPLE_TEST}


@pytest.fixture
def produced_version(tmp_path: Path) -> Callable[..., Region]:
    """Build the version a check measures: a repository with a base commit and a head commit.

    ``head`` is what the change writes over :data:`BASE_TREE` — a path mapped to ``None`` is
    deleted. Left out, the two commits are the same and the change adds nothing.
    """

    def make(head: dict[str, str | None] | None = None) -> Region:
        root = tmp_path / "tree"
        root.mkdir()
        _write_files(root, dict(BASE_TREE))
        git("init", "-q", "-b", "main", cwd=root)
        git("-c", "user.name=t", "-c", "user.email=t@t", "add", ".", cwd=root)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base", cwd=root)
        base_commit = git("rev-parse", "HEAD", cwd=root).strip()
        head_commit = base_commit
        if head:
            _write_files(root, head)
            git("-c", "user.name=t", "-c", "user.email=t@t", "add", "-A", cwd=root)
            git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "change", cwd=root)
            head_commit = git("rev-parse", "HEAD", cwd=root).strip()
        run = Run(
            id=new_id("run"),
            intent=Intent(text="a change"),
            project_root=str(root),
            worktree=str(root),
            status=RunStatus.produced,
        )
        run.iterations.append(
            Iteration(n=1, version=Version(base_commit=base_commit, head_commit=head_commit))
        )
        return Region(root, run, RecordingServices(tmp_path / "state", root))

    return make
