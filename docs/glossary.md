# Glossary: the words 495 uses

One place for the vocabulary. `docs/architecture.md` carries the workflow and the data model,
`README.md` the commands, `docs/decisions/` the reasons; each defines the terms its own subject
needs, and a reader learning what *sufficiency* means otherwise reads whichever of the three
happens to mention it.

An entry says what a term **is**, in one or two sentences, not what it does. An *Avoid* line names
the words in circulation that must not take its place, and why, whenever more than one is.

A term enters here when the code and the records already use it consistently; this file states the
language, it does not legislate it. Renaming a term means changing the code, the records and this
entry in one change.

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
: *Avoid*: stage, step — both are taken. A *stop* is a phase as the surface shows it, a *step* is
one call to `Engine.step`, and a *stage* is one entry of the verify sequence
(`core/engine/checks/sequence.py`).

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
rest on. Ten kinds: `command_result`, `scope_check`, `review_verdict`, `integrity`,
`instrument_check`, `baseline`, `suite_check`, `mutation_check`, `coverage_check`,
`stability_check`.
: *Avoid*: result, output, finding (a *finding* is a reviewer's, below).

**Check**
: One measurement the harness makes of its own accord, beyond running what the specification named.
Eight stages in a declared order (`core/engine/checks/sequence.py`): scope, protected tests, the
verifications themselves, stability, suite, calibration, coverage, mutation. Each yields evidence of
its own kind, and each can leave a requirement `undetermined` without any command having failed.
: Every check is two modules: a **driver** under `core/engine/checks/` that runs the commands and
writes the evidence, and a **reader** under `core/reading/` that says what the runs mean and
executes nothing.

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
: *Avoid*: tool — a *tool* is what the catalogue recommends (mutmut, ruff, vitest), not the command
that runs it.

**Calibration**
: Reading what each instrument reported against what it reported without the change, to decide
whether it is measuring the change at all.

**Stability**
: Whether a command reports the same thing twice on the same version, nothing changed in between.
One that reports success once and failure once says nothing, and credits nothing.

**Mutant**
: A wrong version of the change, one line of the diff altered in a stated way. A mutant no command
reports leaves the requirements resting on those commands undetermined.

**Reach**
: Which lines the change adds the verifications actually execute, read from the project's own
coverage tool and crossed with the diff.

**Suite check**
: What the change did to the test suite that passed on the base: a test deleted, renamed out of the
runner's reach, removed or skipped, or a smaller tally on the change than on the base.

---

## Who acts

**Role**
: One of the five things an agent is asked to be: `clarifier`, `specifier`, `test_designer`,
`producer`, `reviewer`. Each gets its own context and its own system prompt.

**Intervention**
: One call to one agent in one role, with everything it was given and everything it returned, kept
on disk. The unit cost is charged against.
: *Avoid*: call, turn, invocation.

**Perspective**
: The angle a reviewer reads from — one reviewer per perspective, each with its own context. Six
exist: `spec_compliance`, `correctness`, `security`, `test_quality`, `standards`,
`maintainability`.

**Context pack**
: Everything one intervention is given, in two zones: facts the harness measured, and untrusted
content produced by an agent or read from the repository. The only route by which anything reaches
an agent (`core/context.py`).

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
and passed makes a requirement `satisfied`; `undetermined` blocks acceptance
(`core/reading/decide.py`).

**Correction request**
: What a violated requirement becomes: the requirement, the claim and the observation. The
reviewer's explanation and remedy stay out of it.

**Finding**
: What a reviewer reported, citing an observation. A finding with no observation cited cannot
violate a requirement.

**Verdict**
: The outcome of an iteration: `accept`, `reject`, `undetermined`.

---

## What outlives the run

**Profile**
: What the harness read of the project before the run: languages, tooling, commands, which tool
measures which catalogue role, the conditions that held while it read them, the gaps, the lessons in
force, the conventions.

**Catalogue**
: The recommended test library per technology and role, and what a test of each role must show
(`docs/test-libraries.md`, mirrored by `core/reading/catalogue.py`). Rows are admitted by hand;
`495 retro` proposes them.

**Catalogue role**
: One kind of thing a test can show — `runner`, `bdd`, `property`, `fuzzing`, `mutation`,
`coverage`, `architecture`, `static`, `types`, `security`, `contract`, `performance`, `doubles`. A
verification names the role it measures.

**Role coverage**
: Which tools in the project measure which catalogue role, read from markers in the tree.

**Condition**
: A predicate that picks between the several entries of one catalogue cell — a file of the tree, a
dependency the project declares, a tool the role coverage names. Evaluated once, while the project
is profiled, and the outcome recorded on the profile, so that reading the catalogue afterwards opens
no file.

**Gap**
: A catalogue role the project does not measure, or measures with another tool than the recommended
one. Becomes a **proposal**, which the requester accepts, declines or defers. An accepted proposal
creates a run; a declined one is never asked again.

**Retrospective**
: What one run showed about each tool that measured a catalogue role: proven, faulty or
inconclusive, with the catalogue row it yields (`core/reading/retro.py`).

**Lesson**
: What one run showed about the project rather than about its tools — a replaced command, a
hand-written correction, a rule a reviewer blocked on, the scope a version stayed inside, a decision
taken before the specification. Enters the project's criteria on the requester's acceptance alone
(`core/reading/lessons.py`).

**Criteria**
: What the project declares it wants obeyed, in `.495/project.toml`, plus the lessons in force.
Nothing written by the harness.
