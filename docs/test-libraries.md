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
| runner | cargo test | recommended | study 2026-09-13 (`docs/studies/2026-09-13-rust-test-libraries.md`) | 1.98.0 measured; runs the property, bdd and doubles entries as test targets; cargo-nextest runs one process per test but cannot list a `harness = false` target, so the cucumber target is excluded by expression |
| bdd | cucumber | recommended | study 2026-09-13 (rust) | 0.23.0 measured (MSRV 1.88); `.feature` files, steps as attributed functions, a `harness = false` test target run under an executor |
| property | proptest | recommended | study 2026-09-13 (rust) | 1.11.0 measured; strategies with shrinking, failing cases kept in `proptest-regressions/` |
| fuzzing | cargo-fuzz | recommended | study 2026-09-13 (rust) | 0.13.2 measured; libFuzzer through `libfuzzer-sys`, `cargo fuzz init` writes `fuzz/`; builds on a nightly toolchain only (`-Zsanitizer`), measured on stable |
| mutation | cargo-mutants | recommended | study 2026-09-13 (rust) | 27.1.0 measured (MSRV 1.88); 26 mutants in 63 s on the sample, `mutants.out/` with `caught.txt` and `missed.txt`, to be ignored by git; `--in-place` excludes `--jobs` |
| coverage | cargo-llvm-cov | recommended | study 2026-09-13 (rust) | 0.9.1 measured; `--json` and `--lcov` list the executed lines per file; needs `llvm-tools-preview` of the compiling toolchain, or `LLVM_COV` and `LLVM_PROFDATA` from the LLVM release rustc was built with (Homebrew rustc 1.98 with `llvm@22`) |
| architecture | cargo-deny (`[bans]` with `wrappers`) | recommended | study 2026-09-13 (rust) | 0.20.2 measured; a crate banned except through named wrapper crates is a layer rule between the crates of a workspace, `cargo deny check bans` fails on it; module-level rules inside one crate have no tool |
| static | clippy, with rustfmt | recommended | study 2026-09-13 (rust), in use in 495's profile since 2026-09-12 | 1.98 measured; `cargo clippy --all-targets -- -D warnings`, `cargo fmt --check` |
| security | cargo-deny | recommended | study 2026-09-13 (rust) | 0.20.2 measured; `check advisories` reads the RustSec database, `check licenses` fails on an allowed licence the tree does not use and on a crate without a `license` field; the same `deny.toml` as the architecture entry |
| security | cargo-audit | recommended | study 2026-09-13 (rust) | when the project already runs cargo audit: 0.22.2 measured, 1243 advisories of the same RustSec database, `Cargo.lock` scanned |
| performance | criterion | recommended | study 2026-09-13 (rust) | 0.8.2 measured; statistics per benchmark, `target/criterion/<name>/new/estimates.json`, the previous run kept as the baseline |

### Go

| Role | Library | Status | Source | Notes |
|---|---|---|---|---|
| runner | go test | recommended | study 2026-09-13 (`docs/studies/2026-09-13-go-test-libraries.md`), in use in 495's profile since 2026-09-12 | Go 1.27.1 measured; `-json` for a machine reader; testify 1.12.1 for the assertions |
| bdd | godog | recommended | study 2026-09-13 (go) | 0.16.0 measured; a `godog.TestSuite` with `TestingT: t` runs the `.feature` files under `go test` |
| property | rapid | recommended | study 2026-09-13 (go) | 1.3.0 measured; `rapid.Check`, generators typed by the value drawn, shrinking |
| fuzzing | go test -fuzz | recommended | study 2026-09-13 (go) | native since Go 1.18, measured on 1.27.1; `-run=^$ -fuzz=<name> -fuzztime=10s`; a crashing input is written under `testdata/fuzz/` and fails the plain `go test` until the code is fixed |
| mutation | gremlins | recommended | study 2026-09-13 (go) | 0.5.1 measured; the default timeout marks every mutant of a fast suite as timed out, `--timeout-coefficient 20` gave 3 killed and 1 lived on the sample; `.gremlins.yaml` |
| coverage | go test -cover, with gocover-cobertura | recommended | study 2026-09-13 (go) | 1.27.1 and 1.5.0 measured; `-coverprofile=cover.out`, converted to Cobertura with per-line hits, which `diff-cover --compare-branch` reads for the changed lines |
| architecture | go-arch-lint | recommended | study 2026-09-13 (go) | 1.19.0 measured; `.go-arch-lint.yml` version 3, components and `deps`, a crossing reported with file and line; a component under `deps` needs `mayDependOn`, `canUse` or a flag |
| architecture | depguard | recommended | study 2026-09-13 (go) | when the project already runs golangci-lint: 2.2.1 measured through golangci-lint 2.13.2, import deny lists per path in `.golangci.yml` |
| static | golangci-lint | recommended | study 2026-09-13 (go) | 2.13.2 measured; runs staticcheck, gofmt, revive, gocognit and the rest under `.golangci.yml` version 2 |
| security | gosec, govulncheck | recommended | study 2026-09-13 (go) | 2.29.0 and 1.8.0 measured; gosec reports CWE-tagged findings (G204, G401, G501 on the sample), also as a golangci-lint linter; govulncheck reads the Go vulnerability database and reports reachable calls only, no account |
| performance | go test -bench, with benchstat | recommended | study 2026-09-13 (go) | 1.27.1 measured with benchstat of 2026-09-08; `-bench=. -count=4` at least for benchstat to detect a difference, 6 for a confidence interval |

### Java / Kotlin

| Role | Library | Status | Source | Notes |
|---|---|---|---|---|
| runner | junit-jupiter | recommended | study 2026-09-13 (`docs/studies/2026-09-13-java-kotlin-test-libraries.md`) | JUnit 6.1.3 measured with surefire 3.6.0; the platform every other entry runs on |
| runner | kotest | recommended | study 2026-09-13 (jvm) | when the project is written in Kotlin: 6.2.5 measured, its own specs on the JUnit platform |
| bdd | cucumber-jvm | recommended | study 2026-09-13 (jvm) | cucumber-java and cucumber-junit-platform-engine 7.34.8 measured; one `@Suite @IncludeEngines("cucumber")` class runs the `.feature` files under `src/test/resources`; kotest's `BehaviorSpec` is code, not a feature file |
| property | jqwik | recommended | study 2026-09-13 (jvm) | 1.10.1 measured; `@Property` with `@ForAll` and constraints, 1000 tries |
| property | kotest-property | recommended | study 2026-09-13 (jvm) | when the project runs kotest: 6.2.5 measured, `forAll` with `Arb` generators inside the specs |
| mutation | pitest | recommended | study 2026-09-13 (jvm) | 1.30.0 measured with pitest-junit5-plugin 1.2.3; `mutationCoverage`, `mutations.xml` under `target/pit-reports/`; bytecode mutators, Kotlin included |
| coverage | jacoco | recommended | study 2026-09-13 (jvm) | 0.8.15 measured; `prepare-agent` and `report`, XML with per-line counts, which `diff-cover --compare-branch` reads for the changed lines |
| coverage | kover | recommended | study 2026-09-13 (jvm) | when the project is written in Kotlin and built with Gradle: 0.9.9 measured, `koverXmlReport` with per-line counts |
| architecture | archunit | recommended | study 2026-09-13 (jvm) | 1.5.0 measured; rules as JUnit tests over the bytecode, the violation names caller, callee and line; a compile-time constant is inlined and leaves no dependency to see |
| static | checkstyle, with PMD | recommended | study 2026-09-13 (jvm) | 14.1.0 and PMD 7.17.0 (maven-pmd-plugin 3.28.0) measured; checkstyle for the style rules, PMD for complexity and its CPD for duplication (`-DminimumTokens`), build failure on violations |
| static | detekt, with ktlint | recommended | study 2026-09-13 (jvm) | when the project is written in Kotlin: detekt 1.23.8 and ktlint through org.jlleitschuh.gradle.ktlint 13.1.0 measured |
| security | spotbugs (findsecbugs), OWASP dependency-check | recommended | study 2026-09-13 (jvm) | spotbugs 4.10.4 with findsecbugs 1.14.0 measured (command injection, weak digest); dependency-check 13.0.0 needs an NVD API key, free from NIST, and fails its update without one |
| contract | swagger-request-validator | recommended | study 2026-09-13 (jvm) | 3.0.0 measured; a request and response pair validated against the OpenAPI description in-process; adapters for RestAssured, MockMvc, WireMock and Spring |
| performance | jmh | recommended | study 2026-09-13 (jvm) | 1.37 measured; the last release is three years and one month old, the JDK project's repository is active, the study states the exception; JDK 23 and later need `-proc:full` for its annotation processor; kotlinx-benchmark wraps it for Kotlin |
| doubles | mockito | recommended | study 2026-09-13 (jvm) | 5.23.0 measured; final classes mock by default since 5; wiremock for HTTP doubles |
| doubles | mockk | recommended | study 2026-09-13 (jvm) | when the project is written in Kotlin: 1.14.11 measured, `every { } returns` |

### Shell

| Role | Library | Status | Source | Notes |
|---|---|---|---|---|
| runner | bats | recommended | study 2026-09-13 (`docs/studies/2026-09-13-shell-test-libraries.md`) | bats-core 1.14.0, npm `bats` 1.13.0 measured; `run` captures status and output, `--formatter tap`; assertions from bats-assert and bats-support |
| runner | shellspec | recommended | study 2026-09-13 (shell) | when the project keeps its specs in shellspec (`.shellspec`, `spec/*_spec.sh`), or measures coverage, which goes through it: 0.28.1 measured (released 2021-01, the repository last moved 2024-09), runs under any POSIX shell; `When run source` runs the script in the shell kcov traces, `When run script` forks one it does not; a Describe/It DSL of its own, not Gherkin, so it holds no bdd row |
| bdd | cucumber (Ruby), with aruba | recommended | study 2026-09-13 (shell) | no Gherkin runner written in shell has a user base, so the runner is the Cucumber project's own library for command-line programs: cucumber 11.1.1 and aruba 2.4.1 measured, running a command, its output and its exit status are built-in steps and the scenario carries no step code; `GEM_PATH` needs the default gems; `--publish-quiet` |
| coverage | kcov (`shellspec --kcov`) | recommended | study 2026-09-13 (shell) | kcov 43 measured under shellspec 0.28.1: `coverage/*/cobertura.xml` with per-line hits, which `diff-cover --compare-branch` reads for the changed lines, plus `coverage.json` and `sonarqube.xml`; the lines are reached from `When run source` and `When call` only, `When run script` reports none; `ulimit -n 1024` before the run on macOS (kcov puts the trace descriptor in a `select()` set, so a descriptor above 1023 fails the exchange); `--kcov-options --include-path=<scripts dir>` keeps the report to the project's scripts, `--exclude-region=KCOV_EXCL_START:KCOV_EXCL_STOP` for an embedded program; bats under kcov did not finish |
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
| Shell | runner | shunit2 | last release 2020-03 | study 2026-09-13 (shell) |
| Shell | runner | bashunit | active and recent, xUnit style; small user base, no advantage measured over bats | study 2026-09-13 (shell) |
| Shell | bdd | shellkin, g4b, shellot | Gherkin runners written in shell without a user base (5, 2 and 0 stars) | study 2026-09-13 (shell) |
| Shell | static | shellharden | rewrites quoting, a fixer rather than a checker, within shellcheck's scope | study 2026-09-13 (shell) |
| Shell | security | trufflehog | AGPL-3.0; verifies secrets against the providers online | study 2026-09-13 (shell) |
| Shell | coverage | bashcov | 4.0.0 measured: the script's lines reported in 4 runs out of 8 over bats and in none over shellspec or a `bash -c` wrapper, the trace descriptor being lost to the child shells | study 2026-09-13 (shell) |
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
| Rust | property | quickcheck | works; generation from `Arbitrary` without proptest's strategies, no advantage measured | study 2026-09-13 (rust) |
| Rust | fuzzing | afl, bolero | not run; afl needs an AFL++ build, bolero fronts the same engines and needs nightly for libfuzzer too | study 2026-09-13 (rust) |
| Rust | mutation | mutagen | last release 2018-10 | study 2026-09-13 (rust) |
| Rust | coverage | cargo-tarpaulin | not run; a second engine for the measure cargo-llvm-cov takes from rustc's instrumentation | study 2026-09-13 (rust) |
| Rust | architecture | cargo-modules | MPL-2.0; draws the module graph and checks cycles, no rules | study 2026-09-13 (rust) |
| Rust | architecture | cargo-arch | last release 2022-05 | study 2026-09-13 (rust) |
| Rust | security | cargo-geiger | counts `unsafe`, no verdict | study 2026-09-13 (rust) |
| Rust | performance | divan | no baseline comparison between runs | study 2026-09-13 (rust) |
| Rust | performance | iai-callgrind | instruction counts under valgrind, Linux | study 2026-09-13 (rust) |
| Go | runner | ginkgo | a describe/it runner of its own | study 2026-09-13 (go) |
| Go | property | gopter | last release 2024-04; a heavier API than rapid's | study 2026-09-13 (go) |
| Go | property | testing/quick | frozen by the Go team; no shrinking | study 2026-09-13 (go) |
| Go | fuzzing | go-fuzz | the pre-1.18 tool, pseudo-versions only | study 2026-09-13 (go) |
| Go | fuzzing | gofuzz | last release 2020-08; random filling without guidance | study 2026-09-13 (go) |
| Go | mutation | go-mutesting | no tagged release; the upstream's last commit is 2021-06 | study 2026-09-13 (go) |
| Go | coverage | gocov | last release 2024-10; a JSON converter for the same profile | study 2026-09-13 (go) |
| Go | architecture | arch-go | last release 2025-02; not run | study 2026-09-13 (go) |
| Java / Kotlin | runner | testng, spock | runners of their own; a project that has one keeps it | study 2026-09-13 (jvm) |
| Java / Kotlin | property | quicktheories | last release 2019-03 | study 2026-09-13 (jvm) |
| Java / Kotlin | architecture | konsist | `Project directory not found` on the smoke run under Gradle 9.7 with Kotlin 2.4 and 2.2; not run to a verdict | study 2026-09-13 (jvm) |
| Java / Kotlin | static | error-prone | compiler-time bug patterns, a complement to the lint, not the lint | study 2026-09-13 (jvm) |
| Java / Kotlin | contract | spring-cloud-contract | Spring only | study 2026-09-13 (jvm) |
| Java / Kotlin | contract | pact-jvm | consumer-driven contracts between services, a different question than the description against the implementation | study 2026-09-13 (jvm) |
| Java / Kotlin | contract | openapi4j | last release 2021-03 | study 2026-09-13 (jvm) |
