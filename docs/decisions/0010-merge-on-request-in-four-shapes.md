# 0010. Merging happens on request only, in four shapes, and leaves the repository as found on failure

- Status: accepted
- Date: 2026-09-12

## Context

`deliver` leaves a branch and a patch; the user's checkout is untouched. Bringing the change in
is one act with two halves: the merge, and the check that what landed is what was verified. A
merge left unchecked would be the only integration 495 performs and never verifies. The
delivered branch is checked out in the run's worktree, which constrains which git commands can
run.

## Decision

`495 merge <id> --how fast-forward|rebase|squash|merge [--rerun]` is the only command that
writes to the user's checkout, and it always runs the integration check afterwards on `HEAD`.

Preconditions are refusals, each leaving the repository unchanged: tracked files with
uncommitted changes (untracked files are allowed); a branch that already contains the verified
commit; `fast-forward` when the checked-out branch has moved since the run branched.

Shapes (`git.integrate_branch`):

- `fast-forward`: `git merge --ff-only`; adds nothing.
- `rebase`: `git cherry-pick <base>..<branch>`; copies the run's commits under new hashes. A
  `git rebase` is not used: git refuses to move a branch checked out in another worktree, a
  rebase would move the delivered ref rather than copy from it, and standing on the user's
  branch it would replay the wrong side.
- `squash`: `git merge --squash` then one commit whose message cites the verified SHA and the
  run id.
- `merge`: `git merge --no-ff` with a message citing the verified SHA; the only non-linear shape.

On any git error: `merge --abort`, `cherry-pick --abort`, `reset --hard <before>`, then the
error is re-raised with "nothing was changed".

`RunResult.integrated_as` records the shape. `check_integration` computes `contains_commit`
(ancestry) and `files_identical` (blob hash per changed file), optionally re-runs every
verification on a detached worktree of the target, and records the target ref under the branch
name it had (a check asked on `HEAD` records the branch). `Run.integration_state()` derives one
of `unchecked`, `unmerged` (target still at the base commit), `landed`, `differs` from the check
and the base commit; it is not stored, because the two booleans alone cannot tell "not merged
yet" from "something else landed".

## Consequences

- `rebase` and `squash` leave the verified commit absent from the branch; `files_identical` is
  what says the right content landed. Both booleans are read for that reason.
- Adding a fifth shape means adding it to `git.INTEGRATIONS`, `integrate_branch`, `_undo`, the
  CLI choices and `test_each_way_of_integrating_leaves_the_history_it_promises`.
- The HTTP API exposes `check-integration` and not `merge`.

## Where in the code

- `harness495/core/git.py`: `INTEGRATIONS`, `integrate_branch`, `_undo`, `can_fast_forward`,
  `has_uncommitted_changes`, `is_ancestor`, `blob_hash`.
- `harness495/core/engine/engine.py`: `merge_delivery`, `_merge_delivery`, `_integration_message`,
  `check_integration`, `_check_integration`.
- `harness495/core/models.py`: `RunResult.integrated_as`, `IntegrationCheck`,
  `Run.integration_state`.
- `tests/test_engine.py`: `test_fast_forward_adds_nothing_at_all`,
  `test_fast_forward_is_refused_once_your_branch_has_gone_somewhere`,
  `test_each_way_of_integrating_leaves_the_history_it_promises`,
  `test_the_check_records_the_name_the_ref_has_rather_than_where_you_stood`,
  `test_a_squash_says_where_the_evidence_for_it_is`,
  `test_a_merge_that_conflicts_leaves_the_repository_where_it_was`,
  `test_a_dirty_tree_is_refused_rather_than_stashed`, `test_check_integration`.
- `tests/test_tui_pilot.py`: `test_a_ref_nobody_merged_into_is_not_a_failed_integration`,
  `test_the_two_last_stops_say_the_same_thing_about_a_copied_change`.
