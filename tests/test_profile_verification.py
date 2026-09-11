from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from harness495.core.models import (
    ProjectCommand,
    ProjectConfig,
    Requirement,
    Spec,
    Sufficiency,
    Verification,
    VerificationKind,
)
from harness495.core.profile import detect_profile, read_doc_excerpts
from harness495.core.verification import VersionMismatch, assess_sufficiency, run_verification
from harness495.sandbox import Sandbox


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
