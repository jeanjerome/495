"""The error the engine raises when a run cannot be advanced as asked.

It lives on its own so that every region of the engine can raise it without reaching for the
state machine: ``core/engine/engine.py`` and ``core/engine/checks/calibration.py`` both do.
``interfaces`` catches it by the name ``core.engine`` re-exports.
"""

from __future__ import annotations


class EngineError(RuntimeError):
    pass
