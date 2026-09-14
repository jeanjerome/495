# 495

Agent harness: an intent becomes a specified, produced, verified, reviewed change on a branch;
the engine accepts it on evidence it measured itself. Python 3.11+, package `harness495`,
CLI `495`, launcher `./run.sh`.

## Pointers

- Before changing a phase, a decision the run raises, or the verify/review/decide chain, read
  `docs/architecture.md` (workflow, packages, boundaries, data model, state on disk).
- Before changing how evidence is judged, how instruments are measured, what a producer or
  reviewer is shown, how a run is claimed or merged: read the matching record in
  `docs/decisions/` (index: `docs/decisions/README.md`). Each record states what a change to
  that code must preserve.
- When asked to close a known gap, or before proposing a new control: read its entry in
  `docs/etude-harnais-495.md` (ids `E01`..`E49`, each with location, priority, effort, remedy).
- Before writing or changing a test, in 495 or for a host project: read `docs/test-libraries.md`
  (the library to use per technology and role; how an entry gets in).
- For commands, options, exit codes, configuration keys, agent isolation tables: `README.md`.
- For the exact shape of a persisted document: `495 schema run|event|spec|config`.
- Dev commands (tests, lint, typecheck, live tests): `README.md`, section Development.

## Invariants

Keep these true in every change; each has a test or a record that names it.

- Package dependencies point one way: `interfaces` → `core.engine` → `agents` → `sandbox` →
  `core.models`. The exact rules are import-linter contracts in `pyproject.toml`, run by
  `lint-imports` and by `tests/test_architecture.py` (`docs/decisions/0011-package-boundaries.md`).
- A test uses the library the catalogue `docs/test-libraries.md` recommends for its role and
  technology. A hand-written check is admissible only for a role with no entry, and its docstring
  says so (`0012`).
- A test of a behaviour is a Gherkin scenario in a `.feature` file bound to steps by the
  catalogue's `bdd` entry (pytest-bdd for Python with pytest tests, behave otherwise); a test
  of another contract keeps the Given/When/Then shape in its name and body, and asserts only in
  the *then* part (`0013`).
- `core/decide.py::assess` stays a pure function of spec, evidence and reviews. A requirement
  becomes `satisfied` only from a verification that ran on the evaluated commit and passed;
  `violated` only from a failed verification or a reviewer finding that cites an observation;
  `undetermined` otherwise, and `undetermined` blocks acceptance (`0001`).
- Every verification a `behaviour` requirement leans on is measured on the change and on the
  base version carrying the change's test files; a command reporting the same on both leaves
  the evidence (`0002`, `0003`); one that fails on the base by an execution error and not by
  an assertion is `unconfirmed`, still credited, and the `test_quality` reviewer, called
  whenever a test is to be created, is told to read it (`0019`).
- The suite that passed on the base is measured on the change: `core/suite.py` reads the diff
  over the test files that existed there and the runners' tallies on both versions, a test
  deleted, removed or skipped, or a smaller tally, is a failed `suite_check`, and a passing
  command on such a suite credits no `non_regression` requirement (`undetermined` until the
  requester rules); every existing test the change touched is listed to the reviewers (`0021`).
- Every command that passed on the change is run again against a few wrong versions of it, one
  line of the diff altered in a stated way each; a wrong version none of them reports leaves the
  behaviour requirements resting on those commands `undetermined`, never `violated`, and never
  becomes a correction request (`0022`).
- A correction request carries the requirement, the claim and the observation. Reviewer
  explanations and remedies stay out of the producer's context; the producer's transcript stays
  out of every reviewer's context (`0004`, `0005`).
- Build every prompt with `ContextPack`: harness-measured material under facts, agent- or
  repository-produced material under untrusted (`0005`).
- A test to create is written by the test designer, in an intervention of its own before the
  producer; the harness commits the test files it finds written and puts any other file back;
  a version of the change that modifies one of them fails the scope check (`0020`).
- A verification names the catalogue role it measures (`Verification.role`); a role no
  coverage row of the profile measures makes it `insufficient`, with the catalogue's
  recommendation as rationale, and the tool enters the project through a proposal, never
  through the change; a proposal the requester declined is read at profiling and never asked
  again (`0014`).
- Runs work in a git worktree under `~/.cache/495/worktrees/`; the harness makes the commits;
  the user's checkout is written by `495 merge` only (`0006`, `0010`).
- `core/retro.py::retrospect` is a pure function of the run document; `495 retro` writes
  `retrospective.json` under the run and never the catalogue, whose rows are admitted by hand
  (`0015`).
- Cost is `reported`, `estimated` or `unknown` (`0008`).
- Tests use `Scenario` and `FakeAgent` from `tests/conftest.py`. Mark a test that reaches a
  real agent CLI or the network `live`.

## Recording a decision

Trigger: a change introduces or reverses a rule that a reader of the code alone could not
reconstruct (why a value is derived rather than stored, why a command is a cherry-pick, what a
status may and may not mean).

1. Copy `docs/decisions/0000-template.md` to `docs/decisions/NNNN-<statement>.md`, next number.
2. Fill Context, Decision, Consequences, Where in the code. Superseding: write the new record,
   set the old one's status to `superseded by NNNN`, leave its body as it was.
3. Add the row to `docs/decisions/README.md`.

Done when the record names every module and test that carries the decision.

## Written content

Comments, commit messages, PR text and issues describe the behaviour of the code in technical
terms: what it does and why that holds. Reference the code and the record, never the plan,
session, review round or ticket that led to it. No attribution trailer.

Commit subject: `<type>: <description>`, type in `feat fix refactor docs test chore perf ci`.
