# 0001. A change is accepted on evidence only; the decision is a pure function

- Status: accepted
- Date: 2026-09-11

## Context

An agent that implements a change also reports on it, and the report is a claim: it may say a
command passed that never ran, or that a requirement holds because the agent believes it does.
The same model produced the change and the judgement, so the judgement carries the same
misreading. Accepting a change on that report means accepting the agent's interpretation of the
intent as its own verification.

## Decision

`harness495.core.decide.assess(spec, evidence, reviews)` computes the outcome of an iteration
from three inputs and nothing else: the approved specification, the `Evidence` the harness
recorded itself, and the `ReviewVerdict`s of read-only reviewers. It calls no agent and reads no
file.

Each requirement takes one of three statuses:

- `satisfied`: every verification attached to it has a `command_result` on the evaluated commit
  that passed, at least one of those verifications is `sufficient`, and no active reviewer
  reports a violation of it.
- `violated`: a verification it leans on failed on the evaluated commit, or an active reviewer
  reports a `blocker` or `major` finding on it whose `evidence` field is non-empty.
- `undetermined`: anything else. A requirement with no verification, a verification that did
  not run, only `insufficient` verifications, or a set of reviewers who all answered
  `undetermined` despite passing commands.

The iteration is `reject` when any requirement is `violated` or any correction request exists;
`undetermined` when any requirement is `undetermined`, when the spec has no requirement, or when
no active review verdict exists; `accept` otherwise. `undetermined` stops the run and asks the
requester; the harness never resolves it alone.

A reviewer finding of severity `blocker` with no `requirement_id` blocks acceptance when it
cites an observation. A finding without an observation, whatever its severity, changes nothing.

A reviewer's `requirement_assessment` is a claim about each requirement, not an observation.
An entry marked `violated` weighs what the findings behind it weigh: when the same reviewer
carries a `blocker` or `major` finding on that requirement that cites an observation, the finding
is what violates it; when it carries none, the entry is read as `undetermined` and the reason
records that the reviewer assessed the requirement as violated without a cited observation.

## Consequences

- The producer's structured summary (`commands_run`, `not_done`, `files_changed`) is displayed
  and re-measured; it never enters `assess`.
- Adding an agent call, a heuristic on file contents, or a time-dependent rule inside `assess`
  breaks the decision's reproducibility from `run.json` alone. Put new signals in `Evidence`
  first, then let `assess` read them.
- A reviewer that returns no parsable verdict, or that altered the tree, is `undetermined` or
  `discarded`, and both count as absence of review: a run with only such verdicts ends
  `undetermined`, never `accept`.
- A reviewer cannot send the producer into a correction iteration by naming a requirement
  as violated: the correction request is built from the finding's title and evidence, and
  there is none. A run whose only reviewer answers this way ends `undetermined`, like one whose
  reviewer answered `undetermined`.

## Where in the code

- `harness495/core/decide.py`: `assess`, `Assessment`.
- `harness495/core/engine/engine.py`: `Engine._decide` (applies the assessment to the run),
  `Engine._ask_undetermined` (the question raised on `undetermined`).
- `harness495/core/models.py`: `RequirementStatus`, `Verdict`, `Severity`, `Finding.evidence`.
- `tests/features/decide.feature` (steps in `tests/test_decide_scenarios.py`): a finding that
  cites no observation, a finding that cites one, a `violated` assessment without a finding,
  alone and beside an accepting reviewer, and one backed by a finding.
- `tests/test_scope_decide.py`: `test_no_review_means_undetermined_and_discarded_ignored`,
  `test_unattached_blocker_and_scope_block_acceptance`.
- `tests/test_engine.py`: `test_undetermined_refuses_to_conclude`,
  `test_reviewer_tampering_discards_verdict`.
