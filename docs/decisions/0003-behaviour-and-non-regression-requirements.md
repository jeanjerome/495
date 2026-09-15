# 0003. A requirement states behaviour or non-regression, and that decides what a passing command may credit

- Status: accepted
- Date: 2026-09-13

## Context

A command that passed on the base version and passes on the change reports the same thing twice.
Read against "the change makes X true", that is no evidence: X may have been true before, or the
command may not look at X. Read against "X went on holding", it is exactly the evidence wanted.
One `Sufficiency` value cannot serve both readings; the requirement has to say which it is.

## Decision

`Requirement.kind` is `behaviour` (something the change must make true; default, and the reading
applied to any unrecognised value) or `non_regression` (something that already held and must go
on holding).

- At specification time, `assess_sufficiency` receives the set of commands that passed at
  readiness. A `behaviour` requirement carried only by such commands, none of them `to_create`,
  is a gap: its outcome cannot tell the change from its absence. The gap is shown at the gate.
- At verification time, only verifications leaned on by `behaviour` requirements (and
  `to_create` ones) are calibrated (0002).
- At decision time, a `vacuous` verification is credited to a `non_regression` requirement and
  to nothing else; for a `behaviour` requirement it is `uncredited`, and the requirement ends
  `undetermined` unless another verification observes it. A `broken` verification credits
  neither kind.

The specifier prompt states the rule and asks for the kind on each requirement.

## Consequences

- A specification that covers new behaviour with the project's existing suite only is flagged
  before anything is produced, at the cost of one gate question.
- The producer is never asked to make a `non_regression` command "observe the change".
- Known limit: a `non_regression` requirement carried by the full suite is `satisfied` when the
  suite passes on both versions, including when the producer removed or skipped an existing test
  (`docs/etude-harnais-495.md`, E33).

## Where in the code

- `harness495/core/models/enums.py::RequirementKind`;
  `harness495/core/models/specification.py::Requirement.kind`.
- `harness495/core/reading/verification.py`: `assess_sufficiency` (`passing_on_base`).
- `harness495/core/engine/engine.py`: `_specify` (computes `passing_on_base`),
  `spec_from_agent` (unrecognised kind reads as `behaviour`).
- `harness495/core/engine/checks/calibration.py::calibrate` (`leaned_on`).
- `harness495/core/reading/decide.py`: `settled_either_way`, `uncredited`.
- `harness495/core/prompts.py`: `SPECIFIER_TASK`.
- `tests/features/verification.feature` with `tests/test_verification_scenarios.py`: a command
  that already passed on the base version, and the same command once it has not been run.
- `tests/features/decide.feature` with `tests/test_decide_scenarios.py`: success a command
  reports either way is not success the change earned, the same command still shows that what
  worked goes on working, and a command that never passes shows nothing at all, not even
  non-regression.
- `tests/features/calibration.feature` with `tests/test_calibration_scenarios.py`.
