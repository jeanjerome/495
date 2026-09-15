"""One run of an agent: what it was allowed to do, what it consumed, and how it ended.

``Usage`` and ``Cost`` are what the harness read back from the CLI, never a figure it assumed;
``SandboxInfo`` is the isolation the intervention actually ran under, not the one asked for.
"""

from __future__ import annotations

import datetime as dt

from pydantic import Field

from harness495.core.models.base import StrictModel, utcnow
from harness495.core.models.enums import AgentKind, Capability, CostBasis, InterventionStatus, Role


class Usage(StrictModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    requests: int = 0
    context_window: int | None = None
    context_peak_tokens: int | None = None
    context_peak_is_upper_bound: bool = False

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )

    @property
    def context_utilization(self) -> float | None:
        if not self.context_window or self.context_peak_tokens is None:
            return None
        return self.context_peak_tokens / self.context_window

    def add(self, other: Usage) -> Usage:
        peak = max(self.context_peak_tokens or 0, other.context_peak_tokens or 0) or None
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            requests=self.requests + other.requests,
            context_window=other.context_window or self.context_window,
            context_peak_tokens=peak,
            context_peak_is_upper_bound=self.context_peak_is_upper_bound
            or other.context_peak_is_upper_bound,
        )


class Cost(StrictModel):
    usd: float | None = None
    basis: CostBasis = CostBasis.unknown
    source: str = ""


class SandboxInfo(StrictModel):
    backend: str
    network: str = "denied"
    writable_paths: list[str] = Field(default_factory=list)
    detail: str = ""


class AgentIdentity(StrictModel):
    kind: AgentKind
    name: str
    model: str | None = None
    cli_version: str | None = None
    session_id: str | None = None
    effort: str | None = None


class Intervention(StrictModel):
    id: str
    iteration: int
    role: Role
    perspective: str | None = None
    agent: AgentIdentity
    capability: Capability
    allowed_tools: list[str] = Field(default_factory=list)
    sandbox: SandboxInfo
    cwd: str
    timeout_s: int
    status: InterventionStatus = InterventionStatus.running
    started_at: dt.datetime = Field(default_factory=utcnow)
    ended_at: dt.datetime | None = None
    duration_s: float | None = None
    usage: Usage = Field(default_factory=Usage)
    cost: Cost = Field(default_factory=Cost)
    context_ref: str = ""
    transcript_ref: str = ""
    output_ref: str = ""
    exit_code: int | None = None
    error: str | None = None
    version_before: str | None = None
    version_after: str | None = None
    activity: dict[str, int] = Field(default_factory=dict)
    """Tool or command usage counts observed in the transcript (e.g. {"Bash": 5, "Edit": 2})."""
