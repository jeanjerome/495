# 0021. The existing test suite is measured on the change, and a passing command on a weaker suite credits no non-regression requirement

- Status: accepted
- Date: 2026-09-14

## Context

A non-regression requirement leans on a command that already passed on the base, and 0003
lets that command credit it when it passes again on the change: something went on holding.
What the command reports is an exit code over whatever tests it collected, and the change
decides what it collects. `allowed_paths` covers the test tree, as it must for the tests to
create; a producer that deletes a test that stands in its way, marks it skipped, renames it
past the runner's naming convention or deselects it from a configuration file gets the same
exit code as one that kept it, and the requirement was read as `satisfied`. Nothing in the
evidence said the suite had shrunk. The reviewers had the diff, and a reviewer that read the
test tree closely could see it; nothing asked them to, and a reviewer that did not was not
wrong by any rule the harness stated. 0020 protects the tests the designer writes; the tests
that were there before the run had no protection at all.

## Decision

The harness reads what the change did to the suite that passed on the base, and records one
`suite_check` evidence per iteration, in `checks.sequence.SEQUENCE` after the verifications and
before the control runs. Two readings, both pure functions in `core/suite.py`:

- `read_suite_changes(diff)` reads the diff of the change over the test files that existed
  on the base (a file the diff creates is the change's own instrument, left to 0002). Per
  file it states whether the file was deleted, renamed to a path `looks_like_a_test` does
  not read, which test definitions are on removed lines with no added line of the same file
  carrying their name (or how many, for a language that marks tests with an attribute),
  which lines the change adds that skip, ignore, disable or focus tests, how many tests it
  adds and how many hunks it has. The definitions and the markers are those of the runners
  the catalogue names for Python, Node, Go, Rust, the JVM, the shell and Gherkin.
- `count_tests(output)` reads the tally a runner prints at the end of its output (pytest,
  unittest, jest, mocha, `go test -v`, cargo, shellspec and rspec, JUnit, Gradle, behave,
  cucumber) as tests that ran and tests set aside; `compare_counts` pairs, for every
  command a non-regression requirement leans on, the tally of its `baseline` run on the
  base (readiness or preflight, same command string) with the tally of its run on the
  change.

The check fails when a file was deleted or renamed out of reach, a test removed, a skip
added, a tally shrank or its set-aside count grew. Its summary states each observation; its
`requirement_ids` are the non-regression requirements that lean on a test command.

`decide.assess` reads a failed suite check as it reads a vacuous instrument (0003): the
commands it names have passed on the change, and pass they did, but the suite they ran is
not the suite the base passed, so they credit nothing. The requirement is `undetermined`,
with the passing commands and the observation as its reason, listed under `uncredited`; a
reviewer finding on the requirement that cites an observation still makes it `violated`, as
for any requirement. A failed check that names no requirement is an undetermined reason on
the outcome. A passed check changes nothing.

Every reviewer receives the fact "Existing tests modified by the change" whenever the
reading lists a file or a tally: every existing test file the change touched, weakened or
merely modified, and the tallies. `spec_compliance` is told to account for each line: a
test removed, skipped or deselected that no requirement makes obsolete is a major finding on
the non-regression requirement quoting the hunk, and one a requirement calls for is named
with that requirement in the summary. `test_quality` is told to read each modified test
against the requirement it covered, an assertion loosened or an expected value moved to what
the implementation now returns being a finding unless a requirement states the new
behaviour. The producer is told that the existing tests are measured, not to remove or skip
one to get the suite to pass, and to say in its summary which test a requirement makes
obsolete.

## Consequences

- A change that shrinks the suite is never accepted on the harness's own evidence. It is
  accepted by the requester, at the undetermined gate, with the observation and the
  reviewers' account in front of them; or rejected, when a reviewer confirms the weakening
  as a finding, and the producer gets the observation as a correction. Turning the failed
  check into a rejection outright was rejected: a requirement that replaces a behaviour makes
  the test of the old behaviour obsolete, and telling that from a weakening is the judgement
  the reviewers and the requester hold, not the diff.
- Letting a reviewer's account lift the undetermined status was rejected: an account is a
  claim, and 0001 credits claims with nothing. The account is shown where the requester
  rules.
- A renamed test reads as removed: the test that passed on the base no longer runs under its
  name, and whether what runs under the new name observes the same thing is the reviewer's
  reading. The false alarm costs one ruling by the requester; the alternative, matching by
  count, let a producer trade a hard test for an easy one unseen.
- A test whose body changes under the same name is listed, not flagged: the diff cannot tell
  a fix from a weakening, and the reviewers are asked to. The count is read on the whole
  suite, so a deselection made through a configuration file, which the diff over test files
  does not see, shows as a smaller tally; a deselection masked by as many tests added shows
  only in the listing. A runner that prints no tally (`go test` without `-v`) leaves the
  count out, and the check rests on the diff.
- Cost: two readings of text the harness already holds; no command is run for it.
- Protecting every existing test file as 0020 protects the designed ones was rejected: a
  behaviour change legitimately edits the tests of the behaviour it replaces, and a change
  that may not touch them would have to be rejected or the tests left wrong.

## Where in the code

- `harness495/core/suite.py`: `SuiteChange`, `SuiteCount`, `CountComparison`,
  `SuiteReading`, `read_suite_changes`, `count_tests`, `compare_counts`.
- `harness495/core/models/evidence.py::EvidenceKind.suite_check`.
- `harness495/core/engine/checks/suite.py`: `suite_reading`, `check_suite`,
  `non_regression_verifications`; the `suite` stage of `checks/sequence.py::SEQUENCE`.
- `harness495/core/engine/engine.py::_review`: the fact given to the reviewers.
- `harness495/core/decide.py::assess` (`weakened_suite`, `unattached_weakening`).
- `harness495/core/context.py::render_suite_reading`.
- `harness495/core/prompts.py`: the "existing tests" paragraph of `PRODUCER_TASK`, the
  sentences of `PERSPECTIVES["spec_compliance"]` and `PERSPECTIVES["test_quality"]`.
- `harness495/interfaces/tui/reading.py::suite_checks`, `views/checks.py`.
- `tests/features/suite.feature` with `tests/test_suite_scenarios.py`.
