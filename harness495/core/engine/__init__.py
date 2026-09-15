"""What the rest of the repository may import of the workflow engine.

The state machine itself is :mod:`harness495.core.engine.engine`; this module is the name every
other package reaches it by, and the list below is the whole of what it offers.

:class:`Engine` and :class:`EngineError` are the interface: `interfaces` drives a run through
the engine's public methods and catches nothing else. ``spec_from_agent`` is the one mapping
reached from outside `core` — `495 new --spec` and the API's ``spec`` body read a JSON
specification the requester supplied through the reader an agent's answer goes through, so a
hand-written document and an agent's cannot be normalised differently. ``worktrees_root``
answers where a project's run worktrees live without opening a run.

``_clarify_frontier`` and ``_parse_json_text`` stay private to the engine; they are named here
only so the scenarios that measure them reach them at the package name.
"""

from __future__ import annotations

from harness495.core.engine.engine import (
    Engine,
    EngineError,
    _clarify_frontier,
    _parse_json_text,
    spec_from_agent,
    worktrees_root,
)

__all__ = [
    "Engine",
    "EngineError",
    "spec_from_agent",
    "worktrees_root",
    "_clarify_frontier",
    "_parse_json_text",
]
