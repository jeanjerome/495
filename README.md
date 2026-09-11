# 495

495 is an agentic engineering harness. It turns an intent ("add X to this project") into a
software change that is **specified**, **produced in isolation**, **verified by commands**,
**reviewed from independent perspectives**, and **decided on evidence** — then leaves the
integration to you and checks it afterwards. Every run leaves a complete, portable trace.

It drives the agents you already have: **Claude Code**, **Codex**, and any **local model** behind
an OpenAI-compatible API (Ollama, llama.cpp, vLLM, LM Studio).

## Requirements

- macOS or Linux, `git`, Python >= 3.11 (`uv` is used when present, otherwise `venv` + `pip`).
- At least one agent:
  - `claude` CLI, logged in (`claude auth status`), for the `claude_code` agent kind;
  - `codex` CLI, logged in (`codex login status`), for the `codex` kind;
  - an OpenAI-compatible endpoint (e.g. `ollama serve`) for the `openai_compat` kind.
- Optional isolation backends: macOS Seatbelt (`sandbox-exec`, built in) or Docker.

## Quick start

```bash
./run.sh doctor                       # agents, sandboxes, git: what is usable here
./run.sh --project /path/to/repo init # write .495/config.toml + .495/project.toml, show the profile
./run.sh --project /path/to/repo new "Add a --dry-run flag to the deploy command"
```

`./run.sh` with no arguments opens an interactive menu. Every command also accepts `--json` for
automation, and `./run.sh serve` exposes the same workflow over HTTP.

The target project must be a git repository with at least one commit. 495 never touches your
working tree: it works in a dedicated git worktree on branch `495/<run-id>`, created outside
the project under `~/.cache/495/worktrees/<project>-<hash>/` (override with
`HARNESS495_WORKTREES_DIR`), and stores its state under `<project>/.495/runs/<run-id>/` (the
`.495/` directory is added to `.git/info/exclude`). The project tree is fingerprinted around
every intervention: an agent that escapes its worktree is detected, its output discarded, and
a producer escape stops the run.

## The workflow

| phase | what happens | who |
|---|---|---|
| profile | detect languages, tooling, verification commands and conventions; run every command once on the base version to prove it is executable and record what it printed (**readiness**) | harness |
| specify | turn the intent into requirements `R1..Rn`, each tied to verifications `V1..Vm`; flag missing or insufficient verifications and propose new tests to create | specifier agent (read-only) |
| gate | approve the specification (human, or `--auto-approve` when there is no gap) | you |
| produce | implement the change in the worktree; the harness commits the result so the evaluated version is one exact commit | producer agent (write) |
| verify | scope check (only allowed paths touched), then every verification command on that commit, output and hashes kept as evidence; every failing command is re-run on the base version, and one that fails identically there is marked as not observing the change | harness |
| review | independent reviewers, one per perspective (spec compliance, correctness, security, ...) with read-only access, structured verdicts; a reviewer that alters the tree has its verdict discarded | reviewer agents |
| decide | each requirement becomes `satisfied`, `violated` or `undetermined` from the evidence; violations produce correction requests and a new iteration; insufficient evidence stops the run and asks you | harness / you |
| deliver | patch, branch and Markdown report; nothing is merged | harness |
| check-integration | after you merged or applied the patch: does the target ref contain the commit / identical files, optionally re-run the verifications | harness |

A correction request says which requirement is not demonstrated and what was observed, never what
to change: the target is the behaviour a requirement describes, and a verification is only how the
harness looks at it. For the same reason a reviewer's own explanation stays out of the producer's
context, and a verification that fails with and without the change is taken out of the evidence
instead of being turned into work for the producer.

While a run works, the phase it is in, the iteration, what it is doing right now and what it has
spent against the budget stay on a status line at the bottom of the terminal; the transitions
themselves are not printed, since the line already says where the run is.

## The run surface

`495 watch` opens the run as the workflow: seven stops in the order the engine walks them, in
the vocabulary of the table above. A stop is both *where the run is* and *the tab that shows
what that stage produced*, so there is no menu to learn — you look for a fact at the stage that
produced it.

Three things carry the surface:

- **The navigation bar is the pipeline.** Each stop is a framed tab with its own key and its own
  count, so the strip is also a dashboard: checks at 4/6 and a blocker on the review are legible
  without opening either. Colour is the state of the *run* at that stop — green walked, cyan
  working, grey ahead, magenta stopped to ask you; a heavy frame is where *you* are looking.
- **One line always says what the run needs from you** — working, waiting on you, or finished —
  with the key that answers it. A decision is rendered in the body of the stage that raised it,
  not behind a keystroke.
- **Every stage has the same shape: headline, list, detail.** The headline is one sentence
  stating what the stage concluded and why. The detail follows the cursor rather than replacing
  the list, so arrowing down a list of checks reads their outputs in place; `enter` sends the
  full command log to your pager.

Keys: `1`-`7` or `←` `→` walk the pipeline, `n` catches up to where the run is, `↑` `↓` move the
cursor, `g` the event log (`f` filters it), `l` every run in the store, `d` answers the pending
decision, `space` freezes the display, `?` help, `q` quit. Without a terminal the same surface
prints and asks with the same vocabulary, so a piped session loses nothing.

The surface reads the store and never advances a run, so it can be left up in one terminal while
another drives the same run — both are looking at the same files. `--print` renders one view and
exits, `--export view.svg` captures it. `HARNESS495_ICONS=ascii` (or `--ascii-icons`) draws panel
titles with geometric marks instead of emoji.

Interruptions (Ctrl-C, `495 stop <id>` from another shell) pause the run after killing the
current agent; `495 resume <id>` continues at the phase that was interrupted.

## Commands

```
495 new "<intent>" [--agent kind[:model]] [--producer ...] [--reviewer perspective[=agent]]...
        [--max-cost USD] [--max-iterations N] [--timeout S] [--auto-approve] [--spec spec.json]
        [--sandbox host|seatbelt|docker] [--allow-network] [--allowed-path GLOB]... [--no-start]
495 eval "<intent>" [--ref <commit> | --ref <base>..<head> | --patch file.diff]   # evaluate an existing change
495 run <id> | resume <id> | stop <id>
495 decide <id> <choice> [--note "..."]          # answer a pending decision
495 spec <id>                                    # the specification: requirements and checks
495 status <id> | list | events <id> [-f] | report <id> [--format md|json] [-o file]
495 watch [<id>] [--stage checks] [--print] [--export view.svg]   # the run surface
495 check-integration <id> [--ref main] [--rerun]
495 export <id> | cleanup <id> [--delete] | schema run|event|spec|config | validate run.json
495 profile | init | doctor | serve [--port 4950]
```

Exit codes: `0` delivered, `3` waiting for a decision, `4` rejected or aborted, `1` failed.

### Decisions you may be asked to take

- `approve_spec`: approve / approve_with_gaps / revise (note) / abort. The specification is
  printed in full before the question, saved to `artifacts/spec.json` (the path is in the
  question), carried in the decision's `context.spec`, and readable at any time with `495 spec <id>`.
- `readiness`: a verification command cannot run here: drop / retry / abort; or it already fails on
  the base version, so nothing it reports later can be attributed to the change: proceed /
  allow_network (re-run with the network open to the verification commands, for builds that
  resolve dependencies on first use) / retry / abort.
- `instrument_fault`: a verification fails the same way with and without the change, so it cannot
  show whether the requirements it carries hold: respecify (note) / ignore / abort.
- `no_progress`: an iteration delivered the same tree as the previous one: respecify (note) /
  review_anyway / stop / abort.
- `undetermined`: evidence insufficient to conclude: accept_with_risk (note) / rerun / correct (note) / abort.
- `iteration_limit`: continue / stop / abort.  `budget`: raise (note = extra USD) / abort.

Every option states what taking it does to the run, and the facts behind the question — where
each requirement stands, the outstanding corrections, what the producer reported it could not do
— are laid out above it rather than packed into the question.

Non-interactively, a run exits with code 3 and prints the pending decision as JSON; answer with
`495 decide <id> <choice>` (which resumes by default).

## Configuration

`495 init` writes two TOML files under `.495/`:

- `config.toml`: agents, roles, budget, sandbox. Example:

```toml
[agents.default]
kind = "claude_code"      # claude_code | codex | openai_compat
model = "sonnet"

[agents.reviewer]
kind = "codex"

[agents.local]
kind = "openai_compat"
base_url = "http://localhost:11434/v1"
model = "qwen2.5-coder:7b"
context_window = 32768

[roles]
specifier = "default"
producer = "default"
reviewers = [
  { perspective = "spec_compliance", agent = "reviewer" },
  { perspective = "correctness", agent = "default" },
  { perspective = "security", agent = "local" },
]

[budget]
max_cost_usd = 10.0
max_iterations = 3
intervention_timeout_s = 1800
context_warn_ratio = 0.75

[sandbox]
backend = "auto"          # auto | host | seatbelt | docker
```

  A user-level `~/.config/495/config.toml` is read first; the project file overrides it.

- `project.toml`: the project's own criteria — verification commands (detected ones can be
  overridden), conventions, documentation files to show the agents, allowed and forbidden paths.

Built-in reviewer perspectives: `spec_compliance`, `correctness`, `security`, `test_quality`,
`standards`, `maintainability`; any other name works with a generic brief, and `instructions`
in a reviewer entry replaces the brief.

## What the agents get, and what they can do

Each intervention receives a context pack with two clearly separated parts: **established facts**
(the approved specification, the project profile, the exact version, the evidence the harness
collected itself) and **untrusted content** (diffs, repository documents, other agents' output),
labelled as data that may contain misleading instructions. Reviewers never see the producer's
transcript; producers only see correction requests derived from evidence.

| agent | read-only roles | write role | isolation |
|---|---|---|---|
| Claude Code | `--tools Bash,Read`, Bash limited to read-only patterns, `--permission-mode dontAsk` | `--permission-mode acceptEdits`, tools Bash/Edit/Write/Read | Claude Code sandbox enabled with no allowed network domain, permission prompts disabled, session not persisted |
| Codex | `--sandbox read-only` | `--sandbox workspace-write` | `network_access=false`, ephemeral session |
| OpenAI-compatible | bash loop in the harness sandbox, read-only | same, writable | Seatbelt (no network, writes limited to the worktree) or Docker (`--network none`), else host with a warning |

Every intervention records the agent identity (kind, model, CLI version, session id), the tools
allowed, the isolation actually applied, the working directory, the timeout, tokens, context
window utilisation, cost, and the tool activity observed in the transcript (e.g. `Bash 5,
Edit 2`). Claude Code transcripts are kept in full (`stream-json`).

Local models must be able to follow a simple protocol (one fenced `bash` block per turn, a
`final` block to finish, JSON output when asked). Small models (around 1-2B parameters) tend
to loop or ignore the format; the loop detects that and fails the intervention instead of
spending the budget. A 7B coder model is the practical minimum. Budgets (`max_cost_usd`, `max_interventions`, `max_iterations`,
timeouts) are enforced before each intervention; Claude Code also receives `--max-budget-usd`.

Cost is `reported` when the agent states it (Claude Code), `estimated` from
`harness495/data/pricing.json` (copy it to `~/.config/495/pricing.json` to adjust) when only tokens
are known, and `unknown` otherwise — never silently zero.

## Traceability

`<project>/.495/runs/<id>/` holds `run.json` (validated by `495 schema run`), `events.jsonl`,
one directory per intervention (rendered prompt, context summary, raw transcript, structured
output, identity), one per evidence (command output), and `artifacts/` (patches, `report.md`).
`495 export <id>` archives it. `495 serve` publishes `/runs`, `/runs/{id}`, `/runs/{id}/events`,
`/runs/{id}/report`, `/runs/{id}/decisions`, `/schema/{run|event|spec|config}`.

## Development

```bash
./run.sh --version                       # creates .venv and installs the package with dev extras
.venv/bin/python -m pytest -q            # unit, adapter (fake CLIs) and end-to-end (fake agents) tests
.venv/bin/ruff check harness495 tests && .venv/bin/ruff format --check harness495 tests
.venv/bin/mypy harness495
```

See `DECISIONS.md` for the design log and the reuse review of the reference projects.
