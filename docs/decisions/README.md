# Decision records

One file per design decision. A record is immutable once `accepted`; reversing it means a new
record that supersedes it and a status line on the old one.

Adding a record: copy `0000-template.md` to `NNNN-<statement>.md` (next number), fill every
section, add the row below. Done when Where in the code names every module and test that
carries the decision.

| # | Decision | Status | Date |
|---|---|---|---|
| [0001](0001-accept-on-evidence-only.md) | A change is accepted on evidence only; the decision is a pure function | accepted | 2026-09-11 |
| [0002](0002-every-verification-is-measured-on-both-versions.md) | Every verification is measured on the change and on the base version before it counts | accepted | 2026-09-11, refined 2026-09-13 |
| [0003](0003-behaviour-and-non-regression-requirements.md) | A requirement states behaviour or non-regression, and that decides what a passing command may credit | accepted | 2026-09-13 |
| [0004](0004-corrections-name-the-gap-not-the-remedy.md) | A correction request names the gap and the observation, never the remedy | accepted | 2026-09-11 |
| [0005](0005-one-context-per-role-with-two-trust-zones.md) | Each intervention gets a context of its own, split into facts and untrusted content | accepted | 2026-09-11 |
| [0006](0006-a-run-works-in-a-worktree-and-the-harness-commits.md) | A run works in a git worktree outside the project, and the harness makes the commits | accepted | 2026-09-11 |
| [0007](0007-hand-written-strict-output-schemas.md) | Agent output schemas are hand-written, strict and nullable, then re-validated by pydantic | accepted | 2026-09-11 |
| [0008](0008-cost-is-never-silently-zero.md) | Cost is reported, estimated or unknown, never silently zero | accepted | 2026-09-11 |
| [0009](0009-a-run-is-claimed-by-the-process-advancing-it.md) | A run is claimed by the process advancing it; a dead claim is taken over | accepted | 2026-09-12 |
| [0010](0010-merge-on-request-in-four-shapes.md) | Merging happens on request only, in four shapes, and leaves the repository as found on failure | accepted | 2026-09-12 |
| [0011](0011-package-boundaries.md) | Package dependencies point one way, and a test enforces it | accepted | 2026-09-13 |
| [0012](0012-tests-use-proven-libraries-from-a-catalogue.md) | Tests use proven specialised libraries from a catalogue by technology and role, in 495 and in host projects | accepted | 2026-09-13, refined 2026-09-13 |
| [0013](0013-tests-are-behaviour-scenarios-in-gherkin.md) | Tests are behaviour scenarios, in Gherkin or in a Given/When/Then shape that reads like it | accepted | 2026-09-13 |
| [0014](0014-a-verification-names-the-catalogue-role-it-measures.md) | A verification names the catalogue role it measures, and a role the project does not measure is a stated gap, never an invented tool | accepted | 2026-09-13 |
