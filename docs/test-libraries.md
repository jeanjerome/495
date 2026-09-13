# Test libraries: the catalogue

One recommended library per technology and per role. Binds 495's own tests and the host projects
495 works on (`docs/decisions/0012-tests-use-proven-libraries-from-a-catalogue.md`).

## Using the catalogue

- Writing a test for 495: take the `recommended` entry for the role and technology. If the cell
  is empty, either bring an entry in (below) or write the check by hand and state in the test's
  docstring that the catalogue has no entry and what was searched.
- Profiling a host project: a role with no test, or a test using another library than the
  recommended one, is a conformance proposal to the requester (mechanism: E50 in
  `docs/etude-harnais-495.md`).

## Bringing an entry in

An entry has a status, a source and a date. Statuses:

- `recommended`: admitted by a study, a piece of research, or a retrospective on a host project.
  The source column names it. One `recommended` entry per cell.
- `rejected`: examined and set aside; the reason stays so that it is not proposed again.

A library used by 495's own suite counts as a source ("in use in 495 since <date>") once it has
run in the suite for at least one change; it is still listed, not assumed.

## Roles

| Role | Contract it measures | What the test must show |
|---|---|---|
| runner | Produit | planned cases hold, through public interfaces |
| property | Domaine | no counter-example to a stated invariant over a generated input range |
| fuzzing | Domaine, Sécurité | no crash, hang or unbounded consumption on malformed input |
| mutation | Tests | the suite detects a deliberate alteration of the code it covers |
| coverage | Tests | which changed lines the suite executes |
| architecture | Architecture | forbidden dependencies and layer crossings fail the build |
| static | Qualité | lint, formatting, complexity, duplication |
| types | API | type contracts hold |
| security | Sécurité | SAST findings, secrets, vulnerable dependencies |
| contract | API | schemas and API descriptions match the implementation |
| performance | Performance | latency, memory, throughput against a bound |
| doubles | Produit | test doubles and fixtures with a known discipline |

## Entries

Technologies are those the profile detects (`harness495/core/profile.py`). An empty cell means:
no entry yet; bring one in before writing that kind of test.

### Python

| Role | Library | Status | Source | Notes |
|---|---|---|---|---|
| runner | pytest | recommended | in use in 495 since 2026-09-11 | `-p no:cacheprovider` in host-project fixtures keeps the worktree clean |
| architecture | import-linter | recommended | in use in 495 since 2026-09-13 | contracts in `pyproject.toml`, run by `lint-imports` and `tests/test_architecture.py` |
| static | ruff | recommended | in use in 495 since 2026-09-11 | lint and format |
| types | mypy | recommended | in use in 495 since 2026-09-11 | `strict`, pydantic plugin |
| property | | | | |
| fuzzing | | | | |
| mutation | | | | |
| coverage | | | | |
| security | | | | |
| contract | | | | |
| performance | | | | |
| doubles | | | | 495 uses scripted fakes (`tests/conftest.py`); no library entry yet |

### JavaScript / TypeScript

| Role | Library | Status | Source | Notes |
|---|---|---|---|---|
| runner | | | | |
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
| static | | | | |
| security | | | | |

## Rejected

| Technology | Role | Library | Reason | Source |
|---|---|---|---|---|
| | | | | |
