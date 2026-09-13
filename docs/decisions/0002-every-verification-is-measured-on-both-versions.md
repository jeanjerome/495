# 0002. Every verification is measured on the change and on the base version before it counts

- Status: accepted
- Date: 2026-09-11; refined 2026-09-13 (`broken` and `vacuous` told apart, control tree carries the change's test files)

## Context

A verification command is an instrument pointed at a requirement. Two instrument faults look
exactly like a verdict about the change: a command that fails whatever the tree contains (a
missing tool, a filter that selects nothing, a pre-existing red test) reads as a defect and
sends the producer after something no edit can fix; a command that passes whatever the tree
contains (the project's full suite when the requirement states new behaviour and no new test was
written) reads as proof and credits a change that was never observed.

## Decision

After the verifications have run on the evaluated commit, `Engine._calibrate` runs each one that
a `behaviour` requirement leans on (or that is `to_create`) a second time, in a detached
worktree of the base commit onto which the change's test files have been checked out
(`instrument_files`, recognised by naming convention). The pair is read by
`classify_instrument`:

- the two runs differ in exit code or in `failure_signature` (output with timestamps, durations,
  paths, hashes and addresses erased, last 40 non-empty lines): the command observes the change;
  `discriminates = True`.
- both fail identically: `Sufficiency.broken`. No edit inside the change can make it pass.
- both pass, with test files applied: `Sufficiency.vacuous`. It reports success either way.
- both pass, and no test file of the change could be identified: `discriminates = None`,
  sufficiency unchanged, a warning. Not enough to accuse the instrument.

A `broken` or `vacuous` verification leaves the evidence: `assess` neither credits it nor charges
its failure to the change, and a reviewer finding whose `evidence` cites it is set aside. The
run stops on `instrument_fault` and asks: replace the command (`recalibrate`, measured the same
way before it counts), return to the specification (`respecify`), keep it as proof of nothing
(`ignore`, which holds for the rest of the run), or abort. When the producer reported a
different command that exited 0, `_measure_proposal` runs that command on both trees first and
offers it only if it passes on the change and reports something else without it.

Comparison is conservative: a timeout or interruption on either side counts as "the instrument
is sound".

Before any of this, every project command is run once on the base version at `profile`
(readiness: is it executable here, what does it print), and every command the specification
proposes is run once on the base version before the gate (`_preflight`); both outputs are kept
as `baseline` evidence and shown with the question, never concluded from.

## Consequences

- `satisfied` means: the command passed on the evaluated commit and reported something else
  without the change. It does not mean the command measures this requirement; that mapping is
  the specification's, reviewed by the requester at the gate.
- The control run costs one extra execution per leaned-on verification per iteration. Keep the
  set small: only `behaviour` requirements and `to_create` verifications are calibrated;
  `non_regression` ones are not (see 0003).
- `failure_signature` is the equality test. Changing what it erases changes which pairs are
  "identical"; a count is kept on purpose because a different count is a different failure.
- The base tree carries the change's test files so that "the instrument is present, the
  behaviour is absent". A project whose tests follow none of the recognised layouts falls into
  the `None` case and is warned, not judged.
- Known limit: one mutant only, the absence of the change. A test that fails on the base for an
  import error and passes with the change is `discriminating` even if its assertions observe
  nothing (`docs/etude-harnais-495.md`, E03, E30, E32).

## Where in the code

- `harness495/core/verification.py`: `run_control`, `measures_the_change`,
  `classify_instrument`, `failure_signature`, `instrument_files`, `looks_like_a_test`.
- `harness495/core/engine.py`: `_calibrate`, `_measure_proposal`, `_instrument_decision`,
  `_recalibrate`, `_instrument_fault_settled`, `_profile` (readiness), `_preflight`.
- `harness495/core/models.py`: `Sufficiency`, `NON_DISCRIMINATING`, `Verification.discriminates`,
  `EvidenceKind.instrument_check`, `EvidenceKind.baseline`, `DecisionKind.instrument_fault`.
- `harness495/core/decide.py`: `blind`, `tainted`, `rests_on_a_blind_instrument`, `set_aside`.
- `tests/test_profile_verification.py`: `test_failure_signature_ignores_where_and_when_but_not_what`,
  `test_measures_the_change_is_conservative`, `test_a_command_that_fails_on_both_versions_is_broken_not_a_defect`,
  `test_a_command_that_passes_on_both_versions_proves_nothing_either`,
  `test_passing_on_both_settles_nothing_when_the_test_could_not_be_carried_over`.
- `tests/test_engine.py`: `test_verification_blind_to_the_change_is_not_turned_into_a_correction`,
  `test_ignoring_a_blind_verification_holds_for_the_rest_of_the_run`,
  `test_every_command_is_run_once_before_the_specification_is_approved`,
  `test_a_broken_command_is_replaced_and_measured_again_without_producing_anything_twice`,
  `test_a_command_the_producer_says_worked_is_run_on_both_versions_before_it_is_offered`.
- `tests/test_scope_decide.py`: `test_a_verification_that_cannot_see_the_change_is_not_charged_to_the_change`,
  `test_finding_that_rests_on_a_blind_verification_is_set_aside`,
  `test_a_control_run_never_stands_in_for_the_verification_it_checks`.
