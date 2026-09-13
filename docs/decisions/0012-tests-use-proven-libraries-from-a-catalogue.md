# 0012. Tests are implemented with proven specialised libraries, chosen from a catalogue by technology and role that binds 495 and the host projects alike

- Status: accepted
- Date: 2026-09-13; refined 2026-09-13 (a cell may hold several recommended entries, each with
  its condition; a gap is stated only on a role whose measure can contradict the agent)

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
   or a library other than the catalogued one for that role, 495 states the gap to the
   requester at `495 init` and `495 profile`, and proposes to put the catalogued one in place.
   Only the roles whose measure can contradict what the agent produced are compared: a
   scenario the requester approved, inputs the agent did not choose, a verdict on the agent's
   own tests, rules the project set. The runner, the test doubles and the performance bound
   hold no such oracle; they stay in the catalogue for 495's own tests and are never a gap.
   The Roles table of the catalogue marks each role. The proposal is persisted so that it can
   be acted on later, as runs to process or an equivalent record; that part is to be built:
   `docs/etude-harnais-495.md`, E50 (c).

## Consequences

- Adding a role or a technology to the catalogue is a documentation change with a source; adding
  a library without a source is refused in review.
- Profile detection (`harness495/core/profile.py`) carries a notion of *role coverage*: for each
  role of the catalogue and each technology of the project, which tool measures it
  (`RoleCoverage`, with the marker the tool was recognised from). The roles are the enum
  `CatalogueRole`, kept equal to the document's Roles table by `tests/test_catalogue.py`; the
  markers come from the studies' "What a profile can detect" sections. A technology without
  markers has no rows, so that an unmeasured role always states a fact about the project and
  never a gap in the profile. Tools found this way join the profile's tooling, so the agents
  are told about them.
- The comparison with the catalogue (point 4) is `harness495/core/catalogue.py::compare`,
  run at the end of `detect_profile`; its result is stored on the profile (`CatalogueGap`,
  `ProjectProfile.catalogue_gaps`) so that a run records the gaps it saw. `RECOMMENDED`
  mirrors the document's `recommended` entries and `CONTRADICTING_ROLES` its Roles table;
  `tests/test_catalogue.py` keeps both equal to the document. A cell with several entries is
  compared with the first conditional entry whose condition holds in the project, else with
  the default; a project that measures every tool of that entry has no gap, whatever else it
  measures. A technology whose section is empty has no gap: nothing is stated against a
  recommendation that does not exist.
- A host project may keep a library the catalogue does not recommend; 495 proposes, the
  requester decides, and the decision is recorded like any other.
- First application: `tests/test_architecture.py` runs `import-linter` contracts declared in
  `pyproject.toml` instead of parsing imports itself (0011).

## Where in the code

- `docs/test-libraries.md`: the catalogue.
- `pyproject.toml`: `[tool.importlinter]`, dev dependency `import-linter`.
- `tests/test_architecture.py`.
- `AGENTS.md`, section Invariants (the rule for 495's own tests).
- `harness495/core/models.py`: `CatalogueRole`, `RoleCoverage`, `ProjectProfile.role_coverage`.
- `harness495/core/profile.py`: `ROLES_BY_TECHNOLOGY`, `PYTHON_TOOLS`, `SHELL_TOOLS`,
  `_python_coverage`, `_shell_coverage`; `core/context.py::render_profile`, `495 profile` and
  the TUI profile view show the rows.
- `harness495/core/catalogue.py`: `RECOMMENDED`, `CONTRADICTING_ROLES`, `applicable`, `compare`;
  `harness495/core/models.py`: `CatalogueGap`, `GapKind`, `ProjectProfile.catalogue_gaps`;
  `495 profile` and `495 init` print the gaps, the TUI profile view lists them.
- `tests/features/profile.feature` and `tests/features/catalogue.feature` with
  `tests/test_profile_scenarios.py`; `tests/test_catalogue.py`.
- To build: the persisted conformance proposal and the requester's answer (E50 (c)).
