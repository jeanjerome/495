from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest

from harness495.core.models import Event, HarnessConfig, Intent, Run, Spec, Usage
from harness495.core.store import DRIVER_FLAG, RunBusy, RunStore


def test_usage_add_tracks_peak_and_upper_bound() -> None:
    a = Usage(
        input_tokens=10, output_tokens=5, requests=1, context_peak_tokens=100, context_window=1000
    )
    b = Usage(
        input_tokens=20,
        output_tokens=1,
        requests=1,
        context_peak_tokens=300,
        context_peak_is_upper_bound=True,
    )
    c = a.add(b)
    assert c.input_tokens == 30 and c.output_tokens == 6 and c.requests == 2
    assert c.context_peak_tokens == 300 and c.context_window == 1000
    assert c.context_peak_is_upper_bound is True
    assert c.context_utilization == 0.3


def test_run_round_trip_and_schema(tmp_path: Path) -> None:
    run = Run(id="run-x", intent=Intent(text="do it"), project_root=str(tmp_path))
    store = RunStore(tmp_path / ".495")
    store.save(run)
    loaded = store.load("run-x")
    assert loaded.id == "run-x" and loaded.intent.text == "do it"
    schema = Run.model_json_schema()
    assert "properties" in schema and "status" in schema["properties"]
    doc = json.loads(store.run_path("run-x").read_text())
    assert doc["schema_version"] == 1
    assert Run.model_validate(doc).id == "run-x"


def test_store_events_stop_flag_and_export(tmp_path: Path) -> None:
    store = RunStore(tmp_path / ".495")
    run = Run(id="run-y", intent=Intent(text="x"), project_root=str(tmp_path))
    store.save(run)
    store.append_event(Event(run_id="run-y", type="a", message="1"))
    store.append_event(Event(run_id="run-y", type="b", message="2"))
    assert [e.type for e in store.events("run-y")] == ["a", "b"]
    assert [e.type for e in store.events("run-y", offset=1)] == ["b"]
    assert store.event_count("run-y") == 2
    assert store.stop_requested("run-y") is None
    store.request_stop("run-y", "please")
    assert store.stop_requested("run-y") == "please"
    store.clear_stop("run-y")
    assert store.stop_requested("run-y") is None
    ref = store.write_text("run-y", str(store.artifacts_dir("run-y") / "a.txt"), "hello")
    assert ref == "artifacts/a.txt"
    assert store.read_text("run-y", ref) == "hello"
    archive = store.export("run-y", tmp_path / "out" / "run-y.tar.gz")
    assert archive.exists() and archive.stat().st_size > 0
    assert [r.id for r in store.list_runs()] == ["run-y"]


def test_config_agent_lookup() -> None:
    cfg = HarnessConfig()
    assert cfg.agent("default").kind.value == "claude_code"
    ad_hoc = cfg.agent("codex:gpt-5")
    assert ad_hoc.kind.value == "codex" and ad_hoc.model == "gpt-5"
    assert cfg.agent("openai_compat").kind.value == "openai_compat"
    spec = Spec()
    assert spec.requirement("R9") is None


# --------------------------------------------------------------- who is advancing a run


def _store_with_run(tmp_path: Path, run_id: str = "run-z") -> RunStore:
    store = RunStore(tmp_path / ".495")
    store.save(Run(id=run_id, intent=Intent(text="x"), project_root=str(tmp_path)))
    return store


def test_a_claim_refuses_a_second_holder_and_is_given_back(tmp_path: Path) -> None:
    store = _store_with_run(tmp_path)
    store.claim("run-z", "495 run")
    assert store.holder("run-z") is None, "this process holds it; it is not held against us"
    store.release("run-z")
    assert not (store.run_dir("run-z") / DRIVER_FLAG).exists()


def test_a_run_held_by_a_live_process_is_named_not_taken(tmp_path: Path) -> None:
    store = _store_with_run(tmp_path)
    _write_claim(store, "run-z", pid=1, label="495 run")  # pid 1 is always alive
    held = store.holder("run-z")
    assert held is not None and "495 run" in held and "pid 1" in held
    with pytest.raises(RunBusy):
        store.claim("run-z", "the run surface")


def test_a_claim_left_by_a_dead_process_does_not_lock_the_run(tmp_path: Path) -> None:
    """A crashed run would otherwise stay locked behind a file nobody knows to delete."""
    store = _store_with_run(tmp_path)
    _write_claim(store, "run-z", pid=2**30, label="495 run")
    assert store.holder("run-z") is None
    store.claim("run-z", "the run surface")


def test_releasing_someone_else_s_claim_does_nothing(tmp_path: Path) -> None:
    store = _store_with_run(tmp_path)
    _write_claim(store, "run-z", pid=1, label="495 run")
    store.release("run-z")
    assert store.holder("run-z") is not None


def _write_claim(store: RunStore, run_id: str, pid: int, label: str) -> None:
    (store.run_dir(run_id) / DRIVER_FLAG).write_text(
        json.dumps({"pid": pid, "host": socket.gethostname(), "label": label, "since": "now"}),
        encoding="utf-8",
    )
    assert pid != os.getpid()
