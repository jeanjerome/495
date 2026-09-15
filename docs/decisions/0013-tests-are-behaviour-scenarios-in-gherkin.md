# 0013. Tests are behaviour scenarios, written in Gherkin or in a Given/When/Then shape that reads like it

- Status: accepted
- Date: 2026-09-13

## Context

495 accepts a change on evidence: a requirement is tied to verifications, and the decision reads
what those verifications observed (0001). The verifications that carry the most weight are the
tests of a behaviour, written by the producer for the change (`to_create`) or already present
in the host project. Their readability decides whether the requester, the specifier and the
reviewers can tell what a passing test proves. A test written as a function of assertions is
read by whoever knows the code; a scenario written as Given/When/Then is read by whoever knows
the domain, which includes the requester who wrote the intent and the specifier who wrote the
requirement it verifies. The project chose that second reading as the norm. The catalogue
(0012) already recognises `.feature` files as test files (`core/reading/verification.py`) but
had no role for the tool that runs them, and 495's own suite was written as plain pytest
functions.

## Decision

1. A test that verifies a behaviour of the product (the Produit contract: an acceptance test,
   a test created for a requirement) is a Gherkin scenario in a `.feature` file, bound to
   steps by the library the catalogue recommends for the role `bdd` of the technology.
2. A test that measures another contract, where a feature file would say nothing a reader
   needs (a property over generated input, an architecture rule, a benchmark, a fuzz target,
   a contract check driven by an API description), keeps the same shape without the file: its
   name reads as a sentence about the behaviour, and its body is split into what is given,
   what is done and what is then observed. Nothing is asserted outside the *then* part.
3. The catalogue carries a role `bdd`. Its default entry for a technology runs inside the
   technology's `runner` entry, so that every other catalogued library (property, doubles,
   coverage, mutation, performance) stays available to a scenario's steps; a standalone BDD
   runner is the entry to take when the project has no such suite to lose.
4. The rule applies to 495's own suite: a new test follows it; an existing test migrates when
   it is touched. It applies to host projects through the same mechanism as the catalogue: a
   `test` verification is described as a scenario, the producer writes it as a feature file when
   the project has the `bdd` tool, and the absence of that tool is a conformance proposal
   (`docs/etude-harnais-495.md`, E50 and E51).

## Consequences

- A requirement and the scenario that verifies it read in the same language: the requester
  can check that the scenario is the behaviour asked for, not only that a test passed.
- The choice of the `bdd` library follows the `runner`: for Python, pytest-bdd when the
  project has pytest tests, because it is a pytest plugin, and behave when it has none
  (`docs/studies/2026-09-13-python-bdd-libraries.md`). Both are recommended; the condition
  decides. A scenario under behave cannot use the `mocker`, `benchmark` or `limit_memory`
  fixtures, is invisible to mutmut's per-test selection, and does not take the pytest options
  495 passes to host projects, which is why it is not the default for a pytest project.
- pytest-bdd follows pytest slowly: its 8.1 release predates pytest 9 and raises a
  `PytestRemovedIn10Warning`; the dev dependency pins `pytest<10` until the plugin catches up.
  If it stops following pytest, behave is the entry left, at the cost named above.
- Step definitions are code and follow the catalogue like any other test code: a step that
  needs a double uses pytest-mock, a step that states an invariant uses hypothesis.
- Cost: a scenario is two files (feature and steps) where a function was one; the steps of a
  feature are reused across its scenarios, which pays the cost back after the first.
- Rejected alternatives: describe/it nesting (pytest-describe, mamba) is a naming style, not
  Given/When/Then, and gives the requester no file to read; Gherkin-in-docstrings without a
  binding library (a hand-written parser) is the ad-hoc script 0012 forbids.
- To build: the specifier phrases `test` verifications as scenarios; the producer's task
  states the feature-file form when the profile finds the `bdd` tool; the profile detects it
  (E50 role coverage); the report shows the scenarios a requirement leans on.

## Where in the code

- `docs/test-libraries.md`: role `bdd`, Python entry pytest-bdd.
- `docs/studies/2026-09-13-python-bdd-libraries.md`: the study behind the entry.
- `pyproject.toml`: dev dependencies `pytest-bdd`, `pytest<10`.
- `tests/features/decide.feature`, `tests/test_decide_scenarios.py`: first application, the
  decision scenarios of `core/reading/decide.py::assess`.
- `tests/features/scope.feature`, `tests/test_scope_scenarios.py`: the paths a change is
  allowed to touch (`core/reading/scope.py::check_scope`).
- `AGENTS.md`, section Invariants.
- `harness495/core/reading/verification.py::_TEST_SUFFIXES`: `.feature` counted as a test file.
- To build: `harness495/core/prompts.py` (`SPECIFIER_TASK`, `PRODUCER_TASK`),
  `harness495/core/profile.py` (detection of the `bdd` tool).
