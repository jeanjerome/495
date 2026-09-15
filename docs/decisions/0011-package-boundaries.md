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
| `harness495.core.reading` and its modules | `harness495.core.models`, `harness495.core.reading` |
| `harness495.core` (any other module except `engine`) | `harness495.core` |
| `harness495.core.engine` and its modules | `harness495.core`, `harness495.agents`, `harness495.sandbox` |
| `harness495.interfaces` | anything |

Nothing outside `harness495.interfaces` imports it. The table is written as five import-linter
`forbidden` contracts in `pyproject.toml` (`[tool.importlinter]`), each exception as an
`ignore_imports` edge; indirect chains count. `lint-imports` runs them; `tests/test_architecture.py`
runs the same contracts under pytest and fails with the report naming the chain that breaks one,
and asserts how many contracts were run, so that a contract deleted from the configuration fails
the suite rather than passing silently.

`harness495.core.engine.running` is where a verification command is executed, and the only
module of `core` that runs one. What that execution *means* is read by
`harness495.core.reading.verification`, which imports neither `sandbox` nor `engine`; so the
pure modules that read a diff for its test files (`core.reading.diff`, `core.reading.suite`) no
longer reach, through it, the package that executes.

The row for `core.reading` is what makes that hold of every reader rather than of the two the
sentence above names. A reading is a function of the documents and the strings it is handed:
the store, `git`, the sandbox and every module that reaches them are outside what it may
import, and an indirect chain is an import, so a reader cannot get to them one call away
through a neighbour that legitimately does. The contract also names `subprocess`, `os`,
`tempfile`, `socket`, `urllib` and `httpx`, so the same holds of a reader that would reach the
world without going through the harness at all. `shutil.which` on the machine's `PATH` is the
one admitted exception, stated in `core/reading/verification.py`: it is how the audit tells a
command that cannot run from one that can, and it reads no file of the project.

This is why the catalogue is two modules. Its recommendations are a reading and live in
`core/reading/catalogue.py`; the conditions that pick between the entries of a cell open files
of the project and live in `core/conditions.py`, evaluated once while the project is profiled
(0015). In one flat `core` the edge from `retro` to `catalogue` was a legal core-to-core import
and the file it opened was one call away, which is what the contract now rejects.

## Consequences

- A new adapter lives in `agents` and reaches the engine only through the `Agent` protocol in
  `agents/base.py`; a new isolation backend lives in `sandbox` and knows only `core.models`.
- A new core module that needs an agent or a sandbox is either part of `engine`'s
  responsibility or a reason to extend this table in a superseding record.
- A module that only reads — of documents, of strings, of what a command printed — takes the
  shape of a function and lives in `core/reading/`, so that nothing depending on it depends on
  the packages that execute.
- Reading a module on its own does not show what it reaches: grepping each pure module for
  `open(`, `read_text` and `subprocess` answers nothing when the file is opened by a module it
  imports. The contract answers it, since it counts indirect chains.
- A reader that turns out to need the world is a reader in the wrong place: what it needs is
  measured by `core/engine/` and handed to it, or the module is not a reader and leaves the
  package.
- `interfaces` is the only place that may build an `Engine`, load configuration and select a
  sandbox for a user.

## Where in the code

- `pyproject.toml`: `[tool.importlinter]` and its five contracts.
- `tests/test_architecture.py`: `CONTRACTS`, `test_given_the_declared_contracts_when_they_are_run_then_every_one_holds`.
- `harness495/core/reading/`: the package the fifth contract covers; `harness495/core/conditions.py`,
  the half of the catalogue that reads the project and therefore stays outside it.
- `docs/architecture.md`, section Packages and their boundaries.
- `0012-tests-use-proven-libraries-from-a-catalogue.md`: why a library and not a script.
