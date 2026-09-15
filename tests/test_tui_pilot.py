"""Driving a run from the surface: an intent in, a decision answered, a merge checked.

The surface is the workflow, so what it can *do* is tested the way what it shows is tested —
against a real store walked by the fake agents, not against a mock of the engine.
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from harness495.core.store import RunStore
from harness495.interfaces.tui import Shell, StoreSource
from harness495.interfaces.tui.attention import attention
from harness495.interfaces.tui.driving import StoreDriver
from harness495.interfaces.tui.loops import _press, answer, open_merge
from harness495.interfaces.tui.stages import stage_state
from harness495.interfaces.tui.theme import THEME

WAIT = 120.0
"""Long enough for the fake agents and a real pytest run; a hung driver still fails the test."""


@pytest.fixture
def store(sample_project: Path) -> RunStore:
    return RunStore(sample_project / ".495")


@pytest.fixture
def pilot(store: RunStore, sample_project: Path, engine_factory: Any) -> StoreDriver:
    """A driver over the sample project, with the fake agents behind it.

    A run created here reads the project's own configuration from disk — that is the point of
    typing an intent into the surface rather than into a test — so the sample project gets the
    one setting that would otherwise stop every run at the gate.
    """
    (sample_project / ".495" / "config.toml").write_text("auto_approve = true\n", encoding="utf-8")
    return StoreDriver(store, project=sample_project, engine_factory=lambda: engine_factory())


def surface(store: RunStore, pilot: StoreDriver, width: int = 150) -> Shell:
    """A surface with the first run open, if the store holds one; the listing otherwise."""
    console = Console(theme=THEME, file=io.StringIO(), width=width, highlight=False)
    runs = store.list_runs()
    return Shell(
        StoreSource(store),
        console,
        animated=False,
        driver=pilot,
        selected=runs[0].id if runs else None,
    )


def render(shell: Shell, view: str, width: int = 150) -> str:
    shell.view = view
    out = io.StringIO()
    console = Console(theme=THEME, file=out, width=width, highlight=False, legacy_windows=False)
    console.print(shell.flow(width))
    return out.getvalue()


def settle(pilot: StoreDriver, quiet: bool = True) -> None:
    assert pilot.wait(WAIT), "the driver is still working"
    if quiet:
        assert pilot.notice is None, pilot.notice


# --------------------------------------------------------------------- from an intent


# --------------------------------------------------------------------- start, pause, answer


# --------------------------------------------------------------------- the eighth stop


def test_the_integration_check_runs_from_the_surface(
    store: RunStore, pilot: StoreDriver, sample_project: Path
) -> None:
    run_id = pilot.create("add subtract to calc")
    settle(pilot)
    run = store.load(run_id)
    assert run.result.branch
    _git(sample_project, "merge", "--no-ff", "-m", "merge", run.result.branch)

    shell = surface(store, pilot)
    shell.select(run_id)
    shell.view = "integration"
    assert ("i", "check a ref") in shell.controls()
    assert "not checked yet" in render(shell, "integration").lower()

    pilot.integrate(run_id, "HEAD", False)
    settle(pilot)
    shell.source.refresh(force=True)
    check = shell.run.result.integration
    assert check is not None and check.contains_commit and check.files_identical
    assert stage_state(shell.run, "integration") == "done"
    assert "integration check" in render(shell, "integration")


def test_a_ref_nobody_merged_into_is_not_a_failed_integration(
    store: RunStore, pilot: StoreDriver, sample_project: Path
) -> None:
    """Asking about a tree you have not merged into is answered "not yet", not "it broke".

    The check records two booleans and both are false here — which is also what they are when
    a merge went wrong. Told apart by the commit the run branched from, they are opposite
    facts, and only one of them is worth a red stop.
    """
    run_id = pilot.create("add subtract to calc")
    settle(pilot)
    shell = surface(store, pilot)
    shell.select(run_id)
    before = attention(shell.run, can_drive=True)

    pilot.integrate(run_id, "HEAD", False)  # nothing was merged
    settle(pilot)
    shell.source.refresh(force=True)

    check = shell.run.result.integration
    assert check is not None and not check.contains_commit and not check.files_identical
    assert shell.run.integration_state() == "unmerged"
    assert stage_state(shell.run, "integration") == "blocked", "the merge is still yours to make"
    after = attention(shell.run, can_drive=True)
    assert after.tone == before.tone == "good", "asking must not turn a delivered run red"
    assert "has not been merged into" in after.detail
    assert "nothing of this run has been merged into it" in check.detail
    assert "evaluated" not in check.detail, "nothing was integrated, so nothing can differ"


def test_a_tree_that_carries_something_else_is_named_as_such(
    store: RunStore, pilot: StoreDriver, sample_project: Path
) -> None:
    run_id = pilot.create("add subtract to calc")
    settle(pilot)
    _git(sample_project, "commit", "--allow-empty", "-m", "the branch moved on without it")
    pilot.integrate(run_id, "HEAD", False)
    settle(pilot)
    shell = surface(store, pilot)
    shell.select(run_id)
    check = shell.run.result.integration
    assert check is not None and not check.contains_commit and not check.files_identical
    assert shell.run.integration_state() == "differs"
    assert stage_state(shell.run, "integration") == "failed"
    assert attention(shell.run, can_drive=True).tone == "bad"


def test_the_last_moves_are_offered_from_wherever_you_are_standing(
    store: RunStore, pilot: StoreDriver, sample_project: Path
) -> None:
    """What is left to do on a delivered run is not hidden behind the stop that owns it."""
    run_id = pilot.create("add subtract to calc")
    settle(pilot)
    shell = surface(store, pilot)
    shell.select(run_id)
    shell.view = "change"
    assert shell.resolve("m") == "merge" and shell.resolve("i") == "integrate"
    assert ("m", "merge the branch") in shell.controls()
    assert ("i", "check a ref") in shell.controls()
    assert attention(shell.run, can_drive=True).key == "m", "nothing is in the tree yet"
    assert attention(shell.run, can_drive=False).key == "8", "and the stop where it cannot act"


def test_the_surface_makes_the_merge_it_then_checks(
    store: RunStore, pilot: StoreDriver, sample_project: Path
) -> None:
    """One control for one act: the merge is what the check that follows it exists to inspect."""
    run_id = pilot.create("add subtract to calc")
    settle(pilot)
    shell = surface(store, pilot)
    shell.select(run_id)
    assert shell.run.integration_state() == "unchecked"

    pilot.merge(run_id, "fast-forward", False)
    settle(pilot)
    shell.source.refresh(force=True)

    assert shell.run.integration_state() == "landed", shell.driver.notice
    assert stage_state(shell.run, "integration") == "done"
    assert not shell.can("merge"), "there is nothing left to merge"
    assert attention(shell.run, can_drive=True).key == "i"


def test_pressing_the_key_merges_and_the_run_says_so_afterwards(
    store: RunStore, pilot: StoreDriver, sample_project: Path
) -> None:
    """The whole path, keystroke to merge commit: nothing acts until the question is answered."""
    run_id = pilot.create("add subtract to calc")
    settle(pilot)
    shell = surface(store, pilot)
    shell.select(run_id)
    shell.view = "integration"
    before = _git_out(sample_project, "rev-parse", "HEAD")

    _press(shell, "m", None, None)
    assert shell.asking is not None, shell.driver.notice
    assert _git_out(sample_project, "rev-parse", "HEAD") == before, "the question has not acted"

    answer(shell, "enter")  # fast-forward: move the branch onto it
    answer(shell, "enter")  # and on the result: compare only
    settle(pilot)
    shell.source.refresh(force=True)

    assert shell.asking is None
    assert shell.driver.notice is None
    assert _git_out(sample_project, "rev-parse", "HEAD") != before
    assert shell.run.integration_state() == "landed"


def test_the_two_last_stops_say_the_same_thing_about_a_copied_change(
    store: RunStore, pilot: StoreDriver, sample_project: Path
) -> None:
    """A rebase leaves the delivered commit out of your branch on purpose.

    Read off the two booleans, that is indistinguishable from a merge that went wrong — which
    is how the seventh stop came to call a run "not confirmed" while the eighth, three keys
    away, called the same run integrated. Both read the state now, so they cannot disagree.
    """
    run_id = pilot.create("add subtract to calc")
    settle(pilot)
    _git(sample_project, "commit", "--allow-empty", "-m", "your branch went somewhere of its own")

    pilot.merge(run_id, "rebase", False)
    settle(pilot)
    shell = surface(store, pilot)
    shell.select(run_id)

    check = shell.run.result.integration
    assert check is not None and not check.contains_commit and check.files_identical
    assert shell.run.integration_state() == "landed"
    deliver = render(shell, "deliver")
    assert "not confirmed" not in deliver
    assert "main carries it, as a rebase" in deliver
    assert "nothing has been merged" not in deliver, "it has been"
    assert "merge --no-ff" not in deliver, "offering it again would merge it twice"


def test_a_stop_with_nothing_left_to_do_says_so_and_offers_no_work(
    store: RunStore, pilot: StoreDriver, sample_project: Path
) -> None:
    """The last screen of a run has to answer "am I done", in those words.

    A green border and a breakdown of three rows are evidence, not an answer, and a control
    offered in the same shape as before the merge is a fourth row of evidence that there is
    something still owed.
    """
    run_id = pilot.create("add subtract to calc")
    settle(pilot)
    shell = surface(store, pilot)
    shell.select(run_id)

    before = render(shell, "integration")
    assert "Nothing has been merged" in before
    assert "is the next move" in before, "one of the two keys is the one to press"

    pilot.merge(run_id, "fast-forward", False)
    settle(pilot)
    shell.source.refresh(force=True)

    after = render(shell, "integration")
    assert "main carries the verified change" in after
    assert "Nothing is left to do here" in after
    assert "is being looked for" not in after, "the breakdown below is the answer to that"
    assert "bring 495/" not in after, "there is nothing left to bring"
    assert ("i", "check it again") in shell.controls()


def test_a_tree_with_uncommitted_work_is_told_so_before_the_question_opens(
    store: RunStore, pilot: StoreDriver, sample_project: Path
) -> None:
    """A question whose only outcome is a refusal is a refusal asked in four keystrokes."""
    run_id = pilot.create("add subtract to calc")
    settle(pilot)
    calc = sample_project / "calc.py"
    calc.write_text(calc.read_text(encoding="utf-8") + "\n# half an idea\n", encoding="utf-8")
    shell = surface(store, pilot)
    shell.select(run_id)

    open_merge(shell)

    assert shell.asking is None
    assert "uncommitted changes" in (shell.driver.notice or "")
    assert calc.read_text(encoding="utf-8").endswith("# half an idea\n"), "it was left alone"


# --------------------------------------------------------------------- two terminals


# --------------------------------------------------------------------- leaving


def _git_out(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
