# 0027. What a run learns about the project is put to the requester as a lesson, and an accepted lesson is part of the criteria of every run that follows

- Status: accepted
- Date: 2026-09-14

## Context

A run settles things that outlive the change it was opened for. The requester replaces a command
that reports the same thing with and without the change (`checks.calibration.recalibrate`), writes
a correction by hand on a decision the evidence left undetermined, takes the decisions the intent
left open before the specification is written (0025), and lets a change be produced inside a
scope the specifier proposed for that run alone. Reviewers block changes for the same rule run
after run. All of it is written in `run.json`, and none of it reached the next run: the
specification of the following change was derived from the same intent, the same profile and
the same silence, and the same replacement, the same correction and the same rule had to be
found again.

The catalogue already has a route out of a run: `495 retro` states what the run showed about
each tool that measured a catalogue role, and the maintainer admits the row by hand (0015).
That route stops at the catalogue, which is 495's own document; what a run showed about the
*project* — its commands, its conventions, its scope, what its requester decided — had none.

## Decision

`495 retro <run-id>` also reads what the run showed about the project, states each thing as a
**lesson**, and keeps it in `<state_dir>/lessons.json` with the requester's answer.

`core/lessons.py::learn` is a pure function of the run document, the project's criteria as they
stand, and the retrospective of the run when it has been written. It states four kinds:

- `command`: a verification whose command the requester replaced, which the criteria do not
  declare. What is proposed is a command the harness has already run on both versions.
- `convention`: a correction the requester wrote by hand, and a blocking finding no requirement
  asked about. The reviewer's words are an agent's; accepting is what makes them a fact.
- `allowed_path`: the paths a produced version stayed inside, when the criteria do not state
  them — read only from a scope check that passed, never from a specification alone.
- `note`: a decision the requester took before the specification, a specification sent back to
  be written again, a tool the retrospective found unable to report anything the change decided.
  A note declares nothing and is carried for the next specification to read.

A lesson is identified by its kind and by what it would declare, so a lesson several runs show
is one record naming each of them: a rule three runs blocked a change for reads as one line
with three runs behind it. The requester accepts, declines or defers it; `accept --as` declares
it in the requester's own words without changing what the runs showed; a declined lesson keeps
its reason and is never proposed again.

`core/lessons.py::criteria` adds the accepted lessons to the project's criteria, in
`load_config`: a command becomes a `[[commands]]` entry whose source names the lesson, a
convention a line of `conventions`, a scope the globs of `[scope] allowed_paths`. From the next
run on, the command is run at readiness and offered to the specifier, the convention travels as
a fact, the scope bounds the change. The lessons in force are carried on `ProjectProfile.lessons`
and given to the specifier as the fact *What earlier runs showed about this project*.

`495 lessons` lists them and answers them; `<state_dir>/lessons.md` is written next to the
document on every change, as the reading a person opens.

## Consequences

- A lesson is in force because the requester accepted it, not because a file was rewritten.
  `.495/project.toml` is hand-written, with its author's comments and order in it, and nothing
  here writes to it: `toml_lines` states the lines it would take, to copy or not. Rewriting the
  file was rejected — a generated TOML loses the comments, and a project's criteria would then
  have two authors.
- The criteria a run works under are therefore the file *and* the accepted lessons. `495 lessons`
  and `lessons.md` state what is in force, and a command that comes from a lesson says so in its
  `source`. A reader of `project.toml` alone no longer sees everything.
- Accepting a scope lesson on a project that declares none narrows it: everything was allowed,
  and those globs become the only ones. The lesson says so in its own words before it is
  answered.
- A reviewer's finding reaches the next producer only through an acceptance. The trust boundary
  of 0005 is kept: agent-produced text stays a proposal until the requester admits it, and it
  then travels as a fact like any other criterion.
- The lessons a run is given are on its profile, so the report and the retrospective of that run
  read the same later; what was accepted afterwards does not change what the run was told.
- `lessons.md` is a rendering and never a source: the specifier is given the lessons of the
  document, not the text of the file, and an edit made there is not read back. Feeding the
  specifier the file itself was rejected — it would mean parsing prose back into criteria, and a
  hand-edited line would reach an agent as a fact nobody accepted.
- `495 stats` (`core/stats.py`) reads the runs of the store as a series — outcomes, iterations,
  cost per requirement assessed, commands recorded at fault, kinds of verification that decided
  nothing, what each perspective found and what it found again. It is computed on every call,
  persisted nowhere, and decides nothing: what is done about a number is the requester's.
- Reading a run twice changes nothing: `learn` is pure and `reconcile` matches on the lesson's
  identity, so a second `495 retro` on the same run adds no record and no duplicate sentence.

## Where in the code

- `harness495/core/models/lessons.py`: `LessonKind`, `LessonStatus`, `Lesson`, `Lessons`,
  `REPLACED_PREFIX`, `ProjectProfile.lessons`.
- `harness495/core/lessons.py`: `learn`, `reconcile`, `accept`, `decline`, `defer`, `criteria`,
  `toml_lines`, `render_document`.
- `harness495/core/stats.py`: `summarise`, `InstrumentStat`, `KindStat`, `PerspectiveStat`.
- `harness495/core/scope.py`: `effective_allowed`, the paths a run's change may touch.
- `harness495/core/config.py`: `load_config` adds the accepted lessons to the criteria.
- `harness495/core/store.py`: `lessons_path`, `load_lessons`, `save_lessons`, `lessons_doc_path`.
- `harness495/core/engine/engine.py`: `_profile` carries the lessons in force; `_specify` gives them to
  the specifier.
- `harness495/core/context.py`: `render_lessons`.
- `harness495/interfaces/cli.py`: `retro`, the `lessons` commands, `stats`,
  `495 schema lessons|stats`.
- `tests/features/lessons.feature` with `tests/test_lessons_scenarios.py`;
  `tests/features/stats.feature` with `tests/test_stats_scenarios.py`.
