from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from four95.agents.base import Agent, AgentResult, AgentTask
from four95.core.engine import Engine
from four95.core.models import (
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
from four95.core.store import RunStore
from four95.sandbox import Sandbox

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
    monkeypatch.setenv("FOUR95_WORKTREES_DIR", str(tmp_path / "worktrees"))
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
            "rationale": "requested",
            "verification_ids": ["V1"],
        },
        {
            "id": "R2",
            "statement": "existing tests still pass",
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
        self.producers: list[Callable[[Path], None]] = [good_producer]
        self.reviews: dict[str, list[dict[str, Any]]] = {}
        self.default_review: Callable[[str], dict[str, Any]] = accept_review
        self.calls: list[AgentTask] = []
        self.producer_status = InterventionStatus.completed
        self.producer_not_done: list[str] = []
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
        if task.role is Role.specifier:
            structured = sc.spec
        elif task.role is Role.producer:
            sc.next_producer()(task.cwd)
            text = "changed calc.py and tests/test_calc.py; ran pytest: exit 0"
            structured = {
                "summary": text,
                "files_changed": ["calc.py", "tests/test_calc.py"],
                "commands_run": [],
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
    from four95.core.config import load_config

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
