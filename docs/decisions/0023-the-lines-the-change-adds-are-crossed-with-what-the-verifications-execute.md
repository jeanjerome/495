# 0023. The lines the change adds are crossed with what the verifications execute, and a line none of them ran credits no requirement

- Status: accepted
- Date: 2026-09-14

## Context

0002 measures a verification against the base version: it answers "does this command report
something else without the change?". 0022 measures it against wrong versions of the change:
"does it report a line of the change altered in a stated way?". Both are questions about what
a command *reports*, and both are silent on the same thing — a line no command ever runs. The
mutation check makes that silence visible without naming it: a mutant of an unexecuted line
survives, as every mutant of it always will, and the check reports one line of one file at a
time, within the handful of mutants a run can afford.

The measure that answers directly is the catalogue's `coverage` role, whose Roles table already
states what a test of it shows: "which changed lines the suite executes", and "the changed
lines no test of the agent reaches" as what it can contradict. The studies of the six
technologies each measured the tool and the report it writes: coverage.py's JSON,
@vitest/coverage-v8's lcov, cargo-llvm-cov's lcov, `go test -coverprofile`, jacoco's and
kover's XML with per-line counts, kcov's Cobertura through `shellspec --kcov`. The tool is the
project's, the report is a file, and crossing it with the diff is reading.

## Decision

After the control runs and before the mutation check, `checks.coverage.reach` runs the project's
own test commands once more under its own coverage tool and records one `coverage_check` evidence
per iteration, naming the lines of the change no command executed.

`core/diff.py` holds the reading both checks share: `added_lines(diff)` for the number a line
has in the version under review, and `code_lines(diff, commands)` for the lines that carry code
of a technology the catalogue covers — not a comment, not a blank, not the instrument (a file
`looks_like_a_test` recognises, or one a `test` verification's command names whole, so that a
command running `tests/test_calc.py` names that file and not `calc.py`).

`core/reach.py` is pure and does the rest. `instrument(technology, tools, command, directory)`
rewrites the project's test command into one that writes a line-level report, from the tool the
profile recognised for the `coverage` role of that technology (`RoleCoverage`): coverage.py in
front of the runner then `coverage json`, vitest's and jest's own lcov options appended,
`-coverprofile` and `-coverpkg=./...` appended to `go test`, `cargo llvm-cov --lcov` in place of
`cargo test`, jacoco's or kover's report goal appended to the build, `--kcov` appended to
shellspec under a lowered descriptor limit. It appends options or replaces the runner token,
and never restructures the command, so a command that starts with a wrapper still works. It
returns None when the project measures the role with no tool it can drive, or runs a runner
those options do not fit. `READERS` reads the report back — lcov, coverage.py's JSON, a Go
coverage profile, Cobertura and JaCoCo XML — as a count per file and line, and `cross(lines,
hits)` puts the two together.

The engine runs the instrumented commands in the worktree of the evaluated commit, at most
`budget.max_coverage_commands` of them (2 by default, 0 leaves the check out), cheapest first,
and restores the tree afterwards. A command whose run writes no report is a warning and no
evidence: what it executes is not known, and what is not measured is not charged. A line the
reports hold with no hit is charged to every `behaviour` requirement resting on the commands
that were measured, which is what the evidence's `requirement_ids` hold.

`decide.assess` reads such a line as it reads a surviving mutant (0022) and a weakened suite
(0021): the commands passed, but they passed without ever running that line, so they do not
demonstrate the requirement. It is `undetermined`, with the passing commands and the lines as
its reason, listed under `uncredited`; a failing verification or an evidenced finding still
makes it `violated`. The reviewers receive the fact "Lines of the change no verification
executed"; `correctness` is asked whether the line carries behaviour a requirement states, and
`test_quality` to name the verification and the input that would reach it.

## Consequences

- `satisfied` now also means: the commands named ran every line of the change they instrument.
  It still does not mean the code is right, and a line that ran is not a line that was checked —
  that is what 0022 asks of it.
- A line no command executed never becomes a correction request. A guard the project's
  conventions call for, a branch no requirement states, an error path the specification leaves
  out are all unexecuted for reasons that are not defects; only a reader tells them from a hole
  in the tests, and the requester rules at the undetermined gate with the reviewers' account in
  front of them.
- A line the report does not hold is not charged, and neither is a file no report holds a line
  of, beyond a note in the summary. The engines list the lines they instrument: a closing
  brace, a continuation of a statement that starts higher up, a file the tool was not pointed
  at, all come back absent, and reading absence as "not executed" would charge the reader for
  what the tool does not claim. `--source=.` for coverage.py and `-coverpkg=./...` for Go are
  there for the opposite reason: they put a file no test imports in the report, as a file whose
  lines all went unexecuted, which is a measure and not an absence.
- The measure is the project's tool, never one the harness installs. A project that measures
  the role with nothing is not instrumented, and the check makes no evidence for it: the gap is
  stated by the profile and closed by a proposal (0014), which is also how a project whose
  runner these options do not fit adopts one that they do.
- Cost: one extra run of each instrumented command per iteration, bounded by
  `budget.max_coverage_commands` and by `command_timeout_s`. Only a `test` verification is
  instrumented: a linter, a build or a type checker reads the source without executing it, and
  a coverage engine in front of one would report that the change runs nowhere.
- Running the instrumented command *instead of* the plain one was rejected: the evidence the
  run rests on would then come from a command the harness rewrote, and a measure that changes
  what it measures is not the project's command any more. The plain command reports; the
  rewritten one is asked a second, separate question.
- Deriving the instrumented command at profiling, and offering it as one of the project's
  commands, was rejected for the same reason: it would stand in the readiness gate and in the
  list the specifier reads as if the project had written it, and a verification could then
  rest on a command the harness invented. The rewriting is an instrument of the harness's own
  check, made where the check is made.
- Charging only the requirement whose line went unexecuted was rejected for the reason 0022
  gives: the harness does not know which requirement a line serves. What the check asks is
  whether the evidence the run rests on ran the change at all.
- The check is skipped when the calibration found an instrument at fault, since the run stops
  on that and what a blind command reaches describes the command.

## Where in the code

- `harness495/core/diff.py`: `AddedLine`, `added_lines`, `is_comment`, `names_the_file`,
  `code_lines`, `SOURCE_SUFFIXES` — shared with `core/mutation.py` (0022).
- `harness495/core/reach.py`: `Instrumented`, `instrument`, the recipe per technology,
  `READERS` and the four report readers, `same_file`, `Unreached`, `Reading`, `cross`,
  `REPORT_DIR`.
- `harness495/core/models/evidence.py::EvidenceKind.coverage_check`;
  `harness495/core/models/config.py::Budget.max_coverage_commands`.
- `harness495/core/engine/checks/coverage.py`: `coverage_watchers`, `instrumented_command`,
  `reach`.
- `harness495/core/engine/checks/sequence.py`: the `coverage` stage of `SEQUENCE` and the gate
  `instrument_is_readable` it waits on.
- `harness495/core/engine/engine.py::_review`: the fact given to the reviewers.
- `harness495/core/decide.py::assess` (`unexecuted`).
- `harness495/core/context.py::render_reach_reading`.
- `harness495/core/prompts.py`: the sentences of `PERSPECTIVES["correctness"]` and
  `PERSPECTIVES["test_quality"]`.
- `harness495/interfaces/tui/reading.py::coverage_checks`, `views/checks.py`.
- `tests/features/reach.feature` with `tests/test_reach_scenarios.py`.
