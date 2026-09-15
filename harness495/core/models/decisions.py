"""A question the run stops on, and the answer it records.

``PendingDecision`` is the stop as an interface puts it, each option stated with what taking it
does to the run; ``Decision`` is what was answered, by whom, and on which evidence.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import Field

from harness495.core.models.base import StrictModel, utcnow
from harness495.core.models.clarification import ClarifyAnswer, ClarifyQuestion
from harness495.core.models.enums import DecisionKind, DecisionMaker


class DecisionOption(StrictModel):
    key: str
    label: str
    needs_note: bool = False
    consequence: str = ""
    """What happens to the run if this option is taken. Shown with the option, never guessed."""


class PendingDecision(StrictModel):
    kind: DecisionKind
    question: str
    options: list[DecisionOption]
    questions: list[ClarifyQuestion] = Field(default_factory=list)
    """The questions of a ``clarify`` round, answered one by one under the option that says so.
    Empty for every decision that is itself one question."""
    context: dict[str, Any] = Field(default_factory=dict)
    raised_at: dt.datetime = Field(default_factory=utcnow)


class Decision(StrictModel):
    id: str
    kind: DecisionKind
    made_by: DecisionMaker
    outcome: str
    rationale: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    iteration: int = 0
    question: str | None = None
    answers: list[ClarifyAnswer] = Field(default_factory=list)
    """What was answered question by question, when the decision carried several."""
    created_at: dt.datetime = Field(default_factory=utcnow)
