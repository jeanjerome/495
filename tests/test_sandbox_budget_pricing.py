from __future__ import annotations

import platform
import stat
import time
from pathlib import Path

import pytest

from four95.core import budget as budget_mod
from four95.core import pricing
from four95.core.models import (
    AgentIdentity,
    AgentKind,
    Budget,
    Capability,
    Cost,
    CostBasis,
    Intent,
    Intervention,
    Role,
    Run,
    SandboxConfig,
    SandboxInfo,
    Usage,
)
from four95.sandbox import DockerSandbox, Sandbox, SeatbeltSandbox, select_sandbox
from four95.sandbox.base import ExecRequest


def test_host_sandbox_runs_and_kills_on_timeout(tmp_path: Path) -> None:
    sb = Sandbox()
    res = sb.run(ExecRequest(command="echo out; echo err 1>&2; exit 2", cwd=tmp_path, timeout_s=10))
    assert res.exit_code == 2 and "out" in res.output and "err" in res.output
    start = time.monotonic()
    res = sb.run(ExecRequest(command="sleep 30", cwd=tmp_path, timeout_s=1))
    assert res.timed_out and res.exit_code is None and time.monotonic() - start < 10


def test_host_sandbox_stop_check(tmp_path: Path) -> None:
    calls = {"n": 0}

    def stop() -> bool:
        calls["n"] += 1
        return calls["n"] > 2

    res = Sandbox().run(
        ExecRequest(command="sleep 30", cwd=tmp_path, timeout_s=30, stop_check=stop)
    )
    assert res.interrupted and not res.timed_out


@pytest.mark.skipif(platform.system() != "Darwin", reason="seatbelt is macOS only")
def test_seatbelt_confines_writes_and_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tempfile

    work = tmp_path / "work"
    other = tmp_path / "other"
    work.mkdir()
    other.mkdir()
    (work / "tmp").mkdir()
    # pytest's tmp_path lives under the user's TMPDIR, which the profile allows: point TMPDIR inside work.
    monkeypatch.setattr(tempfile, "tempdir", str(work / "tmp"))
    sb = SeatbeltSandbox()
    assert sb.available()[0]
    ok = sb.run(
        ExecRequest(
            command="echo hi > inside.txt && cat inside.txt", cwd=work, timeout_s=20, writable=True
        )
    )
    assert ok.exit_code == 0 and (work / "inside.txt").exists()
    outside = sb.run(
        ExecRequest(command=f"echo hi > {other}/x.txt", cwd=work, timeout_s=20, writable=True)
    )
    assert outside.exit_code != 0 and not (other / "x.txt").exists()
    ro = sb.run(ExecRequest(command="echo hi > ro.txt", cwd=work, timeout_s=20, writable=False))
    assert ro.exit_code != 0 and not (work / "ro.txt").exists()
    net = sb.run(ExecRequest(command="curl -s -m 3 https://example.com", cwd=work, timeout_s=20))
    assert net.exit_code != 0
    info = sb.describe(ExecRequest(command="x", cwd=work, timeout_s=1, writable=False))
    assert info.network == "denied" and info.writable_paths == []


def test_docker_wrap_and_unavailable(tmp_path: Path) -> None:
    fake = tmp_path / "docker"
    fake.write_text("#!/bin/sh\necho 'no daemon' 1>&2\nexit 1\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    sb = DockerSandbox("img:1", executable=str(fake))
    ok, why = sb.available()
    assert not ok and "daemon" in why
    argv = sb.wrap(ExecRequest(command="ls", cwd=tmp_path, timeout_s=1, writable=False))
    assert "--network" in argv and argv[argv.index("--network") + 1] == "none"
    assert any(a.endswith(":/work:ro") for a in argv)
    assert argv[-3:] == ["img:1", "/bin/sh", "-c"][:0] + ["/bin/sh", "-c", "ls"]


def test_select_sandbox_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    sb, warnings = select_sandbox(SandboxConfig(backend="host"))
    assert sb.name == "host" and warnings == []
    monkeypatch.setattr(DockerSandbox, "available", lambda self: (False, "down"))
    sb, warnings = select_sandbox(SandboxConfig(backend="docker"))
    assert sb.name in ("seatbelt", "host") and any("docker" in w for w in warnings)


def test_pricing_lookup_and_estimate() -> None:
    assert pricing.lookup("gpt-5-2026-01-01") is not None
    assert pricing.lookup("openai/gpt-5-mini") is not None
    assert pricing.lookup("totally-unknown") is None
    usage = Usage(input_tokens=1_000_000, output_tokens=0)
    est = pricing.estimate("gpt-5-mini", usage)
    assert est.basis is CostBasis.estimated and est.usd == pytest.approx(0.25)
    unknown = pricing.estimate("nope", usage)
    assert unknown.usd is None and unknown.basis is CostBasis.unknown
    assert pricing.context_window("gpt-5") == 400000
    assert pricing.context_window("nope", 123) == 123


def _run() -> Run:
    return Run(
        id="run-b",
        intent=Intent(text="x"),
        project_root="/tmp",
        budget=Budget(
            max_cost_usd=1.0, max_interventions=2, context_warn_ratio=0.5, context_abort_ratio=0.9
        ),
    )


def _intervention(cost: float | None, peak: int) -> Intervention:
    return Intervention(
        id="int-1",
        iteration=1,
        role=Role.producer,
        agent=AgentIdentity(kind=AgentKind.codex, name="c", model="gpt-5"),
        capability=Capability.write,
        sandbox=SandboxInfo(backend="x"),
        cwd="/tmp",
        timeout_s=1,
        usage=Usage(
            input_tokens=100, output_tokens=10, context_window=1000, context_peak_tokens=peak
        ),
        cost=Cost(usd=cost, basis=CostBasis.estimated if cost is not None else CostBasis.unknown),
    )


def test_budget_checks_and_warnings() -> None:
    run = _run()
    assert budget_mod.check_before(run).ok
    warnings = budget_mod.record(run, _intervention(0.6, 600))
    assert any("context window at 60%" in w for w in warnings)
    assert run.consumption.cost_usd == 0.6 and run.consumption.interventions == 1
    assert budget_mod.per_intervention_budget(run, 10.0) == pytest.approx(0.4)
    warnings = budget_mod.record(run, _intervention(0.5, 950))
    assert any("above the abort ratio" in w for w in warnings) and any(
        "exceeds the limit" in w for w in warnings
    )
    check = budget_mod.check_before(run)
    assert not check.ok and "limit" in check.reason
    run2 = _run()
    budget_mod.record(run2, _intervention(None, 10))
    assert (
        run2.consumption.cost_unknown_interventions == 1
        and run2.consumption.cost_basis is CostBasis.unknown
    )
