# Test libraries: the catalogue

One recommended library per technology and per role. Binds 495's own tests and the host projects
495 works on (`docs/decisions/0012-tests-use-proven-libraries-from-a-catalogue.md`).

## Using the catalogue

- Writing a test for 495: take the `recommended` entry for the role and technology. If the cell
  is empty, either bring an entry in (below) or write the check by hand and state in the test's
  docstring that the catalogue has no entry and what was searched.
- A test of a behaviour is a Gherkin scenario run by the `bdd` entry; the other roles keep the
  Given/When/Then shape in their tests' names and bodies
  (`docs/decisions/0013-tests-are-behaviour-scenarios-in-gherkin.md`).
- Profiling a host project: the profile reports, per technology and per role of the table
  below, the tool the project measures it with and what it was recognised from (the role
  coverage, `harness495/core/profile.py`; the markers are those of the studies' "What a profile
  can detect" sections; a technology whose study is not done has no rows). `495 init` and
  `495 profile` then compare the coverage with the entries below and state each gap: a role
  nothing measures, a role measured with another tool than the recommended one, a role
  measured with part of the recommended entry (`harness495/core/catalogue.py`, which mirrors
  the `recommended` entries; `tests/test_catalogue.py` keeps it equal to this document). Only
  the roles marked *proposed to a host project* in the Roles table are compared: those whose
  measure can contradict what the agent produced. A cell with several entries is compared
  with the one whose condition holds in the project. Each gap is a conformance proposal kept
  in `.495/proposals.json` (`harness495/core/proposals.py`), which the requester accepts,
  declines with a reason, or defers through `495 proposals`; an accepted one becomes a change
  run that puts the entry in place with a first test of the role, a declined one is not
  proposed again.
- Specifying a change: the specifier receives this catalogue against the project's coverage
  as a fact (what a test of each role must show, the tool in place, the recommendation where
  nothing measures the role), and a verification names the role it measures. A role the
  project does not measure makes the verification insufficient with the recommendation in its
  rationale, so that the tool comes in through a proposal and not through the change
  (`docs/decisions/0014-a-verification-names-the-catalogue-role-it-measures.md`).
- A study that fills a section lives in `docs/studies/`, named by date and technology, and
  records what was measured; the source column points to it.

## Bringing an entry in

An entry has a status, a source and a date. Statuses:

- `recommended`: admitted by a study, a piece of research, or a retrospective on a host project.
  The source column names it. A cell may hold several `recommended` entries when each states,
  in its notes, the condition under which it is the one to take; the first listed is the
  default, the others apply when their condition holds (a project without a pytest suite takes
  behave, not pytest-bdd).
- `rejected`: examined and set aside; the reason stays so that it is not proposed again.

A library used by 495's own suite counts as a source ("in use in 495 since <date>") once it has
run in the suite for at least one change; it is still listed, not assumed.

## Roles

The last column says whether a gap on the role is stated to a host project: yes when the
role's verdict comes from outside the agent that produced the change, so that it can
contradict the implementation; no when the role serves the writing of tests without holding an
oracle of its own. A role marked no stays in the catalogue for 495's own tests.

| Role | Contract it measures | What the test must show | Proposed to a host project |
|---|---|---|---|
| runner | Produit | planned cases hold, through public interfaces | no: carries the other roles' tests, holds no oracle of its own |
| bdd | Produit | behaviour scenarios in Gherkin (Given/When/Then), readable by the requester, bound to steps and run by the runner | yes: the scenario is approved by the requester before the agent produces |
| property | Domaine | no counter-example to a stated invariant over a generated input range | yes: inputs the agent did not choose |
| fuzzing | Domaine, Sécurité | no crash, hang or unbounded consumption on malformed input | yes: inputs the agent did not choose |
| mutation | Tests | the suite detects a deliberate alteration of the code it covers | yes: a verdict on the agent's own tests |
| coverage | Tests | which changed lines the suite executes | yes: the changed lines no test of the agent reaches |
| architecture | Architecture | forbidden dependencies and layer crossings fail the build | yes: rules the project set, not the agent |
| static | Qualité | lint, formatting, complexity, duplication | yes: rules the project set, not the agent |
| types | API | type contracts hold | yes: contracts a tool checks, not the agent |
| security | Sécurité | SAST findings, secrets, vulnerable dependencies | yes: rules the project set, not the agent |
| contract | API | schemas and API descriptions match the implementation | yes: the API description against the implementation |
| performance | Performance | latency, memory, throughput against a bound | no: a bound only the project can set |
| doubles | Produit | test doubles and fixtures with a known discipline | no: a writing discipline, no verdict |

## Entries

Technologies are those the profile detects (`harness495/core/profile.py`). An empty cell means:
no entry yet; bring one in before writing that kind of test. The roles of a technology's table
are the rows of its role coverage (`tests/test_catalogue.py` keeps the two equal).

### Python

| Role | Library | Status | Source | Notes |
|---|---|---|---|---|
| runner | pytest | recommended | in use in 495 since 2026-09-11 | `-p no:cacheprovider` in host-project fixtures keeps the worktree clean |
| bdd | pytest-bdd | recommended | study 2026-09-13 (`docs/studies/2026-09-13-python-bdd-libraries.md`), in use in 495 since 2026-09-13 | default, and the one to take when the project already has pytest tests: a pytest plugin, so every entry below applies to a step; 8.1.0 measured; `.feature` files under `tests/features/`, `scenarios()` binds them; raises `PytestRemovedIn10Warning` under pytest 9, hence `pytest<10` in the dev group; import hypothesis' `given` under another name |
| bdd | behave | recommended | study 2026-09-13 (bdd) | when the project has no pytest suite, or keeps its scenarios in a standalone `features/` tree with `steps/`: 1.3.3 measured, 4 scenarios and 12 steps passed; its own runner and `context` object, so the pytest-bound entries below (mocker, benchmark, limit_memory, hypothesis plugin) and mutmut's per-test selection do not reach its steps |
| architecture | import-linter | recommended | in use in 495 since 2026-09-13 | contracts in `pyproject.toml`, run by `lint-imports` and `tests/test_architecture.py` |
| static | ruff | recommended | in use in 495 since 2026-09-11 | lint and format |
| types | mypy | recommended | in use in 495 since 2026-09-11 | `strict`, pydantic plugin |
| property | hypothesis | recommended | study 2026-09-13 (`docs/studies/2026-09-13-python-test-libraries.md`) | 6.168.0 measured; a `@given` test exposes `fuzz_one_input`, the fuzzing entry's target |
| fuzzing | atheris | recommended | study 2026-09-13 | 3.1.0 measured; Linux, or a clang built with libFuzzer: Apple clang does not build it; takes a hypothesis test as target |
| mutation | mutmut | recommended | study 2026-09-13 | 3.8.0 measured; `[tool.mutmut] source_paths`, `pytest_add_cli_args_test_selection`; writes `mutants/` at the project root, to be ignored by pytest (`--ignore=mutants`) and by git |
| coverage | coverage.py, with diff-cover | recommended | study 2026-09-13 | 7.16.0 and 10.5.1 measured; `coverage json` lists executed lines per file, `diff-cover --compare-branch` reports the changed lines the suite misses; pytest-cov is coverage.py's pytest integration, not a second engine |
| security | ruff (rules `S`), pip-audit | recommended | study 2026-09-13 | ruff's `S` set is the port of bandit's rules and reported the same findings on 495; `S404` needs `--preview` in ruff 0.16; pip-audit 2.10.1 measured, environment mode needs `pip` in the audited venv; secrets scanning is not language-specific and has no entry here |
| contract | schemathesis | recommended | study 2026-09-13 | 4.27.0 measured; OpenAPI and GraphQL; `schemathesis.openapi.from_asgi` runs the app in-process under pytest |
| performance | pytest-benchmark, with pytest-memray | recommended | study 2026-09-13 | 5.3.0 and 1.10.0 measured; `--benchmark-compare-fail` fails against a saved baseline; `limit_memory` needs the pytest cache provider, so it breaks under `-p no:cacheprovider` |
| doubles | pytest-mock | recommended | study 2026-09-13 | 3.15.1 measured; `mocker` over `unittest.mock`, undone at teardown; respx (httpx) and time-machine (clock) complement it; a scripted fake of a harness-owned interface (`FakeAgent`, `tests/conftest.py`) is a fake, not a check, and stays code |

### JavaScript / TypeScript

| Role | Library | Status | Source | Notes |
|---|---|---|---|---|
| runner | | | | |
| bdd | | | | |
| property | | | | |
| fuzzing | | | | |
| mutation | | | | |
| coverage | | | | |
| architecture | | | | |
| static | | | | |
| types | | | | |
| security | | | | |
| contract | | | | |
| performance | | | | |
| doubles | | | | |

### Rust

| Role | Library | Status | Source | Notes |
|---|---|---|---|---|
| runner | | | | |
| bdd | | | | |
| property | | | | |
| fuzzing | | | | |
| mutation | | | | |
| coverage | | | | |
| architecture | | | | |
| static | | | | |
| security | | | | |
| performance | | | | |

### Go

| Role | Library | Status | Source | Notes |
|---|---|---|---|---|
| runner | | | | |
| bdd | | | | |
| property | | | | |
| fuzzing | | | | |
| mutation | | | | |
| coverage | | | | |
| architecture | | | | |
| static | | | | |
| security | | | | |
| performance | | | | |

### Java / Kotlin

| Role | Library | Status | Source | Notes |
|---|---|---|---|---|
| runner | | | | |
| bdd | | | | |
| property | | | | |
| mutation | | | | |
| coverage | | | | |
| architecture | | | | |
| static | | | | |
| security | | | | |
| contract | | | | |
| performance | | | | |
| doubles | | | | |

### Shell

| Role | Library | Status | Source | Notes |
|---|---|---|---|---|
| runner | | | | |
| bdd | | | | |
| static | | | | |
| security | | | | |

## Rejected

| Technology | Role | Library | Reason | Source |
|---|---|---|---|---|
| Python | bdd | radish-bdd | own runner outside pytest like behave, with a smaller user base and no advantage measured over it | study 2026-09-13 (bdd) |
| Python | bdd | pytest-describe, mamba | describe/it naming, not Given/When/Then; no feature file for the requester to read | study 2026-09-13 (bdd) |
| Python | bdd | lettuce, pytest-gherkin | last releases 2016-07 and 2019-07 | study 2026-09-13 (bdd) |
| Python | property | pytest-quickcheck | last release 2022-11; no shrinking, no example database | study 2026-09-13 |
| Python | fuzzing | pythonfuzz | last release 2019-11 | study 2026-09-13 |
| Python | fuzzing | hypofuzz | proprietary licence (`LicenseRef-HypoFuzz`) | study 2026-09-13 |
| Python | mutation | mutatest | last release 2022-02 | study 2026-09-13 |
| Python | mutation | pytest-mutagen | last release 2020-07 | study 2026-09-13 |
| Python | security | bandit | same findings as ruff's `S` rules on 495, rule for rule and line for line; a second tool for the same measure | study 2026-09-13 |
| Python | security | safety | current vulnerability database served behind a vendor account | study 2026-09-13 |
| Python | contract | dredd | Node.js tool; its Python hooks last released 2018-04 | study 2026-09-13 |
