"""What the runs of a project showed about the project itself, and the profile they read it from.

A lesson is identified by what it would declare, so the same lesson read from several runs is
one record with several runs behind it. ``ProjectProfile`` is what one run measured the project
as, and it carries the lessons the requester has accepted, which is why it is stated here
rather than beside the pieces it is built from.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from pydantic import Field

from harness495.core.models.base import SCHEMA_VERSION, StrictModel, utcnow
from harness495.core.models.config import ProjectCommand
from harness495.core.models.enums import CatalogueRole, VerificationKind
from harness495.core.models.profile import CatalogueGap, DeclinedRole, ReadinessCheck, RoleCoverage

REPLACED_PREFIX = "replaced `"
"""Opening of the rationale a verification carries once the requester replaced its command."""


class LessonKind(StrEnum):
    """What a lesson of a run bears on: a criterion of the project, or what a later role is
    told about it (``Lesson``)."""

    command = "command"
    """A command the requester put in the place of the one the specification named, which
    ``.495/project.toml`` would declare under ``[[commands]]``."""
    convention = "convention"
    """A rule a correction stated, which the producer had no way of reading before it wrote:
    a line of ``conventions``."""
    allowed_path = "allowed_path"
    """A path the change was allowed to touch that the project's criteria do not declare:
    a glob of ``[scope] allowed_paths``."""
    note = "note"
    """Something the next specification is better written knowing. It declares nothing and
    reaches the specifier as a fact."""
    false_positive = "false_positive"
    """A claim a reviewer made that does not hold in this project. It declares nothing and
    reaches the next reviewer of that perspective as a fact, so that a claim the requester has
    already weighed is not raised against every change."""


class LessonStatus(StrEnum):
    """Where a lesson stands (``Lesson``)."""

    open = "open"
    """Read from a run and put to the requester, not answered yet."""
    accepted = "accepted"
    """In force: it is part of the project's criteria and reaches the next run."""
    declined = "declined"
    """Refused, with the requester's reason; the same lesson is not proposed again."""
    deferred = "deferred"
    """Set aside; stays listed, and can be accepted or declined at any time."""


class Lesson(StrictModel):
    """One thing a run showed about the project itself, put to the requester.

    A lesson is identified by its kind and by what it would declare, so that the same lesson
    read from several runs is one record: ``run_ids`` then names every run that showed it, and
    a lesson three runs in a row have shown is one line with three runs behind it. ``value`` is
    what enters the criteria — the command, the text of the convention, the glob — and is empty
    for a ``note``, which declares nothing; ``statement`` is the lesson in one sentence, as the
    requester and the next specifier read it; ``observed`` is what the runs recorded, in words,
    so that the requester can weigh the lesson against the evidence rather than against a claim.
    """

    id: str
    kind: LessonKind
    statement: str
    value: str = ""
    name: str = ""
    """For a ``command`` lesson, the name its ``[[commands]]`` entry takes."""
    command_kind: VerificationKind | None = None
    perspective: str = ""
    """For a ``false_positive`` lesson, the reviewer whose claim it answers."""
    declared: str = ""
    """What the requester chose to declare in the place of ``value`` when accepting the lesson.
    Kept apart from it so that what the runs showed stays what the runs showed."""
    observed: list[str] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)
    status: LessonStatus = LessonStatus.open
    reason: str = ""
    """The requester's words on a decline or a deferral."""
    created_at: dt.datetime = Field(default_factory=utcnow)
    updated_at: dt.datetime = Field(default_factory=utcnow)
    decided_at: dt.datetime | None = None
    """When the requester last answered; None while the lesson has only been stated."""

    @property
    def key(self) -> str:
        """What tells one lesson from another: its kind, the reviewer it answers when it
        answers one, and what it would declare."""
        head = f"{self.kind.value}:{self.perspective}" if self.perspective else self.kind.value
        return f"{head}:{self.value or self.statement}"

    @property
    def declares(self) -> bool:
        """Whether accepting it adds something to the project's criteria."""
        return self.kind not in (LessonKind.note, LessonKind.false_positive)

    @property
    def answerable(self) -> bool:
        return self.status in (LessonStatus.open, LessonStatus.deferred)


class Lessons(StrictModel):
    """What the runs of one project have shown about it: ``<state_dir>/lessons.json``."""

    schema_version: int = SCHEMA_VERSION
    lessons: list[Lesson] = Field(default_factory=list)

    def get(self, lesson_id: str) -> Lesson | None:
        for lesson in self.lessons:
            if lesson.id == lesson_id:
                return lesson
        return None

    def find(self, key: str) -> Lesson | None:
        for lesson in self.lessons:
            if lesson.key == key:
                return lesson
        return None

    @property
    def in_force(self) -> list[Lesson]:
        """The lessons the requester accepted: the ones a run is given."""
        return [x for x in self.lessons if x.status is LessonStatus.accepted]


class ProjectProfile(StrictModel):
    root: str
    languages: list[str] = Field(default_factory=list)
    tooling: list[str] = Field(default_factory=list)
    commands: list[ProjectCommand] = Field(default_factory=list)
    role_coverage: list[RoleCoverage] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    """The catalogue conditions that held when the project was profiled
    (``core/conditions.py::CONDITIONS``), which pick the entry of a cell holding several.

    Recorded so that reading the catalogue against the profile opens no file: the reading
    answers as the run measured the tree, not as the tree stands, and a name absent from the
    list is a condition that did not hold."""
    catalogue_gaps: list[CatalogueGap] = Field(default_factory=list)
    declined_roles: list[DeclinedRole] = Field(default_factory=list)
    lessons: list[Lesson] = Field(default_factory=list)
    """What earlier runs on this project showed and the requester accepted (``Lesson``)."""
    conventions: list[str] = Field(default_factory=list)
    doc_files: list[str] = Field(default_factory=list)
    detected_from: list[str] = Field(default_factory=list)
    readiness: list[ReadinessCheck] = Field(default_factory=list)
    base_commit: str | None = None
    default_branch: str | None = None

    def command(self, name: str) -> ProjectCommand | None:
        for c in self.commands:
            if c.name == name:
                return c
        return None

    def coverage(self, technology: str, role: CatalogueRole) -> RoleCoverage | None:
        for r in self.role_coverage:
            if r.technology == technology and r.role is role:
                return r
        return None

    def declined(self, technology: str, role: CatalogueRole) -> DeclinedRole | None:
        for d in self.declined_roles:
            if d.technology == technology and d.role is role:
                return d
        return None

    @property
    def ready(self) -> bool:
        return all(r.executable for r in self.readiness)
