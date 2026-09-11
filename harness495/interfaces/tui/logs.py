"""The output a verification command actually printed.

Evidence carries a reference, not the text: a test suite's output is megabytes and a run
carries dozens of them. The detail pane and the pager both want the text itself, so it is read
from the store on demand and kept for as long as the surface is up — a check whose log you are
arrowing past should not re-read the file on every frame.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from harness495.core.models import Evidence

if TYPE_CHECKING:
    from harness495.core.store import RunStore


class Logs(Protocol):
    """Where the recorded output of one piece of evidence comes from."""

    def get(self, evidence: Evidence) -> str | None: ...


class NoLogs:
    """No store behind the surface, so no output to read. Used by previews and exports."""

    def get(self, evidence: Evidence) -> str | None:
        return None


class StoredLogs:
    """The run directory, read lazily and cached by evidence id."""

    def __init__(self, store: RunStore, run_id: str, limit: int = 200_000) -> None:
        self.store = store
        self.run_id = run_id
        self.limit = limit
        self._cache: dict[str, str | None] = {}

    def get(self, evidence: Evidence) -> str | None:
        if evidence.id in self._cache:
            return self._cache[evidence.id]
        text: str | None = None
        if evidence.output_ref:
            try:
                text = self.store.read_text(self.run_id, evidence.output_ref)
            except OSError:
                # A missing or unreadable artifact is not an error the surface can act on: the
                # panel falls back to saying where the output was kept.
                text = None
        if text is not None and len(text) > self.limit:
            kept = text[-self.limit :]
            text = f"[… {len(text) - self.limit} earlier characters not shown …]\n{kept}"
        self._cache[evidence.id] = text
        return text
