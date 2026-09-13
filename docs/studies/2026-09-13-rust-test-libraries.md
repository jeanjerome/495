# Rust test libraries, by role

- Date: 2026-09-13
- Fills: `docs/test-libraries.md`, section Rust
- Rule applied: `docs/decisions/0012-tests-use-proven-libraries-from-a-catalogue.md`

One recommended library per role of the Rust table (runner, bdd, property, fuzzing, mutation,
coverage, architecture, static, security, performance), chosen among the candidates a Rust
project would reach for. Every fact below was measured on the date above; nothing is taken
from memory alone.

## Method

1. **Candidates.** For each role, the crates and cargo subcommands the ecosystem uses,
   including the ones the profile already proposes as commands (`cargo test`, `cargo clippy`).
2. **Maintenance and terms.** Latest stable version, release date, declared minimum Rust
   version, licence and download count, read from the crates.io API for every candidate. A
   crate whose last release is older than three years is not recommended.
3. **Smoke run.** Each retained tool installed with `cargo install --locked` into a scratch
   root (Homebrew cargo and rustc 1.98.0, LLVM 22.1.8) and run once on a sample crate
   (`clamp`, `add`, `parse_pair`, a `Clock` trait) with four tests, one feature file, one
   benchmark. What broke is recorded in the notes.

## Facts measured

### Releases, as read on crates.io

| Crate | Version | Released | MSRV | Licence | Downloads |
|---|---|---|---|---|---|
| proptest | 1.11.0 | 2026-03-24 | 1.85 | MIT OR Apache-2.0 | 186 M |
| quickcheck | 1.1.0 | 2026-02-10 | 1.85 | Unlicense OR MIT | 68 M |
| arbitrary | 1.4.2 | 2025-08-14 | 1.63 | MIT OR Apache-2.0 | 158 M |
| cucumber | 0.23.0 | 2026-04-23 | 1.88 | MIT OR Apache-2.0 | 16.6 M |
| cargo-mutants | 27.1.0 | 2026-06-02 | 1.88 | MIT | 592 k |
| mutagen | 0.1.2 | 2018-10-10 | | Apache-2.0/MIT | 11 k |
| cargo-llvm-cov | 0.9.1 | 2026-09-06 | 1.87 | Apache-2.0 OR MIT | 7.8 M |
| cargo-tarpaulin | 0.37.2 | 2026-08-15 | | MIT OR Apache-2.0 | 3.0 M |
| cargo-fuzz | 0.13.2 | 2026-06-09 | | MIT OR Apache-2.0 | 4.6 M |
| libfuzzer-sys | 0.4.13 | 2026-06-04 | | (MIT OR Apache-2.0) AND NCSA | 62.8 M |
| afl | 0.18.2 | 2026-05-11 | | Apache-2.0 | 2.4 M |
| bolero | 0.13.4 | 2025-07-03 | 1.66 | MIT | 5.5 M |
| cargo-audit | 0.22.2 | 2026-06-05 | 1.88 | Apache-2.0 OR MIT | 11.8 M |
| cargo-deny | 0.20.2 | 2026-07-09 | 1.88 | MIT OR Apache-2.0 | 5.7 M |
| cargo-geiger | 0.13.0 | 2025-08-31 | 1.85 | Apache-2.0 OR MIT | 236 k |
| cargo-nextest | 0.9.144 | 2026-09-10 | 1.91 | Apache-2.0 OR MIT | 12.7 M |
| criterion | 0.8.2 | 2026-02-04 | 1.86 | Apache-2.0 OR MIT | 279 M |
| divan | 0.1.21 | 2025-04-10 | 1.80 | MIT OR Apache-2.0 | 7.7 M |
| iai-callgrind | 0.16.1 | 2025-07-30 | 1.74.1 | Apache-2.0 OR MIT | 1.6 M |
| mockall | 0.15.0 | 2026-06-28 | 1.77 | MIT OR Apache-2.0 | 167 M |
| cargo-modules | 0.27.0 | 2026-08-03 | 1.95 | MPL-2.0 | 250 k |
| cargo-arch | 0.1.5 | 2022-05-10 | | Apache-2.0 | 12 k |
| cargo-vet | 0.10.2 | 2026-01-13 | 1.82 | Apache-2.0/MIT | 626 k |
| cargo-semver-checks | 0.50.0 | 2026-08-01 | 1.93 | Apache-2.0 OR MIT | 626 k |

The toolchain used is Homebrew's (cargo 1.98.0); the rustup default toolchain on the machine
was 1.87, below the MSRV of cargo-mutants, cucumber and cargo-nextest.

### Smoke run, scratch crate

| Tool | What ran | Observed |
|---|---|---|
| cargo test | `cargo test` over a proptest property, a quickcheck property, a mockall `mock!` and a plain test, plus the cucumber target | 4 passed; the cucumber target (`harness = false`) prints its own report |
| cargo-nextest 0.9.144 | `cargo nextest run` | `creating test list failed`: the cucumber binary exits 2 on `--list`, as a `harness = false` target does; `cargo nextest run -E 'not binary(cucumber)'` runs the 4 tests, one process each |
| cucumber 0.23.0 | one feature, three steps with `#[given(expr = ...)]`, `W::run("features")` under `futures::executor::block_on` | 1 scenario, 3 steps passed, the steps printed with ✔ |
| proptest 1.11.0 | `proptest!` with `any::<i64>()` and two ranges on `clamp` | passes; a failing case would be written to `proptest-regressions/` |
| quickcheck 1.1.0 | `quickcheck!` on the commutativity of `add` | passes; generation from `Arbitrary`, no strategy to write |
| mockall 0.15.0 | `mock!` of a `Clock` trait in the integration test, `expect_now().return_const(7)` | passes; `#[automock]` on the trait needs mockall as a dependency of the library, `mock!` in the test does not |
| clippy (1.98) | `cargo clippy --all-targets -- -D warnings` | clean |
| rustfmt (1.98) | `cargo fmt --check` | exit 1 on the one-line benchmark, the diff printed |
| cargo-llvm-cov 0.9.1 | `cargo llvm-cov --json --summary-only`, then `report --lcov` | "failed to find llvm-tools-preview" against Homebrew's rustc, whose sysroot ships no llvm-tools; with `LLVM_COV` and `LLVM_PROFDATA` pointing at Homebrew's `llvm@22` (the same LLVM as rustc 1.98), lines 5 of 9 covered (55.6 %), and the lcov report lists 9 `DA:` lines; under rustup, `rustup component add llvm-tools-preview` is the way |
| cargo-mutants 27.1.0 | `cargo mutants --timeout 60 --jobs 4` | 26 mutants tested in 63 s, 14 caught, 12 missed: the two `<` to `<=` and `>` to `>=` boundary mutants of `clamp` (equivalent on the sample) and ten return-value replacements of `parse_pair`, which no test reaches; `mutants.out/` holds `caught.txt` and `missed.txt`; `--in-place` cannot be combined with `--jobs` |
| cargo-audit 0.22.2 | `cargo audit` | 1243 advisories loaded from the RustSec database, 200 crates of `Cargo.lock` scanned, no vulnerability |
| cargo-deny 0.20.2 | `cargo deny check bans licenses advisories` with a `deny.toml` | advisories ok, bans ok; licenses failed on the unlicensed sample crate and warned on each allowed licence not met, so the allow list must be exactly the licences of the tree |
| cargo-deny 0.20.2, bans with wrappers | `deny = [{ crate = "proptest", wrappers = ["other-crate"] }]`, then `wrappers = ["sample495"]` | `error[banned]: crate 'proptest' is explicitly banned`, "direct parent 'sample495' was not marked as a wrapper"; with the crate itself as wrapper, `bans ok`: a dependency allowed to one crate of the workspace and forbidden to the others |
| cargo-fuzz 0.13.2 | `cargo fuzz init`, `cargo fuzz build` on stable 1.98 | `fuzz/` with `fuzz_targets/fuzz_target_1.rs` written; the build fails, "1 nightly option were parsed" (`-Zsanitizer=address`): a nightly toolchain is required |
| criterion 0.8.2 | `cargo bench --bench clamp -- --warm-up-time 1 --measurement-time 2` | `target/criterion/clamp/new/estimates.json`, mean 0.307 ns; the previous run is kept as the baseline for the next comparison |

## Decisions, by role

| Role | Recommended | Why this one | Set aside |
|---|---|---|---|
| runner | cargo test | the runner every crate has; runs the property, bdd and doubles entries as ordinary test targets; `harness = false` targets included | cargo-nextest: one process per test and retries, but cannot list a `harness = false` target (the cucumber binary) unless it is excluded by expression; a project that runs it keeps it, the runner is never a gap |
| bdd | cucumber | the Rust Cucumber implementation, `.feature` files the requester reads, steps as attributed functions, runs as a `harness = false` test target | none other with a user base |
| property | proptest | strategies with shrinking and a regression file, three times quickcheck's use, the ecosystem's reference | quickcheck: works, generation from `Arbitrary` without strategies, no advantage measured; bolero: a front over the fuzzers, not a property library alone |
| fuzzing | cargo-fuzz | libFuzzer through `libfuzzer-sys`, the standard `fuzz/` layout, what OSS-Fuzz runs for Rust; needs a nightly toolchain, measured | afl: needs an AFL++ build, not run; bolero: one front over libfuzzer, afl and honggfuzz, not run; the nightly requirement holds for its libfuzzer engine too |
| mutation | cargo-mutants | the maintained mutation tester of the ecosystem, a release three months before the study; caught 14 of 26 mutants on the sample and named the untested function through the missed ones | mutagen: last release 2018-10 |
| coverage | cargo-llvm-cov | LLVM's source-based coverage through rustc's own instrumentation, `json` and `lcov` reports listing the executed lines, which diff-cover reads for the changed lines; needs the toolchain's llvm-tools or a matching LLVM | cargo-tarpaulin: maintained, not run; a ptrace engine historically Linux-only, an llvm engine since, for the same measure |
| architecture | cargo-deny (`[bans]` with `wrappers`) | the one rule engine over the dependency graph: a crate banned except through named wrapper crates is a layer rule between the crates of a workspace, and `cargo deny check bans` fails the build on it; module-level rules inside one crate have no tool, the module system and `pub(crate)` are the enforcement | cargo-modules: MPL-2.0, draws the module graph, checks cycles, no rules; cargo-arch: last release 2022-05, generates the graph |
| static | clippy, with rustfmt | the toolchain's own lints and formatter, `-D warnings` and `--check` fail the build | none |
| security | cargo-deny | reads the RustSec advisory database (the same as cargo-audit) and checks licences and bans from the same `deny.toml` the architecture entry uses; no account | cargo-audit: the RustSec project's own tool, the same advisories; kept as the conditional entry for a project that already runs it. cargo-geiger: counts `unsafe`, no verdict |
| performance | criterion | statistics per benchmark, the previous run kept as the baseline under `target/criterion`, which is the base-versus-change comparison 495 makes | divan: simpler API, no baseline comparison; iai-callgrind: instruction counts under valgrind, Linux |

## Notes carried into the catalogue

- cargo-fuzz builds on nightly only.
- cargo-llvm-cov needs `llvm-tools-preview` of the toolchain that compiles, or `LLVM_COV` and
  `LLVM_PROFDATA` from the LLVM release rustc was built with.
- cargo-mutants writes `mutants.out/`, to be ignored by git; `--in-place` excludes `--jobs`.
- cargo-deny's licence check fails on an allowed licence the tree does not use, and on a crate
  without a `license` field.
- cargo-nextest cannot list a `harness = false` target.

## What a profile can detect

| Role | Marker of the recommended tool |
|---|---|
| runner | `Cargo.toml` (cargo test); `.config/nextest.toml` or `cargo nextest` in a CI file (cargo-nextest) |
| bdd | `cucumber` in the dev-dependencies; `.feature` files under `features/` or `tests/` |
| property | `proptest` in the dev-dependencies; `proptest-regressions/`; `quickcheck` |
| fuzzing | `fuzz/Cargo.toml` with `libfuzzer-sys`, `fuzz/fuzz_targets/` (cargo-fuzz); `afl`, `bolero` in the dependencies |
| mutation | `.cargo/mutants.toml`; `mutants.out/`; `cargo mutants` in a CI file |
| coverage | `cargo llvm-cov` or `cargo-llvm-cov` in a CI file; `tarpaulin.toml`, `.tarpaulin.toml`, `cargo tarpaulin` |
| architecture | `deny.toml` with a `[bans]` section |
| static | `clippy.toml`, `.clippy.toml`, `[lints.clippy]` in `Cargo.toml`, `cargo clippy` in a CI file; `rustfmt.toml`, `.rustfmt.toml`, `cargo fmt` |
| security | `deny.toml` with an `[advisories]` section or `cargo deny` in a CI file; `.cargo/audit.toml`, `cargo audit` or the `rustsec/audit-check` action (cargo-audit) |
| performance | `criterion` in the dev-dependencies; `benches/`; `divan`, `iai-callgrind` |

## Follow-ups

- A run of cargo-fuzz under a nightly toolchain, to measure the target and the crash
  reporting as the JavaScript study did for Jazzer.js.
