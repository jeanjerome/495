# 0024. A verification is run twice on the same version, and one that does not report the same thing twice decides nothing

- Status: accepted
- Date: 2026-09-14

## Context

Every control the harness runs compares two trees. 0002 runs a command on the change and on
the base carrying the change's test files; 0021 compares the suite on both; 0022 runs it on
wrong versions of the change; 0023 runs it under a coverage tool and crosses the report with
the diff. Each of them reads a command's result as a property of the tree it ran on.

A command run once per tree makes that reading an assumption. A test that depends on the
order its cases run in, on the clock, on a port or a directory another process holds, or on
state an earlier test left behind, reports one thing on one run and another on the next, with
nothing about the tree changed in between. The harness then reads that difference as the
change: a requirement moves from `satisfied` to `violated` between two iterations although the
producer never touched the code it names, or a command that failed on the base and passes on
the change is called discriminating when what differed was the weather. The failure costs the
producer a whole iteration, spent looking for a defect that will not be there when it looks,
and the correction request it gets names an observation nobody can reproduce.

Nothing measured it, although the material was already in place: `failure_signature` normalises
away what differs between any two runs of one command (timestamps, durations, paths, hashes,
addresses) and keeps everything else, counts included, which is exactly what is needed to say
whether two runs failed for the same reason.

## Decision

After the verifications have run on the evaluated commit and before anything is concluded from
them, `checks.stability.repeat` runs the commands the requirements lean on a second time, and
records one `stability_check` evidence per command.

`verification.reports_the_same_twice` reads the pair. Two runs that both report the exit code
the verification expects are one reading, whatever they printed: the outcome of a verification
is its exit code, and a passing run's output carries counts and orderings that differ between
any two runs. Two runs that both fail are compared on their `failure_signature` as well, since
a command that fails for a different reason each time hands the producer an observation that
will not be there. A run that reports success and a run that does not — a failure, a timeout —
is not a reading at all.

The second run follows the first in the worktree the verification pass left, in the order the
commands ran in, so that a command finding what an earlier one built still finds it. Which
commands: every verification that a requirement names, whose sufficiency is admissible and
that reported something on the change; the one whose result flipped since the previous
iteration goes first, then the cheapest, and one slower than `budget.repeat_command_max_s` is
left out with a warning. `budget.max_repeated_commands` (default 4) caps the check, and 0
leaves it out.

`decide.assess` sets an unstable verification aside in both directions at once. What it
reported credits no requirement — the requirement is `undetermined`, with the pair as its
reason, listed under `uncredited` when the run it is losing was a passing one — and charges
none: it produces no failed verification, so no correction request, and a reviewer's finding
citing it is set aside exactly as one citing a blind instrument is (0002). A requirement
another verification demonstrates is still demonstrated.

The same reading takes the command out of the other controls for this iteration. It is not
calibrated (0002), since comparing a reading that came up heads with a third run on another
tree would name an instrument at fault on the strength of a coin toss; it watches no mutant
(0022) and is not instrumented for coverage (0023), since what it reports on another tree is
not a statement about that tree. The reviewers receive the fact "Verifications that did not
report the same thing twice"; `test_quality` is asked to name what in the test depends on
something other than the change, and `correctness` not to read either run as a defect.

## Consequences

- A run now costs one more execution of each command a requirement leans on, per iteration,
  bounded by `max_repeated_commands` and by `repeat_command_max_s`. That is the price of the
  reading; a flaky command was already costing an iteration of producer time, which is more.
- Two runs is the smallest number that can show instability and the weakest evidence of
  stability: a command that fails one run in twenty passes this check nineteen times out of
  twenty. The check does not say a command is deterministic; it says the harness did not see
  it change its mind. Running each command n times was rejected for what it costs, since the
  detection rate rises far more slowly than the bill.
- An unstable verification never becomes a correction request, for the same reason a surviving
  mutant does not (0022): the harness sees that two runs disagreed, not why they did. The
  requester rules at the undetermined gate, with the reviewers' account in front of them.
- The comparison is on the verdict, and on the failure signature only when both runs failed.
  Reading a difference between two passing runs' output as instability was rejected: a runner
  prints durations, seeds and orderings that differ every time, and every project whose suite
  prints one would be reported as unstable.
- A command that flips because an earlier command in the pass built something it needs is read
  as unstable, which it is from where the decision stands: what it reports depends on something
  other than the version. Resetting the worktree between the two runs would turn that case into
  the opposite mistake — a project whose test command legitimately follows its build command
  would be called unstable on every run — so the tree is left as the first pass left it.
- The flip since the previous iteration only decides which command is repeated first, not what
  is concluded. A flip is expected when the producer has just fixed what the command reported,
  and the repeat then confirms it; it is a symptom when the command changed its mind on its
  own. Both readings ask for the same thing, and only the repeat tells them apart.
- A command the check leaves out for being slow is measured exactly as it was before: this
  record adds a reading, it does not withdraw one. The warning says which command that is.
- A project that measures flakiness with its own tool (a rerun plugin, a repeated-run mode)
  declares it as a verification like any other. This check does not replace it: it repeats the
  commands of one run twice, not a suite many times.

## Where in the code

- `harness495/core/reading/verification.py`: `reported_success`, `reports_the_same_twice`,
  over the `failure_signature` the control run of 0002 already uses.
- `harness495/core/models/evidence.py::EvidenceKind.stability_check`;
  `harness495/core/models/specification.py::Verification.stable`;
  `harness495/core/models/config.py`: `Budget.max_repeated_commands`,
  `Budget.repeat_command_max_s`.
- `harness495/core/engine/checks/stability.py`: `flipped_since`, `repeat_watchers`, `repeat`;
  the `stability` stage of `checks/sequence.py::SEQUENCE`.
- The `stable` guard in `checks/calibration.py::calibrate`,
  `checks/coverage.py::coverage_watchers` and `checks/mutation.py::mutation_watchers`.
- `harness495/core/engine/engine.py::_review`: the fact given to the reviewers.
- `harness495/core/decide.py::assess` (`unstable`, `unreadable`, `unsteady`).
- `harness495/core/context.py::render_stability_reading`.
- `harness495/core/prompts.py`: the sentences of `PERSPECTIVES["correctness"]` and
  `PERSPECTIVES["test_quality"]`.
- `harness495/interfaces/tui/reading.py`: `stability_checks`, `unstable_verifications`,
  `verification_state`; `views/checks.py`.
- `tests/features/stability.feature` with `tests/test_stability_scenarios.py`.
