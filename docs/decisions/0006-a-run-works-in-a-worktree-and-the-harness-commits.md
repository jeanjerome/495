# 0006. A run works in a git worktree outside the project, and the harness makes the commits

- Status: accepted
- Date: 2026-09-11

## Context

Evidence has to point at one exact version, and the user's working tree has to stay untouched
while agents edit files and run commands. An agent left to commit chooses what to commit and
when; a worktree inside the project is reachable by relative paths and pollutes the project's
status.

## Decision

- `create_run` requires a git repository with at least one commit; `profile` records
  `base_commit`.
- The run's worktree is `~/.cache/495/worktrees/<project>-<sha1(project path)[:8]>/<run-id>`
  (override: `HARNESS495_WORKTREES_DIR`, `sandbox.worktrees_dir`), on branch `495/<run-id>` at
  the base commit. Control runs use a sibling detached worktree `<run-id>.control`; the
  integration re-run uses `<run-id>-integration`.
- The producer does not commit. After the intervention, `git.commit_all` stages everything
  except well-known caches (`TRANSIENT_PATTERNS`) and commits as `495 harness <495@localhost>`;
  the resulting SHA is the evaluated version. The patch base..head is saved and hashed.
- Before every verification, `run_verification` checks that the worktree's `HEAD` is the
  evaluated commit and raises `VersionMismatch` otherwise; `reset_hard_clean` restores the
  exact tree between phases.
- The project's working tree is fingerprinted (`git status` + `git diff HEAD`) before and after
  every intervention; a difference marks the intervention `tampered`, records `integrity`
  evidence, and stops the run when the producer did it. A reviewer that leaves the worktree
  dirty or moved has its verdict discarded and the tree restored.
- `495 eval` materialises the change under evaluation (a commit, a range, a patch, the working
  tree) as one commit in the worktree so the same machinery applies.
- `.495/` is added to `.git/info/exclude`, never to tracked files.

## Consequences

- Every `Evidence.subject_version` is a SHA; `check-integration` compares against it by
  ancestry and by blob hash of each changed file.
- Two iterations that produce byte-identical patches are detected (`no_progress`) by
  `patch_sha256`.
- Caches written by test runners inside the worktree are excluded from the commit and cleaned;
  a project whose build output is not in `TRANSIENT_PATTERNS` will see it committed.
- Escape detection covers the project tree only; writes elsewhere on the host rely on the
  sandbox (`docs/etude-harnais-495.md`, E42).

## Where in the code

- `harness495/core/git.py`: `add_worktree`, `add_worktree_detached`, `commit_all`,
  `TRANSIENT_PATTERNS`, `reset_hard_clean`, `diff`, `sha256_text`, `ensure_excluded`.
- `harness495/core/engine/engine.py`: `worktrees_root`, `worktree_path`, `project_snapshot`,
  `_intervene` (tamper check), `_produce` (freeze), `_save_patch`,
  `_prepare_evaluation_worktree`, `cleanup_worktree`.
- `harness495/core/engine/running.py`: `VersionMismatch`, `run_verification`.
- `tests/test_engine.py`: `test_worktree_is_outside_project_and_escape_is_detected`,
  `test_reviewer_tampering_discards_verdict`, `test_evaluate_working_tree_and_patch`.
- `tests/features/workflow.feature` with `tests/test_run_scenarios.py`: a second version
  identical to the first stops the run instead of being read again.
- `tests/features/running.feature` with `tests/test_running_scenarios.py`.
