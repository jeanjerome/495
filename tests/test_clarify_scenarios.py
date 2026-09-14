"""Scenarios of ``tests/features/clarify.feature``: the requester's decisions are taken before
the specification, in rounds, and a settled question is never asked again.

The round scenarios call ``core.engine._clarify_frontier`` on one agent answer; the engine
scenarios walk a change run with the scripted agents of ``conftest``, giving the clarifier a
frontier to return, and read the run, the prompts and the report back. Nothing is asserted
outside a ``Then``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core.engine import EngineError, _clarify_frontier
from harness495.core.models import (
    Clarification,
    ClarifyAnswer,
    ClarifyQuestion,
    ClarifyReply,
    ClarifyRound,
    DecisionKind,
    DecisionMaker,
    Role,
    RunMode,
    RunStatus,
)
from harness495.core.report import render_markdown
from tests.conftest import Scenario

scenarios("features/clarify.feature")

TIMEZONE = "Which timezone do the timestamps use?"


def timezone_question(qid: str = "Q1", title: str = TIMEZONE) -> dict[str, Any]:
    """The frontier a clarifier returns for an intent that does not say which clock to read."""
    return {
        "id": qid,
        "title": title,
        "body": "The intent says the log carries a timestamp; nothing in the repository fixes "
        "the timezone, and the two readings are not the same behaviour.",
        "options": [
            {
                "key": "utc",
                "label": "UTC",
                "consequence": "R2 states UTC and V2 asserts the offset is zero.",
            },
            {
                "key": "local",
                "label": "The host timezone",
                "consequence": "R2 states the host timezone and V2 asserts it against the clock.",
            },
        ],
        "recommended": "utc",
        "checked": ["calc.py holds no clock", "README.md says nothing about time"],
    }


@dataclass
class World:
    raw: dict[str, Any] = field(default_factory=lambda: {"questions": []})
    clarification: Clarification = field(default_factory=Clarification)
    kept: list[ClarifyQuestion] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    engine: Any = None
    run: Any = None
    refusal: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def world() -> World:
    return World()


# --------------------------------------------------------------------------- what a round asks


@given(parsers.parse('a round that asks "{title}"'))
def a_round_that_asks(world: World, title: str) -> None:
    world.raw["questions"].append(
        {"id": "Q1", "title": title, "body": "", "options": [], "recommended": "", "checked": []}
    )


@given(parsers.parse('a round that asks "{title}" under the identifier "{qid}"'))
def a_round_that_asks_under(world: World, title: str, qid: str) -> None:
    world.raw["questions"].append(
        {"id": qid, "title": title, "body": "", "options": [], "recommended": "", "checked": []}
    )


@given(parsers.parse('it offers "{key}" saying "{consequence}"'))
def it_offers(world: World, key: str, consequence: str) -> None:
    world.raw["questions"][-1]["options"].append(
        {"key": key, "label": key.upper(), "consequence": consequence}
    )


@given(parsers.parse('it offers "{key}" saying nothing'))
def it_offers_nothing(world: World, key: str) -> None:
    world.raw["questions"][-1]["options"].append(
        {"key": key, "label": key.upper(), "consequence": ""}
    )


@given(parsers.parse('it recommends "{key}"'))
def it_recommends(world: World, key: str) -> None:
    world.raw["questions"][-1]["recommended"] = key


@given(parsers.parse('the requester answered "{title}" with "{option}"'))
def the_requester_answered(world: World, title: str, option: str) -> None:
    world.clarification.rounds.append(
        ClarifyRound(
            n=1,
            intervention_id="int-c",
            answers=[
                ClarifyAnswer(question_id="Q1", question=title, option=option, label=option.upper())
            ],
        )
    )


@when("the harness reads the round")
def the_harness_reads_the_round(world: World) -> None:
    world.kept, world.dropped = _clarify_frontier(world.raw, world.clarification)


@then(parsers.parse("the requester is asked {n:d} question"))
def the_requester_is_asked(world: World, n: int) -> None:
    assert len(world.kept) == n, world.dropped


@then("the requester is asked nothing")
def the_requester_is_asked_nothing(world: World) -> None:
    assert world.kept == [], [q.title for q in world.kept]


@then(parsers.parse('the question offers the answer "{key}"'))
def the_question_offers(world: World, key: str) -> None:
    assert world.kept[0].option(key) is not None, [o.key for o in world.kept[0].options]


@then(parsers.parse('the harness says it dropped a question "{text}"'))
def the_harness_says_it_dropped(world: World, text: str) -> None:
    said = world.dropped or [w for w in (world.run.warnings if world.run else [])]
    assert any(text in line for line in said), said


# --------------------------------------------------------------------------- through the engine


@given("the sample project")
def the_sample_project(
    world: World, sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    world.extra["project"] = sample_project
    world.extra["config"] = config
    world.extra["scenario"] = scenario
    world.engine = engine_factory()


@given("the requester answers the questions themselves")
def the_requester_answers_themselves(world: World) -> None:
    world.extra["config"].auto_approve = False


@given("the requester is asked which timezone the timestamps use")
def asked_which_timezone(world: World) -> None:
    world.extra["scenario"].clarify_rounds = [{"questions": [timezone_question()]}]


@given("the requester is asked two questions in one round")
def asked_two_questions(world: World) -> None:
    second = timezone_question("Q2", "Does an empty log file still get a header?")
    world.extra["scenario"].clarify_rounds = [{"questions": [timezone_question(), second]}]


@given("the next round asks it again, and one more thing")
def the_next_round_asks_it_again(world: World) -> None:
    second = timezone_question("Q2", "Does an empty log file still get a header?")
    world.extra["scenario"].clarify_rounds.append(
        {"questions": [timezone_question(), second]},
    )


@given("every round asks something new")
def every_round_asks_something_new(world: World) -> None:
    world.extra["scenario"].clarify_rounds = [
        {"questions": [timezone_question(f"Q{i}", f"Decision number {i}?")]} for i in range(1, 5)
    ]


@given("the requester approves everything in advance")
def the_requester_approves_everything(world: World) -> None:
    world.extra["config"].auto_approve = True


@given(parsers.parse("the requester answers at most {n:d} round"))
def at_most_n_rounds(world: World, n: int) -> None:
    world.extra["config"].budget.max_clarify_rounds = n


@given("the clarification is allowed no round")
def no_round(world: World) -> None:
    world.extra["config"].budget.max_clarify_rounds = 0


@given("the clarifier fails")
def the_clarifier_fails(world: World) -> None:
    world.extra["scenario"].clarify_rounds = [{}]
    world.extra["scenario"].clarifier_fails = True


def _create(world: World) -> Any:
    return world.engine.create_run(
        "add a subtract function to calc",
        world.extra["project"],
        world.extra["config"],
        RunMode.change,
    )


@when("a change run walks the workflow")
def a_change_run_walks(world: World) -> None:
    world.run = world.engine.run(_create(world).id)


@when("a change run walks the workflow to its first stop")
def a_change_run_walks_to_its_first_stop(world: World) -> None:
    world.run = world.engine.run(_create(world).id)


@when("the run walks on")
@when("the run walks on to its next stop")
def the_run_walks_on(world: World) -> None:
    world.run = world.engine.run(world.run.id)


def _answer(world: World, replies: list[ClarifyReply], choice: str = "answer") -> None:
    try:
        world.run = world.engine.decide(world.run.id, choice, "", DecisionMaker.human, replies)
    except EngineError as exc:
        world.refusal = str(exc)
        world.run = world.engine.store.load(world.run.id)


@when("the requester approves the specification")
def the_requester_approves_the_specification(world: World) -> None:
    world.run = world.engine.decide(world.run.id, "approve", "", DecisionMaker.human)


@when(parsers.parse('the requester answers "{option}"'))
def the_requester_answers(world: World, option: str) -> None:
    questions = world.run.pending_decision.questions
    _answer(world, [ClarifyReply(question_id=questions[0].id, option=option)])


@when(parsers.parse('the requester answers "{option}" with the note "{note}"'))
def the_requester_answers_with_a_note(world: World, option: str, note: str) -> None:
    questions = world.run.pending_decision.questions
    _answer(world, [ClarifyReply(question_id=questions[0].id, option=option, note=note)])


@when("the requester answers only the first question")
def the_requester_answers_only_the_first(world: World) -> None:
    questions = world.run.pending_decision.questions
    _answer(world, [ClarifyReply(question_id=questions[0].id, option="utc")])


@then(parsers.parse("the clarifier ran {n:d} time"))
@then(parsers.parse("the clarifier ran {n:d} times"))
def the_clarifier_ran(world: World, n: int) -> None:
    calls = [t for t in world.extra["scenario"].calls if t.role is Role.clarifier]
    assert len(calls) == n, len(calls)


@then("the run raised no clarification decision")
def no_clarification_decision(world: World) -> None:
    kinds = [d.kind for d in world.run.decisions]
    assert DecisionKind.clarify not in kinds, kinds


@then("the run awaits the requester on a clarification")
def the_run_awaits_a_clarification(world: World) -> None:
    assert world.run.status is RunStatus.awaiting_decision, (
        world.run.status,
        world.run.stop_reason,
    )
    assert world.run.pending_decision.kind is DecisionKind.clarify


@then(parsers.parse("the round puts {n:d} question to the requester"))
def the_round_puts_n_questions(world: World, n: int) -> None:
    assert len(world.run.pending_decision.questions) == n, [
        q.title for q in world.run.pending_decision.questions
    ]


@then(parsers.parse('the answer is refused, saying "{text}"'))
def the_answer_is_refused(world: World, text: str) -> None:
    assert text in world.refusal, world.refusal


@then(parsers.parse('the run records the decision "{question}" as "{choice}"'))
def the_run_records_the_decision(world: World, question: str, choice: str) -> None:
    answers = world.run.clarification.answers
    assert any(a.question == question and choice in (a.label or a.option) for a in answers), [
        (a.question, a.label) for a in answers
    ]


@then("the decision was taken by the harness")
def the_decision_was_taken_by_the_harness(world: World) -> None:
    answers = world.run.clarification.answers
    assert all(a.taken_by is DecisionMaker.harness for a in answers), [a.taken_by for a in answers]


@then(parsers.parse("the run leaves {n:d} question unanswered"))
def the_run_leaves_questions_unanswered(world: World, n: int) -> None:
    open_ = world.run.clarification.open_questions
    assert len(open_) == n and world.run.clarification.stopped_at_cap, [q.title for q in open_]


@then(parsers.parse('the specification carries the decision "{question}"'))
def the_specification_carries_the_decision(world: World, question: str) -> None:
    taken = world.run.spec.decisions_taken
    assert any(d.question == question for d in taken), [d.question for d in taken]


def _prompt_of(world: World, role: Role, marker: str = "") -> str:
    prompts = [
        t.prompt
        for t in world.extra["scenario"].calls
        if t.role is role and (not marker or marker in t.prompt)
    ]
    assert prompts, f"no {role.value} intervention{' for ' + marker if marker else ''}"
    return prompts[-1]


@then(parsers.parse('the specifier\'s prompt says "{text}"'))
def the_specifiers_prompt_says(world: World, text: str) -> None:
    assert text in _prompt_of(world, Role.specifier)


@then(parsers.parse('the producer\'s prompt says "{text}"'))
def the_producers_prompt_says(world: World, text: str) -> None:
    assert text in _prompt_of(world, Role.producer)


@then(parsers.parse('the test designer\'s prompt says "{text}"'))
def the_test_designers_prompt_says(world: World, text: str) -> None:
    assert text in _prompt_of(world, Role.test_designer)


@then(parsers.parse('the "{perspective}" reviewer\'s prompt says "{text}"'))
def the_reviewers_prompt_says(world: World, perspective: str, text: str) -> None:
    marker = f"Review the change from the perspective: **{perspective}**"
    assert text in _prompt_of(world, Role.reviewer, marker)


@then(parsers.parse('the run warns "{text}"'))
def the_run_warns(world: World, text: str) -> None:
    assert any(text in w for w in world.run.warnings), world.run.warnings


@then(parsers.parse('the report says "{text}"'))
def the_report_says(world: World, text: str) -> None:
    assert text in render_markdown(world.run, world.engine.store)


@then("the run ends delivered")
def the_run_ends_delivered(world: World) -> None:
    assert world.run.status is RunStatus.delivered, (world.run.stop_reason, world.run.warnings)
