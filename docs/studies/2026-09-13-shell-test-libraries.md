# Shell test libraries, by role

- Date: 2026-09-13
- Fills: `docs/test-libraries.md`, section Shell
- Rule applied: `docs/decisions/0012-tests-use-proven-libraries-from-a-catalogue.md`

One recommended library per role of the shell table (runner, bdd, coverage, static, security), chosen
among the candidates a project written in shell would reach for. Every fact below was measured
on the date above; nothing is taken from memory alone.

## Method

1. **Candidates.** For each role, the tools a shell project uses, including the ones the
   profile already recognises (shellcheck, shfmt, shellspec, bats, shunit2). Shell has no
   Gherkin runner of its own with a user base, so the `bdd` candidates are the Gherkin runners
   of other ecosystems driving the scripts as subprocesses. The `coverage` candidates are the
   two engines that count the lines a shell executes: kcov (the DEBUG trap of bash, zsh and
   ksh) and bashcov (bash's xtrace on a descriptor, read by SimpleCov).
2. **Maintenance and terms.** Latest release, release date and licence, read from the GitHub
   releases API for every candidate (shell tools are not distributed through one registry), and
   from npm or RubyGems where the tool is installed from there. A tool whose last release is
   older than three years is not recommended, unless it carries a measure no current tool
   gave in the smoke run (shellspec, for coverage).
3. **Smoke run.** Each retained tool run once on a sample script (`scripts/greet.sh`: an
   argument with a default, an `rm -rf $dir/`, an `eval`), with the tests of each runner
   written for the same two behaviours. What broke is recorded in the notes. Each coverage
   engine run over each runner and over the script alone, several times where the report
   differed between runs.
4. **Search.** The GitHub search API for repositories matching "gherkin bash", "cucumber shell
   script" and "bdd bash" in the Shell language, sorted by stars, to establish that no Gherkin
   runner written in shell has a user base.

## Facts measured

### Releases, as read on GitHub, npm and RubyGems

| Tool | Version | Released | Licence | Last push | Stars |
|---|---|---|---|---|---|
| bats-core | v1.14.0 (npm `bats` 1.13.0, 2025-11-07) | 2026-07-21 | MIT | 2026-09-13 | 6257 |
| bats-support | v0.3.0 | 2022-03-04 | 0BSD | 2025-08-21 | 58 |
| bats-assert | v2.2.4 | 2025-10-14 | CC0-1.0 | 2025-11-06 | 122 |
| shellspec | 0.28.1 | 2021-01-11 | MIT | 2025-11-24 (master: 2024-09-12) | 1396 |
| shunit2 | v2.1.8 | 2020-03-29 | Apache-2.0 | 2026-03-15 | 1739 |
| bashunit | 0.50.1 | 2026-08-22 | MIT | 2026-09-13 | 427 |
| sstephenson/bats | none | archived | MIT | 2019-09-27 | 7101 |
| shpec | none | | MIT | 2022-12-19 | 386 |
| assert.sh | none | | LGPL-3.0 | 2022-01-21 | 491 |
| shellcheck | v0.11.0 | 2025-08-04 | GPL-3.0 | 2026-08-04 | 40033 |
| shfmt (mvdan/sh) | v3.14.1 | 2026-09-06 | BSD-3-Clause | 2026-09-09 | 9054 |
| shellharden | v4.3.2 | 2026-06-27 | MPL-2.0 | 2026-07-09 | 4804 |
| gitleaks | v8.30.1 | 2026-03-21 | MIT | 2026-09-09 | 29290 |
| trufflehog | v3.97.4 | 2026-09-03 | AGPL-3.0 | 2026-09-12 | 27863 |
| semgrep | v1.177.0 | 2026-09-10 | LGPL-2.1 | 2026-09-11 | 16618 |
| aruba (cucumber/aruba, RubyGems) | v2.4.1 | 2026-05-15 | MIT | 2026-09-12 | 966 |
| kcov (SimonKagstrom/kcov, Homebrew) | v43 | 2024-07-23 | GPL-2.0 | 2026-09-03 | 829 |
| bashcov (infertux/bashcov, RubyGems) | v4.0.0 | 2026-08-25 | MIT | 2026-09-11 | 173 |
| simplecov-cobertura (RubyGems) | 4.0.0 | | MIT | | |
| cucumber (RubyGems) | 11.1.1 | | MIT | | |
| @cucumber/cucumber (npm) | 13.2.1 | 2026-08-04 | MIT | | |

Gherkin runners written in shell, from the search: shellkin (5 stars, pushed 2026-08-21),
g4b (2 stars, archived 2017), shellot (0 stars, 2022), bash-specs (12 stars, 2017),
ralph-wiggum-bdd (8 stars, 2026-06). None has a user base; none was run.

### Smoke run

Sample: `scripts/greet.sh` (`name=${1:-world}`, `dir=$2`, `echo "hello, $name"`,
`rm -rf $dir/`, `eval "echo $name"`), tools installed under a scratch directory (bats and its
helpers from npm, shunit2 from its release, bashunit from its release, cucumber and aruba
into a scratch `GEM_HOME`, cucumber-js from the JavaScript study's `node_modules`).

| Tool | What ran | Observed |
|---|---|---|
| bats 1.13.0, bats-support, bats-assert | two `@test`s with `run`, `assert_success`, `assert_line --index 0`, `assert_output --partial` | 2 passed; `--formatter tap` gives TAP; when the script failed, the report carried the status (2) and the four lines of output `run` captured |
| shellspec 0.28.1 | one `Describe`/`It` with `When run script`, `The line 1 should equal`, `The status should be success` | 1 example, 0 failures; a describe/it DSL of its own, no Gherkin, no feature file |
| shunit2 2.1.8 | one `testGreets` with `assertEquals`, `. ./shunit2` at the end of the script | 1 test OK; sourced by the script under test, no runner command of its own |
| bashunit 0.50.1 | one `function test_greets` with `assert_equals` | 1 assertion passed, 192 ms; a runner command and xUnit style like shunit2 |
| shellcheck 0.11.0 | `shellcheck -f gcc`, `-f json`, `-S warning`, `-o all`, `--list-optional` | SC2115 (warning, `rm -rf $dir/` may expand to `/`), SC2086 (info, unquoted expansion); `-S warning` exits 1 on the warning alone; `-o all` adds three optional findings; 11 optional checks listed |
| shfmt 3.13.1 | `shfmt -d` on the sample and on a misindented `if` block | silent on the sample; a unified diff for the block |
| gitleaks 8.30.1 | `gitleaks dir . --report-format json` on a `scripts/env.sh` with a random 36-character `ghp_` token and the AWS example key | one finding, `github-pat`, `scripts/env.sh` line 1, exit 1; the AWS example key (`AKIAIOSFODNN7EXAMPLE`) and an all-`A` token were not reported, one being allowlisted and the other of low entropy |
| cucumber 11.1.1 with aruba 2.4.1 | one scenario: `Given the script is on the PATH`, `` When I run `greet.sh alice /tmp/none` ``, `Then the output should contain "hello, alice"`, `And the exit status should be 0` | 1 scenario, 4 steps passed in 0.1 s; three of the four steps are aruba's own, only the PATH step was written (`prepend_environment_variable`); `GEM_PATH` must include the default gems (aruba's `ffi` came from there); `--publish-quiet` silences the report upload prompt |
| @cucumber/cucumber 13.2.1 | the same feature, four steps written in an `.mjs` around `spawnSync` | 1 scenario, 4 steps passed; every step to write, nothing built in for commands |
| shellspec 0.28.1 `--kcov`, kcov 43 | the two examples with `When run source`, then a third on the script's `exit 2` path | `coverage/<name>/cobertura.xml` with per-line hits (lines 2, 3, 7 hit twice, 4 and 5 once from the third example, 100 % of the script), `coverage.json`, `sonarqube.xml`, `codecov.json`; same figures on a second run; kcov instrumented every `.sh` under the root, the scratch `node_modules/` included, hence `--include-path` |
| shellspec 0.28.1 `--kcov` | the same examples with `When run script` | 2 examples passed, 0 executed lines of 5: the script ran in a shell kcov did not trace |
| shellspec 0.28.1 `--kcov`, macOS default `ulimit -n` (1048576) | the same | `Failed to exchange stderr for pipe: Bad file descriptor`, 0 examples: kcov puts the trace descriptor in a `select()` set, whose limit is 1024; `ulimit -n 1024` before the run fixes it |
| kcov 43 over bats 1.13.0 | `kcov --include-path=scripts out bats test/` | no report after 3 minutes, the bats process tree waiting; killed |
| kcov 43 over the script alone | `kcov out scripts/greet.sh alice` | per-line hits, one invocation at a time: no suite |
| bashcov 4.0.0 over bats 1.13.0 | `bashcov --root . -- bats test/`, bash 5.3 and bash 3.2, `.simplecov` with the Cobertura formatter | the script's lines with hits in 4 runs out of 8, `0 / 0` in the other 4, the runner's own `libexec/` scripts counted until filtered out |
| bashcov 4.0.0 over shellspec 0.28.1 | `bashcov --root . -- shellspec`, `--shell bash` too | `0 / 0` and `Stopped processing SimpleCov as a previous error not related to SimpleCov has been detected`, 2 runs |
| bashcov 4.0.0 over a `bash -c` running the script twice | 3 runs | `0 / 0` each time: the descriptor bash traces on is not inherited by the script's own shell |

## Decisions, by role

| Role | Recommended | Why this one | Set aside |
|---|---|---|---|
| runner | bats; shellspec when the project keeps its specs in it or measures coverage | bats is the shell runner with the user base (bats-core, the maintained fork of sstephenson/bats), a release two months before the study, TAP output, `run` capturing status and output, assertions from bats-assert and bats-support; already what the profile recognises from `.bats` files. shellspec is the second entry of the cell: its last release is 2021-01, beyond the three years of the method, and the repository moved until 2024-09; it is admitted on the coverage measure, which no other runner gave (below), and because `When run source` runs the script in the shell kcov traces; the DSL is its own, which keeps it out of the bdd role | shunit2: last release 2020-03. bashunit: active and recent, xUnit style, small user base, no advantage measured over bats |
| bdd | cucumber (Ruby), with aruba | no Gherkin runner written in shell has a user base, so the runner comes from another ecosystem; aruba is the Cucumber project's own library for command-line applications: running a command, its output and its exit status are built-in steps, so the requester's scenario is the whole test and carries no step code; Ruby is present on macOS and the common Linux distributions | @cucumber/cucumber: works, every step to write; the runner to take when the project is JavaScript, which the profile then reports as such. shellspec: describe/it, not Gherkin. shellkin, g4b, shellot: no user base |
| coverage | kcov, through `shellspec --kcov` | the one engine that gave per-line hits for a suite, twice over with the same figures, in Cobertura (which diff-cover reads for the changed lines), JSON and SonarQube form; GPL-2.0 binary from Homebrew or the distributions, no Ruby | bashcov: MIT and current, but the script's lines came back in half the runs over bats and never over shellspec or a `bash -c` wrapper: a measure that is sometimes empty cannot say which changed lines a suite misses. kcov over bats: did not finish |
| static | shellcheck, with shfmt | shellcheck is the shell analyser (40 000 stars, GPL-3.0, findings with a wiki page each, `-S` to choose the failing severity, `-f json`); shfmt formats and diffs, reading the `.editorconfig` keys the profile already recognises | shellharden: rewrites quoting, a fixer rather than a checker, with a scope shellcheck covers |
| security | shellcheck (`-S warning`), gitleaks | shellcheck's warnings are the analysis there is for shell: injection through unquoted expansions, `rm -rf` on an expansion that may be empty, `eval`; `-S warning` makes the command fail on them and not on style; gitleaks finds committed secrets (MIT, no account, `--report-format json`), the one check a script with credentials needs; shell has no dependency manifest, so no vulnerable-dependency check applies | trufflehog: AGPL-3.0, verifies secrets against the providers online. semgrep: cross-language engine with an online rule registry, out of this per-technology study |

## Notes carried into the catalogue

- gitleaks does not report the documentation example keys nor low-entropy strings: a test
  of the tool needs a random secret.
- aruba under a scratch `GEM_HOME` needs the default gem directory on `GEM_PATH`.
- shellcheck with `-S warning` exits non-zero on warnings and errors only; `-o all` turns the
  optional checks on.
- kcov reaches a script's lines from `When run source` and `When call`; `When run script`
  reports none. On macOS, `ulimit -n 1024` before `shellspec --kcov` (the guard shellspec
  carries only raises the limit). `--kcov-options --include-path=<scripts dir>` keeps the
  report to the project's scripts; `--exclude-region=KCOV_EXCL_START:KCOV_EXCL_STOP` leaves
  an embedded program (an awk or Python body in a string) out of the instrumented lines.

## What a profile can detect

| Role | Marker of the recommended tool |
|---|---|
| runner | `.bats` files (bats); `.shellspec` or `spec/*_spec.sh` (shellspec); a `shunit2` file (shunit2); a `bashunit` file at the root or under `lib/`, `*_test.sh` with `function test_` (bashunit) |
| coverage | `--kcov` in `.shellspec`, `kcov` in a CI file or Makefile (kcov); `bashcov` in the `Gemfile` or a CI file (bashcov) |
| bdd | `Gemfile` listing `cucumber` and `aruba`; `features/support/env.rb` requiring `aruba/cucumber`; `cucumber.js`, `.mjs`, `.cjs`, `.json`, `.yaml` or `.yml` at the root (@cucumber/cucumber); `features/steps/` or `behave.ini` (behave) |
| static | `.shellcheckrc` or a `# shellcheck` directive (shellcheck); shfmt's keys in `.editorconfig` (shfmt) |
| security | shellcheck recognised as above; `.gitleaks.toml`, or `gitleaks` in a CI file or `.pre-commit-config.yaml` |

## Follow-ups

- gitleaks is not specific to shell: a cross-technology row for secrets scanning, which the
  Python study also asked for, would carry it once.
