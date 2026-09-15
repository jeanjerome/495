"""What one stage of the verification sequence is: what it is given, and what it hands back.

A stage takes the services, the run, the iteration whose version is under verification and the
evidence the stages before it produced, and returns a :class:`Reading`. That uniform shape is
what lets the order of the stages be declared as data in :mod:`.sequence` rather than inferred
from the order of statements in one method.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from harness495.core.engine.services import RunServices
from harness495.core.models import Evidence, Iteration, Run


@dataclass(frozen=True)
class Reading:
    """What one stage measured.

    ``proposals`` is the calibration's alone: the commands the producer reported that the
    harness ran on both versions and found usable, which the instrument-fault question names
    back to the requester. Every other stage leaves it empty.
    """

    evidence: list[Evidence]
    proposals: dict[str, str] = field(default_factory=dict)


Measure = Callable[[RunServices, Run, Iteration, list[Evidence]], Reading]
Gate = Callable[[Run, Iteration], bool]


@dataclass(frozen=True)
class Stage:
    """One entry of the sequence: what it measures, and what has to hold for it to run."""

    name: str
    measure: Measure
    gate: Gate | None = None
    gated_because: str = ""
