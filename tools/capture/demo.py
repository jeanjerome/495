#!/usr/bin/env python3
"""The two halves of the recorded demo: the store it opens on, and the 495 that drives it.

The recording is not a reconstruction. What is typed into it is the real command, what answers
is the real surface, and the run it opens is walked by the real engine — the worktree, the
commits, the project's own check scripts, the control runs on the base version, the verdict,
the merge and the integration check all happen. The only thing replaced is what a second take
would otherwise cost: the specifier, the producer and the reviewers are the scripted objects
:mod:`surface` already uses for the README's images, so a take calls no agent and spends no
quota.

Three of the four chapters are walked before the camera runs, which is what gives the store a
history to open on. The fourth is left for the camera, because it is the one thing a still
cannot show: a run created from an intent typed into the surface, stopping at the
specification gate, and carrying on from the answer given there.

Usage::

    python tools/capture/demo.py stage --at /tmp/495-demo   # prints the project it built
    python tools/capture/demo.py cli watch                  # what the tape types as `495`

``record.sh`` runs both: it stages, puts a ``495`` on PATH that lands here, and hands the tape
to vhs.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import surface  # noqa: E402
from surface import LANG, REPEAT, SHOUT, STDIN  # noqa: E402

STAGED = (LANG, REPEAT, STDIN)
"""What the store already holds when the recording starts: one stopped on a requirement no
command can decide, one delivered after a correction iteration, one standing at the gate."""

LIVE = SHOUT
"""The chapter left for the camera, and the one the README's console blocks narrate.

Every requirement it raises has a command that decides it, so the run walks to a verdict that
rests on evidence alone and to a branch that fast-forwards. It still stops once, at the
specification gate, because that gate is where a run asks before anything is produced —
which is the one thing a still cannot show.
"""

PACE = float(os.environ.get("DEMO_PACE", "8.0"))
"""Seconds an intervention holds before answering.

A real one takes minutes, a scripted one microseconds, and neither is watchable: the first
outlasts the recording, the second walks all eight stops between two frames. This is the third
thing, and it is the only number in the demo chosen for the camera rather than by the work.

Eight seconds is what makes a stage still be working when the recording arrives at it: five
interventions hold the run for forty, which is about as long as the tape spends walking from
the specification to the verdict. Shorter, and every stage is already finished when it is
shown.
"""

WHERE = Path(os.environ.get("DEMO_AT", "/tmp/495-demo"))
"""Where the project is built. It is on screen — the store's page prints the root it reads —
so it is somewhere that says "a demo project" rather than a temporary directory's noise."""

CONFIG = """# How 495 is set up for this project.

[agents.default]
kind = "claude_code"
model = "sonnet"

[roles]
specifier = "default"
test_designer = false
producer = "default"
reviewers = [
  { perspective = "spec_compliance", agent = "default" },
  { perspective = "correctness", agent = "default" },
  { perspective = "conventions", agent = "default" },
]

[budget]
max_cost_usd = 5.0
max_iterations = 3

[sandbox]
backend = "seatbelt"
"""
"""The configuration the recorded CLI reads for itself.

The images set this in code and hand it to the engine; the recording cannot, because the run
it opens is created by 495 from a keystroke, and what that reads is the file. Same agents,
same reviewers, same ceilings — written where a project would write them.

Nothing says ``auto_approve`` here, so it is off, as it is for anyone who has not turned it
on: the run created on camera stops at the specification gate and waits to be approved.
"""


def stage(at: Path) -> Path:
    """Build the project and walk the store up to where the recording starts."""
    from harness495.core.config import load_config
    from harness495.core.engine import worktrees_root
    from harness495.core.store import RunStore

    # Beside the project, so that wiping one wipes the other. A run's worktree is registered
    # with the repository it was cut from, and the repository here is rebuilt at the same path
    # every time: worktrees kept anywhere else would outlive it and be handed to git as
    # directories of a repository that no longer exists.
    os.environ.setdefault("HARNESS495_WORKTREES_DIR", str(at / "worktrees"))

    shutil.rmtree(at, ignore_errors=True)
    at.mkdir(parents=True)
    project = surface.make_project(at / "greeter")
    shutil.rmtree(worktrees_root(None, project), ignore_errors=True)
    (project / ".495" / "config.toml").write_text(CONFIG, encoding="utf-8")

    # The chapters walked here are walked exactly as the images walk them, gate included: an
    # approval given off camera is an approval nobody sees, so it is not asked for.
    config = load_config(project)
    config.auto_approve = True

    store = RunStore(project / ".495")
    # What each chapter settled on goes to stderr: the tape reads this command's stdout to
    # learn where the project is, and a line of anything else there is a path it would cd to.
    with contextlib.redirect_stdout(sys.stderr):
        surface.build(project, config, store, chapters=STAGED)
    # Ages, but not a pretended root: these runs are about to be advanced and merged on
    # camera, and a run can only be driven where it really is.
    surface.dress(store, root=None)
    return project


def cli(argv: list[str]) -> None:
    """495 itself, with the scripted agents behind the engine.

    Behind the *engine* only. ``doctor`` resolves agents through the registry rather than
    through a run, so it goes on probing the real ones and reports what this machine actually
    has — which is what makes it worth showing at all.
    """
    from harness495.core import engine as engine_mod

    held = {"script": LIVE.script()}
    engine_mod.build_agent = surface.scripted(held, PACE)  # type: ignore[assignment,attr-defined]
    surface.pin_ids([LIVE.run_id])

    from harness495.interfaces.cli import main

    sys.argv = ["495", *argv]
    main()


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "stage":
        parser = argparse.ArgumentParser(prog="demo.py stage", description="build the store")
        parser.add_argument("--at", type=Path, default=WHERE, help="where to build the project")
        print(stage(parser.parse_args(sys.argv[2:]).at))
    elif mode == "cli":
        cli(sys.argv[2:])
    else:
        sys.exit(f"usage: {Path(sys.argv[0]).name} stage [--at <dir>] | cli <495 arguments>")


if __name__ == "__main__":
    main()
