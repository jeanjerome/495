# Sequenced work, and what is the requester's to settle

Nothing here has been applied. The repository is untouched by this review, apart from the eight
documents in this directory.

**The target is the tree drawn in [07-layout.md](07-layout.md)** — not a direction, that tree.
Every part of it is created by a task named below, and the *Order* table at the end of that file
maps the correspondence both ways. Nothing in the layout is left to arrive on its own.

## How the work is cut

A task is the smallest unit that carries its own test cycle and could be rejected while its
neighbour is approved. Setup and documentation fold into the task whose deliverable needs them.
Every task ends on something independently testable — which is the same bar `docs/decisions/0001`
sets for a requirement, applied to the work that changes the harness.

Effort follows the étude's scale: **S** under a day, **M** a few days, **L** a week or more.

### The tests migrate with the modules they measure — `E51` (a)

`E51` (a) is open: the suite of 495 still holds **187 tests written as plain functions**, against
290 Gherkin scenarios in 19 feature files. The étude asks that they migrate *au fil des
modifications*, the acceptance tests of `test_engine.py` and `test_cli_api.py` first. This chantier
moves nearly every module those tests exercise, which makes it the occasion the entry was written
for.

```
$ ast: test functions in tests/*.py with no scenarios() binding
test_tui.py 40 · test_engine.py 35 · test_profile_verification.py 24 · test_tui_pilot.py 18
test_tui_asking.py 13 · test_agents.py 11 · test_scope_decide.py 11 · test_cli_api.py 9
test_models_store.py 8 · test_sandbox_budget_pricing.py 7 · test_catalogue.py 6
test_live.py 4 · test_architecture.py 1                                       = 187
```

The rule, from `docs/decisions/0013` and unchanged by this review: a test **of a behaviour** becomes
a Gherkin scenario in a `.feature` file bound by pytest-bdd; a test of another contract keeps
Given/When/Then in its name and its body and asserts only in the *then* part.

Applied to the tasks below:

- Every task that moves a module migrates the tests of that module in the same commit. A move that
  leaves its tests in the old form is not done.
- Every task that writes new tests writes them in the target form from the start — T8 in
  particular, whose four checks already have `tests/features/{stability,suite,reach,mutation}.feature`
  to bind to.
- T7 and the phases split reach `test_engine.py`'s 35 functions, which are the acceptance tests the
  étude names first. They migrate as the region they exercise leaves the engine.
- `test_architecture.py`'s single function is a contract test, not a behaviour: it keeps its shape
  and gains the Given/When/Then naming.

**Done when** `E51` (a) can be marked closed: no test function remains outside the two forms, and
the count above reads zero. The étude is the requester's document; this review proposes, and does
not write, that closure.

---

## Wave 1 · Guards, before anything moves

Five tasks. Three change no behaviour at all; T3 and T4 each change one thing deliberately, and say
which. Together they are the net that makes wave 2 safe, and each is worth doing whether or not
wave 2 happens.

### T1 · Bind the decision kinds to their stops · S

**Files** · `tests/test_tui.py` (or a new `tests/test_decision_kinds.py`)

A test asserting `set(DECISION_STAGE) == set(DecisionKind)`, and a second asserting every
`EvidenceKind` member is constructed somewhere in `harness495/`.

**Done when** both tests exist and F2's two dead `EvidenceKind` members are either constructed or
removed. `DecisionKind.scope` is *not* settled here — it waits on Q1.

**Note on removal.** `EvidenceKind` is a field of a persisted model, so `Run.model_json_schema()`
carries its members and `495 schema run` publishes them. Removing `diff` and `agent_output` changes
that published output — in the direction `docs/architecture.md` already documents, which names ten
kinds and omits both. Worth stating in the commit; nothing archived can hold a member never
constructed.

### T2 · Make the decision cascade exhaustive · S

**Files** · `harness495/core/engine.py:440-574`

Convert the outer `if`/`elif` over `DecisionKind` to `match kind:` with `case _: assert_never(kind)`,
and give `acceptance` an explicit case saying it is recorded by the harness and never raised.

**Done when** `mypy --strict` fails on a `DecisionKind` member with no case, verified by adding one
temporarily. No behaviour changes; the existing suite is the regression check.

### T3 · Give the salvage path a rule and a test · S · changes behaviour

**Files** · `harness495/core/engine.py:3430-3451`, `tests/test_engine.py`

Decide which candidate wins when several parse — the last, or the largest — write it in the
docstring, and cover it: prose, one fence, two fences, a `jsonc` fence, a brace span inside prose,
unparsable text.

This is the one task in wave 1 that changes what the code returns, and it changes it on purpose:
today's rule is neither chosen nor stated (F1). Any agent answer with two parsable JSON objects is
read differently afterwards.

**Done when** `_parse_json_text` has no unexecuted line, and the two-fence case asserts which block
is returned.

### T4 · Stop `retrospect` reading the tree · S · changes behaviour

**Files** · `harness495/core/catalogue.py`, `harness495/core/profile.py`,
`harness495/core/models.py`

F5. Evaluate each conditional catalogue entry's predicate once, at profiling, and record the outcome
on the profile; `applicable()` reads the recorded outcome instead of opening `build.gradle.kts`.

A retrospective taken after the tree changed now answers as the run measured it rather than as the
tree stands — which is what `docs/decisions/0015` already claims, and a change in what the command
returns all the same.

The predicates are separated from the recommendation data in the same commit, which is what makes
them movable: they become `project/conditions.py` and the data becomes `reading/catalogue.py` at
T10 and T11. A contract would be the stronger guard, but it cannot be written against today's flat
`core/` — the edge that broke the rule (`retro` → `catalogue`) is a legal core-to-core import.

**Done when** the two-call proof in F5 returns the same entry both times for one `ProjectProfile`,
and `retrospect` reaches no predicate that touches a path.

### T5 · Run the four documented commands on every push · S

**Files** · `.github/workflows/` (new)

`pytest`, `ruff check` and `format --check`, `mypy`, `lint-imports` — the four already in
`README.md` §Development. Nothing new is decided; what is already the contract becomes enforced.

Add, in the same workflow, the report Q4 settles on: the largest module of `harness495/` and its
delta against the merge base, printed in the job summary. It gates nothing. It is the only thing in
this plan that would have reported the finding this review opened with, on the day it happened.

**Done when** a pull request that breaks any of the four is reported as failing, and the summary of
a pull request that grows a module says by how much.

---

## Wave 2 · The internal seam

Depends on wave 1 for its net. [04-deepening.md](04-deepening.md) D1 is the design.

### T6 · Name the services · S

**Files** · `harness495/core/engine.py`

Introduce `RunServices` carrying the seven collaborators every region already reaches for — `store`,
`sandbox`, `emit`, `warn`, `worktree`, `stop_check`, `set_status` — construct it once in
`Engine.__init__`, and have the engine's own methods use it. No method moves yet.

The seven are what four of the seven regions reach for and nothing else. They are not the whole
boundary: the checks region reaches two further members, the interventions region one, the phases
region eight at 35 call sites ([04-deepening.md](04-deepening.md) D1, last column). T6 names the
seven; each later move states what it does with what it reaches beyond them.

**Done when** the seven are reached through `RunServices` rather than through `self`, and the suite
is unchanged.

### T12 · Make `core/engine` a package without moving its interface · S

**Files** · `harness495/core/engine.py` → `harness495/core/engine/`, `pyproject.toml`

The mechanical half of T7, taken first and alone so that the move that follows is reviewable.
`engine.py` becomes `engine/engine.py` under a package whose `__init__.py` re-exports what the rest
of the repository imports by name:

```
$ grep -rhn "core.engine import" harness495/ tests/ | sed 's/.*import //' | sort -u
Engine · EngineError · _clarify_frontier · _spec_from_agent
```

Twelve import sites across five modules of `interfaces` and four test modules. `Engine` and
`EngineError` are the interface and stay so. The other two are module-level free functions of the
agent-output mapping, which [07-layout.md](07-layout.md) sends to `engine/reading.py`:
`_spec_from_agent` is imported by `interfaces/cli.py:282` and `interfaces/api.py:210` — two modules
outside `core` reaching past the public interface, which is the one hole in the external seam
([02-measured-state.md](02-measured-state.md)). It loses its underscore and becomes
`engine.spec_from_agent`, re-exported from the package. `_clarify_frontier` stays private and its
one test follows it to its new module.

The four `ignore_imports` lines of contract 4 that read `harness495.core.engine -> …` become
`harness495.core.engine.** -> …` in the same commit, or the contract stops covering the package.

**Done when** no import site outside `core/engine/` has changed except the two that named
`_spec_from_agent`, `lint-imports` reports every contract kept, and the full suite passes
unchanged.

### T7 · Move the instruments region behind the seam · M

**Files** · `harness495/core/engine/engine.py` → `harness495/core/engine/checks/`

The 17 definitions of the verification-and-instruments region — 1 001 lines — take a `RunServices`.
The region reaches two things outside itself: `_raise_decision`, for the instrument-fault question,
which becomes a returned value the engine raises; and `_ensure_sandbox`, which the seam already
carries as `sandbox`.

Land them as `engine/checks/` directly rather than as one `checks.py`: the five groups make zero
calls to each other, so the sub-split costs nothing extra at the moment the region moves, and costs
a second migration if deferred ([04-deepening.md](04-deepening.md) D4).

**Interfaces** · consumes `RunServices`; produces `list[Evidence]` and an optional
`PendingDecision`. `Engine`'s twelve public methods do not change; `docs/decisions/0011` does not
change.

**Done when** the package imports no agent and no phase, the engine's public interface is unchanged,
the records that name the moved functions name their new module (T13), and the full suite passes.

### T8 · Test the region through its own interface · M

**Files** · tests for the new package

A `RunServices` with a recording store and a fake sandbox; scenarios for the stability, suite,
coverage and mutation checks reached directly rather than by driving a run to `produced`.

Written as Gherkin from the start: `tests/features/{stability,suite,reach,mutation}.feature` exist
and are what these scenarios bind to.

**Done when** the region's coverage is measured on its own, and the scenarios that exist today reach
it without the engine.

---

## Wave 2 bis · `core/models/` — independent of everything above

### T9 · Turn `models.py` into a package · S

**Files** · `harness495/core/models.py` → `harness495/core/models/`

Twelve modules along the twelve comment-delimited sections, with `__init__.py` re-exporting every
name. Ordering is constrained only by the 30 references evaluated at import time, which form a DAG;
annotations are lazy and impose nothing.

**Done when** no import site outside the package has changed, `mypy --strict` passes, and
`lint-imports` still reports every contract kept.

Takeable before, during or after wave 2: it shares no file with any other task. See
[04-deepening.md](04-deepening.md) D5 for the measurement that reversed this candidate, and
[07-layout.md](07-layout.md) for what the re-export shim costs.

---

## Wave 2 ter · The pure core, and the contract that keeps it pure

T4 removed the impurity. These two make it impossible to reintroduce. **T11 comes before T10**: the
purity contract cannot pass while two of the modules it covers import a module that imports
`sandbox`.

### T11 · Split `verification.py` in two · S

**Files** · `harness495/core/verification.py` → `harness495/core/engine/running.py` and
`harness495/core/reading/verification.py`

287 lines of the file are pure functions of strings and documents; 117 are `run_verification` and
`run_control`, which execute in the sandbox and are called from `engine.py` alone. `git` and
`Sandbox` are imported for those two functions only.

The split is what unblocks the contract. `reading/diff.py` and `reading/suite.py` are pure, and both
import the 14-line predicate `looks_like_a_test` from this file — so today they depend on a module
that imports `sandbox`, which is why contract 4 carries `core.verification -> sandbox` as an
exemption.

**Done when** the two `core.verification -> sandbox` exemptions are gone from `pyproject.toml`,
contract 4 reads *only `core.engine.running` reaches `sandbox`*, and `lint-imports` reports every
contract kept. Nine exemptions remain, down from eleven.

### T10 · `core/reading/`, and the contract that says it is pure · M

**Files** · nine modules of `harness495/core/` → `harness495/core/reading/`, `pyproject.toml`,
`tests/test_architecture.py`

`decide` 392 · `lessons` 504 · `retro` 333 · `stats` 220 · `suite` 455 · `reach` 443 ·
`mutation` 227 · `diff` 145 · `scope` 80 — 2 799 lines that touch nothing — plus `catalogue`'s
recommendation half from T4, some 330 more. After T4 and T11 they import `core.models`, each other,
and nothing else.

Contract 5, new and `forbidden`: `harness495.core.reading` may import `harness495.core.models` and
`harness495.core.reading`. No store, no git, no sandbox, no subprocess, no filesystem. This is
`AGENTS.md`'s purity invariants — today upheld by discipline with nothing enforcing them
([02-measured-state.md](02-measured-state.md)) — turned into a test.

`tests/test_architecture.py` asserts the literal string `Contracts: 4 kept, 0 broken`. It becomes
`5 kept` here and `6 kept` at contract 6 in wave 3. The assertion is the reason the count is worth
stating in the task rather than discovering in a failing run.

**Done when** `lint-imports` reports `Contracts: 5 kept, 0 broken`, `tests/test_architecture.py`
asserts the new count, the 29 import statements naming the moved modules are updated, and F5's
remedy is a rule the build enforces rather than a paragraph in a record.

---

## Wave 3 · The rest of the tree

Every remaining part of [07-layout.md](07-layout.md), each its own commit, each with an effort.
None depends on another except where said.

| | What it creates | Effort |
|---|---|---|
| **D4** | `engine/checks/` behind a declared sequence — no longer a later step: it is what T7 produces, since the five groups make zero calls to each other | — |
| `engine/phases/` | seven modules, 89 to 214 lines, one call between them in total (`produce` → `design_tests`, per `0020`); `step` is already a dispatch table. One phase per commit. The region reaches eight members beyond `RunServices`, so the first phase to move settles what widens the seam and the other six follow it | M |
| `engine/context.py` · `prompts.py` · `schemas.py` | a move, not a split: each has exactly one importer, `engine.py`, and each sits today at the level of modules ten others depend on | S |
| `engine/decisions.py` · `delivery.py` · `interventions.py` · `reading.py` | the four remaining regions, once the phases are out; `reading.py` is where `spec_from_agent` and `_clarify_frontier` land (T12) | M |
| `core/project/` | `profile.py`, `proposals.py`, `conditions.py` (from T4) and `coverage/`; plus contract 6, `forbidden`: `core.project` does not import `core.engine`. `tests/test_architecture.py` reads `6 kept` | S |
| `project/coverage/` | one module per technology — 175 · 147 · 137 · 79 · 58 · 38 — behind the 215-line marker vocabulary. Lowest priority of the set: it is the file that grows when a technology is added, not when a feature is | S |
| `interfaces/cli/` | six command modules along the two sub-apps `add_typer` already declares, plus `main.py`, `options.py` and an `__init__.py` re-exporting `app`. Also surfaces ~180 lines of printing that live in `cli.py` and belong in `render.py`. Size and coverage are separate problems; a command is easier to test in a 200-line module than at line 1 100 of 1 614 | M |
| **D3** | one intervention returning a validated document. Independent of D1 and worth taking on its own; it is what gives `_parse_json_text` a single call site | S |
| **D2** | the decision registry. Worth taking when the *next* decision kind is added, so it is built against a real second case. T1 and T2 carry most of its safety until then | M |
| **L1** | the `instrument` rename — `reach.Instrumented` → `UnderCoverage`, `engine._instrument` → `_under_coverage`. Internal names only, no persisted document changes. Cheapest before T7 moves the region | S |

**Not in this plan, and measured.** The coverage deficit concentrates in `interfaces`, not in the
engine: 670 statements missed across `interactive` 100, `cli` 263, `loops` 168, `api` 55, `app` 46
and `keys` 38, against the engine's 193 ([02-measured-state.md](02-measured-state.md)). Only
`interactive.py` is addressed here, by Q2. The rest is a second chantier, on a second axis, and
naming it is the whole of what this plan does about it.

---

## T13 · The documents follow the modules · S, and once per move

**Files** · `docs/decisions/0001`..`0028`, `AGENTS.md`, `docs/architecture.md`, plus a new test

`AGENTS.md` requires of a decision record: *"Done when the record names every module and test that
carries the decision."* The layout renames most of what they name.

```
$ documents citing a harness495 module path that the layout moves
27 of the 28 decision records · AGENTS.md (7 paths in the invariants)
docs/architecture.md §Packages and their boundaries — every core module, by name
209 distinct module paths cited across docs/ and AGENTS.md, 0 stale today
```

Two halves, and the order matters.

**Per move.** Each task above updates, in its own commit, the records that name what it moved. A
move whose records still point at the old path is not done — it is the same bar the task's own
*Done when* sets, applied to the documents that carry the decision.

**Once, at the end.** `docs/architecture.md` §*Packages and their boundaries* is rewritten around
the tree rather than the flat list, and gains the second axis [07-layout.md](07-layout.md) names:
layers by dependency, and inside the core a functional core under an imperative shell. `AGENTS.md`
gains one line under **Pointers** for the glossary (Q3) and its seven invariant paths are updated.

**The guard.** A test that reads every `harness495/…py` path cited in `docs/**/*.md` and `AGENTS.md`
and asserts the file exists. 209 distinct paths today, none stale — so it passes before the chantier
starts and fails the moment a module moves without its records following. It costs ten lines and it
is the difference between remembering to update the documents and being told.

**Done when** the test exists and passes, `docs/architecture.md` describes the tree that is on disk,
and `docs/decisions/0029` — the architecture as a functional core under an imperative shell,
partitioned by effect — is written. `AGENTS.md` requires that record to name every module and test
that carries it, so it cannot be written before T7, T9, T10 and T11 have landed;
[07-layout.md](07-layout.md) states what it would have to name.

---

## Order at a glance

Every task, and what of [07-layout.md](07-layout.md) it leaves behind.

| | Task | Creates | Blocks / blocked by |
|---|---|---|---|
| 1 | T1 · decision kinds bound to stops | — | — |
| 2 | T2 · exhaustive cascade | — | — |
| 3 | T3 · salvage path | — | — |
| 4 | T4 · `retrospect` stops reading the tree | the material of `project/conditions.py` and `reading/catalogue.py` | before T10 |
| 5 | T5 · CI, and the growth report | — | — |
| 6 | T6 · `RunServices` | `engine/services.py` | before T7 |
| 7 | T12 · `core/engine` becomes a package | `engine/__init__.py` | before T7 |
| 8 | T7 · the checks move | `engine/checks/` | after T6, T12 |
| 9 | T8 · the checks are tested on their own | — | after T7 |
| 10 | T9 · `models.py` becomes a package | `core/models/` | independent |
| 11 | T11 · `verification.py` splits | `engine/running.py`, `reading/verification.py` | before T10 |
| 12 | T10 · the pure core and contract 5 | `core/reading/` | after T4, T11 |
| 13 | wave 3 | `engine/phases/` · `engine/{context,prompts,schemas,decisions,delivery,interventions,reading}.py` · `core/project/` + contract 6 · `project/coverage/` · `interfaces/cli/` | after T7 |
| 14 | T13 · the documents follow | `docs/decisions/0029` | per move, then once |

Every intermediate state is a working repository: the suite passes, the contracts hold, and
`495` runs.

**On landing this against a moving repository.** The engine took 100 to 420 lines per invariant over
the two days this review measured, and the étude holds roughly fifteen open entries at medium or
high priority. T7 moves 1 001 lines of the file those entries will touch. Two ways to keep that from
becoming a merge problem, and the choice is Q5's neighbour rather than this plan's: take T6, T12 and
T7 in one uninterrupted run, or take them at a moment when no étude entry is in flight. What does
not work is taking them over a week of feature commits.

---

## Entries this would warrant in the étude

Proposed, not written. `docs/etude-harnais-495.md` is untouched by this review, and assigning an
`E` id is the requester's act.

| Finding | Why it warrants an id |
|---|---|
| F1 | A wrong specification can reach the requester; it is a defect, not a structural preference |
| F3 + D1 | The observation orphaned inside the resolved `E45` — `engine.py` concentrating phases, decisions, calibration, merge and integration — with the growth curve that gives it a priority |
| F6 | Distinct from `E49`, which is about 495 *having* a CI mode |
| L1 | One word, two meanings, one of them load-bearing in the model |

F2, F4, F5 and L2 sit better as tasks than as entries: each is settled by one change, with no
reading of the harness's behaviour behind it. L2's is Q6.

Evidence for entries that already exist, not new ones:

- **`E46`** (no property or mutation testing on 495 itself) — F1 and F2 are two things mutation
  testing would have reported. They belong under it. Contract 5 (T10) and contract 6 close the
  *architecture* half of the same entry, which `0011` left partly open.
- **`E51` (a)** (the suite of 495 is not written as behaviour scenarios) — this chantier is the
  occasion it names. See **The tests migrate with the modules they measure**, above.
- **`E12`** (no glossary or typed documents for the specifier) — [05-language.md](05-language.md) is
  what 495 would declare if `E12` were closed and 495 were run against itself.

---

## The frontier

Six decisions whose prerequisites are settled. Each carries a recommendation; none is acted on.

---

**Q1 · `DecisionKind.scope` — wire it up, or remove it?**

It is declared, handled in `_apply_decision`, and mapped to the `change` stop, and no
`PendingDecision` has ever carried it (F2). A scope violation currently becomes a `[scope]`
correction request to the producer (`core/decide.py:339-340`); the requester is never asked.

Removing it is a three-line deletion. Wiring it up means the requester can say "this excursion is
fine" and have the correction dropped — which is what the handler already does.

➡️ **Remove it.** A scope excursion the requester would allow is a specification whose
`allowed_paths` were wrong, and `docs/decisions/0027` already has the mechanism for that: the run
records it as an `allowed_path` lesson, the requester accepts it, and every later run is
specified correctly. A per-run override would let the same wrong scope be waved through run after
run without ever entering the criteria. If it is removed, the reason is worth a line in the record
that mentions it — otherwise it will be proposed again.

---

**Q2 · `interfaces/interactive.py` — delete it, or test it?**

167 lines, 0 % coverage, reached by `./run.sh` with no arguments, so it is the first thing a new
user sees. Three of its seven entries delegate to the TUI or re-enter the CLI. It imports two
`cli` privates (F4).

➡️ **Delete it, and point `./run.sh` with no arguments at the TUI.** The deletion test answers
against it: the TUI already holds browse, open, resume and decide; `report` and `doctor` are CLI
commands one word away. The two entries with no TUI equivalent — "new change" and "evaluate
existing change" — are `ask_intent` in `tui/views/intent.py` and a second prompt. Keeping it means
writing tests for a menu whose purpose is to reach three things that are each better reached
directly.

Against: it is the only surface that works where the TUI cannot run, and `watch()` returns 1 when
there is nothing to open. If that case matters, keep it and test it — but then `_apply_overrides`
stops being private either way.

---

**Q3 · Where does the glossary live?**

[05-language.md](05-language.md) is a draft of one. `domain-modeling` prescribes a root
`CONTEXT.md`; `AGENTS.md` is deliberately under 120 lines of pointers, and a fifth root document
costs a line of always-loaded context.

➡️ **`docs/glossary.md`, with one line in `AGENTS.md` under Pointers**, beside
`docs/test-libraries.md`. Same reach, no new root file. If `E12` is closed, it is also what 495
declares under `ProjectConfig.docs` when run against itself.

---

**Q4 · Does the module growth become a bound, or a report?**

`engine.py` grew 52,5 % in two days and nothing measures it. The repository already enforces package
boundaries with import-linter, which cannot express a size.

➡️ **Report it, do not bound it.** A failing test at N lines has one cheap evasion — move code to a
second file without giving it a seam — which is worse than the thing it prevents, because it looks
like progress. A line in the CI summary (largest module, and its delta against the merge base) puts
the number in front of a reader on every change, and the reader decides. T5 carries it. If a bound
is wanted later, it should be a bound on something that resists that evasion: the number of methods
reachable from one `self`, or the number of modules a decision kind touches.

---

**Q5 · Do these eight documents stay, or fold into the étude?**

They sit in `docs/architecture-review/`, a directory the repository did not have. The étude is the
established place for anything with an id.

➡️ **Keep the directory; move the findings.** [01-method.md](01-method.md) and
[05-language.md](05-language.md) are artifacts with a life of their own — the first is the method a
later review re-runs, the second becomes `docs/glossary.md` under Q3. The findings and the
candidates are a snapshot: once the four entries proposed above have ids, the entry is the record
and these documents say what was measured on 2026-09-14 and point at it. A finding recorded in two
places drifts, which is the shape of F2.

---

**Q6 · `watcher` — promote the concept, or retire the word?**

`_repeat_watchers`, `_coverage_watchers` and `_mutation_watchers` each answer the same question:
which verifications does this check select, and in what order. The concept is real and load-bearing
— the selection rules encode `docs/decisions/0022`, `0023` and `0024`. The word appears in 22 lines
of one module and in the documents only as the name of one of those three functions; nothing defines
it, and "watcher" recruits no prior that helps, since nothing is being watched (L2).

Promoting it means defining it in `docs/architecture.md`, giving it a return type, and letting the
report say which verifications each check selected and why one was left out. Retiring it means
naming the functions after what they return: `_verifications_to_repeat`,
`_verifications_to_instrument`, `_verifications_to_mutate`.

➡️ **Retire the word, and take the question it was hiding to the étude.** The rename is free and
lands with T7, which moves all three functions anyway. But the reason to promote it is real and
outlives the name: today the exclusions surface only as warnings (`engine.py:2005-2012`), which is a
thin channel for a decision that determines what the harness can prove. That is a capability gap,
measured on what the harness does rather than on how it is built, and it belongs in the étude with
an id — not in a rename.
