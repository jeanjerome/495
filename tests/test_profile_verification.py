from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from harness495.core.models import (
    BehaviourScenario,
    ProjectCommand,
    ProjectConfig,
    Requirement,
    RequirementKind,
    Spec,
    Sufficiency,
    Verification,
    VerificationKind,
)
from harness495.core.profile import detect_profile, read_doc_excerpts
from harness495.core.verification import (
    VersionMismatch,
    assess_sufficiency,
    classify_instrument,
    instrument_files,
    looks_like_a_test,
    run_verification,
)
from harness495.sandbox import Sandbox
from harness495.sandbox.base import CommandResult


def test_detect_python_and_node_and_makefile(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\ndependencies=["pytest","ruff"]\n[tool.mypy]\nstrict=true\n'
    )
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest", "lint": "eslint ."}})
    )
    (tmp_path / "Makefile").write_text("build:\n\techo hi\n")
    (tmp_path / "CONTRIBUTING.md").write_text("be nice")
    prof = detect_profile(tmp_path)
    names = {c.name: c for c in prof.commands}
    assert "python" in prof.languages and "javascript/typescript" in prof.languages
    assert names["test"].command.endswith("pytest -q")  # python detected first
    assert names["lint"].command.endswith("ruff check .")
    assert names["typecheck"].command.endswith("mypy .")
    assert names["build"].command == "make build"
    assert "CONTRIBUTING.md" in prof.doc_files
    assert read_doc_excerpts(tmp_path, ["CONTRIBUTING.md"])["CONTRIBUTING.md"] == "be nice"


def test_shell_is_detected_wherever_the_scripts_are_kept(tmp_path: Path) -> None:
    """Shell has no manifest to be recognised by, and its scripts are rarely at the root."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "deploy.sh").write_text("#!/bin/sh\necho deploying\n")
    assert "shell" in detect_profile(tmp_path).languages


def test_a_script_shipped_by_a_dependency_is_not_the_project(tmp_path: Path) -> None:
    """What is vendored says what a library is written in, not what this project is."""
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "install.sh").write_text("#!/bin/sh\n")
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".cache" / "leftover.sh").write_text("#!/bin/sh\n")
    assert "shell" not in detect_profile(tmp_path).languages


def test_a_helper_script_does_not_make_the_project_shell(tmp_path: Path) -> None:
    """The common layout everywhere: one deploy script beside the code it deploys."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\ndependencies=["pytest"]\n')
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "deploy.sh").write_text("#!/bin/sh\necho deploying\n")
    (tmp_path / "run.sh").write_text("#!/bin/sh\nexec python -m x\n")
    assert detect_profile(tmp_path).languages == ["python"]


def _shell_project(root: Path) -> None:
    (root / "scripts").mkdir()
    (root / "scripts" / "deploy.sh").write_text("#!/bin/sh\necho deploying\n")


def test_shellcheck_is_read_from_its_configuration(tmp_path: Path) -> None:
    _shell_project(tmp_path)
    (tmp_path / ".shellcheckrc").write_text("disable=SC2086\n")
    prof = detect_profile(tmp_path)
    assert "shellcheck" in prof.tooling
    assert prof.command("lint").command == "shellcheck $(git ls-files '*.sh')"


def test_shellcheck_is_read_from_a_directive_left_in_a_script(tmp_path: Path) -> None:
    """The commoner evidence by far: nobody writes the config, everybody silences a finding."""
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "release.sh").write_text(
        "#!/bin/sh\n# shellcheck disable=SC2086\nrm $files\n"
    )
    assert "shellcheck" in detect_profile(tmp_path).tooling


def test_bats_is_run_where_its_tests_are(tmp_path: Path) -> None:
    _shell_project(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "deploy.bats").write_text("@test 'it runs' {\n  true\n}\n")
    prof = detect_profile(tmp_path)
    assert "bats" in prof.tooling
    assert prof.command("test").command == "bats tests"


def test_shfmt_is_read_from_the_keys_only_it_knows(tmp_path: Path) -> None:
    _shell_project(tmp_path)
    (tmp_path / ".editorconfig").write_text("[*.sh]\nindent_style = space\n")
    assert "shfmt" not in detect_profile(tmp_path).tooling, "every editor reads indent_style"
    (tmp_path / ".editorconfig").write_text("[*.sh]\nswitch_case_indent = true\n")
    prof = detect_profile(tmp_path)
    assert "shfmt" in prof.tooling and prof.command("format").command == "shfmt -d ."


def test_shunit2_is_named_but_brings_no_command(tmp_path: Path) -> None:
    """It is sourced by the test script that uses it, and which one that is, is not ours."""
    _shell_project(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "shunit2").write_text("# vendored\n")
    prof = detect_profile(tmp_path)
    assert "shunit2" in prof.tooling
    assert [c.name for c in prof.commands] == []


def test_a_shell_toolchain_is_named_but_does_not_become_another_stack_lint(
    tmp_path: Path,
) -> None:
    """Naming it is right — it is used here. Making it the project's lint is not: it would
    say that two helper scripts are all this repository checks."""
    (tmp_path / "pom.xml").write_text("<project/>")
    _shell_project(tmp_path)
    (tmp_path / ".shellcheckrc").write_text("disable=SC2086\n")
    prof = detect_profile(tmp_path)
    assert prof.languages == ["java"] and "shellcheck" in prof.tooling
    assert all(c.name != "lint" for c in prof.commands)


def test_user_commands_win(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\ndependencies=["pytest"]\n')
    cfg = ProjectConfig(
        commands=[ProjectCommand(name="test", command="make check", kind=VerificationKind.test)]
    )
    prof = detect_profile(tmp_path, cfg)
    assert prof.command("test").command == "make check"


def test_assess_sufficiency_flags_gaps() -> None:
    spec = Spec(
        requirements=[
            Requirement(id="R1", statement="a", verification_ids=["V1"]),
            Requirement(id="R2", statement="b", verification_ids=["V2"]),
            Requirement(id="R3", statement="c", verification_ids=[]),
            Requirement(id="R4", statement="d", verification_ids=["V3"]),
        ],
        verifications=[
            Verification(id="V1", kind=VerificationKind.test, description="x", command="pytest -q"),
            Verification(id="V2", kind=VerificationKind.review, description="y"),
            Verification(
                id="V3",
                kind=VerificationKind.command,
                description="z",
                command="nonexistent-tool --check",
            ),
        ],
    )
    gaps = assess_sufficiency(spec, {"pytest -q"})
    assert spec.verification("V1").sufficiency is Sufficiency.sufficient
    assert spec.verification("V2").sufficiency is Sufficiency.insufficient
    assert spec.verification("V3").sufficiency is Sufficiency.insufficient
    assert [g.split(" ")[0] for g in gaps] == ["R2", "R3", "R4"]


def test_run_verification_records_evidence_and_checks_version(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", repo], check=True)
    (repo / "f").write_text("1")
    subprocess.run(
        ["git", "-c", "user.name=a", "-c", "user.email=a@a", "add", "."], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "-c", "user.name=a", "-c", "user.email=a@a", "commit", "-qm", "i"],
        cwd=repo,
        check=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    outputs: dict[str, str] = {}

    def sink(eid: str, text: str) -> str:
        outputs[eid] = text
        return f"evidence/{eid}/output.txt"

    v = Verification(
        id="V1",
        kind=VerificationKind.command,
        description="d",
        command="echo hello && exit 3",
        expected_exit_code=3,
    )
    ev = run_verification(v, repo, head, Sandbox(), 1, 30, sink, None, ["R1"])
    assert ev.passed is True and ev.exit_code == 3 and ev.requirement_ids == ["R1"]
    assert "hello" in outputs[ev.id] and ev.output_sha256
    with pytest.raises(VersionMismatch):
        run_verification(v, repo, "0" * 40, Sandbox(), 1, 30, sink)
    ev2 = run_verification(
        Verification(id="V2", kind=VerificationKind.manual, description="m"),
        repo,
        head,
        Sandbox(),
        1,
        30,
        sink,
    )
    assert ev2.passed is None and "not executed" in ev2.summary


def test_interpreter_normalisation() -> None:
    from harness495.core.verification import normalise_command, project_interpreters

    interpreters = project_interpreters({"/repo/.venv/bin/python -m pytest -q", "make lint"})
    assert interpreters == {"python": "/repo/.venv/bin/python", "python3": "/repo/.venv/bin/python"}
    cmd, note = normalise_command('python -c "import m; assert m.f.__doc__"', interpreters)
    assert cmd == '/repo/.venv/bin/python -c "import m; assert m.f.__doc__"' and note
    assert normalise_command("make lint", interpreters) == ("make lint", None)
    spec = Spec(
        requirements=[Requirement(id="R1", statement="a", verification_ids=["V1"])],
        verifications=[
            Verification(
                id="V1",
                kind=VerificationKind.command,
                description="d",
                command="python3 -c 'print(1)'",
            )
        ],
    )
    assert assess_sufficiency(spec, {"/repo/.venv/bin/python -m pytest -q"}) == []
    assert spec.verifications[0].command.startswith("/repo/.venv/bin/python -c")
    assert spec.verifications[0].sufficiency is Sufficiency.sufficient


def test_sufficiency_accepts_executables_on_path() -> None:
    spec = Spec(
        requirements=[
            Requirement(id="R1", statement="a", verification_ids=["V1"]),
            Requirement(id="R2", statement="b", verification_ids=["V2"]),
        ],
        verifications=[
            Verification(
                id="V1", kind=VerificationKind.command, description="w", command="echo hi"
            ),
            Verification(
                id="V2",
                kind=VerificationKind.command,
                description="z",
                command="no-such-tool-495 x",
            ),
        ],
    )
    gaps = assess_sufficiency(spec, {"pytest -q"})
    assert spec.verification("V1").sufficiency is Sufficiency.sufficient
    assert "exists on PATH" in spec.verification("V1").rationale
    assert spec.verification("V2").sufficiency is Sufficiency.insufficient
    assert "not found on this machine" in spec.verification("V2").rationale
    assert gaps == [
        "R2 has no sufficient verification (V2: insufficient (executable 'no-such-tool-495' not found on this machine))"
    ]


def test_failure_signature_ignores_where_and_when_but_not_what() -> None:
    from harness495.core.verification import failure_signature

    run_a = "FAILED at 10:04:11 in /Users/a/wt/x.py after 1.3 s (abc1234def5678)"
    run_b = "FAILED at 23:57:02 in /Users/b/other/x.py after 12.9 s (99ffee11223344)"
    assert failure_signature(run_a) == failure_signature(run_b)
    assert failure_signature("Tests run: 7, Failures: 0") != failure_signature(
        "Tests run: 7, Failures: 1"
    )
    assert failure_signature("no tests matching pattern") != failure_signature(
        "AssertionError: expected 3"
    )


def test_measures_the_change_is_conservative() -> None:
    from harness495.core.verification import measures_the_change
    from harness495.sandbox.base import CommandResult

    def result(exit_code: int | None, output: str, **kw: object) -> CommandResult:
        return CommandResult("cmd", exit_code, output, 0.1, **kw)  # type: ignore[arg-type]

    same = 'no tests matching pattern "NewTest" on project core'
    # Identical failure with and without the change: the command is not watching the change.
    assert not measures_the_change(1, same, result(1, same))
    # A different failure, or a different exit code, means the change moved the needle.
    assert measures_the_change(1, "AssertionError: expected 3", result(1, same))
    assert measures_the_change(2, same, result(1, same))
    # Anything that blurs the comparison is resolved in favour of the instrument.
    assert measures_the_change(None, same, result(1, same), subject_timed_out=True)
    assert measures_the_change(1, same, result(None, same, timed_out=True))


def _pair(exit_code: int, output: str = "") -> CommandResult:
    return CommandResult(command="c", exit_code=exit_code, output=output, duration_s=0.1)


def test_a_command_that_already_passes_cannot_carry_new_behaviour() -> None:
    """It reported success on a tree without the change; it will report it again after."""
    spec = Spec(
        requirements=[
            Requirement(id="R1", statement="a new class exists", verification_ids=["V1"]),
            Requirement(
                id="R2",
                statement="the existing suite still passes",
                kind=RequirementKind.non_regression,
                verification_ids=["V1"],
            ),
            Requirement(id="R3", statement="the new test asserts it", verification_ids=["V2"]),
        ],
        verifications=[
            Verification(id="V1", kind=VerificationKind.test, description="suite", command="mvn t"),
            Verification(
                id="V2",
                kind=VerificationKind.test,
                description="a new test",
                command="mvn t -Dtest=New",
                to_create=True,
                scenario=BehaviourScenario(when=["New runs"], then=["it asserts the behaviour"]),
            ),
        ],
    )
    gaps = assess_sufficiency(spec, {"mvn t"}, {"mvn t"})
    # R1 leans on a command that was green before the change. R2 asks exactly that of it, and R3
    # creates what it runs, so neither is a gap.
    assert [g.split(" ")[0] for g in gaps] == ["R1"]
    assert "already passed on the base version" in gaps[0]


def test_the_same_command_carries_new_behaviour_once_it_has_not_been_run() -> None:
    spec = Spec(
        requirements=[Requirement(id="R1", statement="a", verification_ids=["V1"])],
        verifications=[
            Verification(id="V1", kind=VerificationKind.test, description="s", command="mvn t")
        ],
    )
    assert assess_sufficiency(spec, {"mvn t"}, set()) == []


@pytest.mark.parametrize(
    "path,is_test",
    [
        ("infrastructure/src/test/java/io/x/UserFileRepositoryTest.java", True),
        ("infrastructure/src/main/java/io/x/UserFileRepository.java", False),
        ("tests/test_calc.py", True),
        ("pkg/foo_test.go", True),
        ("src/a.spec.ts", True),
        ("src/__tests__/a.js", True),
        ("features/login.feature", True),
        ("src/latest.py", False),
        ("docs/testing.md", False),
    ],
)
def test_which_files_of_a_change_are_the_instrument(path: str, is_test: bool) -> None:
    assert looks_like_a_test(path) is is_test
    assert instrument_files([path]) == ([path] if is_test else [])


def test_a_command_that_reports_something_else_without_the_change_is_believed() -> None:
    v = Verification(id="V1", kind=VerificationKind.test, description="d", command="c")
    discriminates, sufficiency, _ = classify_instrument(
        v, True, 0, "2 passed", False, _pair(1, "E   assert 8 == 2"), "abc123", ["tests/t.py"]
    )
    assert discriminates is True and sufficiency is Sufficiency.sufficient


def test_a_command_that_fails_on_both_versions_is_broken_not_a_defect() -> None:
    v = Verification(id="V1", kind=VerificationKind.test, description="d", command="c")
    same = "No tests matching pattern"
    discriminates, sufficiency, why = classify_instrument(
        v, False, 1, same, False, _pair(1, same), "abc123", ["tests/t.py"]
    )
    assert discriminates is False and sufficiency is Sufficiency.broken
    assert "no edit inside the change can make it report success" in why


def test_a_command_that_passes_on_both_versions_proves_nothing_either() -> None:
    v = Verification(id="V1", kind=VerificationKind.test, description="d", command="c")
    discriminates, sufficiency, why = classify_instrument(
        v, True, 0, "ok", False, _pair(0, "ok"), "abc123", ["tests/t.py"]
    )
    assert discriminates is False and sufficiency is Sufficiency.vacuous
    assert "either way" in why


def test_passing_on_both_settles_nothing_when_the_test_could_not_be_carried_over() -> None:
    """Without the change's test on the base version, the command had nothing to run there."""
    v = Verification(
        id="V1", kind=VerificationKind.test, description="d", command="c", to_create=True
    )
    discriminates, sufficiency, why = classify_instrument(
        v, True, 0, "ok", False, _pair(0, "ok"), "abc123", []
    )
    assert discriminates is None and sufficiency is Sufficiency.sufficient
    assert "not enough to tell" in why
