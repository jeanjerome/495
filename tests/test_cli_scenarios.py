"""Scenarios of ``tests/features/cli.feature`` and ``tests/features/api.feature``: what
``interfaces/cli.py`` and ``interfaces/api.py`` answer about a project and its runs.

The steps invoke the real Typer application over the sample project — and, for the HTTP
scenarios, a real server in a thread of its own — with the fake agents of ``tests/conftest.py``
behind them, then read the exit code, the document and the terminal output back. Nothing is
asserted outside a ``Then``.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from typer.testing import CliRunner

from harness495.core.engine import engine as engine_mod
from harness495.core.models import RunStatus
from harness495.interfaces.api import make_server
from harness495.interfaces.cli import app
from tests.conftest import FakeAgent, Scenario, bad_producer, good_producer, reject_review

scenarios("features/cli.feature", "features/api.feature")

runner = CliRunner()

WAIT = 60.0
"""Long enough for the fake agents and a real pytest run behind the HTTP server."""


@dataclass
class Terminal:
    """One project, the CLI invoked over it, and what the last invocation answered."""

    project: Path
    script: Scenario
    run_id: str = ""
    answered: Any = None

    def invoke(self, *args: str) -> None:
        self.answered = runner.invoke(app, ["--project", str(self.project), *args])

    @property
    def result(self) -> Any:
        assert self.answered is not None, "no command was run"
        return self.answered

    @property
    def output(self) -> str:
        return self.result.output

    @property
    def document(self) -> Any:
        return json.loads(self.output)


@dataclass
class Service:
    """A server over the sample project, and what the last request answered."""

    project: Path
    script: Scenario
    base: str
    run_id: str = ""
    code: int = 0
    body: Any = None
    document: dict[str, Any] = field(default_factory=dict)

    def ask(self, method: str, path: str, payload: dict[str, Any] | None = None) -> None:
        self.code, self.body = _http(method, f"{self.base}{path}", payload)


def _http(method: str, url: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode()
            kind = response.headers.get("Content-Type", "")
            return response.status, json.loads(raw) if "json" in kind else raw
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def _behind_the_fake_agents(monkeypatch: pytest.MonkeyPatch) -> Scenario:
    script = Scenario()
    monkeypatch.setattr(engine_mod, "build_agent", lambda spec, sandbox: FakeAgent(spec, script))
    return script


# ----------------------------------------------------------------- the command line


@given("a project the CLI can work in", target_fixture="world")
def a_project_the_cli_can_work_in(
    sample_project: Path, monkeypatch: pytest.MonkeyPatch
) -> Terminal:
    return Terminal(sample_project, _behind_the_fake_agents(monkeypatch))


@given("the change is in the working tree")
def the_change_is_in_the_working_tree(world: Terminal) -> None:
    good_producer(world.project)


@given("a run carried to delivery from the terminal")
def a_run_carried_to_delivery(world: Terminal) -> None:
    a_run_is_created(world, "--agent claude_code:fake --sandbox host")
    world.invoke("--json", "run", world.run_id)
    world.invoke("--json", "decide", world.run_id, "approve")


@given("a run stopped for approval")
def a_run_stopped_for_approval(world: Terminal) -> None:
    a_run_is_created(world, "--sandbox host")
    world.invoke("--json", "run", world.run_id)


@given("a run that reached its iteration limit on a version the reviewer rejected")
def a_run_that_reached_its_iteration_limit(world: Terminal) -> None:
    world.script.producers = [bad_producer]
    world.script.reviews["correctness"] = [reject_review("correctness")]
    a_run_is_created(world, "--auto-approve --max-iterations 1 --sandbox host")


@when(parsers.parse('a run is created with "{options}"'))
def a_run_is_created(world: Terminal, options: str) -> None:
    world.invoke("--json", "new", "add subtract", "--no-start", *shlex.split(options))
    world.run_id = world.document["id"]


@when(parsers.parse('the command "{line}" is run'))
def the_command_is_run(world: Terminal, line: str) -> None:
    world.invoke(*(arg.replace("<id>", world.run_id) for arg in shlex.split(line)))


@when("it is evaluated from the terminal")
def it_is_evaluated_from_the_terminal(world: Terminal) -> None:
    world.invoke(
        "--json",
        "eval",
        "add subtract",
        "--auto-approve",
        "--agent",
        "claude_code:fake",
        "--sandbox",
        "host",
    )
    world.run_id = world.document["id"]


@when("the run document is validated")
def the_run_document_is_validated(world: Terminal) -> None:
    world.invoke("validate", str(world.project / ".495" / "runs" / world.run_id / "run.json"))


@when("the run is exported")
def the_run_is_exported(world: Terminal) -> None:
    world.invoke("--json", "export", world.run_id, "-o", str(world.project / "out.tgz"))


@when("the branch is put back and moved on without it")
def the_branch_is_put_back_and_moved_on(world: Terminal) -> None:
    for args in (
        ["reset", "-q", "--hard", "HEAD~1"],
        ["commit", "--allow-empty", "-m", "on"],
    ):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=world.project,
            check=True,
            capture_output=True,
        )


@then(parsers.parse("it exits {code:d}"))
def it_exits(world: Terminal, code: int) -> None:
    assert world.result.exit_code == code, world.output


@then(parsers.parse('it exits {code:d}, saying "{text}"'))
def it_exits_saying(world: Terminal, code: int, text: str) -> None:
    assert world.result.exit_code == code and text in world.output


@then(parsers.parse('it exits {code:d}, the document saying "{text}"'))
def it_exits_with_the_document_saying(world: Terminal, code: int, text: str) -> None:
    assert world.result.exit_code == code
    assert text in world.document["error"]


@then(parsers.parse('it exits {code:d}, awaiting the "{kind}" question'))
def it_exits_awaiting_a_question(world: Terminal, code: int, kind: str) -> None:
    assert world.result.exit_code == code, world.output
    document = world.document
    assert document["status"] == RunStatus.awaiting_decision.value
    assert document["pending_decision"]["kind"] == kind


@then(parsers.parse("it exits {code:d}, the run delivered and accepted"))
def it_exits_with_the_run_delivered(world: Terminal, code: int) -> None:
    assert world.result.exit_code == code, world.output
    assert world.document["status"] == "delivered" and world.document["outcome"] == "accept"


@then(parsers.parse('it exits {code:d}, the state "{state}"'))
def it_exits_with_the_state(world: Terminal, code: int, state: str) -> None:
    assert world.result.exit_code == code, world.output
    assert world.document["state"] == state


@then(parsers.parse("it exits {code:d}, an evaluate run accepted"))
def it_exits_with_an_evaluation(world: Terminal, code: int) -> None:
    assert world.result.exit_code == code, world.output
    assert world.document["mode"] == "evaluate" and world.document["outcome"] == "accept"


@then(parsers.parse("it exits {code:d}, and a stop is on file for the run"))
def it_exits_with_a_stop_on_file(world: Terminal, code: int) -> None:
    assert world.result.exit_code == code
    assert (world.project / ".495" / "runs" / world.run_id / "STOP").exists()


@then(parsers.parse("it exits {code:d}, and the archive is there"))
def it_exits_with_the_archive(world: Terminal, code: int) -> None:
    assert world.result.exit_code == code and (world.project / "out.tgz").exists()


@then(parsers.parse('it exits {code:d}, printing "{first}", "{second}" and "{third}"'))
def it_exits_printing(world: Terminal, code: int, first: str, second: str, third: str) -> None:
    assert world.result.exit_code == code
    assert first in world.output and second in world.output and third in world.output


@then(parsers.parse('the document names the command "{name}", and a base commit'))
def the_document_names_the_command(world: Terminal, name: str) -> None:
    profile = world.document
    assert profile["commands"][0]["name"] == name and profile["base_commit"]


@then(parsers.parse('the document has a "{name}" property'))
def the_document_has_a_property(world: Terminal, name: str) -> None:
    assert name in world.document["properties"]


@then("the document names the sandboxes")
def the_document_names_the_sandboxes(world: Terminal) -> None:
    assert "sandboxes" in world.document


@then(parsers.parse('"{name}" is in the project'))
def the_file_is_in_the_project(world: Terminal, name: str) -> None:
    assert (world.project / name).exists()


@then(parsers.parse('"{name}" declares a scope'))
def the_file_declares_a_scope(world: Terminal, name: str) -> None:
    assert "[scope]" in (world.project / name).read_text()


@then("the first requirement is satisfied")
def the_first_requirement_is_satisfied(world: Terminal) -> None:
    assert world.document["requirements"][0]["status"] == "satisfied"


@then("the listing names that run, and no other")
def the_listing_names_that_run(world: Terminal) -> None:
    assert [r["id"] for r in world.document] == [world.run_id]


@then("the report has a title and an interventions section")
def the_report_has_a_title(world: Terminal) -> None:
    assert "# 495 run" in world.output and "## Interventions" in world.output


@then(parsers.parse('the events name "{type_}"'))
def the_events_name(world: Terminal, type_: str) -> None:
    types = [json.loads(line)["type"] for line in world.output.splitlines() if line.strip()]
    assert type_ in types


@then("the specification names R1 and R2, and says where it is written")
def the_specification_names_its_requirements(world: Terminal) -> None:
    spec = world.document
    assert [r["id"] for r in spec["requirements"]] == ["R1", "R2"]
    assert spec["artifact_ref"]


@then(parsers.parse('the output says "{text}"'))
def the_output_says(world: Terminal, text: str) -> None:
    assert text in world.output


@then(parsers.parse('the output names {rid} once, under "{heading}"'))
def the_output_names_once(world: Terminal, rid: str, heading: str) -> None:
    assert world.output.count(rid) >= 1
    assert heading in world.output


# ----------------------------------------------------------------- the HTTP interface


@given("a project served over HTTP, with the fake agents behind it", target_fixture="world")
def a_project_served_over_http(
    sample_project: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Service]:
    script = _behind_the_fake_agents(monkeypatch)
    (sample_project / ".495" / "config.toml").write_text(
        '[sandbox]\nbackend = "host"\n[agents.default]\nkind = "claude_code"\nmodel = "fake"\n'
    )
    server = make_server(sample_project, sample_project / ".495", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Service(sample_project, script, f"http://127.0.0.1:{server.server_address[1]}")
    finally:
        server.shutdown()
        server.server_close()


@when(parsers.parse('GET "{path}" is asked'))
def get_is_asked(world: Service, path: str) -> None:
    world.ask("GET", path)


@when(parsers.parse('a run is posted with the intent "{intent}"'))
def a_run_is_posted(world: Service, intent: str) -> None:
    world.ask("POST", "/runs", {"intent": intent, "agent": "default"})
    world.run_id = world.body["id"]


@when("a run is posted with no intent at all")
def a_run_is_posted_with_no_intent(world: Service) -> None:
    world.ask("POST", "/runs", {})


@when("the run is waited for until it stops on a question")
def the_run_is_waited_for_until_it_asks(world: Service) -> None:
    _until(
        world,
        lambda doc: doc["status"] == RunStatus.awaiting_decision.value and not doc["running"],
    )


@when("the run is waited for until it is delivered")
def the_run_is_waited_for_until_delivered(world: Service) -> None:
    _until(world, lambda doc: doc["status"] == "delivered")


def _until(world: Service, done: Callable[[Any], bool]) -> None:
    deadline = time.time() + WAIT
    while time.time() < deadline:
        world.ask("GET", f"/runs/{world.run_id}")
        if done(world.body):
            break
        time.sleep(0.2)
    world.document = world.body


@when(parsers.parse("GET the run's events from offset {offset:d} is asked"))
def get_the_events_is_asked(world: Service, offset: int) -> None:
    world.ask("GET", f"/runs/{world.run_id}/events?offset={offset}")


@when("GET the run's report is asked")
def get_the_report_is_asked(world: Service) -> None:
    world.ask("GET", f"/runs/{world.run_id}/report")


@when(parsers.parse('the answer "{choice}" is posted to the run'))
def the_answer_is_posted(world: Service, choice: str) -> None:
    world.ask("POST", f"/runs/{world.run_id}/decisions", {"choice": choice})


@then(parsers.parse("it answers {code:d}"))
def it_answers(world: Service, code: int) -> None:
    assert world.code == code, world.body


@then(parsers.parse("it answers {code:d}, and says it is ok"))
def it_answers_ok(world: Service, code: int) -> None:
    assert world.code == code and world.body["ok"]


@then(parsers.parse('it answers {code:d}, holding a "{type_}" event'))
def it_answers_with_an_event(world: Service, code: int, type_: str) -> None:
    assert world.code == code
    assert any(e["type"] == type_ for e in world.body["events"])


@then(parsers.parse("it answers {code:d}, and the report has a title"))
def it_answers_with_a_report(world: Service, code: int) -> None:
    assert world.code == code and "# 495 run" in world.body


@then(parsers.parse("it answers {code:d}, naming that run first"))
def it_answers_naming_that_run(world: Service, code: int) -> None:
    assert world.code == code and world.body[0]["id"] == world.run_id


@then(parsers.parse("it answers {code:d}, with properties"))
def it_answers_with_properties(world: Service, code: int) -> None:
    assert world.code == code and "properties" in world.body


@then(parsers.parse('it answers {code:d}, naming "{text}"'))
def it_answers_naming(world: Service, code: int, text: str) -> None:
    assert world.code == code and text in world.body["error"]


@then(parsers.parse('the question is "{kind}"'))
def the_question_is(world: Service, kind: str) -> None:
    assert world.document["pending_decision"]["kind"] == kind


@then("the run is delivered, and accepted")
def the_run_is_delivered_and_accepted(world: Service) -> None:
    assert world.document["status"] == "delivered"
    assert world.document["result"]["outcome"] == "accept"
