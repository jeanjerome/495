"""Questions answered on the surface: the keys that answer them, and the steps they take."""

from __future__ import annotations

import io
from typing import Any

import pytest
from rich.console import Console

from harness495.core.models import (
    DecisionKind,
    DecisionOption,
    Intent,
    PendingDecision,
    Run,
    RunStatus,
)
from harness495.interfaces.tui import Shell
from harness495.interfaces.tui.asking import Ask, LineEditor, ask_in_prompt
from harness495.interfaces.tui.keys import take_key
from harness495.interfaces.tui.loops import _press, open_create, open_decide
from harness495.interfaces.tui.source import StaticSource
from harness495.interfaces.tui.theme import THEME
from harness495.interfaces.tui.views import decision_question, intent_question, intent_taken


def _run(status: RunStatus = RunStatus.awaiting_decision) -> Run:
    return Run(
        id="run-0",
        harness_version="0",
        intent=Intent(text="add subtract to calc"),
        project_root="/p",
        status=status,
    )


def _asked(*, needs_note: bool = False) -> tuple[Run, PendingDecision]:
    run = _run()
    run.pending_decision = PendingDecision(
        kind=DecisionKind.acceptance,
        question="what should happen to the change?",
        options=[
            DecisionOption(key="accept", label="accept it", consequence="it is delivered"),
            DecisionOption(
                key="reject", label="reject it", consequence="nothing is", needs_note=needs_note
            ),
        ],
    )
    return run, run.pending_decision


def _type(ask: Ask, text: str) -> None:
    for character in text:
        ask.key(character)


# --------------------------------------------------------------------- the line


def test_the_line_takes_what_a_one_line_field_is_asked_for() -> None:
    editor = LineEditor("deploy")
    editor.key(" ")
    _keys(editor, "refuses a dirty tree")
    assert editor.text == "deploy refuses a dirty tree"
    editor.key("\x17")  # ctrl-w
    assert editor.text == "deploy refuses a dirty "
    editor.key("home")
    editor.key("X")
    assert editor.text.startswith("Xdeploy") and editor.caret == 1
    editor.key("\x15")  # ctrl-u
    assert editor.text == "deploy refuses a dirty " and editor.caret == 0


def _keys(editor: LineEditor, text: str) -> None:
    for character in text:
        editor.key(character)


def test_a_caret_in_the_middle_inserts_and_rubs_out_there() -> None:
    editor = LineEditor("abc")
    editor.key("left")
    editor.key("X")
    assert editor.text == "abXc"
    editor.key("backspace")
    assert editor.text == "abc" and editor.caret == 2


# --------------------------------------------------------------------- the keyboard


@pytest.mark.parametrize(
    ("data", "keys"),
    [
        (b"a", ["a"]),
        ("é".encode(), ["é"]),
        ("écrit".encode(), list("écrit")),
        (b"\x1b[A", ["up"]),
        (b"\x1b[B\x1b[B", ["down", "down"]),
        (b"\x1b", ["escape"]),
        (b"\r", ["enter"]),
        (b"\x7f", ["backspace"]),
        (b"\x15", ["\x15"]),
    ],
)
def test_the_bytes_a_terminal_sends_come_back_as_keys(data: bytes, keys: list[str]) -> None:
    """One key at a time, whatever the byte count: a paste is read whole and handed out."""
    out, rest = [], data
    while True:
        key, rest = take_key(rest)
        if key is None:
            break
        out.append(key)
    assert out == keys and rest == b""


def test_half_a_character_is_kept_and_a_stray_byte_is_dropped() -> None:
    """A terminal can split a character across two reads; a stray byte must not stop the key."""
    assert take_key("é".encode()[:1]) == (None, "é".encode()[:1])
    assert take_key(b"\xffA") == (None, b"A")


# --------------------------------------------------------------------- the steps


def test_a_run_that_produces_its_own_change_is_never_asked_for_a_ref() -> None:
    ask = Ask(intent_question(), commit=lambda answers: None)
    _type(ask, "make the deploy refuse a dirty tree")
    ask.key("enter")
    ask.key("enter")  # who writes it: 495 does, the first answer
    assert ask.state == "done"
    assert intent_taken(ask.answers) == ("make the deploy refuse a dirty tree", "")


def test_a_change_that_already_exists_is_asked_which_one() -> None:
    ask = Ask(intent_question(), commit=lambda answers: None)
    _type(ask, "port the store to sqlite")
    ask.key("enter")
    ask.key("down")
    ask.key("enter")  # it already exists
    ask.key("down")
    ask.key("enter")  # a commit
    assert ask.state == "asking"
    ask.key("enter")  # the ref, taking the default
    assert ask.state == "done"
    assert intent_taken(ask.answers) == ("port the store to sqlite", "HEAD")


def test_an_answer_that_needs_a_why_asks_for_one_and_refuses_an_empty_one() -> None:
    run, pending = _asked(needs_note=True)
    ask = Ask(decision_question(run, pending), commit=lambda answers: None)
    ask.key("down")
    ask.key("enter")  # reject, which needs a note
    assert ask.state == "asking" and ask.step is not None and ask.step.name == "note"
    ask.key("enter")
    assert ask.state == "asking" and ask.notice, "an empty record is not a record"
    _type(ask, "the deploy path is untested")
    ask.key("enter")
    assert ask.state == "done"
    assert ask.answers == {"choice": "reject", "note": "the deploy path is untested"}


def test_an_answer_that_needs_no_why_is_the_whole_question() -> None:
    run, pending = _asked()
    ask = Ask(decision_question(run, pending), commit=lambda answers: None)
    ask.key("enter")
    assert ask.state == "done" and ask.answers == {"choice": "accept"}


def test_escape_takes_back_the_last_answer_then_leaves() -> None:
    """The steps are a function of the answers, so going back is dropping one."""
    ask = Ask(intent_question(), commit=lambda answers: None)
    _type(ask, "port the store")
    ask.key("enter")
    ask.key("down")
    ask.key("enter")  # it already exists
    assert ask.step is not None and ask.step.name == "which"
    ask.key("escape")
    assert ask.step is not None and ask.step.name == "who"
    assert ask.cursor == 1, "it comes back standing on the answer it took"
    ask.key("escape")
    assert ask.step is not None and ask.step.name == "intent"
    assert ask.editor.text == "port the store", "and with what was typed into it"
    ask.key("escape")
    assert ask.state == "cancelled"


# --------------------------------------------------------------------- both ways of asking


def test_a_prompted_session_walks_the_same_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    """One question, two renderings: the steps are the question, so the answers must agree."""
    typed = iter(["port the store to sqlite", "evaluate", "commit", "main..work"])
    monkeypatch.setattr(
        "harness495.interfaces.tui.asking.Prompt.ask",
        staticmethod(lambda *args, **kwargs: next(typed)),
    )
    console = Console(theme=THEME, file=io.StringIO(), width=100)
    answers = ask_in_prompt(console, intent_question())
    assert answers is not None
    assert intent_taken(answers) == ("port the store to sqlite", "main..work")

    ask = Ask(intent_question(), commit=lambda a: None)
    _type(ask, "port the store to sqlite")
    ask.key("enter")
    ask.key("down")
    ask.key("enter")
    ask.key("down")
    ask.key("enter")
    _type(ask, "main..work")
    ask.key("enter")
    assert ask.answers == answers


# --------------------------------------------------------------------- on the surface


def _surface(run: Run) -> Shell:
    console = Console(theme=THEME, file=io.StringIO(), width=150, highlight=False)
    return Shell(StaticSource([run], []), console, animated=False, selected=run.id)


def test_a_question_owns_the_keyboard_while_it_is_open() -> None:
    """`q` typed into a field is a q. A key that quit the surface would lose the answer."""
    run, pending = _asked(needs_note=True)
    shell = _surface(run)
    shell.view = "verdict"
    open_decide(shell)
    assert shell.asking is not None
    shell.asking.key("down")
    shell.asking.key("enter")
    for key in "quit s p":
        _press(shell, key, None, None)  # type: ignore[arg-type]
    assert shell.running, "q went into the note"
    assert shell.asking is not None and shell.asking.editor.text == "quit s p"
    assert shell.can("decide") is False, "no control acts while the keyboard is taken"
    assert [k for k, _, _ in shell.footer_keys()] == ["enter", "esc"]


def test_the_question_is_drawn_where_the_panel_it_replaces_stood() -> None:
    run, pending = _asked()
    shell = _surface(run)
    shell.view = "verdict"
    before = _drawn(shell)
    assert "d " in before and "answer it here" in before
    open_decide(shell)
    after = _drawn(shell)
    assert "what should happen to the change?" in after
    assert "answer it here" not in after, "the panel that only points at the question is gone"
    assert "take it" in after


def _drawn(shell: Shell, width: int = 150) -> str:
    out = io.StringIO()
    console = Console(theme=THEME, file=out, width=width, highlight=False, legacy_windows=False)
    console.print(shell.body(width, 60))
    return out.getvalue()


def test_a_surface_with_no_project_says_so_instead_of_asking(monkeypatch: Any) -> None:
    shell = _surface(_run(RunStatus.created))
    open_create(shell)
    assert shell.asking is None
    assert shell.driver.notice is not None and "no project" in shell.driver.notice
