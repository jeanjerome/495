# Proposed layout

A directory is a claim about what belongs together. This one is derived from the import graph and
from the commit history, not from taste.

## Three corrections

This file's first version stopped too early, and two of its claims do not survive measurement. Both
were mine, and both were asserted rather than checked.

**`models.py` should be split.** [04-deepening.md](04-deepening.md) D5 argued against it on the
ground that "its twelve sections are the seams a package would create" and that splitting "reduces
nothing, because a change touching `Spec` touches `Spec` wherever it lives". The first half is
true and turns out to be the argument *for* the split; the second is true and beside the point.
Measured over the last 25 commits that touched the file, **the median commit touches one section**,
and 16 of 21 touch one or two. What changes is not which class a commit edits but how much file a
reader opens to edit it. And the split is mechanically safe: zero cycles between classes, and the
30 import-time references form a clean DAG.

**`engine.py` at ~1 400 lines is not a floor.** The first version left the phases as one module
without asking whether they were one concept. They are not: seven phases, 89 to 214 lines each, and
**exactly one call between them** — `_produce` calls `_design_tests`, which `docs/decisions/0020`
requires. `Engine.step` is already a dispatch table from status to handler (`engine.py:285-298`);
making each phase a module changes nothing about the dispatch.

**`checks.py` at ~1 000 lines is not a floor either.** Five check groups plus an orchestrator, with
**zero calls between the groups**:

```
orchestration  132 ln  1 fn   -> calibration, stability, suite, coverage, mutation
stability      143 ln  3 fn   -> aucun autre groupe
suite           69 ln  2 fn   -> aucun autre groupe
coverage       153 ln  3 fn   -> aucun autre groupe
mutation       184 ln  3 fn   -> aucun autre groupe
calibration    261 ln  3 fn   -> aucun autre groupe
```

That also settles D4, which hedged at `Worth exploring` because "the gate is not uniform". The gate
lives in the orchestrator — 132 lines, one module — and the grouping behind it is unambiguous.

## What the import graph says

| core module | imported by core | by agents | by interfaces |
|---|---:|---:|---:|
| `models` | 18 | 5 | 33 |
| `store` | 3 | 0 | 9 |
| `engine` | 0 | 0 | 7 |
| `report` | 1 | 0 | 3 |
| `verification` | 3 | 0 | 0 |
| `catalogue` | 3 | 0 | 0 |
| `context` · `prompts` · `schemas` | 1 each | 0 | 0 |

Three readings decide the rest of the layout.

**`context`, `prompts` and `schemas` have exactly one importer: `engine.py`.** They are the engine's
own material, sitting at the same level as modules ten others depend on.

**`verification.py` is two modules in one file.** 287 lines are pure functions of strings and
documents; 117 are `run_verification` and `run_control`, which execute in the sandbox. `git` is
imported for those two functions only, and they are called only from `engine.py`. Meanwhile `diff`
and `suite` — both pure — import one 14-line predicate from it, `looks_like_a_test`, and thereby
depend on a module that imports `sandbox`. That is why the contract carries
`core.verification -> sandbox` as an exemption.

**`catalogue.py` mixes recommendation data with predicates that read the tree.** `applicable()`
calls them, and one of its three callers — `retro.retrospect` — is documented as a pure function of
the run document (F5). The impurity travels along a legal core-to-core edge, which is why reading
each module in isolation does not reveal it.

## The layout

```
harness495/
├── core/
│   ├── models/                           the shared vocabulary — a package, re-exported whole
│   │   ├── __init__.py                   every name, so all 56 import sites keep working
│   │   ├── enums.py               195
│   │   ├── run.py                 201    Run · Iteration · Version · RunResult · IntegrationCheck
│   │   ├── config.py              143    HarnessConfig · Budget · RolesConfig · ScopeConfig
│   │   ├── clarification.py       169
│   │   ├── lessons.py             157
│   │   ├── specification.py        99    Spec · Requirement · Verification · BehaviourScenario
│   │   ├── interventions.py        93    Intervention · Usage · Cost · AgentIdentity
│   │   ├── profile.py             ~80    ProjectProfile · RoleCoverage · CatalogueGap
│   │   ├── evidence.py             73    Evidence · Finding · ReviewVerdict
│   │   ├── proposals.py            72
│   │   ├── retrospective.py        72
│   │   └── decisions.py            36
│   │
│   ├── engine/
│   │   ├── __init__.py                   re-exports Engine · EngineError · spec_from_agent
│   │   ├── engine.py             ~250    the state machine and the twelve public methods
│   │   ├── services.py            ~60    RunServices — the internal seam
│   │   ├── phases/
│   │   │   ├── produce.py        ~228    ├─ one call between phases in total:
│   │   │   ├── profile.py        ~217    │  produce → design_tests (ADR 0020)
│   │   │   ├── review.py         ~208    │
│   │   │   ├── clarify.py        ~192    │
│   │   │   ├── gate.py           ~149    │
│   │   │   ├── design_tests.py    132    │
│   │   │   └── specify.py         109    ┘
│   │   ├── checks/
│   │   │   ├── sequence.py        132    the order, and the gate on instrument faults
│   │   │   ├── calibration.py     261    ├─ zero calls between these five
│   │   │   ├── mutation.py        184    │
│   │   │   ├── coverage.py        153    │
│   │   │   ├── stability.py       143    │
│   │   │   └── suite.py            69    ┘
│   │   ├── decisions.py           331    raise · record · apply   (D2 shrinks this)
│   │   ├── reading.py             306    agent output → models
│   │   ├── delivery.py            290    deliver · merge · integration check
│   │   ├── interventions.py       168    one call to one agent
│   │   ├── running.py             117    run_verification · run_control   ← from verification.py
│   │   ├── context.py             511    ContextPack and sixteen renderers
│   │   ├── prompts.py             425
│   │   └── schemas.py             180
│   │
│   ├── reading/                          pure: no I/O, enforced by contract
│   │   ├── lessons.py             504    decide.py 392 · retro.py 333 · stats.py 220
│   │   ├── suite.py               455    reach.py 443 · mutation.py 227 · diff.py 145
│   │   ├── verification.py       ~290    ← the pure half of today's verification.py
│   │   ├── catalogue.py          ~330    ← RECOMMENDED · ROLE_CONTRACTS · compare · applicable
│   │   └── scope.py                80
│   │
│   ├── project/
│   │   ├── profile.py             662
│   │   ├── coverage/
│   │   │   ├── markers.py         215    the marker vocabulary and rows()
│   │   │   └── python.py 175 · node.py 147 · jvm.py 137 · rust.py 79 · go.py 58 · shell.py 38
│   │   ├── conditions.py          ~60    ← the tree-reading predicates, evaluated once at profiling
│   │   └── proposals.py           209
│   │
│   ├── store.py 346 · git.py 362 · report.py 362 · config.py 195 · budget.py 76 · pricing.py 61
│
├── interfaces/
│   ├── cli/                              six command modules; `lessons` and `proposals` are the
│   │   │                                 two sub-apps `add_typer` already declares
│   │   ├── __init__.py                   re-exports `app`, so `interfaces.cli:app` keeps resolving
│   │   ├── main.py · options.py          the app, Ctx, the shared option decoding
│   │   ├── lifecycle.py           305    new · eval · run · resume · stop · decide · status · list · events · watch
│   │   ├── lessons.py 165 · proposals.py 141 · output.py 122 · setup.py 101 · integrate.py 93
│   ├── api.py · render.py · interactive.py
│   └── tui/                              unchanged: chrome · views · widgets, 47 modules
│
├── agents/  ·  sandbox/                  unchanged
```

Figures are measured where a module moves whole and marked `~` where one splits.

## What this shape is called

**A functional core under an imperative shell** (Gary Bernhardt, *Boundaries*, 2012), the shell
being a state machine over a persisted document.

The name fits because the partition above is **by effect**, not by domain and not by level of
abstraction. Each directory states what a module may do to the world:

| | |
|---|---|
| `models/` | says what things are — no behaviour |
| `reading/` | computes judgements — touches nothing, and an import-linter contract says so |
| `engine/` | acts — executes, persists, emits, transitions |
| `project/` | reads the world and turns it into a document |

The measurement that makes the name more than a label is the pairing it exposes: **one pure reader
and one executing driver per check** — `reading/suite.py` with `engine/checks/suite.py`,
`reading/reach.py` with `engine/checks/coverage.py`, `reading/mutation.py` with
`engine/checks/mutation.py`. That couple was not introduced here. It already exists, with its
executing half collapsed into one file.

And 495 already states the rule for one function. `docs/decisions/0001` is titled *"A change is
accepted on evidence only; the decision is a pure function"*, and its Decision section says of
`assess`: "It calls no agent and reads no file." What the layout does is carry that from one
function to a package, and from prose to a contract. F5 is what the local version costs: `retrospect`
breaks the same rule one call away, and nothing reports it.

### The second axis

The name covers one axis only. The other — `interfaces` → `core.engine` → `agents` → `sandbox` →
`core.models` — is a **layering by dependency**, fixed by `docs/decisions/0011` and untouched here.
Stated in full: layers by dependency, and inside the core, a functional core under an imperative
shell.

### What it is not

**Hexagonal.** Real ports exist — `Sandbox` and `Agent`, three adapters each — but they predate this
layout, and two ports are not an organising principle. `RunServices` is not a port: it is a bundle
of capabilities, not an interface across which something varies in production.

**Clean architecture.** No use-case layer, no entity/gateway split. `Run` is aggregate-shaped, but
nothing was designed as an aggregate.

**DDD tactical patterns.** No repositories, no domain events as a scheme of organisation.

The vocabulary this review judged with — deep module, seam, the interface as test surface — is the
instrument, not the shape it measured. The two should not be confused in the record.

### Where the name strains

Three places, worth stating so the name is not asked to carry them:

- `models/` is neither core nor shell. It is the vocabulary, underneath both.
- `project/` is shell, but the half that *gathers* rather than the half that *acts*. The full cycle
  is gather → judge purely → act, and "shell" flattens the two ends into one word.
- `RunServices` has no place in the original formulation. Bernhardt's shell needs no internal
  structure; this one is 2 500 lines, so it needs one.

### The mirror

Gather, judge purely, act is also what the harness does to a target: profile, then `assess`, then
deliver and merge. The architecture and the domain would be the same cycle at two scales. That is
either the reason the shape fits so well, or a coincidence worth not over-reading — but it is the
kind of thing a later reader should be told was noticed.

### When this becomes a record

Not yet. `AGENTS.md` requires a decision record to name every module and test that carries the
decision, and none of the modules above exist. If the layout is applied, `docs/decisions/0029` is
where this section belongs, and it would have to name: `core/reading/` and the contract that keeps
it pure, the reader-and-driver pair per check, `engine/services.py`, and `tests/test_architecture.py`
as the test that carries it. [06-plan.md](06-plan.md) T13 is where it is written, and it cannot be
written before T7, T9, T10 and T11 have landed — `AGENTS.md` requires a record to name every module
and test that carries the decision, and none of them exist yet. Until then the claim lives here,
where everything is a proposal.

## The stopping rule

The question the tree above cannot answer on its own is where to stop. Three cases, and the
discriminator is measurable in each.

**Several concepts in one file → split by concept.** The test is whether the parts call each other.
Zero or near-zero cross-calls means they were never one thing. `models.py` (median one section per
commit), `engine.py` (one call between seven phases), `checks.py` (zero calls between five checks),
`cli.py` (seven command groups) all fail this test and should be split.

**One concept, once per case, and the file grows per case → split by case.** Adding a case then adds
a file instead of editing a shared one. `coverage.py` at 849 lines is six technology tables behind
one 215-line marker vocabulary, and it grows by 40 to 175 lines each time a technology is added.
Split it. `reach.py` at 443 has the same shape and has not yet earned it.

**One concept, flat peer-set, stable size → keep.** `context.py` is `ContextPack` plus sixteen
renderers, median 20 lines; `suite.py` is eleven runner parsers, median 8; `prompts.py` is prompt
text. These are long because the world has many cases, not because the file has many jobs.
Splitting them buys a reader nothing and costs an index.

One thing the rule does not cover, found while applying it: `reading/decide.py` is 392 lines of
which **`assess()` alone is 345** — one function, and the one `docs/decisions/0001` rests on. That is
a question about function length, not about layout, and it is not addressed here.

## Largest module, before and after

| | Today | After |
|---|---:|---:|
| 1 | `core/engine.py` 3 775 | `core/engine/context.py` 511 |
| 2 | `interfaces/cli.py` 1 614 | `core/reading/lessons.py` 504 |
| 3 | `core/models.py` 1 420 | `core/reading/suite.py` 455 |
| 4 | `core/coverage.py` 849 | `core/reading/reach.py` 443 |
| 5 | `interfaces/tui/shell.py` 736 | `core/engine/prompts.py` 425 |

Every one of the five that remains is in the third category of the stopping rule: a flat peer-set
whose length comes from the number of cases it covers.

## What the contracts become

Today, four contracts carrying eleven `ignore_imports` exemptions. After:

1. *(unchanged)* `interfaces` is outermost.
2. *(unchanged)* `sandbox` imports nothing of 495 but `core.models`.
3. *(unchanged)* `agents` import only `sandbox`, `core.models` and `core.pricing`.
4. *(tightened)* Inside `core`, only `core.engine` reaches `agents`, and only
   `core.engine.running` reaches `sandbox` — the two `core.verification -> sandbox` exemptions go,
   leaving nine.
5. *(new)* `core.reading` imports `core.models` and `core.reading` alone. No store, no git, no
   subprocess, no filesystem. F5's remedy, and `AGENTS.md`'s purity invariants enforced rather than
   stated.
6. *(new)* `core.project` does not import `core.engine`.

## What the split does not buy

Worth saying plainly, because it is the one place the layout promises less than it looks like it
promises.

`core/models/__init__.py` re-exports every name, so all 56 import sites keep working unchanged and
the migration is one commit that no other module notices. The price is that
`harness495.core.models` stays a single namespace to import-linter: **no contract can distinguish
who imports the specification models from who imports the evidence models.** The reader gains; the
enforcement does not. Buying the enforcement means dropping the shim and rewriting 56 import sites
in one commit — a change no reviewer can read, which is the opposite of what this review is for.
Take the shim.

## Order

The layout is not a step. It is what the tasks in [06-plan.md](06-plan.md) leave behind if they are
taken one at a time, and every intermediate state is a working repository.

Every part of the tree above is created by one named task, and no part arrives on its own.

| Part of the tree | Task | Effort |
|---|---|---|
| the material of `project/conditions.py` and `reading/catalogue.py` | T4 | S |
| `engine/services.py` | T6 | S |
| `engine/__init__.py`, and `engine/` becomes a package | T12 | S |
| `engine/checks/` — the six modules, with the sequence and its gate | T7 | M |
| `core/models/` — the twelve modules and the re-export shim | T9 | S |
| `engine/running.py` + `reading/verification.py`, and contract 4 tightened | T11 | S |
| `core/reading/` — the nine pure modules, and contract 5 | T10 | M |
| `engine/phases/` — seven modules, one per commit | wave 3 | M |
| `engine/context.py` · `prompts.py` · `schemas.py` — a move, one importer each | wave 3 | S |
| `engine/decisions.py` · `delivery.py` · `interventions.py` · `reading.py` | wave 3 | M |
| `core/project/`, and contract 6 | wave 3 | S |
| `project/coverage/` — one module per technology | wave 3 | S |
| `interfaces/cli/` — six command modules, `main`, `options`, the shim | wave 3 | M |
| the records, `AGENTS.md`, `docs/architecture.md`, and `0029` | T13 | S, per move |

`core/models/` is the one that can be done first and alone: it depends on no other task, it has no
cycles to untangle, and the re-export shim means nothing outside the package changes.

Two orderings are not free. `engine/` must be a package (T12) before the checks can move into it
(T7), and `verification.py` must be split (T11) before contract 5 can pass (T10) — two of the
modules that contract covers import, today, a module that imports `sandbox`.
