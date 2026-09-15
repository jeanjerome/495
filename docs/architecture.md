# Architecture

Reference: the workflow, the packages and their boundaries, the data model, the state on disk.
Reasons are in `docs/decisions/`; read the record named next to a rule before changing that rule.

## The workflow

A run is a resumable state machine over one `Run` document. The engine walks it phase by phase,
saving the document before and after each phase, and stops in `awaiting_decision` whenever a
question is the requester's to answer, or in `paused` on interruption.

```
created ─► profiled ─► clarifying ─► clarified ─► specified ─► ready ─► producing ─►
                  (one round per stop)                   (design tests, then produce)
        ─► produced ─► verifying ─► verified ─► reviewing ─► reviewed ─► accepted ─► delivered
                                 └► rejected ─► ready        (one more iteration)
                                 └► undetermined             (the run asks)
```

| Phase | Who | What it establishes |
|---|---|---|
| profile | harness | languages, tooling, verification commands, role coverage (which tool measures each catalogue role), the gaps against the catalogue and the proposals the requester declined, the lessons earlier runs showed and the requester accepted, conventions, documents; every command run once on the base version (readiness and baseline). Outside a run, `495 init` and `495 profile` also turn each gap into a conformance proposal recorded under `.495/` |
| clarify | clarifier agent, read-only, one intervention per round | the decisions the intent leaves open, as the frontier: the questions whose prerequisites are settled, each with at least two options, what each option does to the specification, a recommended answer and what the clarifier read to recommend it. The harness completes the options with `other`, drops a question already answered, one offering fewer than two options and one whose option states no consequence, and raises one decision for the whole round; the answers are facts for the specifier, the test designer, the producer and every reviewer. The phase ends when a round returns no question, or at `budget.max_clarify_rounds`, the questions still open being recorded as unanswered (`docs/decisions/0025-the-decisions-are-taken-before-the-specification-in-rounds.md`) |
| specify | specifier agent, read-only | requirements `R1..Rn` tied to verifications `V1..Vm` (each naming the catalogue role it measures, if any; a test stated as a given/when/then scenario), out of scope, assumptions, allowed paths; the specifier is given the catalogue against the project's role coverage, and the harness then audits sufficiency, a role the project does not measure or a test to create without a scenario being insufficient |
| gate | requester (or `--auto-approve` when there is no gap) | approval of the specification; every proposed command has been run once on the base version first |
| design tests | test designer agent, write | once per approved specification with a test to create: the tests, written from their scenarios' steps as a feature file where the project measures `bdd` and in the project's runner otherwise, on a tree where the behaviour does not exist; the harness keeps the test files, puts every other file back, commits them (`Run.test_design`) and protects them from the change |
| produce | producer agent, write | the change, in the run's worktree, with the designed tests as read-only files (without a designer the producer writes the tests to create itself); the harness commits the work so the evaluated version is one commit |
| verify | harness | scope check (allowed paths, and no designed test modified), then every verification on that commit, then the stability check (each command a requirement leans on run a second time on that same commit, one that reports success once and failure once crediting no requirement and charging none), then the suite check (the diff over the test files that existed on the base, and the runners' tallies on both versions: a test deleted, removed or skipped, or a smaller tally, fails it); each one a behaviour requirement leans on is run again on the base version carrying the change's test files, and one that reports the same both times leaves the evidence; one that fails there by an execution error rather than an assertion is `unconfirmed`, still credited; then the coverage check, the test commands run once more under the project's own coverage tool and their report crossed with the lines the change adds, a line no command executed leaving the behaviour requirements resting on them undetermined; last the mutation check, a few wrong versions of the change (one line of the diff altered each) every command that passed is run against until one reports it, a version none of them reports leaving the behaviour requirements resting on those commands undetermined |
| review | reviewer agents, read-only, one per perspective | structured verdicts with findings that cite an observation; `test_quality`, called whenever a test is to be created, holds each scenario against its requirement and its test and reads an unconfirmed test's assertions; a reviewer that alters the tree is discarded |
| decide | harness | each requirement `satisfied`, `violated` or `undetermined`; violations become correction requests and a new iteration; `undetermined` stops and asks |
| deliver | harness | patch, branch `495/<run-id>`, Markdown report; nothing merged |
| merge, check-integration | harness, on request | the delivered branch brought into the checked-out branch in one of four shapes, then the target ref compared with what was verified |
| retro | harness, on request | what the run showed about each tool that measured a catalogue role, read from the run document: proven, faulty or inconclusive, with the row the catalogue takes by hand; and what it showed about the project itself, as lessons the requester accepts, declines or defers — a replaced command, a correction written by hand, a rule a reviewer blocked the change for, the scope a produced version stayed inside, a decision taken before the specification. An accepted lesson is part of the project's criteria from the next run on and reaches the specifier as a fact (`docs/decisions/0027-what-a-run-learns-about-the-project-is-put-to-the-requester.md`) |
| stats | harness, on request | every run of the store read as a series: outcomes, iterations, cost per requirement assessed, the commands recorded unable to tell the change from its absence, the kinds of verification that decided nothing, what each perspective found and found again. Computed on every call, persisted nowhere |

`495 eval` runs the same machine without a producer: the existing change (a commit, a range, a
patch or the working tree) is materialised as one commit in the worktree and enters at `produced`.

## Packages and their boundaries

```
interfaces   cli · interactive · api · render · tui/        outermost; nothing imports it
    │
core.engine  the workflow; the only core module that builds agents
    │
agents       claude_code · codex · openai_compat · registry  one adapter per agent
    │
sandbox      base (host) · seatbelt · docker                  command execution with isolation
    │
core.models  every persisted object, as a pydantic model      the shared vocabulary
```

Dependencies point downwards only (`docs/decisions/0011-package-boundaries.md`):

- `interfaces` may import anything. Nothing outside `interfaces` imports it.
- Inside `core`, only `engine` imports `agents`, and only `engine` and `verification` import
  `sandbox`. The rest of `core` (`models`, `decide`, `scope`, `context`, `prompts`, `schemas`,
  `profile`, `catalogue`, `coverage`, `proposals`, `retro`, `lessons`, `stats`, `suite`,
  `diff`, `mutation`, `reach`, `git`, `store`, `report`, `config`, `pricing`, `budget`)
  depends on `core` alone.
- `agents` imports `core.models`, `core.pricing` and `sandbox`; never `core.engine`, `core.store`
  or `core.decide`.
- `sandbox` imports `core.models` and nothing else of 495.

The rules are import-linter contracts in `pyproject.toml`; `lint-imports` checks them, and
`tests/test_architecture.py` runs the same check under pytest.

### `core`

| Module | Responsibility |
|---|---|
| `models` | the domain model: `Run`, `Spec`, `Requirement`, `Verification`, `Intervention`, `Evidence`, `ReviewVerdict`, `Decision`, `Iteration`, `Version`, configuration; all `StrictModel` (`extra="forbid"`) |
| `engine` | a package: `engine/engine.py` holds the phases, the decisions raised to the requester and how each answer moves the run, calibration of instruments, merge and integration check; `engine/__init__.py` names what anything outside may import — `Engine` and `EngineError`, `spec_from_agent` (the reader a requester-supplied JSON specification goes through) and `worktrees_root` |
| `decide` | `assess()`: the pure acceptance decision over spec, evidence and reviews |
| `verification` | running one command on the exact commit, the control run on the base version, the second run on the same version (`reports_the_same_twice`), the failure signature and the nature of a failure (assertion or execution error), sufficiency, test-file recognition |
| `profile` | detection of languages, tooling and commands from manifests and from the tree; gathers what each technology's markers read (a `coverage.Tree`) |
| `coverage` | role coverage against the catalogue's roles: the roles per technology (`ROLES_BY_TECHNOLOGY`), the marker table of each technology (`PYTHON_TOOLS`, `SHELL_TOOLS`, `NODE_TOOLS`, `RUST_TOOLS`, `GO_TOOLS`, `JVM_TOOLS`), `rows()`: one `RoleCoverage` per role with the tools whose markers hold |
| `catalogue` | the catalogue's recommended entries per technology and role (`RECOMMENDED`), what a test of each role must show (`ROLE_CONTRACTS`), the roles whose measure can contradict the agent (`CONTRADICTING_ROLES`), `compare()`: the profile's gaps against them, and `unmeasured_role()`: why a verification of a role cannot run in the project. The conditions that pick between the entries of one cell (`CONDITIONS`) are the only part that reads the project; `conditions_holding()` evaluates them once, at profiling, and `applicable()` reads the recorded outcome |
| `proposals` | the conformance proposals: `reconcile()` opens one per gap and resolves those no longer stated, `intent_for()` writes the intent of the run an acceptance creates, `accept()`, `decline()`, `defer()` record the requester's answer |
| `retro` | the retrospective of a run: `measurements()` pairs each run of a verification on the change with its control run, `read()` turns a pair into a verdict, a contradiction, a fault or nothing, `retrospect()` states one `ToolObservation` per technology and role with the catalogue row it yields |
| `lessons` | what a run showed about the project: `learn()` reads a replaced command, a correction written by hand, a blocking finding no requirement asked about, the scope a produced version stayed inside, a decision taken before the specification and a tool the retrospective found faulty; `reconcile()` keeps one record per lesson however many runs show it; `accept()`, `decline()`, `defer()` record the answer; `criteria()` adds the accepted ones to the project's criteria; `toml_lines()` and `render_document()` state them |
| `stats` | `summarise()`: the runs of the store read as a series — outcomes, iterations, cost per requirement, `InstrumentStat` per command, `KindStat` per kind of verification, `PerspectiveStat` per reviewer perspective with what it found again |
| `scope` | which files a change may touch, and `effective_allowed()`: the project's criteria, or the specification's where it declares none |
| `suite` | what the change did to the test suite that passed on the base: `read_suite_changes()` reads the diff over the test files that existed there (deleted, renamed out of the runner's reach, tests removed, skips added), `count_tests()` reads the tally a runner prints, `compare_counts()` pairs the base's with the change's |
| `context` | `ContextPack`: facts versus untrusted content, the only route by which anything reaches an agent, and the renderers of spec, profile, evidence, reviews |
| `prompts` | system prompts and tasks for the five roles; the reviewer perspectives |
| `schemas` | hand-written JSON schemas for agent output, validated again by pydantic |
| `git` | worktrees, exact versions, diffs, patches, the four integration shapes and their rollback |
| `store` | one directory per run, atomic writes, append-only events, the claim of a run by the process advancing it; the project's `proposals.json`, `lessons.json` and `lessons.md`; a run's `retrospective.json` |
| `report` | the Markdown restitution of a run from its persisted state; under each requirement, the scenario of every verification stated as one and what it reported on the evaluated commit |
| `config` | precedence: defaults, `~/.config/495/config.toml`, `.495/config.toml`, `.495/project.toml`, command line; the criteria then take the lessons in force |
| `budget`, `pricing` | limits checked before each intervention; cost `reported`, `estimated` or `unknown` |

### `agents`

Each adapter turns an `AgentTask` (role, capability, prompts, cwd, timeout, budget, output
schema) into an `AgentResult` (status, text, structured output, usage, cost, identity, sandbox
applied, transcript). `claude_code` drives `claude -p` with restricted tools and the CLI's own
sandbox; `codex` drives `codex exec` with `read-only` or `workspace-write`; `openai_compat` is a
bash-only loop for any OpenAI-compatible chat endpoint, executing every command through the
harness sandbox.

No adapter lets its CLI read the target project's own configuration: `claude -p` runs with no
setting source and `codex exec` with `project_doc_max_bytes=0`, so the context is the pack and
nothing else, and a repository file keeps one trust status whichever CLI runs the role (0026).

### `sandbox`

`Sandbox.run(ExecRequest)` executes a shell command in its own process group with a timeout and
a stop check; `seatbelt` wraps it in a `sandbox-exec` profile (no network, writes limited to the
worktree and scratch directories); `docker` runs it in a container with `--network none` and the
worktree mounted. Selection is automatic with a warning when only the host is available.

### `interfaces`

Three surfaces over one engine: `cli` (typer, `--json` everywhere), `api` (HTTP on
`127.0.0.1:4950`, no merge), and `tui` (the run surface: eight stops in the order the engine walks
them, plus the store page). `render` is shared by the CLI and the interactive menu; the TUI
renders from the store and drives the engine through the same public methods as the CLI.

## The data model

A `Run` has an `Intent`, a `HarnessConfig`, a `ProjectProfile` (languages, tooling,
`ProjectCommand`s, a `RoleCoverage` per technology and `CatalogueRole`, the catalogue
conditions that held when the project was profiled, the `CatalogueGap`s
against the catalogue, the `DeclinedRole`s read from the proposals, the `Lesson`s in force,
`ReadinessCheck`s), one
`Clarification`, one
`Spec`, a `Budget` and its `Consumption`, and grows lists of `Iteration`, `Intervention`, `Evidence`, `ReviewVerdict` and
`Decision`, linked by identifiers. A `Clarification` is the `ClarifyRound`s the phase walked —
each one intervention, the `ClarifyQuestion`s it put to the requester with their
`ClarifyOption`s, the `ClarifyAnswer`s taken and what the harness dropped — plus the questions
left open when the round cap was reached. A `Spec` is `Requirement`s (each `behaviour` or
`non_regression`) tied to `Verification`s (each with a `Sufficiency` the harness computes,
when it measures a catalogue role, that `CatalogueRole`, and when it is a test, the
`BehaviourScenario` it enacts: given, when and then steps), the `DecisionTaken`s it was
written under, and the assumptions nobody was asked about. An
`TestDesign` records the tests the test designer wrote for the specification: the commit
that holds them, the protected files, the paths put back, and what the designer reported. An
`Iteration` freezes one `Version` (base commit, head commit, patch hash, files changed) and
collects the evidence and reviews measured on it. `Evidence` is what the harness observed:
`command_result`, `scope_check`, `suite_check`, `coverage_check`, `mutation_check`,
`stability_check`, `review_verdict`, `instrument_check`, `baseline`, `integrity`. A
`PendingDecision` is a question with `DecisionOption`s, each stating its consequence, and, for
a clarification round, the `ClarifyQuestion`s it carries; a `Decision` records who answered and
what, with one `ClarifyAnswer` per question when it carried several. `RunResult` holds the delivered branch, patch, report
and the `IntegrationCheck`. Outside any run, a `Proposals` document holds one `Proposal` per
gap against the catalogue, identified by technology and role: the gap as last stated, a
`ProposalStatus` (`open`, `accepted` with the run it created, `declined` with the reason,
`deferred`, `resolved`), and the intent an acceptance turns into a run. Next to a run, a
`Retrospective` holds one `ToolObservation` per technology and `CatalogueRole` a
verification measured: the tools, a `ToolVerdict` (`proven`, `faulty`, `inconclusive`), the
counts and sentences of each measurement, and the catalogue row it yields. Outside any run
too, a `Lessons` document holds one `Lesson` per thing a run showed about the project,
identified by its `LessonKind` (`command`, `convention`, `allowed_path`, `note`,
`false_positive`), by the reviewer perspective it answers when it answers one, and by what it
would declare: the runs that showed it, what each of them recorded in words, a `LessonStatus`
(`open`, `accepted`, `declined` with the reason, `deferred`) and, on an acceptance, the words
the requester chose to declare instead. The two kinds that declare nothing travel as a fact to
the role they bear on, a `note` to the specifier and a `false_positive` to the reviewer of its
perspective. The JSON schema of each document comes from these
models, and `495 schema stats` publishes the shape of the series `core/stats.py` reads.

## State on disk

```
<project>/.495/                        excluded from git by .git/info/exclude
  config.toml  project.toml            configuration and project criteria
  proposals.json                       the conformance proposals and the requester's answers
  lessons.json  lessons.md             what the runs showed about the project, and what is in force
  runs/<run-id>/
    run.json                           the Run document, atomic writes
    retrospective.json                 what the run showed about the tools, written by 495 retro
    events.jsonl                       append-only event log
    DRIVER  STOP                       claim of the process advancing the run; stop request
    interventions/<id>/                prompt.md, context.json, transcript, output, meta.json
    evidence/<id>/output.txt           what each command printed
    artifacts/                         spec.json, iteration-N.patch, report.md
~/.cache/495/worktrees/<project>-<hash>/<run-id>      the run's worktree, branch 495/<run-id>
                                     <run-id>.control the throwaway base checkout for control runs
```

Every reference inside `run.json` is relative to the run directory, so a run can be archived
(`495 export`) and validated (`495 validate`) as a whole. Git remains the source of history.
