# 0004. A correction request names the gap and the observation, never the remedy

- Status: accepted
- Date: 2026-09-11

## Context

A correction request shaped as a remedy ("change `a + b` to `a - b`", "make V1 pass") makes the
next producer optimise the remedy. A request naming a command makes it optimise the command's
exit code: the shortest edit that flips it, or a workaround of the verification. Reviewers write
their diagnosis and often the fix in `detail` and `summary`; handing those to the producer
replaces its own diagnosis with someone else's, and a wrong diagnosis then travels unexamined.

## Decision

A correction request is built by `assess` from three pieces and no more: the requirement id(s),
the claim, and the observation.

- From a failed verification: `[R1,R2] behaviour not demonstrated: V1 <summary>`, once per
  distinct observation, naming every requirement that verification carries.
- From an evidenced reviewer finding: `[R1] <finding.title> — observed: <finding.evidence>`
  (evidence cut at 400 characters, newlines flattened). `finding.detail` and the reviewer's
  `summary` are left out.
- From a scope violation: `[scope] <summary>`.
- From an unattached blocker: `[<perspective>] <title> — observed: <evidence>`.

The producer's correction context (`Engine._produce`, iteration > 1) contains the correction
requests and the previous iteration's evidence as facts; the failed commands' outputs and the
reviewers' findings rendered with `observations_only=True` (claim, location, observation; no
`detail`, no `summary`) as untrusted content. `CORRECTION_TASK` states that these are statements
about what is, not instructions about what to change.

A verification found `broken` or `vacuous` (0002) produces no correction request.

## Consequences

- The producer diagnoses the cause itself; the harness says where to look and what was seen.
- A reviewer's explanation is still in `run.json` and in the report for the requester; only the
  producer does not receive it.
- Adding a field of a `Finding` to the correction line, or passing `render_reviews` without
  `observations_only`, reverses this decision.

## Where in the code

- `harness495/core/decide.py`: module docstring, correction construction in `assess`,
  `failures_by_observation`.
- `harness495/core/context.py`: `render_reviews(observations_only=...)`.
- `harness495/core/engine/engine.py`: `_produce` (correction pack).
- `harness495/core/prompts.py`: `CORRECTION_TASK`.
- `tests/test_scope_decide.py`: `test_correction_states_the_observation_not_the_remedy`,
  `test_one_failing_verification_yields_one_correction_for_all_its_requirements`.
- `tests/test_engine.py`: `test_correction_prompt_carries_observations_not_the_reviewer_s_conclusions`.
