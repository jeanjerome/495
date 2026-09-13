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
  coverage, `harness495/core/coverage.py`; the markers are those of the studies' "What a profile
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
  rationale, so that the tool comes in through a proposal and not through the change; a
  role whose proposal the requester declined is shown as such with the reason, and the
  specifier does not call for it
  (`docs/decisions/0014-a-verification-names-the-catalogue-role-it-measures.md`).
- A study that fills a section lives in `docs/studies/`, named by date and technology, and
  records what was measured; the source column points to it.
- Closing a run on a host project: `495 retro <run-id>` reads back what the run showed about
  each tool that measured a role (`harness495/core/retro.py`): proven when its report
  differed with and without the change or contradicted the agent, faulty when it timed out,
  failed identically on both versions, failed before any change too or had its command
  replaced by the requester, inconclusive otherwise. It prints the row below that each proven
  or faulty tool yields, with `retrospective <date> (<project>, run <id>)` as source, and
  keeps the document under the run (`retrospective.json`). The row is pasted here by hand
  once read; the command never writes this file
  (`docs/decisions/0015-a-retrospective-states-what-each-tool-showed.md`).

## Bringing an entry in

An entry has a status, a source and a date. Statuses:

- `recommended`: admitted by a study, a piece of research, or a retrospective on a host project
  (`495 retro`, whose proven tools yield the row). The source column names it. A cell may hold several `recommended` entries when each states,
  in its notes, the condition under which it is the one to take; the first listed is the
  default, the others apply when their condition holds (a project without a pytest suite takes
  behave, not pytest-bdd).
- `rejected`: examined and set aside; the reason stays so that it is not proposed again. A
  tool a retrospective found faulty yields a row for the Rejected table, its reason the
  measurements that failed outside the change's reach.

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
| runner | vitest | recommended | study 2026-09-13 (`docs/studies/2026-09-13-javascript-typescript-test-libraries.md`) | 5.0.0 measured; runs ESM and TypeScript sources as they are; carries the coverage, property and doubles entries below |
| bdd | @cucumber/cucumber | recommended | study 2026-09-13 (js) | 13.2.1 measured; TypeScript steps on Node 24 through `NODE_OPTIONS="--import tsx"`, the `loader` option fails there; @amiceli/vitest-cucumber runs the same `.feature` as vitest tests for a project that wants everything under vitest |
| property | fast-check | recommended | study 2026-09-13 (js) | 4.10.0 measured with @fast-check/vitest 0.5.0, whose `test.prop` makes a property a vitest test |
| fuzzing | @jazzer.js/core | recommended | study 2026-09-13 (js) | 4.0.0 measured; libFuzzer for Node.js, coverage-guided, `jazzer <target> --sync -- -max_total_time=20`, the crashing input written to `./crash-<hash>` |
| mutation | @stryker-mutator/core | recommended | study 2026-09-13 (js) | 10.0.0 measured with its vitest runner: 9 of 11 mutants killed on vitest 4.1.11, none on vitest 5.0.0 (issue 6210, the per-test filter matches nothing); pin vitest 4 for the mutation run until the runner supports 5; `stryker.config.json`, report under `reports/mutation/` |
| coverage | @vitest/coverage-v8 | recommended | study 2026-09-13 (js) | 5.0.0 measured; `lcov` and `json` reporters list the executed lines per file; `diff-cover coverage/lcov.info --compare-branch` (the Python entry) reports the changed lines the suite misses; c8 reads the same V8 counters outside the runner |
| architecture | dependency-cruiser | recommended | study 2026-09-13 (js) | 18.2.0 measured; `forbidden` rules in `.dependency-cruiser.cjs`, `tsPreCompilationDeps` for TypeScript, exit 1 with the violations listed |
| static | eslint, with prettier | recommended | study 2026-09-13 (js) | 10.10.0 and 3.9.6 measured; flat config with typescript-eslint, whose peer range needs `typescript@<6.1`; `prettier --check` fails on an unformatted file; @biomejs/biome lints and formats in one binary for a project that has it |
| types | typescript | recommended | study 2026-09-13 (js), in use in 495's profile since 2026-09-12 | 6.0.3 measured, `tsc --noEmit`; 7.0.2 is npm's `latest` and typescript-eslint 8.70 does not accept it yet |
| security | eslint-plugin-security, npm audit | recommended | study 2026-09-13 (js) | 4.0.1 measured, `configs.recommended` in the flat config reports object injection and non-literal RegExp as warnings; `npm audit --json` reads the registry's advisories with no account |
| contract | @stoplight/prism-cli | recommended | study 2026-09-13 (js) | 5.16.0 measured; `prism proxy <spec> <url> --errors` answers 500 with the violation for a response that breaks the description, whatever the framework; needs the implementation running |
| contract | express-openapi-validator | recommended | study 2026-09-13 (js) | when the project uses Express: 5.6.2 measured, the middleware with `validateResponses: true` rejects the response in-process, inside a vitest test |
| performance | tinybench | recommended | study 2026-09-13 (js) | 6.2.0 measured; the engine vitest's `bench` mode wraps, results under `task.result.latency` and `.throughput`; vitest 5.0.0 does not export `bench`, so the engine is used directly |
| doubles | vi (vitest), with msw | recommended | study 2026-09-13 (js) | vitest 5.0.0 and msw 2.15.0 measured; `vi.fn`, `vi.spyOn`, `vi.mock`, fake timers, undone by `vi.restoreAllMocks`; msw intercepts `fetch` at the network boundary; sinon for a project not on vitest |

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
| runner | bats | recommended | study 2026-09-13 (`docs/studies/2026-09-13-shell-test-libraries.md`) | bats-core 1.14.0, npm `bats` 1.13.0 measured; `run` captures status and output, `--formatter tap`; assertions from bats-assert and bats-support |
| bdd | cucumber (Ruby), with aruba | recommended | study 2026-09-13 (shell) | no Gherkin runner written in shell has a user base, so the runner is the Cucumber project's own library for command-line programs: cucumber 11.1.1 and aruba 2.4.1 measured, running a command, its output and its exit status are built-in steps and the scenario carries no step code; `GEM_PATH` needs the default gems; `--publish-quiet` |
| static | shellcheck, with shfmt | recommended | study 2026-09-13 (shell), in use in 495's profile since 2026-09-12 | 0.11.0 and 3.13.1 measured; `-S warning` chooses the failing severity, `-f json`; shfmt reads its `.editorconfig` keys and `-d` prints the diff |
| security | shellcheck (`-S warning`), gitleaks | recommended | study 2026-09-13 (shell) | shellcheck's warnings are the analysis for injection through unquoted expansions, `rm -rf` on an expansion and `eval`; gitleaks 8.30.1 measured for committed secrets, `dir .` with `--report-format json`, allowlists the documentation example keys; shell has no dependency manifest, so no vulnerable-dependency check |

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
| Shell | runner | shellspec | last release 2021-01; a describe/it DSL of its own | study 2026-09-13 (shell) |
| Shell | runner | shunit2 | last release 2020-03 | study 2026-09-13 (shell) |
| Shell | runner | bashunit | active and recent, xUnit style; small user base, no advantage measured over bats | study 2026-09-13 (shell) |
| Shell | bdd | shellkin, g4b, shellot | Gherkin runners written in shell without a user base (5, 2 and 0 stars) | study 2026-09-13 (shell) |
| Shell | static | shellharden | rewrites quoting, a fixer rather than a checker, within shellcheck's scope | study 2026-09-13 (shell) |
| Shell | security | trufflehog | AGPL-3.0; verifies secrets against the providers online | study 2026-09-13 (shell) |
| JavaScript / TypeScript | bdd | jest-cucumber | last release 2024-07; jest only | study 2026-09-13 (js) |
| JavaScript / TypeScript | fuzzing | jsfuzz | last release 2021-01 | study 2026-09-13 (js) |
| JavaScript / TypeScript | coverage | nyc | instruments the source for the measure V8 gives through @vitest/coverage-v8 or c8 | study 2026-09-13 (js) |
| JavaScript / TypeScript | architecture | madge | last release 2024-08; cycles and graphs, no rules | study 2026-09-13 (js) |
| JavaScript / TypeScript | security | snyk | service behind a vendor account | study 2026-09-13 (js) |
| JavaScript / TypeScript | security | audit-ci | last release 2024-07; a wrapper over `npm audit` | study 2026-09-13 (js) |
| JavaScript / TypeScript | contract | dredd | last release 2021-11 | study 2026-09-13 (js) |
| JavaScript / TypeScript | contract | jest-openapi, chai-openapi-response-validator, openapi-response-validator | last releases 2022-01 and 2023-05 | study 2026-09-13 (js) |
| JavaScript / TypeScript | contract | @pact-foundation/pact | consumer-driven contracts between services, a different question than the description against the implementation | study 2026-09-13 (js) |
| JavaScript / TypeScript | performance | benchmark | last release 2017-03 | study 2026-09-13 (js) |
| JavaScript / TypeScript | performance | mitata | last release 2025-02; no statistics on the sample count | study 2026-09-13 (js) |
| JavaScript / TypeScript | doubles | testdouble | last release 2024-03 | study 2026-09-13 (js) |
