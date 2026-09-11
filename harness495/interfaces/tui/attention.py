"""The one line that says what the run needs from you.

A run's status ("reviewing") leaves the user to work out whether that means "wait", "act" or
"it is over". Those are the only three answers that matter, and they belong on every screen,
not on a tab. This is that line.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from harness495.core.models import Capability, Run, RunStatus
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


def attention(run: Run, paused: bool = False) -> Attention:
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
    if paused or run.status is RunStatus.paused:
        return Attention(
            tone="attn.you",
            glyph="‖",
            headline="paused",
            detail="the display is frozen; the run itself keeps going",
            key="space",
            action="resume",
        )
    if run.status in {RunStatus.failed, RunStatus.aborted, RunStatus.rejected}:
        return Attention(
            tone="attn.dead",
            glyph="✕",
            headline=f"stopped · {run.status.value}",
            detail=clip(run.stop_reason or run.result.summary or "nothing was delivered", 150),
            key=STAGES[STAGE_INDEX[stage_of(run)]].key,
            action="see where it stopped",
        )
    if run.status is RunStatus.delivered:
        return Attention(
            tone="attn.done",
            glyph="●",
            headline="delivered",
            detail="the patch and the branch are ready; nothing has been merged",
            key="7",
            action="what to do with it",
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
            key=STAGES[STAGE_INDEX[stage_of(run)]].key,
            action="watch it",
            working=True,
        )
    return Attention(
        tone="attn.work",
        glyph="◉",
        headline=f"{stage_of(run)} running",
        detail=HARNESS_WORK.get(run.status, "working"),
        working=True,
    )
