# Go test libraries, by role

- Date: 2026-09-13
- Fills: `docs/test-libraries.md`, section Go
- Rule applied: `docs/decisions/0012-tests-use-proven-libraries-from-a-catalogue.md`

One recommended library per role of the Go table (runner, bdd, property, fuzzing, mutation,
coverage, architecture, static, security, performance), chosen among the candidates a Go
module would reach for. Every fact below was measured on the date above; nothing is taken
from memory alone.

## Method

1. **Candidates.** For each role, the modules and commands the ecosystem uses, including the
   toolchain's own (`go test`, its `-fuzz`, `-cover` and `-bench` modes, `go vet`), which the
   profile already proposes as commands.
2. **Maintenance and terms.** Latest version and release date, read from the Go module proxy
   (`proxy.golang.org`, `@latest`) for every candidate. A module whose last release is older
   than three years is not recommended; a module with no tagged release is noted as such.
3. **Smoke run.** Go 1.27.1 (darwin/arm64, from the official archive into a scratch
   `GOROOT`) on a sample module (`mathx` with `Clamp`, `Add`, a `ParsePair` that panics on
   an input without a comma; an `internal/domain` package importing `internal/infra`; an
   `insecure` package using `md5` and `exec.Command` with a variable), each tool installed
   with `go install ...@latest` into a scratch `GOPATH`.

## Facts measured

### Releases, as read on the module proxy

| Module | Version | Released |
|---|---|---|
| github.com/stretchr/testify | v1.12.1 | 2026-08-17 |
| github.com/cucumber/godog | v0.16.0 | 2026-07-31 |
| pgregory.net/rapid | v1.3.0 | 2026-03-30 |
| github.com/leanovate/gopter | v0.2.11 | 2024-04-03 |
| github.com/go-gremlins/gremlins | v0.5.1 | 2024-05-14 |
| github.com/zimmski/go-mutesting | pseudo-version | 2021-06-10 |
| github.com/avito-tech/go-mutesting | pseudo-version | 2025-12-26 |
| github.com/golangci/golangci-lint/v2 | v2.13.2 | 2026-08-27 |
| honnef.co/go/tools (staticcheck) | v0.8.1 | 2026-08-21 |
| github.com/mgechev/revive | v1.16.0 | 2026-08-21 |
| github.com/securego/gosec/v2 | v2.29.0 | 2026-08-25 |
| golang.org/x/vuln (govulncheck) | v1.8.0 | 2026-09-08 |
| github.com/fe3dback/go-arch-lint | v1.19.0 | 2026-09-07 |
| github.com/arch-go/arch-go | v1.7.0 | 2025-02-25 |
| github.com/OpenPeeDeeP/depguard/v2 | v2.2.1 | 2025-03-06 |
| golang.org/x/perf (benchstat) | pseudo-version | 2026-09-08 |
| github.com/boumenot/gocover-cobertura | v1.5.0 | 2026-05-15 |
| github.com/axw/gocov | v1.2.1 | 2024-10-11 |
| go.uber.org/mock | v0.6.0 | 2025-08-18 |
| github.com/vektra/mockery/v3 | v3.8.0 | 2026-09-09 |
| github.com/onsi/ginkgo/v2 | v2.32.2 | 2026-09-09 |
| gotest.tools/gotestsum | v1.13.0 | 2025-09-11 |
| github.com/dvyukov/go-fuzz | pseudo-version | 2024-09-24 |
| github.com/google/gofuzz | v1.2.0 | 2020-08-04 |
| github.com/pact-foundation/pact-go/v2 | v2.7.1 | 2026-08-26 |
| github.com/getkin/kin-openapi | v0.149.0 | 2026-08-28 |
| github.com/anchore/grype | v0.118.0 | 2026-08-27 |

### Smoke run, scratch module

| Tool | What ran | Observed |
|---|---|---|
| go test, testify 1.12.1, rapid 1.3.0 | `go test ./...` over three testify tests and one `rapid.Check` property | ok, 0.3 s; `go test -json` gives one event per test for a machine reader |
| godog 0.16.0 | a `godog.TestSuite` with `TestingT: t` in a `_test.go` next to the feature file | the scenario runs under `go test`, `progress` format, ok |
| go test -fuzz | `go test ./mathx -run=^$ -fuzz=FuzzParsePair -fuzztime=10s` | the panic found before the first second, the input written to `testdata/fuzz/FuzzParsePair/<hash>`; the plain `go test` then fails on that input as a regression test until the code is fixed or the file removed, which broke the coverage and mutation runs below until it was removed |
| go test -bench, benchstat | two runs of `-bench=. -count=3 -benchtime=200ms`, `benchstat old.txt new.txt` | `Clamp-16 0.2514n ± ∞`, `~ (p=1.000 n=3)`; benchstat asks for at least 6 samples for a confidence interval and 4 to detect a difference |
| go test -cover, gocover-cobertura 1.5.0 | `-coverprofile=cover.out`, `gocover-cobertura < cover.out > cobertura.xml` | 100 % of statements, `mode: set` blocks; the Cobertura file lists per-line hits (`mathx.go` lines 6 to 15 hit once), the format diff-cover reads for the changed lines |
| go vet | `go vet ./...` | exit 0 on the sample |
| golangci-lint 2.13.2 | `.golangci.yml` version 2 enabling gosec, depguard, gocognit, staticcheck, with a depguard rule for `internal/domain` | 4 issues: the depguard violation (`domain must not import infra`), G501 (md5 import), G204 (subprocess with variable), G401 (weak primitive) |
| gosec 2.29.0 | `gosec -quiet ./...` | the same three findings with CWE ids, confidence and severity, exit 1 |
| govulncheck 1.8.0 | `govulncheck ./...` | "No vulnerabilities found"; call-graph based, no account |
| staticcheck 0.8.1 | `staticcheck ./...` | exit 0 on the sample |
| go-arch-lint 1.19.0 | `.go-arch-lint.yml` version 3 with `domain` and `infra` components | a component listed under `deps` without `mayDependOn`, `canUse` or a flag is a configuration error; with `infra: { anyProjectDeps: true }` and `domain` absent from `deps`, the violation is reported ("Component domain shouldn't depend on .../internal/infra") with a notice per file not attached to a component, 5 notices |
| gremlins 0.5.1 | `gremlins unleash ./mathx`, then with `--timeout-coefficient 20` | with the default timeout every mutant of a 0.3 s suite is TIMED OUT (6 of 6, in 643 ms); with the coefficient, 3 killed, 1 lived, 2 timed out, 75 %; `--dry-run` lists the 6 runnable mutants |
| go-mutesting (avito fork) | `go-mutesting ./mathx` | 8 mutants, score 0.375 (3 caught); the fork has no tagged release, the upstream's last commit is 2021-06 |
| mockgen (go.uber.org/mock 0.6.0) | `go install`, `mockgen -version` | installs; not run against an interface, the table has no doubles row |

## Decisions, by role

| Role | Recommended | Why this one | Set aside |
|---|---|---|---|
| runner | go test | the toolchain's runner, `-json` for a machine reader, the fuzzing, coverage and benchmark modes are its flags; testify's assertions ride on it | ginkgo: a describe/it runner of its own; gotestsum: a formatter over `go test -json` |
| bdd | godog | the Cucumber project's Go implementation, `.feature` files the requester reads, runs under `go test` through `TestingT` | none other with a user base |
| property | rapid | shrinking, generators typed by the value drawn, a release six months before the study | gopter: last release 2024-04, a heavier API; `testing/quick`: frozen by the Go team, no shrinking |
| fuzzing | go test -fuzz | native since Go 1.18, coverage-guided, found the panic on the smoke run and keeps the crashing input as a regression test | go-fuzz: the pre-1.18 tool, pseudo-versions only; gofuzz: last release 2020-08, fills structures at random without guidance |
| mutation | gremlins | the one Go mutation tester with tagged releases and a configuration file; killed 3 of 4 reachable mutants once its timeout was scaled | go-mutesting: no tagged release, upstream last committed in 2021 |
| coverage | go test -cover, with gocover-cobertura | the toolchain's profile, converted to Cobertura with per-line hits, which diff-cover reads for the changed lines | gocov: last release 2024-10, a JSON converter for the same profile |
| architecture | go-arch-lint | a components-and-dependencies file over the packages, fails on a crossing with the file and line | depguard: import deny lists per path inside golangci-lint, the entry to take when the project already runs it, measured; arch-go: last release 2025-02, not run |
| static | golangci-lint | runs staticcheck, gofmt, revive, gocognit and the rest under one configuration, the ecosystem's convention | staticcheck alone: one of the linters golangci-lint runs; go vet: the toolchain's minimum, already a detected command |
| security | gosec, govulncheck | gosec is the Go SAST (CWE-tagged findings, also runnable inside golangci-lint); govulncheck is the Go team's checker over the Go vulnerability database, reporting only reachable calls, no account | grype: scans images and lockfiles across ecosystems, out of this study |
| performance | go test -bench, with benchstat | the toolchain's benchmarks and the Go team's comparison tool, which is the base-versus-change comparison 495 makes and states its own confidence | none |

## Notes carried into the catalogue

- A fuzz crasher under `testdata/fuzz/` makes `go test` fail until the code is fixed: it is
  the regression test the fuzzer wrote.
- gremlins needs `--timeout-coefficient` on a fast suite; the default marks every mutant as
  timed out.
- benchstat wants at least 4 samples (`-count=4`) to detect a difference, 6 for a confidence
  interval.
- go-arch-lint: a component named under `deps` needs `mayDependOn`, `canUse` or a flag.

## What a profile can detect

| Role | Marker of the recommended tool |
|---|---|
| runner | `go.mod` (go test); `github.com/onsi/ginkgo` in `go.mod` (ginkgo) |
| bdd | `github.com/cucumber/godog` in `go.mod`; `.feature` files |
| property | `pgregory.net/rapid` in `go.mod`; `github.com/leanovate/gopter`; `testing/quick` imported in a test |
| fuzzing | `func Fuzz` in a `_test.go`; `testdata/fuzz/` |
| mutation | `.gremlins.yaml`, `gremlins` in a CI file; `go-mutesting` in a CI file |
| coverage | `-coverprofile` in a CI file or Makefile; `gocover-cobertura` in a CI file |
| architecture | `.go-arch-lint.yml`; `depguard` in the golangci-lint configuration; `arch-go.yml` |
| static | `.golangci.yml`, `.golangci.yaml`, `.golangci.toml`, `golangci-lint` in a CI file; `staticcheck.conf`, `staticcheck` in a CI file; `revive.toml` |
| security | `gosec` in the golangci-lint configuration or a CI file; `govulncheck` in a CI file |
| performance | `func Benchmark` in a `_test.go`; `benchstat` in a CI file |

## Follow-ups

- A doubles row for Go (go.uber.org/mock, mockery) if the table gains one; the catalogue's Go
  table has none today.
