# 0025. The requester's decisions are taken before the specification, in rounds, and a settled question is never asked again

- Status: accepted
- Date: 2026-09-14

## Context

`Engine._specify` is one read-only intervention that returns a whole specification, and
`SPEC_SCHEMA` has no field for an open question. Facing an ambiguity in the intent, the
specifier has one exit: decide, and record the decision in `Spec.assumptions`, a flat list of
strings that also carries the requester's revision notes (`_apply_decision` appends
`revision requested: <note>` to it). At the gate the requester approves requirements and
verifications; nothing in front of them separates a fact the specifier could not check (the
project targets one runtime) from a decision that was theirs to take (an unknown key is
ignored rather than refused).

The cost of a wrong reading is the highest the harness can pay, because every control it has
measures the change against the specification. A specification approved on a misreading is
implemented faithfully by the producer, confirmed as conformant by `spec_compliance`, and
measured by verifications that name what the specification named: 0001 to 0024 all hold, and
the run accepts the thing nobody asked for. No control compares the specification with the
intent.

The interview discipline that answers this is known and stated outside 495 (mattpocock/skills,
`grilling`, whose two review axes `prompts.py` already adapts): the decisions form a tree; the
**frontier** is every decision whose prerequisites are settled, which is exactly the set that
can be asked without guessing at answers not yet heard; a round asks the whole frontier,
numbered, each question with a recommended answer; the answers reshape the tree and the
frontier is **recomputed** for the next round; finding facts is the agent's job and taking
decisions is the human's; the session ends when the frontier is empty, nothing silently
assumed.

That discipline was written for an interactive session: an unbounded chat loop, the tree held
in the model's context, facts fetched by sub-agents. A 495 run blocks on a `PendingDecision`
persisted in `run.json`, answered minutes or hours later from another process through
`495 decide`, by an agent that has no session across interventions and no sub-agent
(`--disallowedTools Task, Agent, Skill`). The tree therefore cannot live in the agent; it has
to be a document the harness holds and hands back.

## Decision

A phase `clarify` runs between `profile` and `specify`, in rounds, and its answers are facts
for every later intervention.

**The role.** `Role.clarifier`, capability `read`, its own entry in `RolesConfig`, its own
output schema. It is not the specifier: the schema differs, the transcript is out of the
specifier's context by construction (0005), and the role can be pointed at another model.

**A round is one intervention.** The clarifier is given the intent, the profile, the catalogue
against the project's role coverage, the tracked files, the repository's documents as untrusted
content, and — as facts — every question already answered, with the answer. It returns the
frontier: the questions whose prerequisites are settled. Each carries an id, a title, a body,
at least two options, a recommended option, and `checked`: the files it read and the commands
it ran to reach that recommendation. Each option states its **consequence on the
specification** (which requirement appears or disappears, which verification changes kind),
the same rule `DecisionOption.consequence` already imposes on every question 495 asks. The
harness completes the options with `other`, which takes a note: a tree may not force a false
choice.

**The tree is recomputed, never popped.** The harness keeps no queue of questions. Each round
is a new intervention over all the answers so far, because a question's options depend on
answers not yet given. A question the harness has already recorded as answered is dropped from
the round and the drop is recorded as a warning: a round never re-asks a settled question.
A question with fewer than two options, or an option with no consequence, is dropped the same
way — a question that changes nothing about what gets specified is not put to the requester —
and so is one whose recommendation names no option it offers, since the answer `--auto-approve`
would take does not exist.

**One decision per round.** `DecisionKind.clarify`, one `PendingDecision` carrying the round's
questions. The requester answers question by question, or takes every recommendation in one
gesture. `--auto-approve` takes the recommendations and records them as taken by the harness,
so the report distinguishes what the requester chose from what the harness took on their
behalf.

**Where the answers go.** They are persisted on the run as `ClarifyRound`s and enter the facts
of the specifier, the test designer, the producer and every reviewer under `Requester's
decisions`: a human approved that text, which puts it in the same trust class as the approved
specification. The clarifier's transcript goes nowhere. `Spec.decisions_taken` records
question, options, choice and who took it; `Spec.assumptions` keeps only what the clarifier
could not verify and nobody was asked about.

**The end.** The phase ends when a round comes back with no question — the frontier is empty.
`budget.max_clarify_rounds` bounds the rounds put to the requester, not the interventions: one
further round runs after the last answered one, because only a round can say whether the
frontier is empty, and when it is not, its questions are recorded as unanswered rather than
asked. Reaching the cap therefore does not pass in silence — the questions left open are on the
run, the specifier is given them as open, and an assumption taken in their place says what it
stands on. A first round with no question raises no decision at all: the phase then costs one
read-only intervention and the run walks on to `specify`. `max_clarify_rounds = 0` leaves the
phase out, agent and stop alike.

## Consequences

- An assumption that was a decision is either answered by the requester or visible as
  unanswered. That is what the record buys, and it is the only thing that addresses the
  misreading at its source rather than downstream of it.
- A run costs one clarifier intervention per round and one human stop per round, bounded by
  `max_clarify_rounds`. A run whose intent is unambiguous costs one intervention and no stop.
- The answers are run state. On the same project, round one asks the same questions run after
  run until something carries them forward; that is E44's subject, and this record does not do
  it.
- A reviewer that compares the diff with intent and decisions (E41) becomes cheap, because the
  decisions exist as text a third party can read.
- Letting the specifier ask inside `SPEC_SCHEMA` (a `questions` field on the specification) was
  rejected: the question would arrive with its answer already built into the requirements
  around it, and the gate would ask two different things at once — approve this specification,
  and answer this question. They are two stops because they are two questions.
- One `PendingDecision` per question was rejected as the shape, and kept as the fallback: it
  needs no change to the model and every surface already handles it, but it offers no single
  gesture for "take every recommendation" and it hands the requester six unrelated stops where
  the round is one reading. The cost of the chosen shape is `PendingDecision.questions` and an
  answer table through the CLI, the API, the interactive menu and the run surface; on the
  surface, `tui/asking.py` already walks a sequence of steps whose next step is a pure function
  of the answers given, which is a frontier walk.
- Shipping the discipline as an agent skill was rejected. Claude Code and Codex both load
  skills, and both load them from paths the harness does not control: the repository under
  test and the operator's home. `claude` is given `--disallowedTools ... Skill`; `codex exec`
  has no equivalent flag, only per-path `enabled = false` entries in `~/.codex/config.toml`,
  and it scans `.agents/skills` from the worktree upwards. A skill channel would put agent
  instructions in the run that `run.json` cannot name, leave `openai_compat` without them, and
  let the target repository speak as an instruction on the very path 495 treats as untrusted
  content (E20). The discipline travels in the prompt the harness composes, as
  `COMMON_RULES` already does.
- Fetching facts through a sub-agent, which is how the discipline resolves "facts are the
  agent's job", is not available: `Task` and `Agent` are disallowed on both CLI adapters. The
  clarifier searches the worktree itself with its read-only tools, and `checked` states per
  question what it read. A question whose answer sits in the repository then shows as one, in
  front of the requester, instead of resting on the prompt.

## Where in the code

- `harness495/core/models.py`: `Role.clarifier`, `RolesConfig.clarifier`, `DecisionKind.clarify`,
  `ClarifyOption`, `ClarifyQuestion`, `ClarifyAnswer`, `ClarifyRound`, `Clarification`,
  `ClarifyReply`, `DecisionAnswer`, `DecisionTaken`, `normalise_question`, `Run.clarification`,
  `PendingDecision.questions`, `Decision.answers`, `Spec.decisions_taken`,
  `Budget.max_clarify_rounds`, `RunStatus.clarifying` and `RunStatus.clarified`.
- `harness495/core/schemas.py`: `CLARIFY_SCHEMA`, hand-written and strict (0007); no field for
  an answer, because the clarifier does not take the decisions it states.
- `harness495/core/prompts.py`: `CLARIFIER_SYSTEM` and `CLARIFIER_TASK`; the paragraph of
  `SPECIFIER_TASK` that makes a decision binding and keeps `assumptions` for what nobody was
  asked; the sentence of the `spec_compliance` perspective that reads the diff against them.
- `harness495/core/engine.py`: `_clarify` and its round loop, `_clarify_frontier` (the three
  drops), `_clarify_answers` and `_record_clarify_answers`, `_clarify_decision`,
  `_recommended_answer`, `_decisions_taken`, `OTHER_OPTION`, the `clarify` branch of
  `_apply_decision`, the `step` entries for the two new statuses, and the fact added in
  `_specify`, `_design_tests`, `_produce` and `_review`.
- `harness495/core/context.py`: `render_decisions_taken` and `render_clarify_question`; the
  decisions on the rendered specification.
- `harness495/core/report.py`: `_clarification_section` — what was decided, by whom, what was
  left open, what the harness did not ask.
- `harness495/interfaces/`: `cli.py` (`495 decide --answer ID=OPTION --answer-note ID=TEXT`,
  `--clarifier`), `api.py` (`answers` on the decision body), `render.py`
  (`prompt_clarify_answers`), `tui/views/decision.py` (`_question_step`, `clarify_replies`),
  `tui/driving.py`, `tui/loops.py`, `tui/stages.py` and `tui/attention.py`.
- `tests/features/clarify.feature` with `tests/test_clarify_scenarios.py`: what a round may
  ask and the three drops, a settled question dropped under a new identifier, a round answered
  whole or refused, the next round recomputed, the recommendations taken under
  `--auto-approve`, the cap reached with a question left open, and the answers present in the
  facts of the four later roles.
