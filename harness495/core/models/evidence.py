"""What the harness measured itself, and what a reviewer claimed of what it read.

An ``Evidence`` names the kind of measurement, the version it ran on and what it reported;
a ``ReviewVerdict`` carries a reviewer's findings, each one citing what it was observed from.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from pydantic import Field

from harness495.core.models.base import StrictModel, utcnow
from harness495.core.models.enums import RequirementStatus, Severity, Verdict
from harness495.core.models.interventions import SandboxInfo


class EvidenceKind(StrEnum):
    command_result = "command_result"
    scope_check = "scope_check"
    review_verdict = "review_verdict"
    integrity = "integrity"
    instrument_check = "instrument_check"
    """Control run of a failing verification on the base version, to tell instrument from defect."""
    baseline = "baseline"
    """Readiness run of a project command on the base version, before any change exists."""
    suite_check = "suite_check"
    """Whether the existing test suite is, on the change, the suite that passed on the base:
    no test file deleted, no test removed or skipped, no smaller tally printed by the runner."""
    mutation_check = "mutation_check"
    """Whether the verifications that observe the change also constrain it: one mutant, a line
    the change added altered in one stated way, and what the commands reported on it."""
    coverage_check = "coverage_check"
    """Which lines the change adds the verifications execute: the test commands run again under
    the project's coverage tool, and their report crossed with the diff."""
    stability_check = "stability_check"
    """Whether a command reports the same thing twice on the same version: the second run of a
    command a requirement leans on, read against the first."""


class Evidence(StrictModel):
    id: str
    kind: EvidenceKind
    iteration: int
    subject_version: str | None = None
    verification_id: str | None = None
    requirement_ids: list[str] = Field(default_factory=list)
    produced_by: str = "harness"
    command: str | None = None
    exit_code: int | None = None
    expected_exit_code: int | None = None
    passed: bool | None = None
    summary: str = ""
    output_ref: str | None = None
    output_sha256: str | None = None
    duration_s: float | None = None
    sandbox: SandboxInfo | None = None
    created_at: dt.datetime = Field(default_factory=utcnow)


class Finding(StrictModel):
    severity: Severity
    title: str
    detail: str = ""
    file: str | None = None
    line: int | None = None
    requirement_id: str | None = None
    verification_id: str | None = None
    """Set when the finding is about how something is measured rather than about the change."""
    evidence: str = ""
    """What the reviewer observed that supports the finding (file, command output...)."""


class ReviewVerdict(StrictModel):
    intervention_id: str
    perspective: str
    verdict: Verdict
    summary: str = ""
    findings: list[Finding] = Field(default_factory=list)
    requirement_assessment: dict[str, RequirementStatus] = Field(default_factory=dict)
    confidence: float | None = None
    discarded: bool = False
    discard_reason: str = ""
