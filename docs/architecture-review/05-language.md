# The domain language

495 is written in an unusually deliberate vocabulary. `AGENTS.md`, `docs/architecture.md` and the
28 decision records define terms carefully and use them consistently, and the code follows the
prose rather than the other way round — a reversal of the usual order worth naming.

What is missing is the vocabulary as an artifact. The definitions are distributed across a 183-line
architecture document, a 906-line README and 28 records, so a term is learned by reading the
document that happens to use it. This file states the language in one place, in the format
`domain-modeling` prescribes: one or two sentences, what the term **is** rather than what it does,
and an opinionated `Avoid` line wherever more than one word is in circulation.

Three terms are reported as findings at the end. The rest is the language as it stands, written
down.

---

## The run

**Run**
: One intent carried from its statement to a decided change on a branch. The unit everything else
belongs to; resumable, claimed by the process advancing it.

**Intent**
: What the requester wants the change to accomplish, in their own words, before anything is
specified.
: *Avoid*: request, task, goal.

**Phase**
: One step of the workflow the engine walks, with one thing it establishes. Named in
`docs/architecture.md`; the requester sees them as **stops** on the surface.
: *Avoid*: stage, step (both are taken: a *stop* is a phase as the surface shows it, a *step* is one
call to `Engine.step`).

**Iteration**
: One pass of produce, verify, review and decide over one version. A rejected iteration produces
correction requests and the next one.

**Version**
: The exact tree an iteration judged: a base commit, a head commit, a patch hash, the files changed.
Everything measured names the commit it was measured on.

**Base version**
: The commit the change starts from, as it was before the change existed. What a control run runs
on.
: *Avoid*: baseline (taken, below), original, parent.

**Worktree**
: The git worktree under `~/.cache/495/worktrees/` where a run works. The user's checkout is written
by `495 merge` and by nothing else.

---

## What is asked and what is promised

**Clarification**
: The decisions the intent leaves open, put to the requester in rounds before the specification is
written. Its answers are facts for every role that follows.

**Frontier**
: The decisions whose prerequisites are settled — the questions that can be asked now without
guessing at answers not yet heard. Recomputed each round.

**Specification**
: What the change must accomplish, as requirements tied to verifications, with what is out of scope
and what nobody was asked about. Written by the specifier, approved by the requester at the gate.
: *Avoid*: spec in prose (fine as a type name, `Spec`).

**Requirement**
: One thing the change must accomplish, of kind `behaviour` or `non_regression`, tied to the
verifications that would show it.

**Verification**
: One command, or one test to create, that would show a requirement met. Names the catalogue role it
measures, if any.
: *Avoid*: check (taken, below), test (a verification may be a linter or a build).

**Behaviour scenario**
: A verification that is a test, stated as given / when / then before it exists. What the requester
approves and what the test designer writes from.

**Sufficiency**
: What the harness computed about a verification before anything ran: whether it can show what it
claims. A role the project does not measure makes it `insufficient`.

**Allowed paths**
: The files a change may touch — the project's criteria, or the specification's where the project
declares none.

---

## What is measured

**Evidence**
: One thing the harness observed, on a named commit. The only material a requirement's status may
rest on. Ten kinds, listed in `docs/architecture.md`.
: *Avoid*: result, output, finding (a *finding* is a reviewer's, below).

**Check**
: One measurement the harness makes of its own accord, beyond running what the specification named:
scope, suite, stability, coverage, mutation, instrument. Each yields evidence of its own kind, and
each can leave a requirement `undetermined` without any command having failed.

**Control run**
: The same command run on the base version carrying the change's test files, to tell a command that
reports the change from one that reports the same thing either way.
: *Avoid*: baseline run, reference run.

**Baseline**
: The readiness run of a project command on the base version, before any change exists — evidence
that the command runs at all. A different thing from a control run; both words are load-bearing and
neither may take the other's place.

**Instrument**
: A verification command seen as a measuring device rather than as a test: something that can be
sound, blind, or unstable. What `instrument_check`, `instrument_fault` and `495 stats` are about.
: *Avoid*: tool (a *tool* is what the catalogue recommends — mutmut, ruff, vitest — not the command
that runs it). See L1 below.

**Calibration**
: Reading what each instrument reported against what it reported without the change, to decide
whether it is measuring the change at all.

**Mutant**
: A wrong version of the change, one line of the diff altered in a stated way. A mutant no command
reports leaves the requirements resting on those commands undetermined.

**Reach**
: Which lines the change adds the verifications actually execute, read from the project's own
coverage tool and crossed with the diff.

---

## Who acts

**Role**
: One of the five things an agent is asked to be: clarifier, specifier, test designer, producer,
reviewer. Each gets its own context and its own system prompt.

**Intervention**
: One call to one agent in one role, with everything it was given and everything it returned, kept
on disk. The unit cost is charged against.
: *Avoid*: call, turn, invocation.

**Perspective**
: The angle a reviewer reads from — one reviewer per perspective, each with its own context.

**Context pack**
: Everything one intervention is given, in two zones: facts the harness measured, and untrusted
content produced by an agent or read from the repository. The only route by which anything reaches
an agent.

**Fact** / **Untrusted**
: The two trust zones of a context pack. A repository file is untrusted whichever CLI reads it; what
the requester wants obeyed travels as a fact.

**Agent**
: The adapter that drives one CLI or endpoint in one role. Three exist; none lets its CLI read the
target project's own configuration.

---

## What is decided

**Decision**
: Something settled during the run, by the harness or by the requester, recorded with who settled
it and why.

**Pending decision**
: A question the run is stopped on, with its options, each stating its consequence. The run sits in
`awaiting_decision` until it is answered.

**Requirement status**
: `satisfied`, `violated`, or `undetermined`. Only a verification that ran on the evaluated commit
and passed makes a requirement `satisfied`; `undetermined` blocks acceptance.

**Correction request**
: What a violated requirement becomes: the requirement, the claim and the observation. The
reviewer's explanation and remedy stay out of it.

**Finding**
: What a reviewer reported, citing an observation. A finding with no observation cited cannot
violate a requirement.

**Verdict**
: The outcome of an iteration: accept, reject, undetermined.

---

## What outlives the run

**Profile**
: What the harness read of the project before the run: languages, tooling, commands, which tool
measures which catalogue role, the gaps, the lessons in force, the conventions.

**Catalogue**
: The recommended test library per technology and role, and what a test of each role must show. Rows
are admitted by hand; `495 retro` proposes them.

**Catalogue role**
: One kind of thing a test can show — unit, property, bdd, mutation, coverage, and the rest. A
verification names the role it measures.

**Role coverage**
: Which tools in the project measure which catalogue role, read from markers in the tree.

**Gap**
: A catalogue role the project does not measure. Becomes a **proposal**, which the requester
accepts, declines or defers. An accepted proposal creates a run; a declined one is never asked
again.

**Retrospective**
: What one run showed about each tool that measured a catalogue role: proven, faulty or
inconclusive, with the catalogue row it yields.

**Lesson**
: What one run showed about the project rather than about its tools — a replaced command, a
hand-written correction, a rule a reviewer blocked on, the scope a version stayed inside. Enters the
project's criteria on the requester's acceptance alone.

**Criteria**
: What the project declares it wants obeyed, in `.495/project.toml`, plus the lessons in force.
Nothing written by the harness.

---

# Language findings

## L1 · Important · `instrument` carries two unrelated meanings

**Sense A — a verification command as a measuring device.** The load-bearing one. It is in the
model (`DecisionKind.instrument_fault`, `EvidenceKind.instrument_check`,
`Iteration.instrument_faults`), in the statistics (`stats.InstrumentStat`), in the decision records,
and in the prose of `AGENTS.md`.

**Sense B — a command rewritten to emit a coverage report.** `core/reach.py:159`:

```python
@dataclass(frozen=True)
class Instrumented:
    """A project's own test command, rewritten so that it writes a coverage report."""
```

This is "instrumented" in the coverage-tooling sense, which has nothing to do with sense A.

The two meet inside one class, ninety lines apart:

```
engine.py:2196   def _instrument(self, run, command) -> Instrumented | None:     # sense B
engine.py:2564   def _instrument_fault_settled(run: Run) -> bool:                # sense A
engine.py:2569   def _instrument_decision(self, run, it, proposals):             # sense A
```

`_instrument` and `_instrument_fault_settled` read as members of one family and are not.

**Why it matters here more than elsewhere.** Sense A is one of the concepts the harness *reasons
with*: a run stops when an instrument is found faulty, `495 stats` counts instrument faults per
command, and `495 retro` proposes catalogue rows on the strength of what the instruments showed. A
word that carries the harness's judgement of its own measurements should not also name a shell
command with `coverage run` prepended.

**Remedy.** Keep `instrument` for sense A — it is in the model, the ADRs and the published
statistics, and moving it would cost a schema change. Rename sense B into the coverage vocabulary it
belongs to: `reach.Instrumented` → `reach.UnderCoverage`, `engine._instrument` →
`engine._under_coverage`. Internal names only; no persisted document changes.

## L2 · Minor · `watcher` is a coinage with no definition

```
$ grep -rn "watcher" harness495/ --include="*.py" | wc -l   # 22, all in engine.py
$ grep -rn "watcher" docs/ --include="*.md" | wc -l         # 5, every one a function name
```

`_repeat_watchers`, `_coverage_watchers` and `_mutation_watchers` each answer the same question —
**which verifications does this check select, and in what order** — and each answers it well, with a
careful docstring. The concept is real, recurring, and load-bearing: the selection rules encode
`docs/decisions/0022`, `0023` and `0024`.

The word naming it appears in one module, and in the documents only as the name of one of those
three functions, inside a *Where in the code* list (`0022`, `0023`, `0024`, and `E52` in the étude).
Nothing defines it. It is not in `models.py`, not in `architecture.md`, and no record says what a
watcher *is*. A reader meets it three times and never meets its definition,
and "watcher" recruits no prior that helps: nothing is being watched.

**Remedy.** One of two, and the choice is worth making deliberately. Either promote the concept —
define it in `architecture.md`, give it a return type, and let the report say which verifications
each check selected and why one was left out — or retire the word and name the functions after what
they return (`_verifications_to_repeat`, `_verifications_to_instrument`, `_verifications_to_mutate`).
The first is better if the requester should see the selection; today the exclusions surface only as
warnings (`engine.py:2005-2012`), which is a thin channel for a decision that determines what the
harness can prove.

## L3 · Minor · The glossary has no home

Every term above is defined somewhere in the repository. None of them is defined *once*.

`docs/architecture.md` carries the data model as prose; `AGENTS.md` carries the invariants; each ADR
defines the terms its decision needs; `README.md` defines the commands. A reader learning what
`sufficiency` means reads whichever of the four happens to mention it.

The cost is not confusion today — the vocabulary is consistent, which is the hard part and it is
already done. The cost is that the consistency is maintained by one person's memory, and there is no
artifact a reviewer, a contributor, or a future run's specifier can be pointed at.

**Remedy, and its cost.** `domain-modeling` prescribes a root `CONTEXT.md`. For 495 that would be a
fifth always-visible document at the root, and `AGENTS.md` is deliberately under 120 lines of
pointers. The cheaper placement is `docs/glossary.md`, reached by one line in `AGENTS.md` under
**Pointers**, next to `docs/test-libraries.md`. This file can be that document, or its draft —
see [06-plan.md](06-plan.md) Q3.

There is one reason to think it is worth more here than in most repositories, and it connects to an
entry the étude already holds. `E12` states that the specifier has no domain vocabulary to work
from: it reads `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md` and `README.md` truncated to 4 000
characters each, as untrusted content, with no slot for a glossary — naming `CONTEXT.md` as the
shape that is missing. Its remedy is to type the documents a project declares (`glossary`,
`architecture`, `adr`, `conventions`) and route each to the role it serves.

`ProjectConfig.docs` already exists (`core/models.py:346`) and `profile._collect_docs` already reads
declared paths ahead of `DOC_CANDIDATES` (`core/profile.py:609-613`); only the typing is missing. If
`E12` is closed, 495 is the obvious first project to run it against — and it would need a glossary
to declare. Writing one now costs nothing that `E12` will not need anyway.
