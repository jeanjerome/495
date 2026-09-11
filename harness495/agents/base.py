"""Agent protocol shared by the Claude Code, Codex and OpenAI-compatible adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness495.core.models import (
    AgentIdentity,
    AgentSpec,
    Capability,
    InterventionStatus,
    Role,
    SandboxInfo,
    Usage,
)


@dataclass
class AgentTask:
    role: Role
    capability: Capability
    system_prompt: str
    prompt: str
    cwd: Path
    timeout_s: int
    max_budget_usd: float | None = None
    output_schema: dict[str, Any] | None = None
    scratch_dir: Path | None = None
    stop_check: Callable[[], bool] | None = None
    env: dict[str, str] = field(default_factory=dict)
    max_steps: int = 60


@dataclass
class AgentResult:
    status: InterventionStatus
    text: str
    structured: dict[str, Any] | None
    usage: Usage
    cost_usd: float | None
    cost_reported: bool
    identity: AgentIdentity
    sandbox: SandboxInfo
    allowed_tools: list[str]
    transcript: str
    exit_code: int | None
    error: str | None = None
    duration_s: float = 0.0
    argv: list[str] = field(default_factory=list)
    activity: dict[str, int] = field(default_factory=dict)


class Agent:
    """One agent backend. Instances are cheap and stateless between tasks."""

    kind: str = "base"

    def __init__(self, spec: AgentSpec) -> None:
        self.spec = spec

    def check(self) -> tuple[bool, str]:
        """Return (available, detail) without spending tokens."""
        raise NotImplementedError

    def run(self, task: AgentTask) -> AgentResult:
        raise NotImplementedError


class AgentError(RuntimeError):
    pass
