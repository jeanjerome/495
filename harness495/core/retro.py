"""The retrospective on a run: what each tool that measured a catalogue role showed.

A run measures the tools of the host project every time it runs a verification that names a
catalogue role (``Verification.role``): on the change, on the base version carrying the
change's test files, and once before any change exists. ``retrospect`` reads those
measurements back from the run document and states, per technology, role and tool, whether
the tool proved itself, posed a problem, or showed nothing, with each measurement in words
and the Markdown row the catalogue takes with the run as its source. Nothing here reads
outside the document, so the retrospective can be written again at any time and reads the
same; the catalogue is written by hand from the rows, never by a command
(``docs/decisions/0015-a-retrospective-states-what-each-tool-showed.md``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from harness495.core.catalogue import applicable
from harness495.core.models import (
    CatalogueRole,
    Evidence,
    EvidenceKind,
    Retrospective,
    RoleCoverage,
    Run,
    ToolObservation,
    ToolVerdict,
    Verification,
    utcnow,
)

SECTION_NAMES: dict[str, str] = {"python": "Python", "shell": "Shell"}
"""The catalogue's section heading per technology, as the Rejected table names it."""

VERDICT = "verdict"
CONTRADICTION = "contradiction"
FAULT = "fault"
INCONCLUSIVE = "inconclusive"


@dataclass
class Measurement:
    """One run of a verification on the change, with the control run that read it, if any."""

    verification: Verification
    subject: Evidence
    control: Evidence | None = None


@dataclass
class _Tally:
    tools: list[str]
    verification_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    runs: int = 0
    verdicts: int = 0
    contradictions: int = 0
    faults: int = 0
    detail: list[str] = field(default_factory=list)


def _reported_success(e: Evidence) -> bool | None:
    """What a control or baseline run reported, read from its exit code.

    Those runs carry ``passed=None`` because they are statements about the instrument, not
    about the change; the exit code against the expected one says what the tool reported.
    """
    if e.exit_code is None:
        return None
    return e.exit_code == (e.expected_exit_code if e.expected_exit_code is not None else 0)


def measurements(run: Run) -> list[Measurement]:
    """Pair each run of a verification on the change with the control run that followed it.

    A control run is paired with the last run on the change of the same verification, in the
    same iteration and with the same command; the runs of a command the producer reported,
    recorded as controls too, carry that command and pair with nothing.
    """
    out: list[Measurement] = []
    pending: dict[str, Measurement] = {}
    for e in run.evidence:
        if not e.verification_id:
            continue
        v = run.spec.verification(e.verification_id)
        if v is None:
            continue
        if e.kind is EvidenceKind.command_result:
            m = Measurement(v, e)
            out.append(m)
            pending[v.id] = m
        elif e.kind is EvidenceKind.instrument_check:
            last = pending.get(v.id)
            if (
                last is not None
                and last.control is None
                and last.subject.iteration == e.iteration
                and last.subject.command == e.command
            ):
                last.control = e
    return out


def _baseline(run: Run, command: str | None) -> Evidence | None:
    for e in run.evidence:
        if e.kind is EvidenceKind.baseline and command and e.command == command:
            return e
    return None


def _at_fault(run: Run, m: Measurement) -> bool:
    it = next((i for i in run.iterations if i.n == m.subject.iteration), None)
    return it is not None and any(
        f.startswith(f"{m.verification.id}:") for f in it.instrument_faults
    )


def read(run: Run, m: Measurement) -> tuple[str, str]:
    """What one measurement showed about the tool: its outcome and a sentence.

    Only a report read against another one says something about the tool: a report that
    differs with and without the change is a verdict (a contradiction when the tool failed on
    the change); a failure with no edit of the change able to fix it is a fault; a report with
    nothing to read it against, or the same success on both versions, is inconclusive.
    """
    v, s, c = m.verification, m.subject, m.control
    where = f"{v.id}, iteration {s.iteration}"
    if s.summary == "timed out":
        return FAULT, f"{where}: timed out"
    if s.passed is None:
        return INCONCLUSIVE, f"{where}: not run ({s.summary})"
    if c is not None:
        without = _reported_success(c)
        if without is None:
            return INCONCLUSIVE, f"{where}: run on the base version without a report"
        if s.passed and not without:
            return VERDICT, f"{where}: passes with the change and fails without it"
        if not s.passed and without:
            return (
                CONTRADICTION,
                f"{where}: fails with the change and passes without it, contradicting the agent",
            )
        if s.passed:
            return (
                INCONCLUSIVE,
                f"{where}: passes with and without the change, showing nothing about the tool",
            )
        if s.command != v.command:
            return (
                FAULT,
                f"{where}: failed on both versions and the requester replaced its command "
                f"(`{s.command}` by `{v.command}`)",
            )
        if _at_fault(run, m):
            return (
                FAULT,
                f"{where}: fails identically with and without the change (exit {s.exit_code})",
            )
        return (
            CONTRADICTION,
            f"{where}: fails with the change and fails otherwise without it, contradicting the "
            "agent",
        )
    base = _baseline(run, s.command)
    before = _reported_success(base) if base is not None else None
    if s.passed:
        if before is True:
            return VERDICT, f"{where}: passes with the change, as on the base version before it"
        if before is False:
            return (
                VERDICT,
                f"{where}: passes with the change and failed on the base version before it",
            )
        return INCONCLUSIVE, f"{where}: passes with the change; not measured on the base version"
    if before is True:
        return (
            CONTRADICTION,
            f"{where}: fails with the change and passed on the base version before it, "
            "contradicting the agent",
        )
    if before is False:
        return (
            FAULT,
            f"{where}: fails with the change as it did on the base version before any change "
            f"(exit {s.exit_code})",
        )
    return (
        INCONCLUSIVE,
        f"{where}: fails with the change, with no measurement on the base version to read it "
        "against",
    )


def _command_names(tool: str) -> tuple[str, ...]:
    """The words a tool appears under in a command line: its name, and without ``.py``."""
    names = {tool, tool.removesuffix(".py"), tool.replace("-", "_")}
    return tuple(n for n in names if n)


def _rows_for(v: Verification, run: Run) -> list[RoleCoverage]:
    """The coverage rows that carry the tools a verification of a role ran.

    Every measured row of the role, unless the command names one of the tools of some rows
    only, in which case those rows are the ones.
    """
    assert run.profile is not None and v.role is not None
    rows = [r for r in run.profile.role_coverage if r.role is v.role and r.measured]
    if len(rows) <= 1 or not v.command:
        return rows
    named = [
        r
        for r in rows
        if any(name in v.command for tool in r.tools for name in _command_names(tool))
    ]
    return named or rows


def _source(run: Run, project: str, when: str) -> str:
    return f"retrospective {when} ({project}, run {run.id})"


def retrospect(run: Run, when: str | None = None) -> Retrospective:
    """The retrospective of a run, from its document alone.

    One observation per technology and role a verification of the run measured, with the
    tools the profile found for it; a verification whose role nothing in the project measures
    never ran and brings nothing. ``when`` is the date the Source column cites, today's by
    default.
    """
    now = utcnow()
    when = when or now.date().isoformat()
    project = Path(run.project_root).name
    src = _source(run, project, when)
    tallies: dict[tuple[str, CatalogueRole], _Tally] = {}
    faults: dict[tuple[str, CatalogueRole], list[str]] = {}

    def tally(row: RoleCoverage) -> _Tally:
        key = (row.technology, row.role)
        if key not in tallies:
            tallies[key] = _Tally(tools=list(row.tools))
            faults[key] = []
        return tallies[key]

    if run.profile is not None:
        for v in run.spec.verifications:
            if v.role is None:
                continue
            for row in _rows_for(v, run):
                t = tally(row)
                for check in run.profile.readiness:
                    if v.command and check.command == v.command and not check.executable:
                        line = f"{v.id}: not executable on the base version ({check.detail})"
                        if line not in t.detail:
                            t.detail.append(line)
                            faults[(row.technology, row.role)].append(line)
                            t.faults += 1
                            if v.id not in t.verification_ids:
                                t.verification_ids.append(v.id)
        for m in measurements(run):
            v = m.verification
            if v.role is None:
                continue
            outcome, line = read(run, m)
            for row in _rows_for(v, run):
                t = tally(row)
                t.runs += 1
                if v.id not in t.verification_ids:
                    t.verification_ids.append(v.id)
                t.evidence_ids.append(m.subject.id)
                if m.control is not None:
                    t.evidence_ids.append(m.control.id)
                t.detail.append(line)
                if outcome == VERDICT:
                    t.verdicts += 1
                elif outcome == CONTRADICTION:
                    t.contradictions += 1
                elif outcome == FAULT:
                    t.faults += 1
                    faults[(row.technology, row.role)].append(line)

    observations: list[ToolObservation] = []
    for (technology, role), t in tallies.items():
        if t.runs == 0 and t.faults == 0:
            continue
        if t.faults:
            verdict = ToolVerdict.faulty
        elif t.verdicts + t.contradictions:
            verdict = ToolVerdict.proven
        else:
            verdict = ToolVerdict.inconclusive
        entry = applicable(technology, role, run.profile) if run.profile is not None else None
        in_catalogue = entry is not None and all(tool in entry.tools for tool in t.tools)
        tools = ", ".join(t.tools)
        if verdict is ToolVerdict.proven:
            catalogue_row = (
                f"| {role.value} | {tools} | recommended | {src} | measured the role in {t.runs} "
                f"run(s) of {len(t.verification_ids)} verification(s), contradicted the agent "
                f"{t.contradictions} time(s) |"
            )
        elif verdict is ToolVerdict.faulty:
            section = SECTION_NAMES.get(technology, technology.capitalize())
            catalogue_row = (
                f"| {section} | {role.value} | {tools} | "
                f"{'; '.join(faults[(technology, role)])} | {src} |"
            )
        else:
            catalogue_row = ""
        observations.append(
            ToolObservation(
                technology=technology,
                role=role,
                tools=t.tools,
                verdict=verdict,
                verification_ids=t.verification_ids,
                evidence_ids=t.evidence_ids,
                runs=t.runs,
                verdicts=t.verdicts,
                contradictions=t.contradictions,
                faults=t.faults,
                detail=t.detail,
                in_catalogue=in_catalogue,
                catalogue_row=catalogue_row,
            )
        )
    return Retrospective(
        run_id=run.id,
        project=project,
        run_status=run.status,
        created_at=now,
        source=src,
        tool_observations=observations,
    )
