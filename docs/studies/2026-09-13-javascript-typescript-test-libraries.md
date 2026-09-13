# JavaScript / TypeScript test libraries, by role

- Date: 2026-09-13
- Fills: `docs/test-libraries.md`, section JavaScript / TypeScript
- Rule applied: `docs/decisions/0012-tests-use-proven-libraries-from-a-catalogue.md`

One recommended library per catalogue role, chosen among the candidates a Node.js project in
JavaScript or TypeScript would reach for. Every fact below was measured on the date above;
nothing is taken from memory alone.

## Method

1. **Candidates.** For each of the thirteen roles, the libraries the ecosystem uses, including
   the tools the profile already recognises from `package.json` scripts and `tsconfig.json`.
2. **Maintenance and terms.** Latest version, release date, supported Node range and licence,
   read from the npm registry for every candidate. A library whose last release is older than
   three years is not recommended; a library whose service sits behind a vendor account is not
   recommended either.
3. **Smoke run.** Each retained library installed in a scratch project (Node 24.19.0,
   npm 11.17.0, TypeScript 6.0.3, ESM) and run once on a two-function module
   (`clamp(x, lo, hi)`, `add(a, b)`) with three tests. What broke is recorded in the notes.
4. **Second runner version.** Where a tool failed against the runner's newest major, the run
   was repeated against the previous major, so that the notes say which versions work together.

## Facts measured

### Releases, as read on npm

| Library | Version | Released | Node | Licence |
|---|---|---|---|---|
| vitest | 5.0.0 | 2026-09-03 | ^22.12 \|\| ^24 \|\| >=26 | MIT |
| jest | 30.5.1 | 2026-09-01 | ^18.14 \|\| ^20 \|\| ^22 \|\| >=24 | MIT |
| mocha | 12.0.1 | 2026-09-11 | ^20.19 \|\| >=22.12 | MIT |
| @cucumber/cucumber | 13.2.1 | 2026-08-04 | 22 \|\| 24 \|\| >=26 | MIT |
| @amiceli/vitest-cucumber | 8.0.0 | 2026-09-05 | | ISC |
| jest-cucumber | 4.5.0 | 2024-07-25 | | Apache-2.0 |
| fast-check | 4.10.0 | 2026-09-11 | >=12.17 | MIT |
| @fast-check/vitest | 0.5.0 | 2026-09-11 | | MIT |
| @jazzer.js/core | 4.0.0 | 2026-04-15 | >=14 | Apache-2.0 |
| jsfuzz | 1.0.15 | 2021-01-09 | | Apache-2.0 |
| @stryker-mutator/core, vitest-runner, jest-runner | 10.0.0 | 2026-08-14 | >=22 | Apache-2.0 |
| @vitest/coverage-v8, @vitest/coverage-istanbul | 5.0.0 | 2026-09-03 | | MIT |
| c8 | 12.0.0 | 2026-07-14 | ^20.19 \|\| ^22.12 \|\| >=23 | ISC |
| nyc | 18.0.0 | 2026-02-22 | 20 \|\| >=22 | ISC |
| dependency-cruiser | 18.2.0 | 2026-08-10 | ^22 \|\| ^24 \|\| >=26 | MIT |
| eslint-plugin-boundaries | 7.2.0 | 2026-08-09 | >=18.18 | MIT |
| madge | 8.0.0 | 2024-08-05 | >=18 | MIT |
| eslint | 10.10.0 | 2026-09-04 | ^20.19 \|\| ^22.13 \|\| >=24 | MIT |
| typescript-eslint | 8.70.0 | | peer typescript >=4.8.4 <6.1 | MIT |
| @biomejs/biome | 2.5.13 | 2026-09-10 | >=14.21.3 | MIT OR Apache-2.0 |
| oxlint | 1.82.0 | 2026-09-07 | ^20.19 \|\| >=22.12 | MIT |
| prettier | 3.9.6 | 2026-07-21 | >=14 | MIT |
| typescript | 7.0.2 (`latest`), 6.0.3 | 2026-07-08, 2026-04-16 | >=16.20 | Apache-2.0 |
| eslint-plugin-security | 4.0.1 | 2026-06-12 | ^18.18 \|\| ^20.9 \|\| >=21.1 | Apache-2.0 |
| @microsoft/eslint-plugin-sdl | 1.1.0 | 2025-02-18 | >=18 | MIT |
| eslint-plugin-no-unsanitized | 4.1.5 | 2026-02-19 | | MPL-2.0 |
| audit-ci | 7.1.0 | 2024-07-03 | >=16 | Apache-2.0 |
| lockfile-lint | 5.0.1 | 2026-08-13 | >=16 | Apache-2.0 |
| snyk | 1.1307.2 | 2026-09-09 | >=12 | Apache-2.0 (client); service behind a vendor account |
| @stoplight/prism-cli | 5.16.0 | 2026-07-17 | >=24.18 | Apache-2.0 |
| express-openapi-validator | 5.6.2 | 2026-01-20 | | MIT |
| dredd | 14.1.0 | 2021-11-16 | >=10 | MIT |
| jest-openapi, chai-openapi-response-validator | 0.14.2 | 2022-01-03 | | MIT |
| openapi-response-validator | 12.1.3 | 2023-05-24 | | MIT |
| @pact-foundation/pact | 17.1.4 | 2026-09-07 | >=22 | MIT |
| pactum | 3.9.1 | 2026-02-27 | >=10 | MIT |
| tinybench | 6.2.0 | 2026-09-09 | >=20 | MIT |
| mitata | 1.0.34 | 2025-02-04 | | MIT |
| benchmark | 2.1.4 | 2017-03-28 | | MIT |
| autocannon | 8.0.0 | 2024-10-14 | | MIT |
| sinon | 22.1.0 | 2026-07-20 | | BSD-3-Clause |
| msw | 2.15.0 | 2026-07-08 | >=18 | MIT |
| nock | 14.0.17 | 2026-07-30 | | MIT |
| testdouble | 3.20.2 | 2024-03-21 | >=16 | MIT |

TypeScript's `latest` tag is 7.0.2, the native port; typescript-eslint 8.70.0 declares a peer
range that stops at 6.1, so `npm install` of both fails with `ERESOLVE` and the scratch project
pins `typescript@^6` (6.0.3 installed). npm 11.17 blocks install scripts until
`npm approve-scripts` (esbuild's postinstall here).

### Smoke run, scratch project

| Library | What ran | Observed |
|---|---|---|
| vitest 5.0.0 | `vitest run`, three tests including a `test.prop` from @fast-check/vitest | 3 passed in 130 ms; the ESM and TypeScript sources need no transpilation step |
| @fast-check/vitest 0.5.0, fast-check 4.10.0 | `test.prop([fc.integer(), ...])` on `clamp` | passes, the property is a vitest test with its seed reported |
| @vitest/coverage-v8 5.0.0 | `vitest run --coverage` with `json`, `lcov` and `text-summary` reporters | 100 % (6/6 statements); `coverage/coverage-final.json` carries the statement map and hit counts per file, `coverage/lcov.info` the `DA:` line hits; `diff-cover coverage/lcov.info --compare-branch=HEAD` (Python, the Python entry) reported the two lines of a function added after the commit as missed |
| typescript 6.0.3 | `tsc --noEmit` on `tsconfig.json` with `strict` | exit 0 |
| eslint 10.10.0, typescript-eslint, eslint-plugin-security 4.0.1 | flat config with `pluginSecurity.configs.recommended` on a module with `execSync("ls " + cmd)`, `obj[key]`, `new RegExp(s)` | two warnings, `security/detect-object-injection` and `security/detect-non-literal-regexp`; the concatenated `execSync` is not reported; exit 0 on warnings |
| prettier 3.9.6 | `prettier --check src` | reports the file that is not formatted, exit 1 |
| @biomejs/biome 2.5.13 | `biome lint src` | 5 files in 6 ms, one info; lints and formats in one binary |
| dependency-cruiser 18.2.0 | a `forbidden` rule `domain` to `infra` over `src/domain/bad.ts` importing `src/infra/db.ts`, with `tsPreCompilationDeps` | `error domain-not-to-infra: src/domain/bad.ts → src/infra/db.ts`, 1 violation, exit 1 |
| @stryker-mutator/core 10.0.0 with the vitest runner, vitest 5.0.0 | `stryker run`, `perTest` then `off` coverage analysis | 11 mutants, 0 killed, 11 survived, "Ran 0.00 tests per mutant": the runner's per-test filter matches nothing on Vitest 5 (stryker-js issue 6210, open, 2026-09-04) |
| the same, vitest 4.1.11 | `stryker run` | 9 killed, 2 survived (the two `<` to `<=` boundary mutants of `clamp`, equivalent), 81.82 %, 1 test per mutant; the JSON report under `reports/mutation/` |
| @jazzer.js/core 4.0.0 | `jazzer fuzz/parse.fuzz.js --sync -- -max_total_time=20` on a function that throws when its input starts with `x` and holds a comma after position 3 | the crash found in under 20 s, the input written to `./crash-<hash>`; libFuzzer options pass after `--` |
| @cucumber/cucumber 13.2.1 | a feature with three steps written in TypeScript | the `loader: ["tsx"]` configuration fails on Node 24 (`addCustomLoader` error in the ESM hooks); with `NODE_OPTIONS="--import tsx"` and `import: ["features/steps/*.ts"]`, 1 scenario and 3 steps passed |
| @amiceli/vitest-cucumber 8.0.0 | the same feature through `describeFeature(loadFeature(...))` in a vitest test | 3 passed; the feature file is read, the steps are vitest tests; the file must match vitest's `include` |
| tinybench 6.2.0 | `new Bench({ time: 200 })`, one task | `latency.mean` 12.67 ns over 7 891 231 samples, `throughput.mean`; results under `task.result.latency` and `.throughput` in 6.x (`result.samples` is gone) |
| vitest 5.0.0 `bench` | a `bench()` in a `.bench.ts` file | `TypeError: bench is not a function`: the benchmark mode is not exported by `vitest` 5.0.0 |
| sinon 22.1.0, vitest `vi`, msw 2.15.0 | `sinon.stub(o, "f").returns(9)` then `restore()`, `vi.fn().mockReturnValue(3)`, `setupServer(http.get(...))` intercepting `fetch` | 3 passed |
| express-openapi-validator 5.6.2 | the middleware with `validateResponses: true` on an Express 5 route answering `{ id }` where the description requires `name` | the response is rejected with status 500 and a message naming `name` |
| @stoplight/prism-cli 5.16.0 | `prism proxy spec.json http://127.0.0.1:4011 --errors` in front of the same route without the middleware | `GET /items/3` answered 500 with `Response body must have required property 'name'`; framework-agnostic, needs the implementation running |
| npm audit | `npm audit --json` on the scratch project | 2 moderate advisories among the development dependencies; built into npm, no account |

## Decisions, by role

| Role | Recommended | Why this one | Set aside |
|---|---|---|---|
| runner | vitest | runs ESM and TypeScript sources as they are, carries the coverage, property and double entries of this table as plugins or built-ins; a release ten days before the study | jest: maintained, needs a transform for TypeScript and ESM; a project that has a jest suite keeps it, the runner is never a gap. mocha: a runner without coverage or doubles of its own. `node:test`: no fixture, coverage or watch of the others |
| bdd | @cucumber/cucumber | the reference Gherkin runner, scenarios in `.feature` files the requester reads; TypeScript steps through `NODE_OPTIONS="--import tsx"` on Node 24 | @amiceli/vitest-cucumber: works and keeps the steps in vitest, a smaller project (ISC, one maintainer); named in the notes for a project that wants everything under vitest. jest-cucumber: last release 2024-07, jest only |
| property | fast-check | the ecosystem's reference, shrinking, seeded reproduction, `@fast-check/vitest` makes a property a vitest test | none with a user base |
| fuzzing | @jazzer.js/core | libFuzzer for Node.js by Code Intelligence, coverage-guided, found the crash on the smoke run; fast-check alone is not coverage-guided | jsfuzz: last release 2021-01 |
| mutation | @stryker-mutator/core | the only maintained mutation tester of the ecosystem; killed 9 of 11 mutants against vitest 4; the two survivors are equivalent | none; the note says Vitest 5 is not supported by the 10.0.0 runner |
| coverage | @vitest/coverage-v8 | V8's own counters through the runner, `lcov` and `json` reporters listing the executed lines per file, which diff-cover reads for the changed lines | c8: the same V8 counters outside the runner; nyc: instruments the source (istanbul), slower for the same measure; @vitest/coverage-istanbul for a project that needs istanbul's instrumentation |
| architecture | dependency-cruiser | rules over the import graph in a configuration file, TypeScript path resolution, fails with a listing of the violations | eslint-plugin-boundaries: the same rules inside ESLint's run, per file, without the graph; madge: last release 2024-08, cycles and graphs, no rules |
| static | eslint, with prettier | ESLint 10 with typescript-eslint is where the ecosystem's rules are; prettier formats, `--check` fails on an unformatted file | @biomejs/biome: lints and formats in one binary in milliseconds, without ESLint's rule ecosystem and without type-aware rules; a project that has it keeps it. oxlint: lint only, same position |
| types | typescript | `tsc --noEmit` is the type check; typescript-eslint's peer range holds it below 6.1 for now | none |
| security | eslint-plugin-security, npm audit | the SAST rules inside the lint the project already runs; `npm audit` reads the registry's advisory database with no account | snyk: service behind a vendor account. @microsoft/eslint-plugin-sdl: a vendor's rule set. audit-ci: last release 2024-07, a wrapper over `npm audit`. semgrep: cross-language, out of this study |
| contract | @stoplight/prism-cli | `prism proxy --errors` validates every response of the running implementation against the OpenAPI description, whatever the framework; found the missing property on the smoke run | express-openapi-validator: the in-process entry when the project uses Express, measured, kept as the conditional entry. dredd: last release 2021-11. jest-openapi, chai-openapi-response-validator: last release 2022-01. openapi-response-validator: last release 2023-05. @pact-foundation/pact: consumer-driven contracts between services, a different question |
| performance | tinybench | the benchmark engine vitest's `bench` mode wraps, statistics per task (mean, p99, margin of error) in `result.latency`; vitest 5.0.0 does not export `bench`, so the engine is used directly | mitata: last release 2025-02, no statistics on the sample count; benchmark.js: last release 2017; autocannon: load tests a running HTTP service |
| doubles | vi (vitest), with msw | `vi.fn`, `vi.spyOn`, `vi.mock` and fake timers are part of the runner and are undone by `vi.restoreAllMocks`; msw intercepts `fetch` and `http` at the network boundary with handlers | sinon: the same discipline for a project not on vitest; nock: HTTP only, Node's `http` module; testdouble: last release 2024-03 |

## Notes carried into the catalogue

- TypeScript 7.0.2 is npm's `latest`; typescript-eslint 8.70 needs `typescript@<6.1`.
- Stryker 10.0.0's vitest runner kills nothing on Vitest 5.0.0 (issue 6210): pin vitest 4 for
  the mutation run until the runner supports 5.
- cucumber-js with TypeScript steps on Node 24: `NODE_OPTIONS="--import tsx"`, not the
  `loader` option.
- tinybench 6: results under `task.result.latency` and `.throughput`.
- npm 11.17 blocks install scripts until `npm approve-scripts`.

## What a profile can detect

| Role | Marker of the recommended tool |
|---|---|
| runner | `vitest` in the dependencies; `vitest.config.*`, `vite.config.*` with a `test` key not checked; `from "vitest"` in the tests |
| bdd | `@cucumber/cucumber` in the dependencies; `cucumber.js`, `.mjs`, `.cjs`, `.json`, `.yaml` or `.yml` at the root |
| property | `fast-check` or `@fast-check/vitest` in the dependencies; `from "fast-check"` in the tests |
| fuzzing | `@jazzer.js/core` in the dependencies; a `fuzz/` directory; `.fuzz.js` or `.fuzz.ts` files |
| mutation | `@stryker-mutator/core` in the dependencies; `stryker.config.*` or `stryker.conf.*` |
| coverage | `@vitest/coverage-v8` or `@vitest/coverage-istanbul`, `c8`, `nyc` in the dependencies; `.nycrc*`, `.c8rc*` |
| architecture | `dependency-cruiser` in the dependencies; `.dependency-cruiser.*`; `eslint-plugin-boundaries` |
| static | `eslint` in the dependencies; `eslint.config.*`, `.eslintrc*`; `prettier` in the dependencies, `.prettierrc*`; `@biomejs/biome`, `biome.json*` |
| types | `typescript` in the dependencies; `tsconfig.json` |
| security | `eslint-plugin-security` in the dependencies; `npm audit`, `pnpm audit`, `yarn npm audit` or `audit-ci` in a `package.json` script or a CI file |
| contract | `@stoplight/prism-cli` in the dependencies or `prism proxy` in a script or CI file; `express-openapi-validator`, `@pact-foundation/pact`, `pactum` in the dependencies |
| performance | `tinybench`, `mitata`, `benchmark`, `autocannon` in the dependencies; `.bench.ts` or `.bench.js` files |
| doubles | `vi.fn(`, `vi.mock(`, `vi.spyOn(` in the tests; `msw`, `sinon`, `nock`, `testdouble` in the dependencies |

## Follow-ups

- A run of Stryker against Vitest 5 once the runner's per-test filter is fixed, to lift the
  version pin from the notes.
