"""What a run showed about the project itself, put to the requester and carried to the next run.

A run measures a project and, on the way, the requester settles things that outlive it: a
command put in the place of one that could not measure anything, a rule stated by hand once the
producer had already broken it, the paths the change was allowed to touch, a decision taken
before the specification was written, a reviewer's claim weighed and found not to hold here.
All of it is in ``run.json`` and none of it reached the next run: the harness was a short loop,
run after run, with no memory between them.

``learn`` reads those back from one run document and the project's current criteria, as
proposals; ``reconcile`` keeps them in ``<state_dir>/lessons.json``, one record per lesson
however many runs showed it, with the requester's answer; ``criteria`` turns the accepted ones
that declare something into the project's criteria, so that the next run is profiled, produced
and verified under them, and the ones that declare nothing travel as a fact to the role they
bear on — the specifier for a ``note``, the reviewer of that perspective for a
``false_positive``; ``render_document`` writes them as ``<state_dir>/lessons.md``. Nothing here writes the project's
own files: a lesson enters ``.495/project.toml`` when the requester copies the lines
``toml_lines`` states, and is in force from the moment it is accepted either way
(``docs/decisions/0027-what-a-run-learns-about-the-project-is-put-to-the-requester.md``).
"""

from __future__ import annotations

from harness495.core.models import (
    REPLACED_PREFIX,
    DecisionKind,
    DecisionMaker,
    EvidenceKind,
    Lesson,
    LessonKind,
    Lessons,
    LessonStatus,
    ProjectCommand,
    ProjectConfig,
    RequirementStatus,
    Retrospective,
    Run,
    Severity,
    ToolVerdict,
    VerificationKind,
    new_id,
    utcnow,
)
from harness495.core.scope import effective_allowed

MAX_OBSERVED = 20
"""Sentences kept per lesson: enough to weigh it, bounded however many runs show it again."""


class LessonError(ValueError):
    """An answer the lesson does not admit: a decline with no reason, words for a note."""


def _flat(text: str) -> str:
    return " ".join(text.split())


def _same(a: str, b: str) -> bool:
    return _flat(a).casefold() == _flat(b).casefold()


def _replaced_command(rationale: str) -> str:
    """The command a verification carried before the requester replaced it, from its rationale."""
    rest = rationale[len(REPLACED_PREFIX) :]
    return rest.partition("`")[0]


# --------------------------------------------------------------------------- reading a run


def learn(run: Run, project: ProjectConfig, retro: Retrospective | None = None) -> list[Lesson]:
    """The lessons one run holds, against what the project already declares.

    A pure function of the run document, the project's criteria and, when the retrospective of
    the run has been written, what it found about the tools. Anything the criteria already
    declare is not proposed: a lesson states what the project does not know yet.
    """
    out: list[Lesson] = []
    out.extend(_commands(run, project))
    out.extend(_conventions(run, project))
    out.extend(_allowed_paths(run, project))
    out.extend(_notes(run, retro))
    out.extend(_false_positives(run))
    for lesson in out:
        lesson.run_ids = [run.id]
        lesson.observed = lesson.observed[:MAX_OBSERVED]
    return out


def _lesson(
    kind: LessonKind,
    statement: str,
    observed: list[str],
    value: str = "",
    name: str = "",
    command_kind: VerificationKind | None = None,
    perspective: str = "",
) -> Lesson:
    return Lesson(
        id=new_id("les"),
        kind=kind,
        statement=_flat(statement),
        value=value,
        name=name,
        command_kind=command_kind,
        perspective=perspective,
        observed=observed,
    )


def _commands(run: Run, project: ProjectConfig) -> list[Lesson]:
    """A command the requester put in the place of the one the specification named.

    The replacement is verified on both versions before it counts (``_recalibrate``), so what is
    proposed here is a command the harness has already run and read; the specification that
    named the other one is gone with the run, and the next one would name it again.
    """
    out: list[Lesson] = []
    for v in run.spec.verifications:
        if not v.command or not v.rationale.startswith(REPLACED_PREFIX):
            continue
        if any(_same(c.command, v.command) for c in project.commands):
            continue
        previous = _replaced_command(v.rationale)
        observed = [f"{v.id}: {v.rationale}"]
        observed += [
            f"iteration {it.n}: {fault}"
            for it in run.iterations
            for fault in it.instrument_faults
            if fault.startswith(f"{v.id}:")
        ]
        out.append(
            _lesson(
                LessonKind.command,
                f"`{v.command}` measures what {v.id} measures, and `{previous}` did not; "
                "the project declares neither, so the next specification names what it finds",
                value=v.command,
                name=v.role.value if v.role else v.kind.value,
                command_kind=v.kind,
                observed=observed,
            )
        )
    return out


def _conventions(run: Run, project: ProjectConfig) -> list[Lesson]:
    """A rule the change was corrected against, which the producer could not read beforehand.

    Two sources, both of them a correction the change already received: what the requester wrote
    by hand, and what a reviewer blocked the change for without any requirement asking about it.
    The reviewer's words are an agent's, and stay a proposal until the requester admits them:
    accepting is what turns them into a fact the next producer is given.
    """
    out: list[Lesson] = []
    seen: list[str] = []

    def add(value: str, statement: str, observed: list[str]) -> None:
        value = _flat(value)
        if not value or any(_same(value, c) for c in project.conventions):
            return
        if any(_same(value, s) for s in seen):
            return
        seen.append(value)
        out.append(_lesson(LessonKind.convention, statement, value=value, observed=observed))

    for d in run.decisions:
        if (
            d.kind is DecisionKind.undetermined
            and d.outcome == "correct"
            and d.made_by is DecisionMaker.human
            and d.rationale.strip()
        ):
            add(
                d.rationale,
                f"the requester corrected the change by hand in iteration {d.iteration}: "
                f"“{_flat(d.rationale)}”; declared, the producer reads it before it writes",
                [f"iteration {d.iteration}: correction written by the requester"],
            )
    for review in run.reviews:
        if review.discarded:
            continue
        for f in review.findings:
            if f.severity is not Severity.blocker or f.requirement_id or not f.evidence.strip():
                continue
            add(
                f.title,
                f"the {review.perspective} reviewer blocked the change for “{_flat(f.title)}”, "
                "which no requirement asked about; the rule it breaks, declared in your own "
                "words, is asked of every change",
                [f"{review.perspective}: {_flat(f.title)} — observed: {_flat(f.evidence)[:200]}"],
            )
    return out


def _allowed_paths(run: Run, project: ProjectConfig) -> list[Lesson]:
    """The scope the run worked under, when the project's criteria do not state it.

    Read only from a version that stayed inside it: the paths are proposed because a change was
    produced within them, not because a specification or a command-line option named them.
    """
    if not any(e.kind is EvidenceKind.scope_check and e.passed for e in run.evidence):
        return []
    allowed = [p for p in effective_allowed(run) if p.strip()]
    if not allowed or not set(allowed) - set(project.scope.allowed_paths):
        return []
    globs = sorted(dict.fromkeys(allowed))
    declared = (
        "the project declares no scope, so a change may touch any path that is not forbidden"
        if not project.scope.allowed_paths
        else "the project declares " + ", ".join(f"`{p}`" for p in project.scope.allowed_paths)
    )
    return [
        _lesson(
            LessonKind.allowed_path,
            f"the change was produced within {', '.join(f'`{p}`' for p in globs)} and stayed "
            f"there; {declared}, and nothing carries that from one run to the next",
            value=", ".join(globs),
            observed=[
                f"iteration {e.iteration}: {e.summary}"
                for e in run.evidence
                if e.kind is EvidenceKind.scope_check and e.passed
            ],
        )
    ]


def _notes(run: Run, retro: Retrospective | None) -> list[Lesson]:
    """What the next specification is better written knowing, and declares nothing.

    The decisions the requester took before this specification, the times a specification was
    sent back to be written again, and the tools the retrospective found unable to measure
    anything here.
    """
    out: list[Lesson] = []
    for a in run.clarification.answers:
        if a.taken_by is not DecisionMaker.human:
            # Taken by the harness under `--auto-approve`: a recommendation nobody confirmed.
            continue
        out.append(
            _lesson(
                LessonKind.note,
                f"the requester decided: {a.statement}",
                observed=[f"clarification of run {run.id}: {_flat(a.statement)}"],
            )
        )
    for d in run.decisions:
        if d.outcome not in ("revise", "respecify") or not d.rationale.strip():
            continue
        out.append(
            _lesson(
                LessonKind.note,
                "a specification of this project was sent back to be written again: "
                f"“{_flat(d.rationale)}”",
                observed=[f"{d.kind.value}: {d.outcome} ({d.made_by.value})"],
            )
        )
    for o in retro.tool_observations if retro is not None else []:
        if o.verdict is not ToolVerdict.faulty:
            continue
        out.append(
            _lesson(
                LessonKind.note,
                f"{', '.join(o.tools)} measures the {o.role.value} role of {o.technology} here "
                "and could not report anything the change decided",
                observed=list(o.detail),
            )
        )
    return out


def _false_positives(run: Run) -> list[Lesson]:
    """A claim a reviewer made that the requester may judge does not hold in this project.

    Only the findings the harness acted on are put: one that blocked the change, and one a
    reviewer read a requirement as violated for. Both cost the run — an iteration, or a
    requirement left undetermined — and both cite an observation, without which 0001 reads the
    claim as deciding nothing and there is nothing to refute.

    The proposition is the refutation, so that accepting it is accepting something true: the
    requester who agrees puts it in force and the next reviewer of that perspective is told,
    the one who disagrees declines it with the reason the claim stood and it is not proposed
    again. A blocking finding no requirement asked about is proposed twice over, here and as a
    ``convention``: the same words are a rule to ask of every change or a claim that does not
    hold, and which of the two it is is the requester's to say.
    """
    out: list[Lesson] = []
    seen: list[str] = []
    for review in run.reviews:
        if review.discarded:
            continue
        for f in review.findings:
            violated = (
                f.requirement_id is not None
                and review.requirement_assessment.get(f.requirement_id)
                is RequirementStatus.violated
            )
            if (f.severity is not Severity.blocker and not violated) or not f.evidence.strip():
                continue
            title = _flat(f.title)
            key = f"{review.perspective}:{title.casefold()}"
            if not title or key in seen:
                continue
            seen.append(key)
            cost = (
                f"read requirement {f.requirement_id} as violated"
                if violated
                else "blocked the change"
            )
            out.append(
                _lesson(
                    LessonKind.false_positive,
                    f"the {review.perspective} reviewer {cost} for “{title}”; that does not "
                    "hold in this project, and every later reviewer of that perspective is told "
                    "so rather than raising it again",
                    value=title,
                    perspective=review.perspective,
                    observed=[
                        f"{review.perspective}: {cost} — {title}; "
                        f"observed: {_flat(f.evidence)[:200]}"
                    ],
                )
            )
    return out


# --------------------------------------------------------------------------- keeping them


def reconcile(lessons: Lessons, learned: list[Lesson]) -> list[Lesson]:
    """Bring the document in step with what one run showed; returns the lessons it touched.

    A lesson nobody has recorded is opened. One already there keeps its status and its answer —
    a declined lesson is not proposed again, an accepted one is already in force — and gains the
    run that showed it again, so that a lesson three runs in a row have shown reads as one line
    with three runs behind it.
    """
    touched: list[Lesson] = []
    now = utcnow()
    for fresh in learned:
        held = lessons.find(fresh.key)
        if held is None:
            lessons.lessons.append(fresh)
            touched.append(fresh)
            continue
        changed = False
        for run_id in fresh.run_ids:
            if run_id not in held.run_ids:
                held.run_ids.append(run_id)
                changed = True
        for line in fresh.observed:
            if line not in held.observed:
                held.observed = [*held.observed, line][-MAX_OBSERVED:]
                changed = True
        if changed:
            held.updated_at = now
        touched.append(held)
    return touched


def accept(lesson: Lesson, text: str = "") -> None:
    """Put the lesson in force, in the requester's own words when they give them.

    ``text`` replaces what the lesson would declare without changing what was read from the
    runs: a reviewer's title is rarely a convention as it should be written, and the record of
    where the lesson comes from is not the requester's to rewrite. A lesson can be answered
    again at any time, whatever it was answered before: the last answer is the one in force,
    and the record keeps when it was given.
    """
    if text.strip() and not lesson.declares:
        raise LessonError(f"{lesson.id} declares nothing, so there is no text to give it")
    now = utcnow()
    lesson.declared = _flat(text) if text.strip() else ""
    lesson.status = LessonStatus.accepted
    lesson.reason = ""
    lesson.decided_at = now
    lesson.updated_at = now


def decline(lesson: Lesson, reason: str) -> None:
    """Record that the requester refused the lesson, and why; it is not proposed again."""
    if not reason.strip():
        raise LessonError(f"declining {lesson.id} needs a reason; it is kept with it")
    now = utcnow()
    lesson.status = LessonStatus.declined
    lesson.reason = _flat(reason)
    lesson.decided_at = now
    lesson.updated_at = now


def defer(lesson: Lesson, note: str = "") -> None:
    """Record that the requester set the lesson aside; it stays listed."""
    now = utcnow()
    lesson.status = LessonStatus.deferred
    lesson.reason = _flat(note)
    lesson.decided_at = now
    lesson.updated_at = now


# --------------------------------------------------------------------------- what they change


def criteria(project: ProjectConfig, lessons: Lessons) -> ProjectConfig:
    """The project's criteria with the accepted lessons in them.

    A copy: the file on disk is the requester's, and a lesson is in force because it was
    accepted, not because something rewrote ``project.toml``. A command whose name is already
    taken by a declared one keeps its own identity rather than replacing it.
    """
    out = project.model_copy(deep=True)
    for lesson in lessons.in_force:
        if lesson.kind is LessonKind.command:
            if any(_same(c.command, lesson.value) for c in out.commands):
                continue
            name = lesson.name or "lesson"
            if any(c.name == name for c in out.commands):
                name = f"{name}-{lesson.id}"
            out.commands.append(
                ProjectCommand(
                    name=name,
                    command=lesson.value,
                    kind=lesson.command_kind or VerificationKind.command,
                    source=f"lesson {lesson.id}",
                )
            )
        elif lesson.kind is LessonKind.convention:
            text = lesson.declared or lesson.value
            if not any(_same(text, c) for c in out.conventions):
                out.conventions.append(text)
        elif lesson.kind is LessonKind.allowed_path:
            for glob in (lesson.declared or lesson.value).split(","):
                glob = glob.strip()
                if glob and glob not in out.scope.allowed_paths:
                    out.scope.allowed_paths.append(glob)
    return out


def _toml_string(text: str) -> str:
    return '"' + _flat(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def toml_lines(lesson: Lesson) -> str:
    """The lines ``.495/project.toml`` takes for the lesson, to merge into the keys it has.

    Stated rather than written: the file is hand-written, with the requester's own comments and
    order in it, and a lesson is in force from the moment it is accepted whether or not the
    lines are ever copied there.
    """
    value = lesson.declared or lesson.value
    if lesson.kind is LessonKind.command:
        kind = (lesson.command_kind or VerificationKind.command).value
        return (
            "[[commands]]\n"
            f"name = {_toml_string(lesson.name or 'lesson')}\n"
            f"command = {_toml_string(value)}\n"
            f"kind = {_toml_string(kind)}"
        )
    if lesson.kind is LessonKind.convention:
        return f"conventions = [{_toml_string(value)}]"
    if lesson.kind is LessonKind.allowed_path:
        globs = ", ".join(_toml_string(g.strip()) for g in value.split(",") if g.strip())
        return f"[scope]\nallowed_paths = [{globs}]"
    return ""


HEADING = {
    LessonKind.command: "Commands",
    LessonKind.convention: "Conventions",
    LessonKind.allowed_path: "Scope",
    LessonKind.note: "For the next specification",
    LessonKind.false_positive: "Reviewer claims that do not hold here",
}


def render_document(lessons: Lessons) -> str:
    """``<state_dir>/lessons.md``: what the runs of this project taught, in force.

    Written from ``lessons.json`` on every change and read back by nobody: the specifier is
    given the lessons of the document, not the text of this file, which is here so that a
    person can read, diff and review the memory of the project.
    """
    lines = [
        "# What the runs have shown about this project",
        "",
        "Written by `495 retro` and `495 lessons`, from `lessons.json`, on every change. Edits",
        "here are not read back: answer a lesson with `495 lessons accept|decline|defer <id>`.",
        "",
    ]
    in_force = lessons.in_force
    if not in_force:
        lines.append("No lesson is in force yet.")
        return "\n".join(lines) + "\n"
    for kind in LessonKind:
        held = [x for x in in_force if x.kind is kind]
        if not held:
            continue
        lines.append(f"## {HEADING[kind]}")
        lines.append("")
        for lesson in held:
            lines.append(f"- {lesson.statement}")
            if lesson.declares:
                lines.append(f"  - declared: `{lesson.declared or lesson.value}`")
            lines.append(f"  - shown by: {', '.join(lesson.run_ids)} ({lesson.id})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
