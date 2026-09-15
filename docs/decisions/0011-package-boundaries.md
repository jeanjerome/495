# 0011. Package dependencies point one way, and a test enforces it

- Status: accepted
- Date: 2026-09-13

## Context

`harness495` has four packages. The dependency direction between them was consistent in the
code and stated nowhere; a documented rule with no check is a convention an agent can cross
whenever crossing it solves the task at hand.

## Decision

Allowed imports of `harness495.*`, by importing package:

| Package | May import |
|---|---|
| `harness495.sandbox` | `harness495.sandbox`, `harness495.core.models` |
| `harness495.agents` | `harness495.agents`, `harness495.sandbox`, `harness495.core.models`, `harness495.core.pricing` |
| `harness495.core` (any module except `engine`) | `harness495.core` |
| `harness495.core.engine` and its modules | `harness495.core`, `harness495.agents`, `harness495.sandbox` |
| `harness495.interfaces` | anything |

Nothing outside `harness495.interfaces` imports it. The table is written as four import-linter
`forbidden` contracts in `pyproject.toml` (`[tool.importlinter]`), each exception as an
`ignore_imports` edge; indirect chains count. `lint-imports` runs them; `tests/test_architecture.py`
runs the same contracts under pytest and fails with the report naming the chain that breaks one.

`harness495.core.engine.running` is where a verification command is executed, and the only
module of `core` that runs one. What that execution *means* is read by
`harness495.core.reading.verification`, which imports neither `sandbox` nor `engine`; so the
pure modules that read a diff for its test files (`core.diff`, `core.suite`) no longer reach,
through it, the package that executes.

## Consequences

- A new adapter lives in `agents` and reaches the engine only through the `Agent` protocol in
  `agents/base.py`; a new isolation backend lives in `sandbox` and knows only `core.models`.
- A new core module that needs an agent or a sandbox is either part of `engine`'s
  responsibility or a reason to extend this table in a superseding record.
- A module that only reads — of documents, of strings, of what a command printed — takes the
  shape of a function and lives outside `engine`, so that nothing depending on it depends on
  the packages that execute.
- `interfaces` is the only place that may build an `Engine`, load configuration and select a
  sandbox for a user.

## Where in the code

- `pyproject.toml`: `[tool.importlinter]` and its four contracts.
- `tests/test_architecture.py`.
- `docs/architecture.md`, section Packages and their boundaries.
- `0012-tests-use-proven-libraries-from-a-catalogue.md`: why a library and not a script.
