# Python BDD libraries: the `bdd` role

- Date: 2026-09-13
- Fills: `docs/test-libraries.md`, role `bdd`, section Python
- Rules applied: `docs/decisions/0012-tests-use-proven-libraries-from-a-catalogue.md`,
  `docs/decisions/0013-tests-are-behaviour-scenarios-in-gherkin.md`

The library that binds Gherkin scenarios to steps and runs them. The constraint that decides
the choice: the scenario's steps must keep every other Python entry of the catalogue, which
are pytest fixtures and plugins (pytest-mock, pytest-benchmark, pytest-memray, hypothesis'
plugin, pytest-cov) or drive pytest themselves (mutmut, schemathesis' pytest integration). A
library with its own runner loses them.

## Facts measured

### Releases, as read on PyPI, and repository activity

| Library | Version | Released | Python | Licence | Last commit |
|---|---|---|---|---|---|
| pytest-bdd | 8.1.0 | 2024-12-05 | >=3.9 | MIT | 2026-08-05 |
| behave | 1.3.3 | 2025-09-04 | >=2.7, not 3.0–3.2 | BSD-2-Clause | 2026-09-11 |
| radish-bdd | 0.18.4 | 2026-02-24 | >=3 | MIT | 2026-09-08 |
| pytest-bdd-ng | 2.3.1 | 2024-11-26 | >=3.9 | MIT | not checked |
| gherkin-official | 42.0.1 | 2026-08-05 | >=3.10 | MIT | parser only, by the Cucumber team |
| pytest-describe | 3.2.0 | 2026-06-12 | >=3.10 | MIT | describe/it, not Gherkin |
| lettuce | 0.2.23 | 2016-07-26 | unstated | unstated | |
| mamba | 0.11.3 | 2023-11-09 | unstated | MIT | describe/it, not Gherkin |
| pytest-gherkin | 0.1.7 | 2019-07-27 | >=3.6 | MIT | |
| tavern | 3.6.3 | 2026-08-31 | >=3.11 | unstated | YAML API tests, not Gherkin |

pytest-bdd's repository: issue 823 open, "Deprecation warnings with pytest 9.1.1", and pull
request 827 open, "avoid deprecated nodeid argument to `_register_fixture`".

### Smoke run, scratch virtualenv, pytest 9.1.1

One feature file, a scenario outline with three examples and one scenario whose *then* step
runs a hypothesis property; the same file under each candidate.

| Library | Command | Observed |
|---|---|---|
| pytest-bdd 8.1.0 | `pytest -p no:cacheprovider tests` | 4 passed; 16 `PytestRemovedIn10Warning` ("Passing nodeid to `_register_fixture` is deprecated"), which `-W error` turns into 4 failures: the plugin will break on pytest 10 as released; `--gherkin-terminal-reporter` available; hypothesis runs inside a step, its `given` imported under another name because pytest-bdd exports a `given` of its own |
| behave 1.3.3 | `behave --format progress` in a `features/` tree with `steps/` | 4 scenarios, 12 steps passed; its own runner, own `context` object, no pytest fixture, no pytest option |
| pytest-describe 3.2.0 | `pytest tests/test_describe_clamp.py` | passes; nested `describe_`/`it_` functions, no feature file, no Given/When/Then binding |

### First application in 495

`tests/features/decide.feature` and `tests/test_decide_scenarios.py`: four scenarios of
`core/decide.py::assess`, moved from `tests/test_scope_decide.py`, run by the suite with the
project's `pytest -p no:cacheprovider`.

## Decision

Two recommended entries, each with its condition (`docs/decisions/0012`, point 2 as refined).

| Role | Recommended | Condition | Why this one | Set aside |
|---|---|---|---|---|
| bdd | pytest-bdd | default; the project already has pytest tests | a pytest plugin: scenarios are pytest items, steps take pytest fixtures, every other Python entry of the catalogue and 495's pytest options apply unchanged; Gherkin parsed by the official parser; scenario outlines, backgrounds, `target_fixture` for state passed between steps | pytest-bdd-ng: a fork, not run, no measured advantage over the original |
| bdd | behave | the project has no pytest suite, or keeps a standalone `features/` tree with `steps/` | Gherkin done well, the longest-lived Python BDD runner, active repository; nothing to lose where no pytest fixture or plugin is in use | radish: same standalone runner, smaller user base, no advantage measured. pytest-describe, mamba: describe/it naming, not Gherkin. lettuce, pytest-gherkin: last releases 2016 and 2019 |

Why the condition and not one winner: a scenario's steps under behave cannot reach the
pytest-bound entries of the catalogue (mocker, benchmark, limit_memory, hypothesis' plugin,
pytest-cov) nor mutmut's per-test selection, so in a pytest project behave would cost the other
roles; in a project without pytest there is nothing to lose and behave's own runner is the
simpler tool.

Risk recorded with the entry: pytest-bdd 8.1 predates pytest 9 and raises a removal warning
for pytest 10; 495 pins `pytest<10` in its dev group until the plugin's fix ships.

## What a profile can detect

| Role | Marker of the recommended tool |
|---|---|
| bdd | `pytest-bdd` in the dependencies; `.feature` files (already counted as test files by `core/verification.py`); `from pytest_bdd import` in `tests/` |

A project with `.feature` files and `behave` in its dependencies measures the role with the
conditioned entry; it is a conformance proposal only if the project also has pytest tests, in
which case pytest-bdd is the entry the condition selects. The requester may decline.

## Follow-ups

- Other technologies, to study before an entry: Cucumber-JVM (Java / Kotlin), cucumber-js and
  jest-cucumber (JavaScript / TypeScript), cucumber-rs (Rust), godog (Go), shellspec (Shell,
  describe/it with a Gherkin-like reporter).
- Migration of the remaining tests of 495 as they are touched (`docs/etude-harnais-495.md`,
  E51).
