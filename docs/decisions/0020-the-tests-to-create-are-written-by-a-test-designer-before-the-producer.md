# 0020. The tests to create are written by a test designer before the producer, and the producer may not touch them

- Status: accepted
- Date: 2026-09-14

## Context

A verification marked `to_create` was created by the producer, in the same intervention as
the code it measures. The specification said what the test does (0016), the reviewer
compared the test against the scenario (0017), and the control run showed that the test
fails without the change (0002); since 0019 the harness also says when that failure is an
import error rather than an assertion. None of that changes who wrote the test: the agent
whose change it judges, with the implementation in front of it. A test written that way
tends to assert what the implementation does rather than what the requirement says, and the
reviewer is the only thing between the two. This is the single-reasoner configuration the
harness exists to break up: one intervention specifies, another produces, others review, and
the tests that decide were still written by the producer.

## Decision

A fourth role, `Role.test_designer`, writes the tests to create. `Engine._design_tests` runs
it once per approved specification, in `change` mode, before the first producer intervention,
when a verification is `to_create` and admissible and `RolesConfig.test_designer` names an
agent (the default; `false` in TOML hands the tests back to the producer). The designer works
in the run's worktree with write capability, on the tree as it stands (the base version, or
the previous iteration's tree after a respecification), and receives the intent, the
approved specification with its scenarios, the profile, the form a behaviour test takes
(0017) and a scope of test files within the allowed paths. Its instructions say the scenario
is the text of the test, through the interface a caller uses; that the behaviour does not
exist yet and the test is expected to fail here, and to fail again if the behaviour were
removed; that it writes no implementation and no stub; to run the command once and report.

After the intervention the harness reads the worktree, not the report: the files found
written that `looks_like_a_test` recognises are kept, every other file is put back as it was
(`git.discard_paths`) with a warning, and the kept files are committed as `495 tests: …` on
top of the version the designer was given. The result is `Run.test_design`: the
intervention, the base and the commit, the files, the discarded paths, and what the designer
reported (which file holds which verification's test, what it could not write), the last two
as claims. A designer that writes no test file leaves an empty design and a warning; the
producer then writes the tests itself, as without a designer.

The producer receives the files under the fact "Tests written by the test designer", with
the sentence that they are read-only and that a version modifying, renaming or deleting one
is rejected on scope, and the same paths under "Scope" as protected. Its task says to make
them pass by implementing the behaviour, not to add a test that stands in for one, and to
report a test it believes wrong in `not_done`, quoting the assertion. Every reviewer receives
the same fact; `test_quality` is told those are the tests to compare, and that a test the
diff adds elsewhere for one of those verifications is the producer's own, a finding on the
verification.

`checks.sequence.protected_tests` adds a second `scope_check` evidence when a design exists: the
files of the design that `git diff --name-only design.commit..head` lists are the ones the change
moved;
the evidence fails and names them, and `assess` turns a failed scope check into a `[scope]`
correction that rejects the iteration, as for any path outside the scope. The control run of
0002 carries the designed files to the base version like any test file of the change.

`Engine._specify` resets `Run.test_design` whenever a specification is adopted, so that a
revised specification gets its tests written again; the tests of the previous one stay in the
tree as any file the previous iteration left. The command line's `--agent` and the API's
`agent` set the designer's agent along with the other roles, unless it is switched off.

## Consequences

- The test and the implementation come from two interventions that never see each other:
  the designer reads the scenario and the tree without the behaviour, the producer reads the
  test and may not change it. A test that fails without the change now fails for the reason
  the scenario states, or the designer wrote it wrong, and that is what the `unconfirmed`
  reading (0019) and the `test_quality` reviewer are left to catch.
- The designer's tests are decided by the tree, not by its report: a designer that writes a
  stub of the behaviour to make its test collect has the stub removed, since a stub is the
  producer's decision and would fix the interface before the producer runs. A test that
  cannot be collected without the stub fails on the change until the producer supplies the
  interface, which is the point.
- Protection is deterministic and total: any edit of a designed file, a fix included,
  rejects the version. A producer that finds a designed test wrong reports it in `not_done`
  and the run surfaces the claim; the requester decides. Allowing edits that "only fix" a
  test was rejected, since telling a fix from a weakening is the judgement the design exists
  to keep away from the producer.
- Cost: one more intervention per specification with a test to create, with the tree and
  the specification in context. Switching the designer off is a configuration decision
  (`test_designer = false`), stated in the run's configuration and visible on the home
  view, and the run then reads as it did before: the producer writes the tests, `unconfirmed`
  and `test_quality` still apply.
- Running the designer as a step of the specifier (read-only, tests returned in the answer)
  was rejected: writing a test that collects needs the tree, the runner and a command to
  run, which is a write intervention. Running it after the producer, as a check, was
  rejected too: a test written with the implementation in view is what this record removes.
- `evaluate` mode has no designer, as it has no producer: the tests of an existing change
  are part of the change under evaluation.

## Where in the code

- `harness495/core/models/enums.py::Role.test_designer`;
  `harness495/core/models/config.py::RolesConfig.test_designer`;
  `harness495/core/models/run.py`: `DesignedTest`, `TestDesign`, `Run.test_design`.
- `harness495/core/config.py::_roles_from` (`false` reads as None), `CONFIG_TEMPLATE`.
- `harness495/core/schemas.py::TEST_DESIGNER_SUMMARY_SCHEMA`.
- `harness495/core/prompts.py`: `TEST_DESIGNER_SYSTEM`, `TEST_DESIGNER_TASK`, the
  "Tests written by the test designer" paragraphs of `PRODUCER_TASK` and of
  `PERSPECTIVES["test_quality"]`.
- `harness495/core/engine/engine.py`: `_design_tests`, the call at the head of `_produce` and the
  facts it adds there and in `_review`, the reset in `_specify`.
- `harness495/core/engine/checks/sequence.py::protected_tests`, the `protected_tests` stage of
  `SEQUENCE`.
- `harness495/core/git.py`: `dirty_paths`, `discard_paths`.
- `harness495/core/context.py::render_test_design`; `harness495/core/report.py` (the
  version section); `harness495/interfaces/cli.py::_apply_overrides`,
  `harness495/interfaces/api.py::_config_from_body`, `harness495/interfaces/tui/views/home.py`,
  `stages.py`, `headlines.py`.
- `tests/conftest.py`: `design_tests`, `Scenario.designers`, the `Role.test_designer` branch
  of `FakeAgent`.
- `tests/features/test_designer.feature` with `tests/test_test_designer_scenarios.py`.
