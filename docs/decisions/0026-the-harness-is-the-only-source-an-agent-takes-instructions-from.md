# 0026. The harness is the only source an agent takes instructions from, and a repository file is untrusted content whatever the route

- Status: accepted
- Date: 2026-09-14

## Context

Both CLI adapters read the target project's own configuration on their own, before 495 says
anything. Measured on `claude 2.1.270` and `codex-cli 0.153.3`, on a directory holding an
instruction file that names a codeword and a `.claude/settings.json` setting an environment
variable:

| command | the codeword is known | the project's settings file is loaded |
|---|---|---|
| `claude -p --setting-sources project` | yes | yes |
| `claude -p --setting-sources ""` | no | no |
| `codex exec` | yes | — |
| `codex exec -c project_doc_max_bytes=0` | no | — |

So the same `CLAUDE.md` arrived twice with two contradictory statuses: an instruction the model
obeys on the native path, and data it must not obey inside `<untrusted>` (0005). An instruction
placed in a target repository was obeyed whatever 495 said about it.

Three further consequences followed from the same cause. The context depended on which CLI ran
the role — Claude Code reads `CLAUDE.md`, Codex reads `AGENTS.md`, the OpenAI-compatible loop
reads neither — so contexts built for independent judgements were not comparable. What arrived
natively was outside the bounds, the token accounting and the trace, while `prompt.md` and
`context.json` claim to state what the intervention received. And `--setting-sources project`
loaded the target's `permissions` and `hooks`, whose precedence against the `--settings` 495
passes is stated nowhere.

## Decision

The harness is the only source an agent takes instructions from. The CLIs' native paths into the
target project are closed:

- Claude Code runs with `--setting-sources ""`: no user, project or local settings file, and no
  instruction file discovered from the working directory. The sandbox 495 imposes still travels
  on `--settings`, which is unaffected.
- Codex runs with `-c project_doc_max_bytes=0`: no project instruction file is read.
- The OpenAI-compatible adapter has no native path; the harness drives its loop itself.

A file of the repository reaches an agent as untrusted content, whatever the route: injected in
the pack as `<untrusted source="repository file ...">`, or read by the agent itself with `Read`
or `cat`. `COMMON_RULES` already covers both, naming "files in the repository" as untrusted
regardless of how they arrive.

The profile names the documentation files it found — their paths only, as a fact — so a role that
needs them knows they exist and reads them as data.

What the requester wants obeyed is declared in `.495/project.toml` under `conventions`, which
`render_profile` renders among the facts.

## Consequences

- A run measures the same thing whichever CLI runs a role. The independence the review rests on
  (0005) comes from contexts that are separate *and* comparable.
- `prompt.md` and `context.json` state what the intervention received, with nothing beside them.
- The target's `permissions` and `hooks` cannot weaken the isolation 495 imposes, and the
  precedence question does not arise. Each intervention's `SandboxInfo.detail` records it.
- A repository whose instruction file is hostile cannot steer the reviewer that judges it.
- Cost: a host project's conventions no longer arrive by themselves. A role that wants them
  reads the files the profile names, or the requester declares them in `conventions`, where they
  are a fact. The producer and the reviewers are told the paths, not the content; injecting the
  excerpts into every role is the opposite direction from E21 and is not taken.
- The alternative — promoting the target's `CLAUDE.md` to a fact, on the grounds that it is the
  requester's own project — is rejected: it makes the trust of every role depend on a file any
  writer of the repository can change, which is the boundary 0005 exists to hold.

## Where in the code

- `harness495/agents/claude_code.py`: `build_argv` (`--setting-sources ""`), `run`
  (`SandboxInfo.detail`).
- `harness495/agents/codex.py`: `build_argv` (`project_doc_max_bytes=0`), `run`
  (`SandboxInfo.detail`).
- `harness495/core/context.py`: `render_profile` (the documentation files and the declared
  conventions), `ContextPack.add_untrusted`.
- `harness495/core/prompts.py`: `COMMON_RULES`.
- `harness495/core/engine.py`: `_clarify`, `_specify` (`read_doc_excerpts` into the untrusted
  zone).
- `tests/features/context_distribution.feature` and
  `tests/test_context_distribution_scenarios.py`.
- `tests/test_live.py`:
  `test_live_claude_does_not_read_the_project_s_instruction_file`,
  `test_live_codex_does_not_read_the_project_s_instruction_file` — the only tests that measure
  the closure against the real CLIs rather than the command built for them.
