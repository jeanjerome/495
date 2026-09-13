# 0012. Tests are implemented with proven specialised libraries, chosen from a catalogue by technology and role that binds 495 and the host projects alike

- Status: accepted
- Date: 2026-09-13; refined 2026-09-13 (a cell may hold several recommended entries, each with its condition)

## Context

A check written as an ad-hoc script (a walk over the tree, a regex over a file, a hand-rolled
comparison) is a second implementation to trust: it has its own bugs, no community reviewing
it, no upgrade path, and it is opaque to a reviewer who knows the domain's standard tool. The
first architecture test of 495 was such a script, parsing imports with `ast`, while
`import-linter` does the same job with published contracts. The same applies to host projects:
a project that measures a contract (property-based testing, mutation, architecture, security)
with a script, or measures it not at all, gives 495 a weaker instrument than the one the
ecosystem already provides.

## Decision

1. A test or a check, in 495 and in a host project, is implemented with a specialised library
   that is proven in its ecosystem. A hand-written script is admissible only when no such
   library exists for that role and technology; the test's docstring then states that the
   catalogue has no entry and what was searched.
2. `docs/test-libraries.md` is the catalogue: the recommended library per technology and per
   role (test runner, BDD scenarios, property-based testing, fuzzing, mutation testing,
   coverage, architecture rules, static analysis, type checking, security, API contract,
   performance, test doubles). A cell holds one entry, or several when each states the
   condition under which it is the one to take: the first is the default, the others apply
   when their condition holds in the project (for Python BDD, pytest-bdd when the project has
   pytest tests, behave otherwise).
   An entry enters the catalogue only through a study, a piece of research, or a retrospective
   on a host project; the entry names its source and date. A rejected library is kept with the
   reason, so that it is not proposed again.
3. The catalogue applies to 495 itself: a test added to `tests/` uses the catalogued library for
   its role, or the exception in point 1.
4. The catalogue applies to host projects: when the profile finds no test of a catalogued role,
   or a library other than the catalogued one for that role, 495 proposes to the requester to
   put the catalogued one in place. The proposal is made at `495 init` (or `495 profile`) and is
   persisted so that it can be acted on later, as runs to process or an equivalent record. The
   mechanism is to be designed and built: `docs/etude-harnais-495.md`, E50.

## Consequences

- Adding a role or a technology to the catalogue is a documentation change with a source; adding
  a library without a source is refused in review.
- Profile detection (`harness495/core/profile.py`) grows a notion of *role coverage*: which roles
  the project measures, with which tool. Until it does, point 4 is a decision without an
  implementation.
- A host project may keep a library the catalogue does not recommend; 495 proposes, the
  requester decides, and the decision is recorded like any other.
- First application: `tests/test_architecture.py` runs `import-linter` contracts declared in
  `pyproject.toml` instead of parsing imports itself (0011).

## Where in the code

- `docs/test-libraries.md`: the catalogue.
- `pyproject.toml`: `[tool.importlinter]`, dev dependency `import-linter`.
- `tests/test_architecture.py`.
- `AGENTS.md`, section Invariants (the rule for 495's own tests).
- To build: role coverage in `harness495/core/profile.py`; the conformance proposal at
  `init`/`profile`; its persistence (E50).
