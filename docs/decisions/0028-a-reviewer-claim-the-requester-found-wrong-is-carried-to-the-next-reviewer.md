# 0028. A reviewer's claim the requester found wrong is a lesson, and the next reviewer of that perspective is told it does not hold here

- Status: accepted
- Date: 2026-09-14

## Context

0027 gave a run a way out: what it showed about the project becomes a lesson, the requester
answers it, and an accepted one is part of the criteria of every run that follows. Everything
that route carries is something the project should start doing — a command to declare, a rule
to obey, a scope to stay inside, something the next specification is better written knowing.

What a reviewer got *wrong* had no route. A reviewer reads the change from one perspective and
writes findings; a blocking finding costs an iteration, and a finding that reads a requirement
as violated leaves that requirement `violated` or, with no observation cited, `undetermined`
(0001) — either way the run pays for it. When the requester looks at such a finding and
concludes the claim does not hold in this project, nothing recorded that conclusion. The next
run put the same change in front of a reviewer of the same perspective, with the same context,
and the same claim came back; `495 stats` could count it coming back (`PerspectiveStat`), and
could do nothing about it.

Half a route existed and was mistaken for the whole one: a blocking finding no requirement asked
about is proposed as a `convention`, and declining it keeps the reason and stops the proposal.
But declining says the words are not a rule of this project, which is not the same as saying the
claim was false — a true observation is often not a general rule — and a declined lesson reaches
nobody. Reviewers were the only role no lesson was ever given.

## Decision

`learn` states a fifth kind, `false_positive`: a claim a reviewer made that does not hold in
this project. `core/reading/lessons.py::_false_positives` reads it from the run document, and puts only
the findings the harness acted on — one that blocked the change, and one a reviewer read a
requirement as violated for — each citing an observation, without which 0001 reads the claim as
deciding nothing and there is nothing to refute. A finding of a review the harness discarded is
not proposed: a reviewer that altered the worktree is not a reviewer whose claims are weighed.

**The proposition put to the requester is the refutation.** Accepting a lesson means the same
thing for every kind — this is true, put it in force — so the statement says the claim does not
hold here. The requester who agrees accepts it; the requester for whom the claim stood declines
it with that reason, and it is not proposed again. `accept --as` is refused: the requester does
not restate a reviewer's claim, only answers it.

A lesson is identified by its kind, the perspective it answers, and the claim, so the same
words from two reviewers are two lessons and the same claim across runs is one record naming
each of them.

The kind declares nothing: `criteria` does not touch it, `toml_lines` states no line, and
`.495/project.toml` has no key it belongs in. In force, it travels as a fact, and to one role —
the reviewer of that perspective, in `_review`, as *Claims of this perspective the requester
found do not hold here* (`core/context.py::render_refuted`). The specifier is given the lessons
that bear on a specification and not these.

## Consequences

- One blocking finding no requirement asked about is now proposed twice over: as a `convention`
  to ask of every change, and as a claim that does not hold. The two are opposite readings of
  the same words, and which one it is is the requester's to say. Accepting both is possible and
  contradictory; nothing prevents it, because a harness that arbitrated between them would be
  deciding what only the requester knows.
- A reviewer is told what the requester answered, never what another reviewer said. Giving one
  perspective the refutations of every angle would read as a list of things not to look at.
- The fact tells the reviewer not to raise the claim again *unless this version gives it an
  observation the earlier one did not have*. A claim can be wrong about the project as a rule
  and right about one version of it, and the refutation is about the project.
- This is the first lesson that reaches a reviewer. The trust boundary of 0005 holds as it does
  for a `convention`: an agent wrote the words, the requester admitted them, and they travel as
  a fact from there. A reviewer still never reads another reviewer's verdict or the producer's
  transcript (0004, 0005).
- A run is given the lessons in force at the moment it is profiled, so what was accepted after
  it does not change what its reviewers were told.
- `Lesson.key` now takes the perspective into account. Lessons of the four kinds that carry no
  perspective keep the key they had, so a document written before this change reads unchanged.
- Nothing here lets the harness decide a finding was wrong. It has no opinion: `_false_positives`
  proposes, and only an answer puts something in force.

## Where in the code

- `harness495/core/models/lessons.py`: `LessonKind.false_positive`, `Lesson.perspective`,
  `Lesson.key`, `Lesson.declares`.
- `harness495/core/reading/lessons.py`: `_false_positives`, `learn`, `HEADING`; `criteria` and
  `toml_lines` leave the kind alone.
- `harness495/core/context.py`: `render_refuted`.
- `harness495/core/engine/engine.py`: `_review` gives the reviewer the claims of its own perspective;
  `_specify` leaves them out of the specifier's lessons.
- `harness495/interfaces/cli.py`: `_print_lesson` names the reviewer a lesson answers;
  `lessons accept` says which reviewer is told.
- `tests/features/lessons.feature` with `tests/test_lessons_scenarios.py`.
