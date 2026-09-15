# 0015. A retrospective states what a run showed about each tool that measured a catalogue role, and the catalogue takes the row by hand with the run as its source

- Status: accepted
- Date: 2026-09-13

## Context

The catalogue (0012) admits an entry through a study, a piece of research, or a retrospective
on a host project, and keeps a rejected library with its reason. Studies exist for Python;
nothing produced a retrospective. Yet every run measures the project's tools: a verification
that names a catalogue role (0014) runs on the change, on the base version carrying the
change's test files (0002), and once before any change exists, and the decision reads those
pairs. A tool that reported something the change decided, or one that failed identically on
both versions, timed out, or had its command replaced by the requester, is on disk in
`run.json` with its evidence, and nobody read it back for the catalogue. The long loop was
missing: what a run learned about a tool stayed in the run.

## Decision

`495 retro <run-id>` writes the retrospective of a run: what the run showed about the tools
that measure each catalogue role, from the run document and nothing else.

For each verification that names a role, every run of it on the change is paired with the
control run that followed it (same verification, iteration and command); a run with no
control is read against the baseline run of the same command before any change, when there
is one. Each pair is read into one of four outcomes, each stated in words with the
verification and the iteration: a *verdict* when the tool's report differed with and
without the change, or agreed on a pass with the baseline; a *contradiction* when the tool
reported a failure on the change that it did not report without it; a *fault* when the
failure was outside the change's reach (timed out, not executable at readiness, failed
identically on both versions and recorded as an instrument fault, failed before any change
too, or the requester replaced its command); *inconclusive* when nothing shows whether the
tool observed the change (the same success on both versions, or a report with nothing to
read it against).

The tools come from the profile's role coverage: the measured rows of the role, narrowed to
the rows whose tool the command names when several technologies measure it. One
`ToolObservation` per technology and role carries the tools, the counts, the evidence ids
and the sentences, and a verdict: `faulty` if any fault, else `proven` if any verdict or
contradiction, else `inconclusive`. A proven tool yields the Markdown row of a `recommended`
entry, a faulty one a row of the Rejected table with the fault sentences as its reason, an
inconclusive one no row; the Source cell of either is `retrospective <date> (<project>, run
<run-id>)`, and the observation says whether the catalogue already recommends the tool for
the cell, in which case the row is a further source for an entry that exists.

The document is `runs/<run-id>/retrospective.json` (`Retrospective`, `495 schema
retrospective`), written again on each call and reading the same. The catalogue is not
written by the command: the maintainer of `docs/test-libraries.md` reads the rows and admits
them.

## Consequences

- A retrospective is a pure function of the run document (`core/reading/retro.py::retrospect`),
  like the decision (0001): it reads evidence, iterations, the spec and the profile, never the
  events, the outputs or the tree. The catalogue entry each observation is stated against is
  read the same way: a cell holding several entries is picked between by conditions, some of
  which read the project's files, and those are evaluated once, while the project is profiled,
  onto `ProjectProfile.conditions`; `catalogue.applicable` reads that record and opens nothing.
  The two halves sit in two packages, so that nothing puts them back together: the conditions
  in `core/conditions.py`, the recommendations in `core/reading/catalogue.py`, which the
  contract on `core.reading` keeps free of anything that could read a file (0011).
  A run read after its project changed answers as the run measured the project, not as the
  project stands. A run archived with `495 export` yields the same retrospective anywhere. The
  cost is that two failures with different signatures on both versions, which the engine tells
  apart from the outputs, are read here from the recorded instrument fault alone: a pair of
  failures with no fault recorded is a contradiction.
- Control and baseline runs carry `passed=None`, being statements about the instrument; the
  retrospective reads what they reported from the exit code against the expected one.
- A verification of a role nothing in the project measures never ran and brings nothing; a
  verification without a role brings nothing either, whatever it showed.
- The catalogue stays a document with a source per entry (0012): one run on one project is
  one observation, and admitting it as a recommendation for every project is the
  maintainer's reading, not a command's side effect. Writing `docs/test-libraries.md` from
  the command was rejected: the catalogue lives in 495's repository, not in the host
  project's, and a rejected row written on one timed-out run would bind every project.
- The retrospective covers the catalogue only. What a run learned about the project's
  commands, conventions and scope is read by the same command, as lessons the requester answers
  (0027); the two readings are separate, since the catalogue is 495's document and the criteria
  are the project's.

## Where in the code

- `harness495/core/models/retrospective.py`: `ToolVerdict`, `ToolObservation`, `Retrospective`.
- `harness495/core/reading/retro.py`: `measurements`, `read`, `retrospect`, `SECTION_NAMES`.
- `harness495/core/conditions.py`: `CONDITIONS`, `conditions_holding`;
  `harness495/core/reading/catalogue.py::applicable` reads what they left;
  `harness495/core/profile.py::detect_profile` records the outcome;
  `harness495/core/models/lessons.py::ProjectProfile.conditions`.
- `harness495/core/store.py`: `RunStore.retrospective_path`, `load_retrospective`,
  `save_retrospective`.
- `harness495/interfaces/cli.py`: the `retro` command, `_print_retrospective`,
  `495 schema retrospective`.
- `docs/test-libraries.md`, section Bringing an entry in.
- `tests/features/retrospective.feature` with `tests/test_retrospective_scenarios.py`;
  `tests/features/catalogue.feature`, scenario "The catalogue is read as the project was
  profiled, not as its tree stands", with `tests/test_profile_scenarios.py`.
