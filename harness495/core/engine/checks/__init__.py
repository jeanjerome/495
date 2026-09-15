"""What the engine measures of a produced version, and what the rest of the engine may ask of it.

Eight stages in a declared order (:mod:`.sequence`), five of them check groups that make no
call to each other. Each group pairs with a pure reader that already exists in ``core/``: the
reader says what a measurement means, the group here is what executes, persists and emits.

=====================  ========================================================
``stability.py``       ``core/reading/verification.py::reports_the_same_twice``
``suite.py``           ``core/suite.py``
``coverage.py``        ``core/reach.py``
``mutation.py``        ``core/mutation.py``
``calibration.py``     ``core/reading/verification.py::classify_instrument``
=====================  ========================================================

The package takes a :class:`~harness495.core.engine.services.RunServices` and produces
evidence; it imports no agent and no phase. ``verify`` returns the instrument-fault question
instead of raising it, because which stop a run takes is the state machine's to decide.
``suite_reading`` is what the review phase gives the reviewers, and ``recalibrate`` is what the
requester's answer to that question does.
"""

from __future__ import annotations

from harness495.core.engine.checks.calibration import recalibrate
from harness495.core.engine.checks.sequence import SEQUENCE, verify
from harness495.core.engine.checks.stage import Reading, Stage
from harness495.core.engine.checks.suite import suite_reading

__all__ = ["SEQUENCE", "Reading", "Stage", "recalibrate", "suite_reading", "verify"]
