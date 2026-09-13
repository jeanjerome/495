# Architecture

Reference: the workflow, the packages and their boundaries, the data model, the state on disk.
Reasons are in `docs/decisions/`; read the record named next to a rule before changing that rule.

## The workflow

A run is a resumable state machine over one `Run` document. The engine walks it phase by phase,
saving the document before and after each phase, and stops in `awaiting_decision` whenever a
question is the requester's to answer, or in `paused` on interruption.

```
created ─► profiled ─► specified ─► ready ─► producing ─► produced ─► verifying ─► verified
        ─► reviewing ─► reviewed ─► accepted ─► delivered
                                 └► rejected ─► ready        (one more iteration)
                                 └► undetermined             (the run asks)
```

| Phase | Who | What it establishes |
|---|---|---|
| profile | harness | languages, tooling, verification commands, role coverage (which tool measures each catalogue role) and the gaps against the catalogue, conventions, documents; every command run once on the base version (readiness and baseline) |
| specify | specifier agent, read-only | requirements `R1..Rn` tied to verifications `V1..Vm`, out of scope, assumptions, allowed paths; the harness then audits sufficiency |
| gate | requester (or `--auto-approve` when there is no gap) | approval of the specification; every proposed command has been run once on the base version first |
| produce | producer agent, write | the change, in the run's worktree; the harness commits it so the evaluated version is one commit |
| verify | harness | scope check, then every verification on that commit; each one a behaviour requirement leans on is run again on the base version carrying the change's test files, and one that reports the same both times leaves the evidence |
| review | reviewer agents, read-only, one per perspective | structured verdicts with findings that cite an observation; a reviewer that alters the tree is discarded |
| decide | harness | each requirement `satisfied`, `violated` or `undetermined`; violations become correction requests and a new iteration; `undetermined` stops and asks |
| deliver | harness | patch, branch `495/<run-id>`, Markdown report; nothing merged |
| merge, check-integration | harness, on request | the delivered branch brought into the checked-out branch in one of four shapes, then the target ref compared with what was verified |

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
  `profile`, `catalogue`, `git`, `store`, `report`, `config`, `pricing`, `budget`) depends on
  `core` alone.
- `agents` imports `core.models`, `core.pricing` and `sandbox`; never `core.engine`, `core.store`
  or `core.decide`.
- `sandbox` imports `core.models` and nothing else of 495.

The rules are import-linter contracts in `pyproject.toml`; `lint-imports` checks them, and
`tests/test_architecture.py` runs the same check under pytest.

### `core`

| Module | Responsibility |
|---|---|
| `models` | the domain model: `Run`, `Spec`, `Requirement`, `Verification`, `Intervention`, `Evidence`, `ReviewVerdict`, `Decision`, `Iteration`, `Version`, configuration; all `StrictModel` (`extra="forbid"`) |
| `engine` | the phases, the decisions raised to the requester and how each answer moves the run, calibration of instruments, merge and integration check |
| `decide` | `assess()`: the pure acceptance decision over spec, evidence and reviews |
| `verification` | running one command on the exact commit, the control run on the base version, the failure signature, sufficiency, test-file recognition |
| `profile` | detection of languages, tooling and commands from manifests and from the tree; role coverage against the catalogue's roles, from markers per technology (`ROLES_BY_TECHNOLOGY`, `PYTHON_TOOLS`, `SHELL_TOOLS`) |
| `catalogue` | the catalogue's recommended entries per technology and role (`RECOMMENDED`), the roles whose measure can contradict the agent (`CONTRADICTING_ROLES`), and `compare()`: the profile's gaps against them |
| `scope` | which files a change may touch |
| `context` | `ContextPack`: facts versus untrusted content, and the renderers of spec, profile, evidence, reviews |
| `prompts` | system prompts and tasks for the three roles; the reviewer perspectives |
| `schemas` | hand-written JSON schemas for agent output, validated again by pydantic |
| `git` | worktrees, exact versions, diffs, patches, the four integration shapes and their rollback |
| `store` | one directory per run, atomic writes, append-only events, the claim of a run by the process advancing it |
| `report` | the Markdown restitution of a run from its persisted state |
| `config` | precedence: defaults, `~/.config/495/config.toml`, `.495/config.toml`, `.495/project.toml`, command line |
| `budget`, `pricing` | limits checked before each intervention; cost `reported`, `estimated` or `unknown` |

### `agents`

Each adapter turns an `AgentTask` (role, capability, prompts, cwd, timeout, budget, output
schema) into an `AgentResult` (status, text, structured output, usage, cost, identity, sandbox
applied, transcript). `claude_code` drives `claude -p` with restricted tools and the CLI's own
sandbox; `codex` drives `codex exec` with `read-only` or `workspace-write`; `openai_compat` is a
bash-only loop for any OpenAI-compatible chat endpoint, executing every command through the
harness sandbox.

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
`ProjectCommand`s, a `RoleCoverage` per technology and `CatalogueRole`, the `CatalogueGap`s
against the catalogue, `ReadinessCheck`s), one
`Spec`, a `Budget` and its `Consumption`, and grows lists of `Iteration`, `Intervention`, `Evidence`, `ReviewVerdict` and
`Decision`, linked by identifiers. A `Spec` is `Requirement`s (each `behaviour` or
`non_regression`) tied to `Verification`s (each with a `Sufficiency` the harness computes). An
`Iteration` freezes one `Version` (base commit, head commit, patch hash, files changed) and
collects the evidence and reviews measured on it. `Evidence` is what the harness observed:
`command_result`, `scope_check`, `review_verdict`, `instrument_check`, `baseline`, `integrity`. A
`PendingDecision` is a question with `DecisionOption`s, each stating its consequence; a
`Decision` records who answered and what. `RunResult` holds the delivered branch, patch, report
and the `IntegrationCheck`. The JSON schema of each document comes from these models.

## State on disk

```
<project>/.495/                        excluded from git by .git/info/exclude
  config.toml  project.toml            configuration and project criteria
  runs/<run-id>/
    run.json                           the Run document, atomic writes
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
