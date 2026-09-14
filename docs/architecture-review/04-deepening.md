# Deepening candidates

Five proposals, two of them corrected after measurement. Each states the files, the friction, the change, and what it wins
in terms of leverage and locality. Strength is a recommendation, not a severity:

| | |
|---|---|
| `Strong` | The measurement supports it and the risk is low |
| `Worth exploring` | Sound, but it depends on a prior change or on a question the requester owns |
| `Speculative` | Stated so it can be dismissed on the record |

Legend for the diagrams: a box is a module, `│` a seam, a figure the measured line count.

---

## D1 · Give the engine internal seams · `Strong`

**Files** · `harness495/core/engine.py` (3 775 lines; 65 methods on `Engine`, 16 free functions)

### Problem

The engine is **deep at its external seam and undifferentiated behind it**. Twelve public methods carry
the whole workflow, and `interfaces` reaches past them at one point only — a free function it
imports twice, not a method (see [02-measured-state.md](02-measured-state.md)). That part is right
and this proposal does not touch it. Behind the interface there is one `self` and 65 methods, every
one of which can reach every other, plus 16 module-level functions sharing the file with them. The
only test surface is the whole machine driven into the right state, which is why 193 statements of
the module are executed by no test and why the least-covered method in the repository is the one
that applies a requester's answer.

The file grew 52,5 % over the 37 commits of 2026-09-13 and 2026-09-14 (see
[02-measured-state.md](02-measured-state.md)). No contract bounds it, because the import contracts
constrain which package may import which and say nothing about what one module may hold.

### What the measurement says

Each region of the engine was scored for what it reaches for on `self`. Every one of the 81
definitions in the file is assigned to exactly one region, so the columns sum to the module:

| Region | Lines | Defs | Unexecuted | Reaches for, beyond the seven |
|---|---:|---:|---:|---|
| phases driving an agent | 1 391 | 16 | 61 | `_fail`×8 `_raise_decision`×7 `_budget_decision`×5 `_ensure_sandbox`×5 `_intervene`×5 `_record_decision`×3 `worktree_path` `_suite_reading` |
| verification and instruments | 1 001 | 17 | 28 | `_ensure_sandbox`×1 `_raise_decision`×1 |
| agent output → models | 329 | 16 | 38 | nothing — already free functions |
| decisions | 220 | 6 | 41 | `decision_handler`×2 `_recalibrate` `_clarify_answers` `_record_clarify_answers` |
| state machine and infrastructure | 190 | 17 | 14 | — it *is* the shared surface |
| deliver, merge, integration | 191 | 6 | 6 | `worktree_path`×2 `label`×2 `_ensure_sandbox` `_integration_message` |
| interventions | 168 | 3 | 5 | `agent_factory`×1 |
| **total in definitions** | **3 490** | **81** | **193** | 285 further lines are imports, the class header and constants |

The seven — `store`, `emit`, `sandbox`, `_worktree`, `_stop_check`, `_warn`, `_set_status` — are
what every region reaches for by way of infrastructure, and they are the only thing four of the
seven regions reach for at all. **That set is the seam**, and it was not designed; it is what the
code already does.

What the last column says is that the seam is not the whole boundary. The checks region has two
edges beyond it and the interventions region one; the phases region has eight, at 35 call sites,
which is why [06-plan.md](06-plan.md) takes the checks out first and leaves the phases to a wave
that can widen `RunServices` against a second real case.

The *Unexecuted* column partitions all 193 uncovered statements and says something the total does
not: there is no soft spot. Every region is under-measured, in rough proportion to its size,
because every region is reached the same single way — by driving a whole run into the state that
calls it.

The agent-output mapping is the exception that makes the point. Those sixteen functions are
already free of `self`, so a test can call any of them directly — and exactly one test does
(`tests/test_clarify_scenarios.py`, on `_clarify_frontier`). The other fifteen carry 38 unexecuted
statements, among them every line of `_parse_json_text` (F1). Where the seam already exists, it is
not used, because nothing about living in a 3 775-line module suggests these functions are reachable
on their own.

The verification-and-instruments region is the cheapest first move: 1 001 lines that touch no agent
and no phase, and reach two things outside themselves — the instrument-fault question, which can be
returned rather than raised, and `_ensure_sandbox`, which the seam already carries as `sandbox`.

### Solution

Name the seven collaborators as one `RunServices` — the store, the sandbox, the event sink, the
warning sink, the worktree resolver, the stop check, the status setter — and move each region into
a module that takes it. The `Engine` class keeps the phases and the state machine, keeps its twelve
public methods unchanged, and constructs it once.

```
BEFORE
                   ┌────────────────────────────────────────────┐
 interfaces ──────▶│ Engine                          3 775 lines│
 12 public methods │ 65 methods on one self + 16 free functions │
                   │  phases 1391 · instruments 1001            │
                   │  mapping 329 · decisions 220               │
                   │  deliver 191 · interventions 168 · sm 190  │
                   │  every method reachable from every other   │
                   │  test surface: the whole machine           │
                   └────────────────────────────────────────────┘

AFTER
                   ┌────────────────────────────────────────────┐
 interfaces ──────▶│ Engine        interface unchanged          │
 12 public methods │ phases + state machine        ~1 600 lines │
                   └──────────────────┬─────────────────────────┘
                                      │  RunServices
                                      │  store · sandbox · emit · warn
                                      │  worktree · stop_check · set_status
              ┌───────────┬───────────┼────────────┬────────────┐
              ▼           ▼           ▼            ▼            ▼
        instruments   decisions  interventions  delivery   (mapping,
          1 001 ln     220 ln       168 ln       191 ln    already free)
        own tests     own tests    own tests    own tests
```

### Wins

- **Locality**: an instrument change lands in one module, not in a file four other concerns share.
- **Leverage**: `RunServices` is learned once and serves every region.
- **The interface becomes the test surface** for each region. Today the mutation, coverage and
  stability checks can only be reached by driving a run to `produced`; behind the seam a test builds
  one and calls the region.
- The seam is real by the two-adapter rule: a production `RunServices` and a test one, the second
  being why the extraction is worth making at all.

### What does not change

The twelve public methods: their signatures and their behaviour. The one free function `interfaces`
imports past them keeps working through the package's `__init__.py` ([06-plan.md](06-plan.md) T12).
This is an internal seam, and `docs/decisions/0011` is untouched.

### Caveat

`RunServices` carries `set_status`, which mutates the run. It is not a pure value object and should
not be dressed as one. It is the engine's own services, named — which is what makes it honest. The
name deliberately avoids `RunContext`: `core/context.py` already owns *context* in the sense of
`ContextPack`, what one agent is given, and a second meaning for the word is the mistake L1 reports.

---

## D2 · A decision option carries what it does · `Strong`

**Files** · `core/models.py:1187-1204` · `core/engine.py:440-574` · `interfaces/tui/stages.py:131-143`

### Problem

One concept — "a question the run puts to the requester" — is spelled in three places that nothing
binds together:

| Where | What it holds |
|---|---|
| `DecisionOption` | `key`, `label`, `needs_note`, `consequence` — everything except what the option *does* |
| `_apply_decision` | what it does, as a 134-line `if`/`elif` cascade with no `else` |
| `DECISION_STAGE` | which stop it belongs to, as a table read through `.get(kind, "verdict")` |

The presentation is already data-driven and correct: `render.print_decision` builds its panel from
`pending.options` and needs no change when a kind is added. The *effect* and the *placement* are
not, and the drift has already happened: `DecisionKind.scope` is declared, handled and mapped, and
raised nowhere (F2). It has been dead since the first commit and nothing reported it.

By the smell baseline this is **Repeated Switches** feeding **Shotgun Surgery**: the same switch on
the same type recurs, and one logical change forces scattered edits.

### Solution

Register an option's effect beside its declaration, so the three facts about an option live in one
place:

```python
@register(DecisionKind.readiness, "drop", stop="profile",
          label="Drop the commands that cannot run",
          consequence="Removes them from the profile and proceeds to the specification.")
def _drop_unrunnable(run: Run, note: str, ctx: RunServices) -> RunStatus:
    bad = {r.command_name for r in run.profile.readiness if not r.executable}
    run.profile.commands = [c for c in run.profile.commands if c.name not in bad]
    run.profile.readiness = [r for r in run.profile.readiness if r.executable]
    return RunStatus.profiled
```

`_apply_decision` becomes a lookup and the common preamble it already performs — validate the
choice, require the note, record the decision, handle `abort`. `DECISION_STAGE` is derived from the
registry rather than maintained beside it. A raise site asks the registry for its options instead of
retyping labels and consequences at nine call sites.

```
BEFORE                                  AFTER

 DecisionKind  ─┬─▶ models.py enum       DecisionKind ──▶ registry
                ├─▶ engine cascade                         key · label · consequence
                │    134 ln, no else                       stop · effect
                │    35 ln unexecuted                          │
                └─▶ stages.py table              ┌────────────┼────────────┐
                     .get(…, "verdict")          ▼            ▼            ▼
                                            _apply_decision  raise sites  stages
 one concept, three modules,                 (a lookup)      (ask)       (derived)
 nothing binds them                     one concept, one place, total by test
```

### Wins

- A kind with no effect fails at import, not on a wedged run.
- An option's consequence and its effect cannot disagree, because they are written together.
- F2 and F3 stop being possible rather than being fixed.
- `_apply_decision` drops from 134 lines of cascade to its preamble.

### Effort and order

Larger than F3's `match` + `assert_never` guard, which is the cheap version of the same protection.
Take the guard first; it costs an hour and buys most of the safety. Take D2 when the next decision
kind is added, so the registry is built against a real second case rather than a hypothetical one.

---

## D3 · One intervention that returns a validated document · `Strong`

**Files** · `core/engine.py` — `_clarify:933`, `_specify:1160`, `_produce:1456`,
`_design_tests:1671`, `_review:2837`

### Problem

Five phases drive an agent, and each repeats the same five-step ritual by hand:

```
$ grep -n "except budget_mod.BudgetExceeded" harness495/core/engine.py
990  1224  1550  1723  2932
$ grep -n "result.structured or _parse_json_text" harness495/core/engine.py
1005  1232  2996
```

1. build a `ContextPack`
2. call `_intervene`, catching `BudgetExceeded` and turning it into `_budget_decision(resume_at=…)`
3. check the result status, `_fail(…, retry_at=…)` if it is not `completed`
4. `result.structured or _parse_json_text(result.text)`, `_fail` if that yields nothing
5. map the dict to a pydantic model, catching `(ValueError, KeyError, TypeError)`, `_fail` again

Steps 2 to 5 are identical at every site but for the status to resume at and the model to build.
Step 1 is genuinely different every time, and must stay so — it is the role's context, and
`docs/decisions/0005` rests on each role getting its own.

Two costs. Each new phase re-derives the ritual, and a phase that gets one step subtly wrong is
invisible: `_clarify` appends `or {}` to step 4 and the other two do not, which is a real difference
in behaviour that no reader would notice as deliberate.

### Solution

One method carrying steps 2 to 5, with the pack and the mapping supplied by the caller:

```python
def _ask(self, run, role, capability, system, pack, schema,
         build: Callable[[dict], T], retry_at: RunStatus) -> T | Run:
```

It returns the built document, or the `Run` the failure produced. The phase keeps what is its own —
the pack, the model, what to do with it — and stops owning budget, status, parsing and schema
failure.

### Wins

- **Locality**: `_parse_json_text` acquires one call site, which is what makes F1 fixable once
  rather than three times.
- **Leverage**: a sixth role costs a pack and a builder.
- The `or {}` divergence becomes a decision someone makes, not an accident three readers scroll past.

---

## D4 · One module per check, behind a declared sequence · `Strong`

**Files** · `core/engine.py:1818-1949` and the 1 002-line instruments region

### Problem

`_verify` inlines eight stages in sequence — scope, protected tests, the verifications, the repeat,
the suite, the calibration, the reach, the mutation — each producing `Evidence`, each with its own
signature, and two of them gated on `it.instrument_faults`. The order and the gate carry real
meaning: `docs/decisions/0023` and `0022` both say that measuring reach and mutants against a blind
instrument would describe the instrument, not the tests.

The friction is that the ordering rule is expressed only as the order of statements in a 132-line
method, so it cannot be read, tested, or reported without reading that method.

### Solution

Declare the sequence as a list of checks, each `(run, iteration, evidence) -> list[Evidence]` with
its gate stated beside it, and let `_verify` walk it.

### What the measurement says

The region's eighteen methods fall into five check groups and one orchestrator, and the groups do
not talk to each other at all:

| Group | Lines | Functions | Calls into another group |
|---|---:|---:|---|
| orchestration (`_verify`) | 132 | 1 | all five — that is its job |
| calibration | 261 | 3 | none |
| mutation | 184 | 3 | none |
| coverage | 153 | 3 | none |
| stability | 143 | 3 | none |
| suite | 69 | 2 | none |

Each group also pairs with a pure reader that already exists: stability with
`verification.reports_the_same_twice`, suite with `suite.py`, coverage with `reach.py`, mutation
with `mutation.py`. The shape is already there — a pure reader and an executing driver per check —
and only the driver half is collapsed into one file.

### Wins

- The order becomes readable and assertable, and `495 schema` could publish it.
- A check is testable without driving a run to `produced`.
- A new check is a new module plus one line in the sequence, not an edit to a 1 000-line file.

### Corrected from `Worth exploring`

This candidate first hedged, on the ground that the gate is not uniform — `instrument_faults`
blocks reach and mutation but not the suite check — so a list would flatten a distinction the ADRs
make deliberately. That objection survives and is answered by the measurement rather than by the
hedge: the gate lives in `sequence.py`, 132 lines, alone, and the five groups behind it share
nothing. Splitting them is not an abstraction over a distinction; it is a split along a line the
code already draws.

D1 still comes first — the checks need `RunServices` before they can leave — but the outcome is no
longer in doubt.

---

## D5 · Split `models.py` into a package · `Strong` — reversed

**Files** · `core/models.py` (1 420 lines, 77 classes, 12 comment-delimited sections)

**This candidate first argued against the split. The measurement overturns it, and the reversal is
recorded rather than quietly edited.**

The original argument had two legs. The first: "its twelve sections are the seams a package would
create." True — and it is the argument *for* the split, not against it, since the seams are already
drawn and the work is to make them cost something. The second: "splitting reduces nothing, because
a change touching `Spec` touches `Spec` wherever it lives." Also true, and beside the point. What
changes is not which class a commit edits but how much file a reader opens to edit it.

### What the measurement says

Sections touched per commit, over the last 25 commits that changed the file:

```
commits par nombre de sections touchées : {1: 11, 2: 5, 3: 2, 4: 1, 6: 1, 9: 1}
médiane : 1
```

**Eleven of twenty-one commits touch exactly one section; sixteen touch one or two.** The outliers
are the package rename (nine, mechanical) and the clarification feature (six, the largest structural
change in the history). A typical change to the vocabulary is a change to one 100-to-200-line
module, presented today as a change to a 1 420-line file.

And the split is mechanically safe, which the original text did not check:

- **Zero cycles** between the 77 classes, annotations included.
- The 30 references evaluated at import time form a clean DAG — `Run -> Budget, Clarification,
  Consumption, HarnessConfig, RunMode, RunResult, RunStatus, Spec` and fifteen others, no loop.
- `from __future__ import annotations` is already on, so every type annotation is lazy and only
  those 30 constrain module order.

### Solution

Twelve modules under `core/models/`, with `__init__.py` re-exporting every name so all 56 import
sites keep working. See [07-layout.md](07-layout.md) for the split and for what it does *not* buy:
the shim keeps `harness495.core.models` a single namespace to import-linter, so the reader gains and
the enforcement does not.

### Still true from the original

The deletion test answers in the vocabulary's favour — it is one concept and belongs in one place.
A package is one place. Scattering the 77 classes across `core/` would be the move to refuse; this
is not that move.

## Considered and not opened

**The four renderers of one domain.** `core/context.py` renders for agents, `core/report.py` for the
Markdown report, `interfaces/render.py` for the terminal, and `tui/views/` for the screens. Four
spellings of "show a specification" looks like duplication and is not: the audiences differ, and the
deletion test says complexity would move rather than vanish. The real risk — a model field reaching
one renderer and not the others — has already occurred and is already owned by the étude as `E47`
(`assumptions` and `out_of_scope` absent from the report). Nothing to add.

**`coverage.py` at 849 lines.** Six marker tables, one per technology, at 100 % coverage. It is data
in the shape of code, and the shape is right: the markers are predicates, not rows.
