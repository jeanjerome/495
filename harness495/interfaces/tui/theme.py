"""One meaning per colour, used the same way in every view.

Six meanings, six hues, and nothing outside them. Every style below is built from one of
these, so a colour can be traced back to what it claims rather than to where it was typed.
Within a group, weight — bold, dim — says how loud, never what: a blocker and a major finding
are both red, and only one of them is bold.
"""

from __future__ import annotations

from rich.theme import Theme

from harness495.core.models import RequirementStatus, Severity, Verdict

GOOD = "green"  # it holds, it passed, it was proven on the candidate
BAD = "red"  # it is contradicted, it failed, it blocks the run
WARN = "yellow"  # it cannot say, it may mislead, you have to judge it yourself
LIVE = "cyan"  # what is happening now, and the handles you can act on
ASK = "magenta"  # the run has stopped and cannot go on without a human
INERT = "grey42"  # not reached, not assessed, not there
FRAME = "grey35"  # the same absence, one step quieter: a rule carries less ink than a word

THEME = Theme(
    {
        # ---- chrome: the things that are always on screen and never claim anything
        # The mark is drawn with block glyphs, so it has to be a foreground colour: reversed,
        # the blocks would paint their own holes and the digits would come out as rectangles.
        "h.logo": f"bold {LIVE}",
        "h.title": "bold white",
        "h.value": "white",
        "h.key": "dim white",
        "h.meta": "dim white",
        "h.ref": LIVE,
        "h.ref.strong": f"bold {LIVE}",  # the same handle, when it is the subject of the panel
        "h.rule": FRAME,
        "chrome.bar": "on grey15",
        "cursor": f"bold black on {LIVE}",
        "key.active": f"bold {LIVE}",
        "key.onfill": "bold white on black",  # a key chip standing on a filled band
        # ---- frames. A panel's border is quiet unless the panel is itself the thing that
        # wants something: the pane under your cursor, a warning, a failure, a delivery, a
        # question. Everywhere else the content carries the colour and the frame stays out.
        "frame.quiet": FRAME,
        "frame.live": LIVE,
        "frame.warn": WARN,
        "frame.bad": BAD,
        "frame.good": GOOD,
        "frame.ask": ASK,
        # ---- the pipeline strip: one hue per tab, which is the run's state at that stop
        "tab.done": GOOD,
        "tab.here": f"bold {LIVE}",
        "tab.todo": INERT,
        "tab.blocked": f"bold {ASK}",
        "tab.failed": f"bold {BAD}",
        "tab.name": "white",
        "tab.name.viewed": "bold white",
        "tab.name.todo": INERT,
        # A count is dim unless it reports something that blocks or misleads. Two reds on the
        # strip point at the trouble; eight coloured counts point at nothing.
        "tab.count": "dim white",
        "tab.count.bad": f"bold {BAD}",
        # ---- attention. "Working" is LIVE, not WARN: an agent holding the worktree is the
        # run doing its job, and painting it the same colour as an undetermined requirement
        # would be the one place where a hue means two unrelated things.
        "attn.work": f"bold {LIVE}",
        "attn.you": f"bold {ASK}",
        "attn.done": f"bold {GOOD}",
        "attn.dead": f"bold {BAD}",
        "attn.hint": "italic dim white",
        # ---- where a requirement stands
        "req.satisfied": GOOD,
        "req.violated": f"bold {BAD}",
        "req.undetermined": WARN,
        "req.pending": INERT,
        # ---- what a check is worth as evidence
        "suf.sufficient": GOOD,
        "suf.insufficient": WARN,
        "suf.missing": WARN,
        # A faulty check fails identically with and without the change: the instrument is
        # broken, not the change. Red would say the opposite, and red is already spoken for.
        "suf.faulty": f"bold {WARN}",
        # ---- what a reviewer concluded, and how loudly
        "verdict.accept": f"bold {GOOD}",
        "verdict.reject": f"bold {BAD}",
        "verdict.undetermined": f"bold {WARN}",
        "sev.blocker": f"bold {BAD}",
        "sev.major": BAD,
        "sev.minor": WARN,
        "sev.info": "dim white",
        # ---- what an agent was allowed to do, and what it spent its turn on
        "cap.write": f"bold black on {WARN}",
        "cap.read": "black on grey58",
        "tool.write": WARN,
        "tool.read": LIVE,
        # ---- how close a ceiling is
        "gauge.ok": GOOD,
        "gauge.warn": WARN,
        "gauge.high": f"bold {BAD}",
        "gauge.empty": "grey30",
    }
)

REQ_STYLE = {
    RequirementStatus.satisfied: "req.satisfied",
    RequirementStatus.violated: "req.violated",
    RequirementStatus.undetermined: "req.undetermined",
    RequirementStatus.pending: "req.pending",
}
REQ_GLYPH = {
    RequirementStatus.satisfied: "●",
    RequirementStatus.violated: "✕",
    RequirementStatus.undetermined: "◐",
    RequirementStatus.pending: "○",
}
VERDICT_STYLE = {
    Verdict.accept: "verdict.accept",
    Verdict.reject: "verdict.reject",
    Verdict.undetermined: "verdict.undetermined",
}
SEVERITIES = (Severity.blocker, Severity.major, Severity.minor, Severity.info)

# The log speaks the same six meanings as everything else: an event is a warning, a failure, a
# delivery, a question, something happening now, or a plain fact.
EVENT_STYLE = {
    "warning": "gauge.warn",
    "control.started": "gauge.warn",
    "run.failed": "attn.dead",
    "run.aborted": "attn.dead",
    "run.delivered": "attn.done",
    "decision.requested": "attn.you",
    "iteration.started": "h.ref",
    "iteration.assessed": "h.ref",
    "review": "h.ref",
    "evidence": "h.value",
    "intervention.started": "h.value",
    "intervention.ended": "h.value",
    "verification.started": "h.meta",
    "status": "h.meta",
}

# Events the header already carries, or that say nothing on their own. The log filters on this
# rather than on a severity the events do not have.
NOISE_EVENTS = frozenset({"status", "verification.started"})
LOUD_EVENTS = frozenset(
    {"warning", "run.failed", "run.aborted", "decision.requested", "control.started"}
)

# Content wants air. One blank line above and below, two columns either side: at (0, 1) — the
# Rich default — every table and every sentence sits against the frame that drew it.
PAD = (1, 2)
PAD_TIGHT = (0, 2)
"""For a surface one line tall, where vertical padding would triple its height: the band, a tab."""
