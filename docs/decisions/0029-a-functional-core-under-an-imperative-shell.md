# 0029. Inside `core`, the directory a module sits in says what it may do to the world

- Status: accepted
- Date: 2026-09-15

## Context

`0011` fixes one axis of the package layout: `interfaces` → `core.engine` → `agents` → `sandbox` →
`core.models`, layers by dependency, enforced by import-linter. It says which package may import
which, and nothing about what a module may do once imported.

`core` was flat. `decide.py`, `suite.py`, `reach.py`, `retro.py`, `lessons.py` computed judgements
from documents and strings and touched nothing; `store.py`, `git.py` and `engine.py` executed
commands, wrote files and persisted state; `catalogue.py` did both. They sat side by side, and what
kept the first group pure was prose: `0001` says of `assess` that "it calls no agent and reads no
file", `0015` says `retrospect` is a pure function of the run document. Nothing measured either
claim.

What that costs was measured on `retro.retrospect`. It reached `catalogue.applicable()`, which
opened `build.gradle.kts` to pick between the two entries of a catalogue cell. The edge
`retro` → `catalogue` is a legal core-to-core import, so no contract reported it, and reading
either module on its own does not reveal it: the file read is two calls away. A retrospective taken
after the tree changed answered as the tree stood rather than as the run had measured it — the
opposite of what `0015` states.

The same file also held both halves of every check of the verify phase: the half that runs commands
in the sandbox and writes evidence, and the half that says what the runs mean. The second half is a
pure function of what the first half measured, and the two had no seam between them.

## Decision

Inside `core`, a module's directory states what it may do to the world. The partition is by effect,
not by domain and not by level of abstraction.

- **`core/models/`** says what things are: pydantic models, enums, the identifier mint. No
  behaviour. It is the vocabulary, underneath the other three.
- **`core/reading/`** says what a measurement means. Its eleven modules are functions of the
  documents and strings they are handed. They execute no command, open no file of the project and
  write nothing. Contract 5 of `pyproject.toml` — `core.reading` may import `core.models` and
  `core.reading` alone, and neither `subprocess`, `os`, `tempfile`, `socket`, `urllib` nor `httpx` —
  is what keeps that true rather than remembered.
- **`core/engine/`** acts: it executes, persists, emits and moves the run from one status to the
  next. `core/engine/running.py` is the only module of `core` that puts a verification command in
  the sandbox.
- **`core/profile.py`, `coverage.py`, `conditions.py`, `proposals.py`** gather: they read the
  project and turn it into a document the other three work from. `conditions_holding()` evaluates
  the catalogue's tree-reading predicates once, while the project is profiled, and the profile keeps
  the names that held — so reading the catalogue against a profile opens no file.

Each check of the verify phase is a pair, one module each side of the seam:

| What is measured | Driver, under `core/engine/checks/` | Reader, under `core/reading/` |
|---|---|---|
| the command reports the same thing twice | `checks/stability.py` | `verification.py::reports_the_same_twice` |
| the suite that passed on the base | `checks/suite.py` | `suite.py` |
| the added lines the commands execute | `checks/coverage.py` | `reach.py` |
| the wrong versions of the change | `checks/mutation.py` | `mutation.py` |
| the instrument, against its control run | `checks/calibration.py` | `verification.py::classify_instrument` |

A region of the engine works through `RunServices` (`core/engine/services.py`) — store, sandbox,
event sink, warning sink, worktree, stop check, status setter — rather than through the state
machine. It is what a region may do to the world, named and passed in; `core/engine/checks/` takes
one and imports no agent and no phase.

The name for this shape is a functional core under an imperative shell, the shell being a state
machine over one persisted document.

## Consequences

**What it guarantees.** A reading that needed the store, git or the sandbox cannot get them without
leaving `core/reading/` first, and that move is a diff a reader sees. The impurity that reached a
file two calls from `retrospect` cannot recur along a legal import, because the import itself is now
illegal. `0001`'s claim about `assess` and `0015`'s about `retrospect` are checked on every run of
the suite rather than asserted in a record.

**What it forbids.** A pure reader may not fetch what it needs; it is handed it. A check that wants
a new measurement grows two modules, not one: the driver that gathers it and the reader that says
what it means. That is the cost of the seam, and it is the reason the region can be tested through
`RunServices` without driving a run to `produced`.

**What it does not buy.** `core/models/__init__.py` re-exports every name, so `harness495.core.models`
is one namespace to import-linter: no contract can distinguish who imports the specification models
from who imports the evidence models. Buying that enforcement means dropping the shim and rewriting
every import site in one commit, a change no reviewer can read. The shim stays.

**Where the name strains**, stated so it is not asked to carry more than it does:

- `models/` is neither core nor shell. It is the vocabulary, under both.
- The gathering modules are shell, but the half that *reads* the world rather than the half that
  *acts* on it. The full cycle is gather, judge purely, act, and "shell" flattens the two ends into
  one word.
- `RunServices` has no place in the original formulation, whose shell needs no internal structure.
  This one is large enough to need one.

**Alternatives rejected.**

- *Hexagonal.* Real ports exist — `Sandbox` and `Agent`, three adapters each — but they predate this
  layout, and two ports are not an organising principle. `RunServices` is not a port: it is a bundle
  of capabilities, not an interface across which something varies in production.
- *Clean architecture.* There is no use-case layer and no entity/gateway split. `Run` is
  aggregate-shaped, but nothing was designed as an aggregate.
- *DDD tactical patterns.* No repositories, no domain events as a scheme of organisation.
- *Keeping the purity as prose.* It had been prose in `0001` and `0015`, and `retrospect` broke it
  without anything reporting it.
- *A bound on module size.* It has one cheap evasion — move code to a second file without giving it
  a seam — which looks like progress and is not. The partition here is by effect, and a module that
  grows stays in the directory whose rule it obeys.

**The second axis is untouched.** `0011` still holds: layers by dependency, and inside the core, a
functional core under an imperative shell. A module sits on both axes, and both are contracts.

## Where in the code

- `harness495/core/reading/` — the eleven pure modules: `decide`, `verification`, `suite`, `diff`,
  `reach`, `mutation`, `catalogue`, `retro`, `lessons`, `stats`, `scope`. Its `__init__.py` states
  the rule the package keeps.
- `pyproject.toml`, `[tool.importlinter]` — contract 5, *core.reading imports core.models and
  core.reading alone*, and contract 4, *inside core, only engine reaches agents and sandbox*.
- `tests/test_architecture.py` — runs the contracts under pytest and asserts the count, so a
  contract deleted from the configuration does not leave the run green with one rule fewer.
- `harness495/core/engine/services.py` — `RunServices`, the seven collaborators a region works
  through.
- `harness495/core/engine/checks/` — the drivers, and `checks/__init__.py`, which names the reader
  each one pairs with. `harness495/core/engine/running.py` — the only module of `core` that puts a
  command in the sandbox.
- `harness495/core/conditions.py` — `CONDITIONS` and `conditions_holding()`, the predicates that
  read the tree, evaluated once at profiling; `harness495/core/models/lessons.py` —
  `ProjectProfile.conditions`, where the outcome is recorded.
- `harness495/core/models/` — the vocabulary, re-exported whole by `models/__init__.py`.
- `docs/architecture.md`, §*Packages and their boundaries* — the tree, the two axes and the pairs.
- `tests/test_documents.py` — asserts that every module path this record and its neighbours name is
  a file of the tree.
