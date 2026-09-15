# 0009. A run is claimed by the process advancing it; a dead claim is taken over

- Status: accepted
- Date: 2026-09-12

## Context

Three interfaces advance runs: the CLI, the HTTP API and the terminal UI, possibly from several
terminals. Two engines stepping the same run write the same `run.json` from two phases at once;
the last writer wins and an intervention, its evidence or a whole iteration disappears.

## Decision

`RunStore.claim(run_id, label)` writes `<run>/DRIVER` with `pid`, `host`, `label`, `since`, and
raises `RunBusy` when a claim already names another holder. `Engine.run`, `merge_delivery` and
`check_integration` claim on entry and release in `finally`. `release` deletes the file only
when the pid is this process. `holder` returns `None` for this process's own claim and for a
claim whose pid no longer exists on this host (`os.kill(pid, 0)`); a claim from another host is
honoured until released.

A surface that finds a run claimed watches it instead of joining in. A run that blocks (decision,
pause, terminal state) releases its claim.

## Consequences

- Concurrent drivers are refused, not serialised; the second one reads and displays.
- A crash leaves a claim that the next driver takes over on the same host. Across hosts sharing
  a state directory, a stale claim must be released by hand.
- `STOP` is a separate flag: any process may request a stop; only the holder advances.

## Where in the code

- `harness495/core/store.py`: `claim`, `release`, `holder`, `_alive`, `DRIVER_FLAG`, `RunBusy`.
- `harness495/core/engine/engine.py`: `run`, `merge_delivery`, `check_integration`.
- `tests/test_models_store.py`: `test_a_claim_refuses_a_second_holder_and_is_given_back`,
  `test_a_run_held_by_a_live_process_is_named_not_taken`,
  `test_a_claim_left_by_a_dead_process_does_not_lock_the_run`,
  `test_releasing_someone_else_s_claim_does_nothing`.
- `tests/features/isolation.feature` with `tests/test_run_scenarios.py`: a run another
  process holds is refused rather than joined, and a run that stops on a question gives
  the claim back.
- `tests/test_tui_pilot.py`: `test_a_run_advanced_elsewhere_is_watched_not_joined`.
