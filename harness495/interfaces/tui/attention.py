"""The one line that says what the run needs from you.

A run's status ("reviewing") leaves the user to work out whether that means "wait", "act" or
"it is over". Those are the only three answers that matter, and they belong on every screen,
not on a tab. This is that line — and since the surface can now advance a run, it also carries
the key that does it, so "it is stopped" and "this is what starts it again" are never two
separate discoveries.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from harness495.core.models import Capability, Run, RunStatus
from harness495.interfaces.tui.driving import Activity
from harness495.interfaces.tui.reading import running_intervention
from harness495.interfaces.tui.stages import STAGE_INDEX, STAGES, stage_of
from harness495.interfaces.tui.widgets.text import clip, hms


@dataclass(frozen=True)
class Attention:
    tone: str
    glyph: str
    headline: str
    detail: str
    key: str | None = None
    action: str = ""
    working: bool = False


# What the harness itself is doing when no agent holds the tree. Without this the header goes
# quiet exactly when the run is between two agents, which reads as "stalled".
HARNESS_WORK = {
    RunStatus.created: "reading the project: languages, tooling, verification commands",
    RunStatus.profiled: "handing the intent to the specifier",
    RunStatus.specified: "waiting at the gate",
    RunStatus.ready: "opening the worktree for the producer",
    RunStatus.produced: "checking the change stayed inside the allowed paths",
    RunStatus.verifying: "running the verification commands on the candidate",
    RunStatus.verified: "dispatching one reviewer per perspective",
    RunStatus.reviewed: "turning the evidence into a verdict, requirement by requirement",
    RunStatus.accepted: "writing the patch, the branch and the report",
}
STOPPED = {RunStatus.failed, RunStatus.aborted, RunStatus.rejected}


def attention(
    run: Run,
    frozen: bool = False,
    activity: Activity | None = None,
    held: str | None = None,
    can_drive: bool = False,
) -> Attention:
    """What the run needs, given what is being done to it and by whom.

    ``activity`` is what this surface is doing to the run, ``held`` is another process doing
    it. A run that is neither is not "working" however promising its status reads: it is
    standing still, and saying so is the difference between waiting for nothing and pressing
    one key.
    """
    here = STAGES[STAGE_INDEX[stage_of(run)]]
    pending = run.pending_decision
    if pending is not None:
        return Attention(
            tone="attn.you",
            glyph="◆",
            headline=f"waiting on you · {pending.kind.value.replace('_', ' ')}",
            detail=clip(pending.question, 150),
            key="d",
            action="answer it",
        )
    if frozen:
        return Attention(
            tone="attn.you",
            glyph="‖",
            headline="display frozen",
            detail="nothing on screen is refreshing; the run itself is untouched",
            key="space",
            action="thaw it",
        )
    if run.status is RunStatus.paused:
        return Attention(
            tone="attn.you",
            glyph="‖",
            headline=f"paused at {stage_of(run)}",
            detail=clip(run.stop_reason or "stopped between two steps", 150),
            key="s" if can_drive else here.key,
            action="continue it" if can_drive else "see where it stopped",
        )
    if run.status in STOPPED:
        retry = can_drive and run.status is RunStatus.failed
        return Attention(
            tone="attn.dead",
            glyph="✕",
            headline=f"stopped · {run.status.value}",
            detail=clip(run.stop_reason or run.result.summary or "nothing was delivered", 150),
            key="s" if retry else here.key,
            action=f"try again at {stage_of(run)}" if retry else "see where it stopped",
        )
    if run.status is RunStatus.delivered and activity is None:
        g = run.result.integration
        if g is None:
            return Attention(
                tone="attn.done",
                glyph="●",
                headline="delivered",
                detail="the patch and the branch are ready; nothing has been merged",
                key="8",
                action="check what you merged",
            )
        landed = g.contains_commit or g.files_identical
        return Attention(
            tone="attn.done" if landed else "attn.dead",
            glyph="●" if landed else "✕",
            headline="delivered and integrated" if landed else "delivered, but not integrated",
            detail=clip(f"{g.target_ref}: {g.detail}", 150),
            key="8",
            action="the integration check",
        )
    live = running_intervention(run)
    if live is not None:
        who = f"{live.agent.kind.value}:{live.agent.model or 'default'}"
        role = live.role.value + (f" · {live.perspective}" if live.perspective else "")
        elapsed = (dt.datetime.now(dt.UTC) - live.started_at).total_seconds()
        return Attention(
            tone="attn.work",
            glyph="◉",
            headline=f"{role} working",
            detail=(
                f"{who}, {'writing to' if live.capability is Capability.write else 'reading'} "
                f"the worktree · {hms(elapsed)} of a {live.timeout_s // 60}m timeout"
            ),
            key="p" if can_drive and held is None else here.key,
            action="pause the run" if can_drive and held is None else "watch it",
            working=True,
        )
    if activity is not None:
        return Attention(
            tone="attn.work",
            glyph="◉",
            headline=f"{activity.verb} · {stage_of(run)}",
            detail=f"{HARNESS_WORK.get(run.status, 'working')} · {hms(activity.elapsed)} from here",
            key="p" if activity.interruptible else None,
            action="pause the run",
            working=True,
        )
    if held is not None:
        return Attention(
            tone="attn.work",
            glyph="◉",
            headline=f"{stage_of(run)} running elsewhere",
            detail=f"{held} is advancing this run; this surface is reading what it writes",
            key="p" if can_drive else here.key,
            action="pause it wherever it runs" if can_drive else "watch it",
            working=True,
        )
    # Nothing holds the run and nothing is advancing it. Whatever its status promises, it is
    # standing still — because it was created without being started, or because whoever was
    # driving it is gone.
    idle = "not started" if run.status is RunStatus.created else f"idle at {stage_of(run)}"
    return Attention(
        tone="attn.you" if can_drive else "attn.work",
        glyph="○" if can_drive else "◉",
        headline=idle,
        detail=(
            f"nothing is advancing it — next: {HARNESS_WORK.get(run.status, 'the next phase')}"
            if can_drive
            else HARNESS_WORK.get(run.status, "working")
        ),
        key="s" if can_drive else None,
        action="start it" if run.status is RunStatus.created else "continue it",
        working=not can_drive,
    )
