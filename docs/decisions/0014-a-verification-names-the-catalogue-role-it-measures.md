# 0014. A verification names the catalogue role it measures, and a role the project does not measure is a stated gap, never an invented tool

- Status: accepted
- Date: 2026-09-13; refined 2026-09-13 (a proposal the requester declined is read at profiling and
  never asked again)

## Context

The specifier was told which commands the project has and, since the role coverage exists
(0012), which tool measures each catalogue role. It was not told what a role measures, nor
what the catalogue recommends where the project measures nothing, and a verification had no
way to say which role it was: a property-based test, a mutation run and a coverage report were
all `test` or `command`. Two failures followed. The specifier, asked for an invariant, wrote a
test with chosen examples where the project had Hypothesis, because nothing said the tool was
there for that. And where the project had no such tool, the specifier either invented it (a
command the project cannot run, discarded at preflight) or asked the producer to add it, which
puts a dependency and a configuration decision of the requester's into an agent's change.

## Decision

A `Verification` carries an optional `role`, one of the catalogue's `CatalogueRole`s, naming
the contract it measures; it stays null for a plain command, a review or a manual check.

The specifier receives, as a fact, the catalogue against the project: for each technology and
role of the profile's coverage, what a test of the role must show (the catalogue's Roles
table), the tool the project measures it with, and, where nothing does, the entry the
catalogue recommends for the technology, with its condition, or the absence of an entry. Its
instructions say which kind of requirement calls for which role, to set `role` and use the
tool in place through the command the project runs it with, and, when the role is not measured,
to still set `role` and neither invent the tool nor ask for it as part of the change.

The sufficiency audit reads the role: a verification whose role no coverage row of the profile
measures is `insufficient`, whatever its command, with a rationale that names the contract,
the catalogue's recommendation per technology and the proposal mechanism. A requirement
carried by such verifications alone is a gap, shown at the gate like any other; the requester
answers the conformance proposal first, or approves the specification with the gap. When the
profile has no row for the role at all (a technology without markers), nothing is known and
the verification is judged on its command alone: an unmeasured role always states a fact about
the project, never a gap in the profile.

A proposal the requester declined is an answer already given, and the gate does not ask it
again. When a run is profiled, the declined proposals of the project are read once and kept on
the run's profile (`DeclinedRole`: technology, role, reason), so that the run records the
answers it knew of. The catalogue fact shows the role as declined with the reason and tells the
specifier not to call for it; a verification that names it anyway is insufficient with a
rationale that cites the refusal and says the decision stands, not a proposal to answer.

## Consequences

- The tool that measures a role enters a project through a proposal the requester answers
  (0012, point 5), never through a producer's change: the audit makes the specification say so
  before anything is produced.
- The role is informative to the harness beyond the audit: the report, the CLI and the TUI show
  it beside the kind, so the requester reads "test / property" and knows what the test claims.
  The kind keeps its meaning (how the harness runs and judges the verification); the role says
  which contract it measures. Adding one `VerificationKind` per role was rejected: `lint` and
  `typecheck` would then duplicate `static` and `types`, and a property test would stop being a
  `test` to the runner.
- The run reads the proposals, which 0012 had kept out of the engine, for this one purpose and
  as a fact about the project: it never writes them, and a run created from a proposal stays an
  ordinary run. Reading the file at specification time instead was rejected: the run would not
  record what it knew, and a refusal given between profiling and specifying would change the
  audit of a profile already persisted.
- The catalogue fact goes to the specifier only. The producer and the reviewers keep the
  profile's coverage list; the role on each verification of the approved specification tells
  them the contract, and what they must do with it is a separate concern (the producer's
  instruction per role, the `test_quality` reviewer's reading of a scenario).
- The specifier's output schema lists the roles as a nullable enum; a role the harness does
  not know is read as null, like an unknown kind is read as `command`.
- `ROLE_CONTRACTS` mirrors the "What the test must show" column of the catalogue's Roles table
  and `tests/test_catalogue.py` keeps them equal, as it does for the recommended entries.

## Where in the code

- `harness495/core/models/specification.py::Verification.role`;
  `harness495/core/models/profile.py::DeclinedRole`;
  `harness495/core/models/lessons.py`: `ProjectProfile.declined_roles`,
  `ProjectProfile.declined`.
- `harness495/core/proposals.py::declined_roles`; `harness495/core/engine/engine.py::_profile` reads
  them onto the run's profile.
- `harness495/core/schemas.py`: `CATALOGUE_ROLES`, the `role` property of `SPEC_SCHEMA`.
- `harness495/core/catalogue.py`: `ROLE_CONTRACTS`, `unmeasured_role`.
- `harness495/core/reading/verification.py::assess_sufficiency` (the `profile` argument).
- `harness495/core/context.py`: `render_catalogue`, the role in `render_spec`.
- `harness495/core/engine/engine.py`: `_specify` (the fact, the profile passed to the audit),
  `spec_from_agent` (the role read from the agent's output).
- `harness495/core/prompts.py::SPECIFIER_TASK`, the two rules on roles.
- `harness495/core/report.py`, `harness495/interfaces/render.py`,
  `harness495/interfaces/tui/views/spec.py`: the role shown beside the kind.
- `tests/features/specifier.feature` with `tests/test_specifier_scenarios.py`; the scenarios
  "The specifier is told ..." of `tests/features/catalogue.feature` with
  `tests/test_profile_scenarios.py`; `tests/test_catalogue.py` (role contracts).
