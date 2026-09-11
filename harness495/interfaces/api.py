"""HTTP JSON API on the standard library server. Same engine, same store as the CLI.

Endpoints::

    GET  /health
    GET  /runs                          list runs
    POST /runs                          {"intent", "mode"?, "evaluate_ref"?, "auto_approve"?, "agent"?, "max_cost_usd"?, "spec"?}
    GET  /runs/{id}                     run document
    GET  /runs/{id}/events?offset=N     event log
    GET  /runs/{id}/report              Markdown report
    POST /runs/{id}/decisions           {"choice", "note"?}
    POST /runs/{id}/resume
    POST /runs/{id}/stop
    POST /runs/{id}/check-integration   {"ref"?, "rerun"?}
    GET  /schema/{run|event|spec|config}

Runs execute in a background thread per run; the API never blocks on an agent.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from harness495 import __version__
from harness495.core.config import load_config
from harness495.core.engine import Engine, EngineError
from harness495.core.models import (
    AgentKind,
    AgentSpec,
    DecisionMaker,
    Event,
    HarnessConfig,
    Run,
    RunMode,
    Spec,
)
from harness495.core.report import render_markdown
from harness495.core.store import RunNotFound, RunStore


class ApiState:
    def __init__(self, project: Path, state_dir: Path) -> None:
        self.project = project
        self.state_dir = state_dir
        self.store = RunStore(state_dir)
        self.threads: dict[str, threading.Thread] = {}
        self.lock = threading.Lock()

    def engine(self) -> Engine:
        return Engine(self.store)

    def start_background(self, run_id: str) -> bool:
        with self.lock:
            t = self.threads.get(run_id)
            if t is not None and t.is_alive():
                return False
            engine = self.engine()

            def target() -> None:
                try:
                    engine.run(run_id)
                except Exception as exc:  # noqa: BLE001
                    try:
                        run = self.store.load(run_id)
                        run.warnings.append(f"background execution error: {exc}")
                        self.store.save(run)
                    except RunNotFound:
                        pass

            t = threading.Thread(target=target, name=f"run-{run_id}", daemon=True)
            self.threads[run_id] = t
            t.start()
            return True

    def running(self, run_id: str) -> bool:
        t = self.threads.get(run_id)
        return t is not None and t.is_alive()


def _config_from_body(base: HarnessConfig, body: dict[str, Any]) -> HarnessConfig:
    agent = body.get("agent")
    if agent:
        if agent in base.agents:
            spec = base.agents[agent]
        else:
            kind, _, model = str(agent).partition(":")
            spec = AgentSpec(name=str(agent), kind=AgentKind(kind), model=model or None)
        base.agents[spec.name] = spec
        base.roles.specifier = spec.name
        base.roles.producer = spec.name
        for r in base.roles.reviewers:
            r.agent = spec.name
    if body.get("max_cost_usd") is not None:
        base.budget.max_cost_usd = float(body["max_cost_usd"])
    if body.get("max_iterations") is not None:
        base.budget.max_iterations = int(body["max_iterations"])
    if body.get("auto_approve"):
        base.auto_approve = True
    if body.get("allowed_paths"):
        base.project.scope.allowed_paths = [str(p) for p in body["allowed_paths"]]
    return base


def run_payload(run: Run, running: bool) -> dict[str, Any]:
    data = run.model_dump(mode="json")
    data["running"] = running
    return data


class Handler(BaseHTTPRequestHandler):
    state: ApiState

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _send(self, code: int, payload: Any, content_type: str = "application/json") -> None:
        body = (
            payload.encode("utf-8")
            if isinstance(payload, str)
            else json.dumps(payload, default=str).encode("utf-8")
        )
        self.send_response(code)
        self.send_header(
            "Content-Type",
            content_type + ("; charset=utf-8" if content_type.startswith("text/") else ""),
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON body: {exc}") from exc
        return data if isinstance(data, dict) else {}

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        query = parse_qs(url.query)
        try:
            if parts == ["health"]:
                self._send(
                    200, {"ok": True, "version": __version__, "project": str(self.state.project)}
                )
            elif parts == ["runs"]:
                self._send(200, [self._summary(r) for r in self.state.store.list_runs()])
            elif len(parts) == 2 and parts[0] == "runs":
                run = self.state.store.load(parts[1])
                self._send(200, run_payload(run, self.state.running(run.id)))
            elif len(parts) == 3 and parts[0] == "runs" and parts[2] == "events":
                offset = int(query.get("offset", ["0"])[0])
                events = [
                    e.model_dump(mode="json") for e in self.state.store.events(parts[1], offset)
                ]
                self._send(
                    200, {"offset": offset, "events": events, "next_offset": offset + len(events)}
                )
            elif len(parts) == 3 and parts[0] == "runs" and parts[2] == "report":
                run = self.state.store.load(parts[1])
                self._send(200, render_markdown(run, self.state.store), "text/markdown")
            elif len(parts) == 2 and parts[0] == "schema":
                models: dict[str, Any] = {
                    "run": Run,
                    "event": Event,
                    "spec": Spec,
                    "config": HarnessConfig,
                }
                model = models.get(parts[1])
                if model is None:
                    self._send(404, {"error": "unknown schema"})
                else:
                    self._send(200, model.model_json_schema())
            else:
                self._send(404, {"error": "not found"})
        except RunNotFound as exc:
            self._send(404, {"error": f"run {exc} not found"})
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        try:
            body = self._body()
            if parts == ["runs"]:
                intent = str(body.get("intent", "")).strip()
                if not intent:
                    self._send(400, {"error": "intent is required"})
                    return
                mode = RunMode(str(body.get("mode", "change")))
                config = _config_from_body(
                    load_config(self.state.project, self.state.state_dir), body
                )
                spec = None
                if isinstance(body.get("spec"), dict):
                    from harness495.core.engine import _spec_from_agent

                    spec = _spec_from_agent(body["spec"])
                    spec.source = "user"
                run = self.state.engine().create_run(
                    intent,
                    self.state.project,
                    config,
                    mode,
                    evaluate_ref=body.get("evaluate_ref"),
                    spec=spec,
                    source="api",
                )
                if body.get("start", True):
                    self.state.start_background(run.id)
                self._send(
                    201, run_payload(self.state.store.load(run.id), self.state.running(run.id))
                )
            elif len(parts) == 3 and parts[0] == "runs":
                run_id, action = parts[1], parts[2]
                if action == "decisions":
                    if self.state.running(run_id):
                        self._send(409, {"error": "run is executing; wait for it to block"})
                        return
                    run = self.state.engine().decide(
                        run_id,
                        str(body.get("choice", "")),
                        str(body.get("note", "")),
                        DecisionMaker.human,
                    )
                    if not run.is_blocked():
                        self.state.start_background(run_id)
                    self._send(
                        200, run_payload(self.state.store.load(run_id), self.state.running(run_id))
                    )
                elif action == "resume":
                    if self.state.running(run_id):
                        self._send(409, {"error": "run is already executing"})
                        return
                    self.state.engine().resume(run_id)
                    self.state.start_background(run_id)
                    self._send(202, run_payload(self.state.store.load(run_id), True))
                elif action == "stop":
                    self.state.store.request_stop(
                        run_id, str(body.get("reason", "stop requested via API"))
                    )
                    self._send(202, {"id": run_id, "stop_requested": True})
                elif action == "check-integration":
                    run = self.state.engine().check_integration(
                        run_id, str(body.get("ref", "HEAD")), bool(body.get("rerun", False))
                    )
                    assert run.result.integration is not None
                    self._send(200, run.result.integration.model_dump(mode="json"))
                else:
                    self._send(404, {"error": "not found"})
            else:
                self._send(404, {"error": "not found"})
        except RunNotFound as exc:
            self._send(404, {"error": f"run {exc} not found"})
        except (EngineError, ValueError) as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": str(exc)})

    @staticmethod
    def _summary(run: Run) -> dict[str, Any]:
        return {
            "id": run.id,
            "status": run.status.value,
            "mode": run.mode.value,
            "outcome": run.result.outcome.value if run.result.outcome else None,
            "iteration": run.iteration_number,
            "intent": run.intent.text,
            "created_at": run.created_at.isoformat(),
            "cost_usd": run.consumption.cost_usd,
        }


def make_server(project: Path, state_dir: Path, host: str, port: int) -> ThreadingHTTPServer:
    state = ApiState(project, state_dir)
    handler = type("BoundHandler", (Handler,), {"state": state})
    server = ThreadingHTTPServer((host, port), handler)
    return server


def serve(project: Path, state_dir: Path, host: str, port: int) -> None:
    server = make_server(project, state_dir, host, port)
    print(
        f"495 API {__version__} listening on http://{host}:{server.server_address[1]} (project {project})"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
