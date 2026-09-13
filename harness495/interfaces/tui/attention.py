"""The one line that says what the run needs from you.

A run's status ("reviewing") leaves the user to work out whether that means "wait", "act" or
"it is over". Those are the only three answers that matter, and they belong on every screen,
not on a tab. This is that line — and since the surface can now advance a run, it also carries
the key that does it, so "it is stopped" and "this is what starts it again" are never two
separate discoveries.

Every state answers the same four things in the same order, which is what makes the band one
sentence rather than nine: **what** is true of the run, **what of** — the stage, the question,
the agent it applies to — **why**, and the **one key** that moves it on. Four tones carry the
four answers to "what", and they are the tones every frame on the surface already takes:

* ``live`` — something is advancing it; there is nothing to do but watch.
* ``ask`` — it is standing still and only a human moves it on: a question to answer, a pause
  to lift, a run never started.
* ``bad`` — it stopped and cannot go on, or what was merged is not what was verified.
* ``good`` — it is done and it holds.

The same shape says what the *store* needs — :func:`store_attention` — because the listing
asks the same question of every run at once, and an answer counted across the store cannot be
read off any one of them.

Two things deliberately do not appear here. A frozen display is a state of the *surface*, not
of the run, and a band that announced it would hide the question the run is stopped on — the
frame says that instead. And a key is offered only where pressing it would work: a surface
that cannot drive the run names the stage that holds the answer, so the band never invites a
keystroke the loops would refuse.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass

from harness495.core.models import Capability, Run, RunStatus
from harness495.interfaces.tui.driving import Activity
from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.reading import running_intervention
from harness495.interfaces.tui.stages import STAGE_INDEX, STAGES, stage_of
from harness495.interfaces.tui.widgets.text import clip, hms, plural, short


@dataclass(frozen=True)
class Attention:
    """One state of the run, in the shape the band draws.

    ``tone`` is a reason, not a colour — the same four words :func:`panel` takes, so the band
    is coloured by what it says the way every other frame on the surface is.
    """

    tone: str
    glyph: str
    headline: str
    detail: str
    about: str = ""
    """What the headline applies to: the stage, the kind of question, the perspective."""
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
    # The three phases an agent walks appear here too, because a run can be standing still in
    # one of them: the agent that held it is gone, and what happens next is that it is handed
    # back to one.
    RunStatus.producing: "putting the producer back on the change",
    RunStatus.produced: "checking the change stayed inside the allowed paths",
    RunStatus.verifying: "running the verification commands on the candidate",
    RunStatus.verified: "dispatching one reviewer per perspective",
    RunStatus.reviewing: "putting the reviewers back on the candidate",
    RunStatus.reviewed: "turning the evidence into a verdict, requirement by requirement",
    RunStatus.accepted: "writing the patch, the branch and the report",
}
STOPPED = {RunStatus.failed, RunStatus.aborted, RunStatus.rejected}


def attention(
    run: Run,
    activity: Activity | None = None,
    held: str | None = None,
    can_drive: bool = False,
) -> Attention:
    """What the run needs, given what is being done to it and by whom.

    ``activity`` is what this surface is doing to the run, ``held`` is another process doing
    it. A run that is neither is not "working" however promising its status reads: it is
    standing still, and saying so is the difference between waiting for nothing and pressing
    one key — including on a surface that cannot press it, which reads the same store and is
    owed the same fact.
    """
    here = STAGES[STAGE_INDEX[stage_of(run)]]
    # The two keys that act from here, offered on exactly the terms the loops accept them: a
    # stop is a file, so it reaches a run this surface does not hold; everything else needs
    # the run to be ours. Anything else names the stage that holds the answer instead.
    ours = can_drive and held is None
    pausable = can_drive and (activity.interruptible if activity is not None else held is not None)

    pending = run.pending_decision
    if pending is not None:
        return Attention(
            tone="ask",
            glyph=ICON["question"],
            headline="waiting on you",
            about=pending.kind.value.replace("_", " "),
            detail=clip(pending.question, 150),
            key="d" if ours else here.key,
            action="answer it" if ours else "read what it asks",
        )
    if run.status is RunStatus.paused:
        return Attention(
            tone="ask",
            glyph=ICON["paused"],
            headline="paused",
            about=stage_of(run),
            detail=clip(run.stop_reason or "stopped between two steps", 150),
            key="s" if ours else here.key,
            action="continue it" if ours else "see where it stopped",
        )
    if run.status in STOPPED:
        retry = ours and run.status is RunStatus.failed
        return Attention(
            tone="bad",
            glyph=ICON["stopped"],
            headline="stopped",
            about=run.status.value,
            detail=clip(run.stop_reason or run.result.summary or "nothing was delivered", 150),
            key="s" if retry else here.key,
            action=f"try again at {stage_of(run)}" if retry else "see where it stopped",
        )
    if run.status is RunStatus.delivered and activity is None:
        # ``i`` acts from wherever you are standing on a delivered run, so the band carries it
        # like it carries ``d``, ``s`` and ``p`` — a stop number sends you to look for the key
        # once you are there, which is one discovery too many for the last thing left to do.
        acts = ours and bool(run.result.report_ref)
        key = "i" if acts else "8"
        # The band names the move that has not been made. While nothing of the run is in the
        # tree that is the merge, not the check: offering the check first sends you to confirm
        # the absence of something you have not put there yet.
        merges = ours and bool(run.result.branch)
        g = run.result.integration
        state = run.integration_state()
        if state in ("unchecked", "unmerged"):
            # The same fact either way — nothing has been merged — so the same tone. A run
            # that reads green until you ask about it and red afterwards is a run whose colour
            # is about the question rather than about the run.
            return Attention(
                tone="good",
                glyph=ICON["delivered"],
                headline="delivered",
                detail=(
                    "the patch and the branch are ready; nothing has been merged"
                    if g is None
                    else f"{g.target_ref} has not been merged into: it is still "
                    f"{short(g.target_commit, 12)}, the commit the run started from"
                ),
                key="m" if merges else key,
                action=(
                    "merge it into the branch you are on"
                    if merges
                    else (
                        "check what you merged"
                        if g is None
                        else ("ask again once you have merged" if acts else "the integration check")
                    )
                ),
            )
        landed = state == "landed"
        return Attention(
            tone="good" if landed else "bad",
            glyph=ICON["delivered"] if landed else ICON["stopped"],
            headline="delivered and integrated" if landed else "delivered, but not integrated",
            detail=clip(f"{g.target_ref}: {g.detail}" if g else "", 150),
            key=key,
            action="check it again" if acts else "the integration check",
        )
    live = running_intervention(run)
    if live is not None:
        who = f"{live.agent.kind.value}:{live.agent.model or 'default'}"
        elapsed = (dt.datetime.now(dt.UTC) - live.started_at).total_seconds()
        return Attention(
            tone="live",
            glyph="◉",
            headline=f"{live.role.value} working",
            about=live.perspective or "",
            detail=(
                f"{who}, {'writing to' if live.capability is Capability.write else 'reading'} "
                f"the worktree · {hms(elapsed)} of a {live.timeout_s // 60}m timeout"
            ),
            key="p" if pausable else here.key,
            action="pause the run" if pausable else "watch it",
            working=True,
        )
    if activity is not None:
        return Attention(
            tone="live",
            glyph="◉",
            headline=activity.verb,
            about=stage_of(run),
            detail=f"{HARNESS_WORK.get(run.status, 'working')} · {hms(activity.elapsed)} from here",
            key="p" if pausable else here.key,
            action="pause the run" if pausable else "watch it",
            working=True,
        )
    if held is not None:
        return Attention(
            tone="live",
            glyph="◉",
            headline="running elsewhere",
            about=stage_of(run),
            detail=f"{held} is advancing this run; this surface is reading what it writes",
            key="p" if pausable else here.key,
            action="pause it wherever it runs" if pausable else "watch it",
            working=True,
        )
    # Nothing holds the run and nothing is advancing it. Whatever its status promises, it is
    # standing still — because it was created without being started, or because whoever was
    # driving it is gone. True of a surface that cannot drive it too: the claim and the
    # running intervention are both in the store, so "idle" is read, never assumed.
    started = run.status is not RunStatus.created
    return Attention(
        tone="ask",
        glyph=ICON["idle"],
        headline="idle" if started else "not started",
        about=stage_of(run) if started else "",
        detail=f"nothing is advancing it — next: {HARNESS_WORK.get(run.status, 'the next phase')}",
        key="s" if ours else here.key,
        action=("continue it" if started else "start it") if ours else "see where it stands",
    )


def attending(runs: Sequence[Run]) -> Run | None:
    """The run the store's attention is on, or ``None`` when nothing is asking for it.

    One function for two things that must never disagree: the run the store band names, and
    the row ``n`` puts the cursor on. Read in the order a human would: what asked a question,
    then what is not what was verified, then what stopped, then what is standing still. What
    is advancing needs nothing, and what is delivered and merged needs nothing either.
    """
    for pick in (
        lambda r: r.pending_decision is not None,
        lambda r: r.integration_state() == "differs",
        lambda r: r.status in STOPPED,
        lambda r: r.status is RunStatus.paused,
        lambda r: not r.is_terminal() and running_intervention(r) is None,
    ):
        for run in runs:
            if pick(run):
                return run
    return None


def store_attention(
    runs: Sequence[Run], advancing: Sequence[str] = (), can_create: bool = False
) -> Attention:
    """What the *store* needs from you, in the shape the band already draws.

    The run band answers "what does this run need"; nothing on the surface answered "what does
    any of them need", and that is the one question the listing exists to ask. Same four tones,
    same four answers, counted across the store instead of read off one run.

    The order is what needs a human first — a question, a merge that is not what was verified,
    a run that stopped, one that was paused, one nothing is advancing — and only then what is
    merely happening. Work is never hidden by that order: it is counted in ``about``, and the
    glyph turns whenever something is moving, whichever headline is on the band.

    ``advancing`` is what this surface is driving, which the store cannot know: between two
    interventions a run being walked from here holds no running intervention, and without this
    the band would call it idle for as long as the harness takes to start the next agent.
    """
    if not runs:
        return Attention(
            tone="ask",
            glyph=ICON["idle"],
            headline="no run yet",
            detail="495 takes an intent and walks it to a branch you can merge",
            key="c" if can_create else None,
            action="write the first intent",
        )
    live = [r for r in runs if running_intervention(r) is not None or r.id in advancing]
    n = len(runs)
    about = f"{n} {plural(n, 'run')}"
    if live:
        about += f" · {len(live)} advancing"
    target = attending(runs)
    key = "n" if target is not None else None
    action = "put the cursor on it" if target is not None else ""

    def band(tone: str, glyph: str, headline: str, detail: str, working: bool = False) -> Attention:
        return Attention(
            tone=tone,
            glyph=glyph,
            headline=headline,
            detail=clip(detail, 150),
            about=about,
            key=key,
            action=action,
            working=working,
        )

    waiting = [r for r in runs if r.pending_decision is not None]
    if waiting:
        asked = ", ".join(
            f"{r.id} {r.pending_decision.kind.value.replace('_', ' ')}"
            for r in waiting[:3]
            if r.pending_decision is not None
        )
        return band(
            "ask",
            ICON["question"],
            f"{len(waiting)} waiting on you",
            f"{asked}{' …' if len(waiting) > 3 else ''}",
        )
    differs = [r for r in runs if r.integration_state() == "differs"]
    if differs:
        return band(
            "bad",
            ICON["stopped"],
            f"{len(differs)} not integrated as verified",
            f"{', '.join(r.id for r in differs)}: what is in the ref is not what was verified",
        )
    stopped = [r for r in runs if r.status in STOPPED]
    if stopped:
        first = stopped[0]
        return band(
            "bad",
            ICON["stopped"],
            f"{len(stopped)} stopped",
            f"{first.id} {first.status.value}: "
            f"{first.stop_reason or first.result.summary or 'nothing was delivered'}",
        )
    paused = [r for r in runs if r.status is RunStatus.paused]
    if paused:
        return band(
            "ask",
            ICON["paused"],
            f"{len(paused)} paused",
            f"{', '.join(r.id for r in paused)} — stopped between two steps, nothing is lost",
        )
    idle = [
        r
        for r in runs
        if not r.is_terminal() and r.id not in {x.id for x in live} and r.pending_decision is None
    ]
    if idle:
        return band(
            "ask",
            ICON["idle"],
            f"{len(idle)} idle",
            "nothing is advancing "
            + plural(len(idle), "it", "them")
            + f" — {', '.join(f'{r.id} at {stage_of(r)}' for r in idle[:3])}",
        )
    if live:
        return band(
            "live",
            "◉",
            f"{len(live)} advancing",
            ", ".join(f"{r.id} at {stage_of(r)}" for r in live[:3]),
            working=True,
        )
    unmerged = [
        r
        for r in runs
        if r.status is RunStatus.delivered and r.integration_state() in ("unchecked", "unmerged")
    ]
    if unmerged:
        return band(
            "good",
            ICON["delivered"],
            f"{len(unmerged)} delivered",
            f"{', '.join(r.id for r in unmerged[:3])} — the patches and the branches are ready; "
            "nothing has been merged",
        )
    return band(
        "good",
        ICON["delivered"],
        "nothing is waiting on you",
        "every run here has been walked to the end and what was merged is what was verified",
    )
