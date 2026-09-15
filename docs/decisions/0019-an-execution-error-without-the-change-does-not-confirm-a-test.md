# 0019. A test that fails without the change by an execution error is unconfirmed, and a test to create calls for the test_quality reviewer

- Status: accepted
- Date: 2026-09-14

## Context

0002 reads a verification's pair of runs: one on the change, one on the base version carrying
the change's test files. A pair that differs makes the verification `discriminating`, and a
passing report on the change then credits the requirement. The comparison did not read *how*
the command failed without the change. A test that imports a function the change creates
fails on the base version with `ImportError` whatever its body says: `assert subtract(5, 3)`
and `assert True` fail there the same way, and both pass with the change. The one mutant the
control run applies, the absence of the change, cannot tell them apart; the pair only shows
that the test's target is absent without the change, never that the test observes what the
target does. The reviewer that reads a test against its requirement, `test_quality`, was not
among the default perspectives, so a test written by the producer for its own change was
judged by nobody unless the requester had configured it.

## Decision

`classify_instrument` reads the control run's output when the pair differs, the command
passed on the change and failed without it. Two readers over the output, one per family of
runner the catalogue names (Python, Node, Go, Rust, the JVM, the shell):

- `asserted`: the output shows a test reaching an assertion and failing it (`AssertionError`,
  pytest's `E   assert`, jest's `expect(received)`, go's `--- FAIL:`, JUnit's `expected: <`,
  shellspec's `expected`).
- `execution_error`: the first line reporting that the code the test needs was not there to
  run (`ImportError`, `NameError`, `AttributeError`, a `TypeError` on a signature, `Cannot find
  module`, `undefined:`, `error[E0…]`, `cannot find symbol`, `command not found`).

When nothing asserted and an execution error is found, the verification is `discriminating`
and its sufficiency is `Sufficiency.unconfirmed`, with a rationale quoting the line: it fails
without the change by an execution error, not by an assertion; the test was seen missing its
target, not observing the behaviour. When the output shows an assertion, or shows neither,
the verification is `sufficient` as before: the comparison stays conservative, and an output
the readers do not recognise accuses nothing.

`unconfirmed` is admissible (`ADMISSIBLE = {sufficient, unconfirmed}`): `assess` credits a
passing unconfirmed verification as a sufficient one, and the requirement's reason carries
`(unconfirmed: …)` after the verification's id; the calibration and the preflight treat it as
a live instrument; `render_spec` prints an `unconfirmed:` line under the verification in every
agent's context; the report prints it after the PASS. The `test_quality` perspective is told
what `unconfirmed` means and to read that test with particular care: state whether its
assertions would fail on an implementation that exists but behaves otherwise, and report a
finding on the verification, quoting the assertion, when they would not.

`RolesConfig.reviewers_for(spec)` gives the reviewers a run calls: the configured ones, and
`test_quality` appended whenever a verification is a test to create and no configured entry
has that perspective. The added entry runs with the agent of the first configured reviewer
(the producer's when none is configured); a configured `test_quality` entry is kept as it is,
its `instructions` included. `Engine._review` walks that list.

## Consequences

- A test whose only observation is that its target exists no longer passes as discriminating
  without anyone knowing. The harness says what it saw, and the perspective that can read the
  test's assertions is in the room every time a test was written for the change under review.
- `unconfirmed` does not block: the requirement is `satisfied` when the test passes, and the
  run is accepted unless a reviewer finds against the test. Deranking to `undetermined` was
  rejected: every test of a new function fails without the change by an import error, so a
  strict reading would stop every such run at a question whose answer is always "the target
  did not exist yet". The reviewer, not the status, is what tells a tautology from a test.
- The readers are pattern lists over the last lines of a run, one per runner family, and they
  err towards `sufficient`: an assertion pattern wins over an error pattern (a test that
  asserted anything did reach its target somewhere), and an output matching neither is
  believed. Adding a runner means adding its lines to both patterns, with a scenario in
  `tests/features/instrument_nature.feature` showing them read.
- Every run with a test to create costs one more reviewer intervention than configured.
  Making `test_quality` a default perspective for every run was rejected: with no test
  written for the change, its instructions have nothing to compare, and the cost would be paid
  on every run for nothing.
- A change that edits an existing test to name the new code is read the same way: the rule is
  on the pair of runs, not on `to_create`, since the tautology is the same wherever the import
  was added.

## Where in the code

- `harness495/core/reading/verification.py`: `asserted`, `execution_error`, `_ASSERTION`,
  `_EXECUTION_ERROR`, the `unconfirmed` branch of `classify_instrument`.
- `harness495/core/models/enums.py`: `Sufficiency.unconfirmed`, `ADMISSIBLE`;
  `harness495/core/models/config.py::RolesConfig.reviewers_for`.
- `harness495/core/reading/decide.py::assess`: `ADMISSIBLE` in place of `sufficient`, the
  `(unconfirmed: …)` note in the requirement's reason.
- `harness495/core/engine/checks/calibration.py::calibrate`: the subjects and the
  `control.ended` event.
- `harness495/core/engine/engine.py`: `_preflight`, `_review` (`reviewers_for`).
- `harness495/core/context.py::render_spec`, `harness495/core/report.py::_observed`,
  `harness495/core/prompts.py::PERSPECTIVES["test_quality"]`,
  `harness495/interfaces/tui/theme.py` (`suf.unconfirmed`).
- `tests/features/instrument_nature.feature` with `tests/test_instrument_nature_scenarios.py`.
