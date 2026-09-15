"""Scenarios of ``tests/features/integration.feature``: bringing a delivered change into the
checkout the requester works in (``core/engine/engine.py``: ``merge_delivery``,
``check_integration``; ``core/git.py::integrate_branch``).

The steps walk one run to delivery over the sample project with the fake agents behind it, act
on the requester's own checkout through the engine, and read the history, the working tree and
the integration check back. Nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core import git
from harness495.core.engine import Engine, EngineError
from harness495.core.models import IntegrationCheck, Run, RunMode

scenarios("features/integration.feature")

INTENT = "add subtract to calc"
"""The intent every scenario here runs, and the subject a squash is expected to carry."""


def git_out(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def commit(root: Path, message: str, *paths: str) -> None:
    if paths:
        subprocess.run(["git", "add", *paths], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-aqm", message],
        cwd=root,
        check=True,
        capture_output=True,
    )


@dataclass
class Landing:
    """One delivered run, the checkout it may be brought into, and what the act reported."""

    project: Path
    engines: Callable[..., Engine]
    run_id: str
    stood_at: str = ""
    refused: Exception | None = None

    @property
    def run(self) -> Run:
        return self.engines().store.load(self.run_id)

    @property
    def verified_commit(self) -> str:
        iteration = self.run.current_iteration
        assert iteration is not None and iteration.version is not None
        return iteration.version.head_commit or ""

    @property
    def check(self) -> IntegrationCheck:
        found = self.run.result.integration
        assert found is not None, "the integration has not been checked"
        return found

    def act(self, what: Callable[[Engine], Run]) -> None:
        """Do one thing to the checkout, keeping a refusal rather than letting it escape."""
        self.stood_at = git.head_commit(self.project)
        try:
            what(self.engines())
        except (EngineError, git.GitError) as exc:
            self.refused = exc


@given("a run carried to delivery", target_fixture="world")
def a_run_carried_to_delivery(
    sample_project: Path, config: Any, engine_factory: Callable[..., Engine]
) -> Landing:
    engine = engine_factory()
    run = engine.create_run(INTENT, sample_project, config, RunMode.change)
    engine.run(run.id)
    return Landing(sample_project, engine_factory, run.id)


@given("the branch has moved on since")
def the_branch_has_moved_on(world: Landing) -> None:
    (world.project / "NOTES.md").write_text(
        "the branch went somewhere of its own\n", encoding="utf-8"
    )
    commit(world.project, "notes", "NOTES.md")


@given("the checkout stands on a detached HEAD")
def the_checkout_is_detached(world: Landing) -> None:
    git_out(world.project, "checkout", "-q", "--detach", "HEAD")


@given("the checkout carries a subtract of its own")
def the_checkout_carries_its_own_subtract(world: Landing) -> None:
    calc = world.project / "calc.py"
    calc.write_text(
        calc.read_text(encoding="utf-8")
        + "\n\ndef subtract(a: int, b: int) -> int:\n    return b - a\n",
        encoding="utf-8",
    )
    commit(world.project, "a subtract of its own")


@given("the checkout has uncommitted work")
def the_checkout_has_uncommitted_work(world: Landing) -> None:
    calc = world.project / "calc.py"
    calc.write_text(calc.read_text(encoding="utf-8") + "\n# half an idea\n", encoding="utf-8")


@given("the branch was merged into the checkout by hand")
def the_branch_was_merged_by_hand(world: Landing) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "merge",
            "-q",
            "--no-ff",
            "-m",
            "merge",
            f"495/{world.run_id}",
        ],
        cwd=world.project,
        check=True,
        capture_output=True,
    )


@when(parsers.parse("the delivery is integrated by {how}"))
def the_delivery_is_integrated(world: Landing, how: str) -> None:
    world.act(lambda engine: engine.merge_delivery(world.run_id, how))


@when(parsers.parse('the integration of "{ref}" is checked'))
def the_integration_is_checked(world: Landing, ref: str) -> None:
    world.act(lambda engine: engine.check_integration(world.run_id, ref))


@when(parsers.parse('the integration of "{ref}" is checked, running the verifications again'))
def the_integration_is_checked_again(world: Landing, ref: str) -> None:
    world.act(lambda engine: engine.check_integration(world.run_id, ref, rerun_verifications=True))


@when("the worktree of the run is cleaned up")
def the_worktree_is_cleaned_up(world: Landing) -> None:
    world.engines().cleanup_worktree(world.run_id)


@then("the checkout stands at the verified commit")
def the_checkout_stands_at_the_verified_commit(world: Landing) -> None:
    assert git_out(world.project, "rev-parse", "HEAD") == world.verified_commit


@then(parsers.parse("the history carries a merge commit: {answer}"))
def the_history_carries_a_merge_commit(world: Landing, answer: str) -> None:
    assert bool(git_out(world.project, "rev-list", "--merges", "HEAD")) is (answer == "yes")


@then(parsers.parse('the run records the integration as "{how}"'))
def the_run_records_the_integration(world: Landing, how: str) -> None:
    assert world.run.result.integrated_as == how


@then("the run records no integration")
def the_run_records_no_integration(world: Landing) -> None:
    assert world.run.result.integrated_as is None


@then("the run reads as landed")
def the_run_reads_as_landed(world: Landing) -> None:
    assert world.run.integration_state() == "landed", "integrating and checking are one command"


@then(parsers.parse('integrating a second time is refused, saying "{text}"'))
def integrating_a_second_time_is_refused(world: Landing, text: str) -> None:
    with pytest.raises(EngineError, match=text):
        world.engines().merge_delivery(world.run_id)


@then(parsers.parse('the integration is refused, saying "{text}"'))
def the_integration_is_refused(world: Landing, text: str) -> None:
    assert world.refused is not None and text in str(world.refused)


@then("the files of the checkout are those of the verified commit")
def the_files_are_those_of_the_verified_commit(world: Landing) -> None:
    assert world.check.files_identical


@then(parsers.parse("the checkout contains the verified commit: {answer}"))
def the_checkout_contains_the_verified_commit(world: Landing, answer: str) -> None:
    assert world.check.contains_commit is (answer == "yes")


@then(parsers.parse('the last commit subject starts with "{subject}"'))
def the_last_commit_subject_starts_with(world: Landing, subject: str) -> None:
    assert git_out(world.project, "log", "-1", "--format=%s").startswith(subject)


@then("what the branch had of its own is still there")
def what_the_branch_had_is_still_there(world: Landing) -> None:
    assert (world.project / "NOTES.md").exists()


@then("the commit message names the verified commit and the run")
def the_commit_message_names_the_evidence(world: Landing) -> None:
    body = git_out(world.project, "log", "-1", "--format=%B")
    assert f"Verified as {world.verified_commit[:12]} by 495 {world.run_id}." in body


@then(parsers.parse('the check names "{ref}" as the branch it landed in'))
def the_check_names_the_branch(world: Landing, ref: str) -> None:
    assert world.check.target_ref == ref, "the branch it landed in, not where the check was run"


@then(parsers.parse('the check records the commit "{ref}" stands at'))
def the_check_records_the_commit(world: Landing, ref: str) -> None:
    assert world.check.target_commit == git_out(world.project, "rev-parse", ref)


@then("the check finds neither the commit nor the files")
def the_check_finds_neither(world: Landing) -> None:
    assert not world.check.contains_commit and not world.check.files_identical


@then("the check finds the commit and the files")
def the_check_finds_both(world: Landing) -> None:
    assert world.check.contains_commit and world.check.files_identical


@then("the verifications passed on the checkout")
def the_verifications_passed_on_the_checkout(world: Landing) -> None:
    assert world.check.verifications_passed is True


@then("nothing is left of the worktree")
def nothing_is_left_of_the_worktree(world: Landing) -> None:
    assert not world.engines().worktree_path(world.run).exists()


@then("the checkout stands where it stood")
def the_checkout_stands_where_it_stood(world: Landing) -> None:
    assert git.head_commit(world.project) == world.stood_at


@then("no merge was left half-made")
def no_merge_was_left_half_made(world: Landing) -> None:
    assert not (world.project / ".git" / "MERGE_HEAD").exists(), "the merge was aborted, not left"


@then("the checkout is clean")
def the_checkout_is_clean(world: Landing) -> None:
    assert not git.is_dirty(world.project)


@then("the uncommitted work is still there")
def the_uncommitted_work_is_still_there(world: Landing) -> None:
    assert (world.project / "calc.py").read_text(encoding="utf-8").endswith("# half an idea\n")
