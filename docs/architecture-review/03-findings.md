# Findings

Six defects. Severity is calibrated, not inflated: one is Critical and five are Important. Each
carries the measurement that produced it, a concrete failure scenario, and a remedy.

| | Finding | Axis | Effort |
|---|---|---|---|
| **F1** | The salvage path that parses an agent's prose returns the first JSON object it finds | Structure | S |
| **F2** | `DecisionKind.scope` is declared, handled and mapped in three modules, and raised nowhere | Contract | S |
| **F3** | `_apply_decision` has no exhaustiveness guard and is the least-measured method in the engine | Structure | S |
| **F4** | The default entry point is executed by no test and reaches into `cli` privates | Structure | M |
| **F5** | `retrospect` is documented as a pure function of the run document and reads the project tree | Contract | S |
| **F6** | The repository has no automated gate | Structure | S |

---

## F1 · Critical · The salvage path returns the first JSON object it finds

`harness495/core/engine.py:3430-3451`

```
$ .venv/bin/python -m coverage json -o /tmp/cov.json
   missing lines 3431..3451   # the entire body of _parse_json_text
```

**What it is.** `_parse_json_text` is the fallback taken whenever an agent CLI returns prose rather
than structured output. Three roles depend on it:

```
engine.py:1005   data = result.structured or _parse_json_text(result.text) or {}   # clarifier
engine.py:1232   data = result.structured or _parse_json_text(result.text)         # specifier
engine.py:2996   data = result.structured or _parse_json_text(result.text)         # reviewer
```

It builds a candidate list — the whole text, then every fenced block, then the span from the first
`{` to the last `}` — and returns **the first candidate that parses as a dict**.

**Failure scenario.** A specifier is asked for a specification and answers:

````
Here is the shape I will use:

```json
{"requirements": [], "verifications": []}
```

And here is the specification:

```json
{"requirements": [{"id": "R1", ...}], "verifications": [{"id": "V1", ...}]}
```
````

`text.split("```")[1::2]` yields both blocks in order. The loop returns the **first** dict that
parses — the illustrative example. The run proceeds with an empty specification, the gate shows the
requester a spec with no requirements, and nothing anywhere reports that the agent's actual answer
was discarded. There is no evidence to read: the discarded block never becomes an artifact.

The same mechanism mis-reads a reviewer that illustrates a finding before stating its verdict, and a
clarifier that shows the option shape before listing its questions.

**Why no test caught it.** `tests/conftest.py::FakeAgent` sets `structured` on every path
(`conftest.py:266-304`), so `result.structured or …` short-circuits and the fallback is never
reached. The double is shaped like the happy path of the CLI it stands for, which is exactly the
"mock at the right level" failure: the slow, external thing was replaced along with the parsing
behaviour that depends on it.

This is also what `docs/decisions/0022` exists to catch in a *host* project — a wrong version of the
code that no command reports. 495's own suite has one, and 495 does not run mutants on itself
(`E46`).

**Remedy.** `_parse_json_text` is a pure function of a string: it needs no engine, no store, no
worktree. A parametrised test over six inputs — prose, one fence, two fences, a `jsonc` fence, a
brace span inside prose, unparsable text — costs minutes and fixes the shape of the answer. Prefer
the last valid candidate, or the largest, and say in the docstring which and why. Either rule is
defensible; today's rule is neither chosen nor stated.

---

## F2 · Important · A decision kind is declared, handled and mapped, and never raised

```
$ grep -rn "DecisionKind.scope" harness495/ tests/
harness495/core/engine.py:564             elif kind is DecisionKind.scope and choice == "allow":
harness495/interfaces/tui/stages.py:135       DecisionKind.scope: "change",

$ grep -n "kind=DecisionKind\." harness495/core/engine.py
   readiness, readiness, approve_spec, budget, no_progress,
   instrument_fault, iteration_limit, undetermined, clarify      # no scope

$ git log --oneline -S "kind=DecisionKind.scope" -- harness495/
   (nothing)
```

**What it is.** `DecisionKind.scope` is declared in `core/models.py:218`, handled in
`engine.py:564` — a branch that strips `[scope]` corrections from the current iteration and resumes
the run at `produced` — and mapped to the `change` stop in `tui/stages.py:135`. No
`PendingDecision` with that kind is ever constructed, and none ever was: the `-S` search finds no
commit that added or removed one.

What actually happens to a scope violation: `_verify` records a `scope_check` evidence, and
`core/decide.py:339-340` turns a failed one into a `[scope]` correction request sent back to the
producer. The requester is never asked.

**Failure scenario.** Two shapes, both real:

- A reader of `models.py` or `stages.py` concludes the harness can put a scope excursion to the
  requester. It cannot. The affordance is documented by its own declaration and does not exist.
- A later change wires the decision up and inherits a handler nobody has ever executed, in the
  least-covered method of the engine (F3), with no test naming what it should do.

**Why it survived.** The concept lives in three modules that no test cross-checks. `tui/stages.py`
reads it through `DECISION_STAGE.get(kind, "verdict")` — a silent default, so a kind missing from
that table lands on the wrong stop rather than failing. Nothing binds enum, handler and table
together.

**It is a pattern, not an accident.** The same check over `EvidenceKind` finds two more members
declared and never constructed:

```
$ for k in command_result scope_check review_verdict diff integrity agent_output \
           instrument_check baseline suite_check mutation_check coverage_check stability_check; do
    echo -n "$k "; grep -rn "EvidenceKind.$k" harness495/ --include="*.py" | wc -l
  done
   diff 0        agent_output 0        (every other member ≥ 1)
```

`docs/architecture.md` names the ten kinds the harness actually observes and correctly omits both.
The documentation is right and the enum is stale — which is the reverse of the usual failure and
says something good about how this repository is written, but leaves two members a reader will
believe in.

**Remedy.** Not a cleanup to perform unasked: whether the requester should be offered a scope
excursion is a design question, not a dead-code question — see [06-plan.md](06-plan.md) Q1. What is
unambiguous is the guard that would have caught all three, one line:

```python
def test_every_decision_kind_has_a_stop() -> None:
    assert set(DECISION_STAGE) == set(DecisionKind)
```

and, for the evidence kinds, a test asserting that every member is constructed somewhere — which
is what mutation testing on 495 itself (`E46`) would report without a test being written for it.

---

## F3 · Important · The decision cascade has no exhaustiveness guard

`harness495/core/engine.py:440-574` · 134 lines · **35 of them executed by no test**, the highest
figure in the module.

```
$ .venv/bin/python -m coverage json && (per-method missing lines)
   _apply_decision      35 / 134 missing
   _parse_json_text     21 /  22 missing
   _specify             18 / 109 missing
```

**What it is.** `_apply_decision` is an `if`/`elif` cascade over `DecisionKind`, nested inside a
second cascade over the option key. There is no `else`. A `(kind, choice)` pair that matches no
branch falls through to the tail:

```python
run.resume_status = None
self.store.save(run)
return run
```

The decision is recorded as taken, the pending question is cleared, and the run's status is
unchanged — it sits in `awaiting_decision` with nothing pending. Nothing raises, nothing warns.

**Failure scenario.** A new decision kind is added, or an option key is added to an existing kind —
both are the routine shape of a 495 feature. The raise site is written, the presentation is generic
and needs nothing, and the apply branch is forgotten. The requester answers the question, the CLI
reports success, and the run is wedged in a state no phase handler serves. `step` then raises
`no handler for status awaiting_decision` on the next advance, pointing at the status rather than at
the missing branch.

`DecisionKind.acceptance` already has no branch here. That one is correct — it is recorded by the
harness in `_decide` and never raised as a question — but nothing in the type or the code says so,
and it is indistinguishable from an omission.

**Why mypy does not help.** Exhaustiveness checking applies to `match` statements against a closed
type with `typing.assert_never` in the default arm. A chain of `elif kind is DecisionKind.x` is not
a construct mypy can complete.

**Remedy.** Two steps, independent:

1. Convert the outer cascade to `match kind:` with `case _: assert_never(kind)`, and give
   `acceptance` an explicit `case` documenting that it is never raised. mypy strict then fails the
   build on a missing kind. No behaviour changes.
2. The inner cascade over option keys is the deepening in [04-deepening.md](04-deepening.md) D2,
   which removes it rather than guarding it.

---

## F4 · Important · The default entry point is executed by no test

`harness495/interfaces/interactive.py` · 167 lines, 100 statements, **0 % coverage**.

`./run.sh` with no arguments reaches it: `cli.py:122-125` dispatches to `interactive_session` when
no subcommand is given. It is the first thing a new user sees, and the suite does not execute one
statement of it.

**What it is.** Three of its seven menu entries delegate straight out — `_open` calls the TUI's
`watch`, entry 6 calls `render_markdown`, entry 7 re-enters the CLI in-process:

```python
from harness495.interfaces.cli import app
app(["--project", str(c.project), "--state-dir", str(c.state_dir), "doctor"],
    standalone_mode=False)
```

And it reaches into a `cli` private:

```python
from harness495.interfaces.cli import _apply_overrides            # interactive.py:104
config = _apply_overrides(config, agent, None, None, None, None,
                          None, None, None, False, None, None)    # interactive.py:106
```

`_apply_overrides` takes thirteen parameters, three of them consecutive `str | None`
(`producer`, `specifier`, `clarifier`). The call passes twelve positionally, nine of them
`None`/`False`.

**Failure scenario.** A parameter is inserted into `_apply_overrides`, or two of the consecutive
`str | None` parameters are reordered. mypy accepts it — the types match. The interactive session
silently configures the wrong role. No test executes the call, so nothing reports it. The
clarification feature already added a parameter at position 5 and updated this call by hand; the
next one has the same exposure and no net.

**On the deletion test.** Deleting `interactive.py` would move complexity, not concentrate it: the
TUI already holds browse, open, resume and decide, and `doctor` and `report` are CLI commands. That
is the signature of a shallow module. Whether to delete it or to test it is a decision for the
requester, not a refactor to perform — see [06-plan.md](06-plan.md) Q2.

**Remedy either way.** `_apply_overrides` is called from three sites across two modules; it is part
of `cli`'s interface in fact if not in name. Rename it, or move it beside the config it builds.
An underscore that two modules ignore is not a seam.

---

## F5 · Important · `retrospect` is documented as pure and reads the project tree

`docs/decisions/0015`, Consequences, first bullet:

> A retrospective is a pure function of the run document (`core/retro.py::retrospect`), like the
> decision (0001): it reads evidence, iterations, the spec and the profile, **never the events, the
> outputs or the tree**. A run archived with `495 export` yields the same retrospective anywhere.

It reads the tree. `retro.py:292`, inside `retrospect()`:

```python
entry = applicable(technology, role, run.profile) if run.profile is not None else None
```

`catalogue.applicable` evaluates each conditional entry's predicate (`catalogue.py:306`), and five
of those predicates open files under `profile.root` — which is the requester's checkout
(`engine.py:754`), not the run's worktree, so it outlives the run:

```
catalogue.py:92    _uses_express        →  package.json / node_modules
catalogue.py:116   _is_kotlin           →  build.gradle.kts · build.gradle · pom.xml
catalogue.py:134   _is_kotlin_on_gradle →  build.gradle.kts · build.gradle
```

**Measured, not inferred.** Same `ProjectProfile` object, one file touched between two calls:

```
$ .venv/bin/python - <<'PY'
  prof = ProjectProfile(root=str(tmp), languages=["java/kotlin"])
  (tmp / "build.gradle.kts").write_text('plugins { kotlin("jvm") version "2.0.0" }')
  print(applicable("java/kotlin", CatalogueRole.runner, prof).tools)   # ('kotest',)
  (tmp / "build.gradle.kts").unlink()
  print(applicable("java/kotlin", CatalogueRole.runner, prof).tools)   # ('junit-jupiter',)
  PY
```

**Failure scenario.** A JVM project runs on Monday while `build.gradle.kts` declares Kotlin; the
retrospective would propose the `kotest` row. The requester drops the Kotlin plugin on Tuesday.
`495 retro <run-id>` on Monday's run now proposes `junit-jupiter` — a catalogue row for a run that
measured a Kotlin project, presented as read from the run document. Nothing marks it as derived
from the tree's present state.

Worse on an exported run: every predicate swallows `OSError` and returns `False`
(`catalogue.py:100-102`, `128-131`), so a run replayed where `project_root` no longer exists gets
the default entry silently, with no error and no warning.

**Why the earlier check missed it.** Grepping each pure module for `open(`, `read_text` and
`subprocess` returns zero across all nine — the I/O is one call away, in a module that is
legitimately impure and that the pure modules legitimately import. Direct inspection cannot see it;
a contract can.

**Remedy, in two parts.** The split is what makes the contract expressible:

1. Evaluate the conditions once, at profile time, and record the outcome on the profile. `applicable`
   then reads the recorded outcome and becomes a pure function of the document, which is what `0015`
   already claims. This is a small behaviour change, not a move.
2. Separate the catalogue's recommendation data from the predicates that read the tree, so a
   `forbidden` import-linter contract over the pure modules can be written at all — see
   [07-layout.md](07-layout.md). Today the offending import (`retro` → `catalogue`) is a legal
   core-to-core edge that no contract could reject without rejecting the whole flat package.

`tests/test_architecture.py` asserts on the literal string `Contracts: 4 kept, 0 broken`, so the
count is part of the change: [06-plan.md](06-plan.md) T10 makes it `5 kept` and contract 6 makes it
`6 kept`. T11 is what makes contract 5 pass at all — `reading/diff.py` and `reading/suite.py` import
`looks_like_a_test` from `verification.py`, which imports `sandbox`.

---

## F6 · Important · The repository has no automated gate

```
$ ls .github          # no such file or directory
$ ls .pre-commit-config.yaml   # no such file or directory
```

Four commands documented in `README.md` §Development — `pytest`, `ruff check` and `format --check`,
`mypy`, `lint-imports` — all run by hand. 59 commits in three days, averaging some four hundred
lines each.

**Failure scenario.** One of the four is skipped on a commit made in a hurry. The break is found on
the next full run, several commits later, and bisecting it costs more than the gate would have.
This is not hypothetical for a repository moving at this rate.

**The asymmetry is the point.** 495 exists so that a change is accepted on evidence the harness
measured itself, twice, on both versions, against mutants. Its own changes are accepted on evidence
a person remembered to gather.

**Note on `E49`.** The étude's `E49` — "le mode CI n'est ni documenté ni testé" — concerns 495
*having* a CI mode for host projects (`--json`, exit codes 0/1/3/4). This finding is that the 495
repository itself has no pipeline. Adjacent, not the same.

**Remedy.** A workflow running the four documented commands on push and on pull request. The four
are already the contract; nothing new is being decided, only enforced.
