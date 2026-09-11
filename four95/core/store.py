"""Durable, portable state for runs.

Layout under ``<state_dir>/runs/<run_id>/``::

    run.json            the full :class:`Run` document (atomic writes)
    events.jsonl        append-only event log
    interventions/<id>/ prompt.md, context.json, transcript.*, output.*
    evidence/<id>/      command output
    artifacts/          patch, report

Everything referenced from ``run.json`` is a path relative to the run directory, so a run
directory can be copied or archived as a whole.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import tarfile
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from four95.core.models import Event, Run, utcnow

STATE_DIR_NAME = ".495"
STOP_FLAG = "STOP"


class RunNotFound(LookupError):
    pass


def default_state_dir(project_root: Path) -> Path:
    env = os.environ.get("FOUR95_STATE_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return project_root / STATE_DIR_NAME


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


class RunStore:
    """Filesystem store for runs. One instance per state directory."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)
        self.runs_dir = self.state_dir / "runs"

    # ---- paths

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def run_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "run.json"

    def events_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "events.jsonl"

    def artifacts_dir(self, run_id: str) -> Path:
        d = self.run_dir(run_id) / "artifacts"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def intervention_dir(self, run_id: str, intervention_id: str) -> Path:
        d = self.run_dir(run_id) / "interventions" / intervention_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def evidence_dir(self, run_id: str, evidence_id: str) -> Path:
        d = self.run_dir(run_id) / "evidence" / evidence_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def worktrees_dir(self) -> Path:
        d = self.state_dir / "worktrees"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def relative(self, run_id: str, path: Path) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.run_dir(run_id).resolve()))
        except ValueError:
            return str(path)

    def resolve(self, run_id: str, ref: str) -> Path:
        p = Path(ref)
        return p if p.is_absolute() else self.run_dir(run_id) / p

    # ---- persistence

    def save(self, run: Run) -> None:
        run.updated_at = utcnow()
        _atomic_write_text(self.run_path(run.id), run.model_dump_json(indent=2))

    def load(self, run_id: str) -> Run:
        path = self.run_path(run_id)
        if not path.exists():
            raise RunNotFound(run_id)
        return Run.model_validate_json(path.read_text(encoding="utf-8"))

    def exists(self, run_id: str) -> bool:
        return self.run_path(run_id).exists()

    def list_runs(self) -> list[Run]:
        if not self.runs_dir.exists():
            return []
        runs: list[Run] = []
        for d in sorted(self.runs_dir.iterdir()):
            if (d / "run.json").exists():
                try:
                    runs.append(self.load(d.name))
                except Exception:
                    continue
        runs.sort(key=lambda r: r.created_at)
        return runs

    def delete(self, run_id: str) -> None:
        shutil.rmtree(self.run_dir(run_id), ignore_errors=True)

    # ---- events

    def append_event(self, event: Event) -> None:
        path = self.events_path(event.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(event.model_dump_json() + "\n")

    def events(self, run_id: str, offset: int = 0) -> Iterator[Event]:
        path = self.events_path(run_id)
        if not path.exists():
            return
        with path.open(encoding="utf-8") as fh:
            for n, line in enumerate(fh):
                if n < offset:
                    continue
                line = line.strip()
                if line:
                    yield Event.model_validate_json(line)

    def event_count(self, run_id: str) -> int:
        path = self.events_path(run_id)
        if not path.exists():
            return 0
        with path.open(encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())

    # ---- files

    def write_text(self, run_id: str, ref: str, text: str) -> str:
        path = self.resolve(run_id, ref)
        _atomic_write_text(path, text)
        return self.relative(run_id, path)

    def write_json(self, run_id: str, ref: str, data: Any) -> str:
        return self.write_text(run_id, ref, json.dumps(data, indent=2, default=str))

    def read_text(self, run_id: str, ref: str) -> str:
        return self.resolve(run_id, ref).read_text(encoding="utf-8")

    # ---- control flags

    def request_stop(self, run_id: str, reason: str = "stop requested") -> None:
        _atomic_write_text(self.run_dir(run_id) / STOP_FLAG, reason)

    def stop_requested(self, run_id: str) -> str | None:
        p = self.run_dir(run_id) / STOP_FLAG
        if p.exists():
            return p.read_text(encoding="utf-8") or "stop requested"
        return None

    def clear_stop(self, run_id: str) -> None:
        p = self.run_dir(run_id) / STOP_FLAG
        if p.exists():
            p.unlink()

    # ---- export

    def export(self, run_id: str, dest: Path) -> Path:
        if not self.exists(run_id):
            raise RunNotFound(run_id)
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(dest, "w:gz") as tar:
            tar.add(self.run_dir(run_id), arcname=run_id)
        return dest
