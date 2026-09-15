# Python test libraries, by role

- Date: 2026-09-13
- Fills: `docs/test-libraries.md`, section Python
- Rule applied: `docs/decisions/0012-tests-use-proven-libraries-from-a-catalogue.md`

One recommended library per catalogue role, chosen among the candidates the Python ecosystem
offers for that role. Every fact below was measured on the date above; nothing is taken from
memory alone.

## Method

1. **Candidates.** For each of the twelve roles, the libraries a Python project would reach
   for, including the ones already catalogued (pytest, import-linter, ruff, mypy) where they
   overlap a role.
2. **Maintenance and terms.** Latest release, release date, supported Python range and licence,
   read from the PyPI JSON API for every candidate. A library whose last release is older than
   three years is not recommended; a library whose current database or engine sits behind a
   vendor account or a proprietary licence is not recommended either.
3. **Smoke run.** Each retained library installed in a scratch virtualenv (CPython 3.12,
   pytest 9.1.1) and run once on a two-function sample package, with the options 495 uses on
   host projects (`-p no:cacheprovider`). What broke is recorded in the notes.
4. **Run on 495.** The security candidates were run on `harness495/` and on 495's frozen
   environment, so that the recommendation rests on findings and not on rule lists.

## Facts measured

### Releases, as read on PyPI

| Library | Version | Released | Python | Licence |
|---|---|---|---|---|
| hypothesis | 6.168.0 | 2026-09-08 | >=3.10 | MPL-2.0 |
| pytest-quickcheck | 0.9.0 | 2022-11-05 | unstated | Apache-2.0 |
| atheris | 3.1.0 | 2026-06-17 | unstated | Apache-2.0 |
| pythonfuzz | 1.0.3 | 2019-11-02 | >=3.5.3 | unstated |
| hypofuzz | 25.11.1 | 2025-11-03 | >=3.10 | LicenseRef-HypoFuzz (proprietary) |
| mutmut | 3.8.0 | 2026-09-12 | >=3.10 | BSD-3-Clause |
| cosmic-ray | 8.7.0 | 2026-08-09 | >=3.9 | MIT |
| mutatest | 3.1.0 | 2022-02-20 | >=3.7 | MIT |
| pytest-mutagen | 1.3 | 2020-07-24 | >=3.6 | MIT |
| coverage | 7.16.0 | 2026-08-28 | >=3.10 | Apache-2.0 |
| pytest-cov | 7.1.0 | 2026-03-21 | >=3.9 | MIT |
| diff-cover | 10.5.1 | 2026-08-16 | >=3.10 | Apache-2.0 |
| bandit | 1.9.4 | 2026-02-25 | >=3.10 | Apache-2.0 |
| pip-audit | 2.10.1 | 2026-06-10 | >=3.10 | Apache-2.0 |
| safety | 3.8.1 | 2026-05-29 | >=3.9 | MIT (client); database behind a vendor account |
| semgrep | 1.177.0 | 2026-09-10 | >=3.10 | LGPL-2.1 (engine); registry rules under their own terms |
| detect-secrets | 1.5.0 | 2024-05-06 | unstated | Apache-2.0 |
| schemathesis | 4.27.0 | 2026-09-12 | >=3.10 | MIT |
| pact-python | 3.4.0 | 2026-05-04 | >=3.10 | MIT |
| hypothesis-jsonschema | 0.23.1 | 2024-02-28 | >=3.8 | MPL-2.0 |
| dredd_hooks | 0.2.0 | 2018-04-09 | unstated | MIT (Dredd itself is a Node.js tool) |
| pytest-benchmark | 5.3.0 | 2026-08-23 | >=3.10 | BSD-2-Clause |
| pytest-codspeed | 5.0.3 | 2026-05-22 | >=3.9 | MIT |
| asv | 0.6.6 | 2026-06-27 | >=3.9 | BSD-3-Clause |
| pytest-memray | 1.10.0 | 2026-08-07 | >=3.8 | Apache-2.0 |
| locust | 2.46.5 | 2026-09-07 | >=3.11 | MIT |
| pytest-mock | 3.15.1 | 2025-09-16 | >=3.9 | MIT |
| responses | 0.26.3 | 2026-08-26 | >=3.8 | Apache-2.0 |
| respx | 0.23.1 | 2026-04-08 | >=3.8 | BSD-3-Clause |
| time-machine | 3.5.1 | 2026-09-08 | >=3.10 | MIT |
| freezegun | 1.5.5 | 2025-08-09 | >=3.8 | Apache-2.0 |
| factory_boy | 3.3.3 | 2025-02-03 | >=3.8 | MIT |

### Smoke run, scratch virtualenv

Sample: a package with `clamp(x, lo, hi)` and `add(a, b)`, six tests.

| Library | What ran | Observed |
|---|---|---|
| hypothesis | `@given(st.integers(), ...)` on `clamp` | passes; `test.hypothesis.fuzz_one_input` is present, so the same test is an atheris target |
| pytest-benchmark | `benchmark(clamp, 5, 0, 3)`, five rounds | min 25.7 ns, mean 28.9 ns; `--benchmark-disable` keeps the test as a plain call |
| pytest-memray | `@pytest.mark.limit_memory("1 MB")` | passes on macOS; under `-p no:cacheprovider` the plugin raises `AttributeError: 'Config' object has no attribute 'cache'` in `pytest_memray/marks.py::limit_memory` |
| pytest-mock | `mocker.patch("pkg.clamp", return_value=9)` | passes, patch undone at teardown |
| coverage.py | `coverage run -m pytest`, `coverage json` | `executed_lines` per file: `[1, 2, 3, 4, 5, 6]` for the package, 100 % |
| diff-cover | a `neg` function added after a commit, `diff-cover coverage.xml --compare-branch=HEAD --json-report` | one violation line (the new body), covered lines listed, 50 % of the diff |
| mutmut | `mutmut run`, `mutmut results`, `mutmut show` | `x_add__mutmut_1` (`a + b` to `a - b`) killed by `test_add`; the two `clamp` mutants (`<` to `<=`, `>` to `>=`) survive and are equivalent; 1.8 to 2.7 mutations per second on the sample |
| schemathesis | `schemathesis.openapi.from_asgi("/openapi.json", app)` on a FastAPI route dividing by the path parameter | finds `item_id = 0` and reports the `ZeroDivisionError` through `case.call_and_validate()` |
| atheris | `uv pip install atheris` on macOS with Apple clang 21 | build fails: Apple clang ships without libFuzzer; the package asks for an LLVM clang built with `compiler-rt` |

Observed on mutmut 3.8 in addition:

- the configuration keys are `[tool.mutmut] source_paths` and
  `pytest_add_cli_args_test_selection`; the older `paths_to_mutate` and `tests_dir` still work
  with a deprecation warning;
- it copies sources and tests into `mutants/` at the project root, and a subsequent `pytest`
  from the root collects that copy and fails with `import file mismatch` unless `mutants/` is
  ignored (`--ignore=mutants`, or `norecursedirs`) and kept out of git;
- `mutants/mutmut-stats.json` records which tests reach each function, and only those tests run
  against that function's mutants.

### Run on 495

| Tool | Target | Result |
|---|---|---|
| bandit 1.9.4 | `harness495/` (80 files) | 38 findings: B101 assert ×20, B603 subprocess ×7, B404 import subprocess ×5, B607 partial path ×3, B108 hard-coded tmp ×1, B324 insecure hash ×1, B112 try-except-continue ×1 |
| ruff 0.16.7 `--select S` | `harness495/` | 33 findings: S101 ×20, S603 ×7, S607 ×3, S108 ×1, S324 ×1, S112 ×1, on the same lines; S404 (the B404 port) is a preview rule in this version and reports the same 5 imports with `--preview` |
| pip-audit 2.10.1 | 495's frozen environment (31 distributions) | `No known vulnerabilities found` |

The B324/S324 hit is `hashlib.sha1` over a project path to derive a worktree name
(`harness495/core/engine.py`), not a security use; both tools take the same `# noqa` or
`usedforsecurity=False` to silence it. `pip-audit -r requirements.txt` builds a temporary
virtualenv with `ensurepip`, which aborted under the uv-managed interpreter on this machine;
the environment mode (`pip-audit` inside the venv, which needs `pip` present) ran cleanly.

## Decisions, by role

| Role | Recommended | Why this one | Set aside |
|---|---|---|---|
| property | hypothesis | the ecosystem's reference; a release a week; shrinking, database of failing examples, `fuzz_one_input` bridge to fuzzers; schemathesis is built on it | pytest-quickcheck: last release 2022, no shrinking |
| fuzzing | atheris | Google's libFuzzer binding, used by OSS-Fuzz for Python; coverage-guided; accepts a hypothesis test as target | pythonfuzz: last release 2019; hypofuzz: proprietary licence; hypothesis alone is not coverage-guided and stays the property entry |
| mutation | mutmut | a release the day before the study; runs only the tests that reach the mutated function; killed the non-equivalent mutant on the smoke run | cosmic-ray: maintained, not run; a session database and an init/baseline/exec/report cycle for the same measure; mutatest and pytest-mutagen: last releases 2022 and 2020 |
| coverage | coverage.py, with diff-cover for the changed lines | coverage.py is the only measurement engine in the ecosystem; `coverage json` lists executed lines per file; diff-cover answers the role's question, which changed lines the suite executes, against a branch | pytest-cov is coverage.py's pytest integration, not a second engine: use it when the suite is driven by pytest |
| security | ruff (rules `S`) for SAST, pip-audit for dependencies | ruff carries the flake8-bandit port of bandit's rules and reported the same findings on 495, rule for rule and line for line (33 stable, 38 with preview against bandit's 38), so a project that already runs ruff measures SAST by enabling one rule set; pip-audit is the PyPA tool over the OSV/PyPI advisory database, no account | bandit: same findings, a second tool for the same measure; safety: current database behind a vendor account; semgrep: cross-language engine with online rule registry, out of this per-technology study; secrets are not language-specific and need a cross-technology entry |
| contract | schemathesis | generates requests from the OpenAPI or GraphQL description and checks the responses against it; found a division by zero through the schema on the smoke run | pact-python: consumer-driven contracts between services, a different question than "does the implementation match its description"; hypothesis-jsonschema: a strategy library schemathesis embeds; dredd: Node.js tool, Python hooks last released 2018 |
| performance | pytest-benchmark, with pytest-memray for memory bounds | pytest-benchmark saves runs and fails on regression against a saved baseline (`--benchmark-compare-fail`), which is the base-versus-change comparison 495 makes; pytest-memray sets a memory bound per test | pytest-codspeed: full value needs the vendor's service; asv: benchmarks a repository's history, heavy configuration for one change; locust: load tests a deployed service |
| doubles | pytest-mock | the `mocker` fixture over `unittest.mock`, undone at teardown; the discipline the ecosystem knows | respx (httpx) and responses (requests) for HTTP doubles, time-machine for the clock: complements, named in the notes, not a second entry |

Already catalogued and confirmed by this study: pytest (runner), import-linter (architecture),
ruff (static), mypy (types).

## Notes carried into the catalogue

- `-p no:cacheprovider`, which 495 passes to host-project runs, breaks `pytest-memray`'s
  `limit_memory`; a memory-bound test needs the cache provider on.
- `mutmut` writes `mutants/` at the project root: ignore it in pytest and in git.
- `atheris` needs Linux, or a clang built with libFuzzer; Apple clang does not build it.
- `pip-audit` in requirements mode needs a working `ensurepip`; environment mode needs `pip`
  in the audited environment.

## What a profile can detect

Input for the role coverage of `docs/etude-harnais-495.md`, E50 (a):

| Role | Marker of the recommended tool |
|---|---|
| property | `hypothesis` in the dependencies; `from hypothesis import` in `tests/` |
| fuzzing | `atheris` in the dependencies; `atheris.Setup(` in a file; an `oss-fuzz` directory |
| mutation | `[tool.mutmut]` in `pyproject.toml`; `setup.cfg` section `[mutmut]`; `mutants/` |
| coverage | `[tool.coverage.*]`; `.coveragerc`; `pytest-cov` or `diff-cover` in the dependencies |
| security | `select` containing `"S"` under `[tool.ruff.lint]`; `pip-audit` in a CI file or the dependencies |
| contract | `schemathesis` in the dependencies; `schema.parametrize()` in `tests/` |
| performance | `pytest-benchmark` or `pytest-memray` in the dependencies; `.benchmarks/`; `benchmark` fixture in `tests/` |
| doubles | `pytest-mock` in the dependencies; `mocker` fixture in `tests/` |

## Follow-ups

- A cross-technology row for secrets scanning (gitleaks or detect-secrets), outside the
  per-technology tables.
- First use in 495 (`docs/etude-harnais-495.md`, E46): hypothesis on `core/reading/decide.py::assess`
  and the verification helpers, mutmut on `decide.py` and `reading/verification.py`.
- The other technologies of the catalogue: JavaScript / TypeScript, Rust, Go, Java / Kotlin,
  Shell.
