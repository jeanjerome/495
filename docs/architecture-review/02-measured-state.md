# Measured state

Everything below was measured on 2026-09-14 at commit `391035c`, on a clean tree. The command that
produced each figure is given.

## What holds

Named first, and specifically, because a review whose findings are trusted has to be a review that
reports what it found rather than what it looked for.

### The context pack is a deep module

`core/context.py::ContextPack` presents four methods — `add_fact`, `add_untrusted`, `render`,
`to_json` — and is the only route by which anything reaches an agent. Behind that interface sit two
trust zones, sixteen renderers and the serialisation that makes an intervention auditable. The
deletion test returns the right answer loudly: deleting it would scatter the fact/untrusted
distinction across five phases and lose the guarantee that `docs/decisions/0005` and `0026` rest on.

This is the shape the rest of the engine should be measured against.

### The engine's external seam is right

```
$ grep -c "^    def " harness495/core/engine.py            # 65 methods on Engine
$ grep -c "^def " harness495/core/engine.py                # 16 module-level functions
$ grep -rn "engine\._\|Engine\._" harness495/interfaces/  # 0 hits
$ grep -rn "core.engine import _" harness495/interfaces/   # 2 hits
```

Twelve public methods — `create_run`, `run`, `resume`, `step`, `decide`, `request_stop`, `sandbox`,
`emit`, `worktree_path`, `merge_delivery`, `check_integration`, `cleanup_worktree` — carry 3 775
lines. `interfaces` calls eight of them by attribute and reaches no private *method* of the engine.
Three surfaces (CLI, HTTP API, TUI) drive the same entry points. That is high depth at the external
seam, and it is the reason the remedy in [04-deepening.md](04-deepening.md) does not touch that
interface.

The seam has one hole, which the grep above cannot see because it matches attribute access and not
an import: `interfaces/cli.py:282` and `interfaces/api.py:210` both import the module-level free
function `_spec_from_agent` from `core.engine`. One function, two call sites, and it belongs to the
agent-output mapping — the region [07-layout.md](07-layout.md) moves to `engine/reading.py`, where
[06-plan.md](06-plan.md) T12 gives it a name without an underscore.

The suite respects the same seam: across 13 218 lines of tests, exactly one reaches into an engine
private, and it is a module-level free function (`tests/test_clarify_scenarios.py` calling
`_clarify_frontier`). The interface is the test surface, as it should be.

### Package boundaries are a test, not a wish

Four import-linter contracts in `pyproject.toml`, run by `lint-imports` and again under pytest by
`tests/test_architecture.py`, which asserts on the exact string `Contracts: 4 kept, 0 broken`.

```
$ .venv/bin/lint-imports        # Contracts: 4 kept, 0 broken
$ .venv/bin/mypy harness495     # Success: no issues found in 90 source files
$ .venv/bin/ruff check harness495 tests   # All checks passed!
```

### The pure core is genuinely pure

`docs/decisions/0001`, `0015` and `0027` state that `decide.assess`, `retro.retrospect`,
`lessons.learn` and `stats.summarise` are pure functions. Checked rather than assumed:

```
$ for f in decide retro lessons stats suite diff reach mutation scope; do
    grep -c "open(\|read_text\|write_text\|\.exists()\|subprocess\|os.environ" harness495/core/$f.py
  done
0 0 0 0 0 0 0 0 0
```

Nine modules, no I/O. `Path` appears in four of them and is used only for suffix and name
manipulation. The invariant holds — upheld by discipline, with nothing enforcing it; see finding F5.

### Every declared seam has two adapters

The one-adapter rule, checked against each seam the architecture claims:

| Seam | Adapters | Real? |
|---|---|---|
| `sandbox.Sandbox` | host, `SeatbeltSandbox`, `DockerSandbox` | yes |
| `agents.Agent` | `ClaudeCodeAgent`, `CodexAgent`, `OpenAICompatAgent` | yes |
| `tui.driving.Driver` | `ReadOnly`, `StoreDriver` | yes |

No hypothetical seams. Every port carries something that actually varies across it.

### The suite is disciplined

548 tests, 4 deselected as `live`; 290 Gherkin scenarios across 19 feature files bound with
pytest-bdd, per `docs/decisions/0013`. 13 218 lines of test against 24 661 of production. 85 % line
coverage.

## The numbers

```
$ find harness495 -name '*.py' | xargs wc -l          # 24 661 in 90 files
$ .venv/bin/python -m pytest -p no:warnings --collect-only   # 548/552 collected
$ .venv/bin/python -m coverage run --source=harness495 -m pytest -q && coverage report
```

| | |
|---|---|
| Production | 24 661 lines, 90 modules (26 in `core`, 47 in `interfaces/tui`) |
| Tests | 13 218 lines, 548 tests, 290 Gherkin scenarios |
| Coverage | 85 % overall |
| Decision records | 28 |
| Commits | 59, from 2026-09-11 to 2026-09-14 |

Ten largest modules:

| Lines | Module |
|---:|---|
| 3 775 | `core/engine.py` |
| 1 614 | `interfaces/cli.py` |
| 1 420 | `core/models.py` |
| 849 | `core/coverage.py` |
| 736 | `interfaces/tui/shell.py` |
| 662 | `core/profile.py` |
| 516 | `core/verification.py` |
| 511 | `core/context.py` |
| 504 | `core/lessons.py` |
| 470 | `interfaces/tui/views/integration.py` |

Coverage, worst first — the deficit concentrates in `interfaces`:

| Module | Statements | Missed | Cover |
|---|---:|---:|---:|
| `interfaces/interactive.py` | 100 | 100 | **0 %** |
| `interfaces/tui/app.py` | 62 | 46 | 26 % |
| `interfaces/tui/loops.py` | 260 | 168 | 35 % |
| `interfaces/tui/keys.py` | 91 | 38 | 58 % |
| `interfaces/cli.py` | 865 | 263 | 70 % |
| `interfaces/api.py` | 192 | 55 | 71 % |
| `core/engine.py` | 1 570 | 193 | 88 % |

## The growth curve

`core/engine.py`, one line per commit that touched it, last fourteen:

```
$ git log --format=%H --reverse -- harness495/core/engine.py | tail -14 |
  while read c; do git cat-file -p $c:harness495/core/engine.py | wc -l; done
```

| Date | Lines | Δ | Commit subject |
|---|---:|---:|---|
| 2026-09-13 | 2 475 | | the last stop says which branch carries the change |
| 2026-09-13 | 2 483 | +8 | the specifier is given the catalogue |
| 2026-09-13 | 2 485 | +2 | a run reads the proposals the requester declined |
| 2026-09-13 | 2 502 | +17 | a test to create is specified as a scenario |
| 2026-09-13 | 2 505 | +3 | the form of a test follows the project's runner |
| 2026-09-14 | 2 515 | +10 | an execution error without the change does not confirm |
| 2026-09-14 | 2 706 | **+191** | the tests to create are written by a test designer |
| 2026-09-14 | 2 803 | **+97** | the existing suite is measured on the change |
| 2026-09-14 | 3 003 | **+200** | the verifications are measured against wrong versions |
| 2026-09-14 | 3 176 | **+173** | the lines the change adds are crossed with what runs |
| 2026-09-14 | 3 340 | **+164** | a verification is run twice on the same version |
| 2026-09-14 | 3 759 | **+419** | the decisions the intent leaves open are put first |
| 2026-09-14 | 3 761 | +2 | what a run showed about the project |
| 2026-09-14 | 3 775 | +14 | a reviewer's claim the requester found wrong |

**+1 270 lines on 2026-09-14 alone, across nine `feat` commits; +1 300 and +52,5 % over the
thirteen commits of the table, none of which removed anything.**

The growth is not confined to the engine. Measured on one baseline — `5b99938b`, the first row of
the table above — against `391035c`, 37 commits later:

```
$ for m in core/engine.py interfaces/cli.py core/context.py core/models.py; do
    git cat-file -p 5b99938b:harness495/$m | wc -l; git cat-file -p HEAD:harness495/$m | wc -l
  done
```

| Module | `5b99938b` | `391035c` | |
|---|---:|---:|---:|
| `core/engine.py` | 2 475 | 3 775 | +52,5 % |
| `interfaces/cli.py` | 910 | 1 614 | +77,4 % |
| `core/context.py` | 192 | 511 | +166,1 % |
| `core/models.py` | 719 | 1 420 | +97,5 % |

Read as a rate rather than a state: **one new invariant costs the engine 100 to 420 lines**, and
costs `models`, `context` and `cli` a share of the same order. `docs/etude-harnais-495.md`
holds roughly fifteen open entries at medium or high priority. At the observed rate the engine
reaches six to seven thousand lines before they are closed.

Nothing in the repository measures this, bounds it, or would report it. The import contracts
constrain which package may import which; no contract constrains what one module may hold.

## Where a change lands

The cost of adding one concept, measured on the most recent structural feature — the clarification
phase, `d02aae3`:

```
$ git show --stat d02aae3
```

**20 production files**, plus tests: `models`, `engine` (+455), `context`, `prompts`, `report`,
`schemas`, `config`, `api`, `cli`, `interactive`, `render`, and seven TUI modules.

Fourteen modules name the word today:

```
$ grep -rl "clarify\|Clarify" harness495/ | wc -l    # 14
```

Some of that is irreducible — a phase genuinely has a prompt, a schema, a renderer and a screen.
The part that is not irreducible is measured in [03-findings.md](03-findings.md) F1 and
[04-deepening.md](04-deepening.md) D2: a *decision kind*, which is a much smaller concept than a
phase, still costs four to seven modules, and nothing checks that all of them were edited.
