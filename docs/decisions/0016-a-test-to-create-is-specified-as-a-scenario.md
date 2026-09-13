# 0016. A test to create is specified as a scenario, and its steps are the text the requester approves

- Status: accepted
- Date: 2026-09-13

## Context

A `test` verification the producer has to create was described in a sentence (`description`):
"a test exercising subtract with positive and negative values". The requester approved that
sentence at the gate, the producer wrote whatever test the sentence allowed, and the reviewers
judged the test against the sentence. Nothing in the specification said what the test would
actually do, so approving it was approving a promise. 0013 made a behaviour test a Gherkin
scenario, read by whoever knows the domain, and left to build the step where the specifier
phrases it: the text of a test that does not exist yet is the only thing the requester can
read of it, and it has to be there before anything is produced.

## Decision

A `Verification` carries an optional `BehaviourScenario`: three lists of steps, `given`, `when`
and `then`, one step per entry, in the words of the requirement and through the interface a
caller uses. The specifier's instructions say that every `test` verification carries one,
complete on its own (concrete inputs, the exact observable outcome), one behaviour per
scenario, and null for every other kind.

The sufficiency audit requires it of a test to create: a `test` verification with `to_create`
and no scenario, or a scenario with no `when` or no `then` step, is `insufficient`, with a
rationale that says why the text is required and what is missing. A requirement carried by
such verifications alone is a gap, and the gate asks the requester about it like any other. An
existing test is judged on its command whether it has a scenario or not: its text is in the
repository, and the audit does not ask the specifier to transcribe it.

The steps are shown whole, never clipped, wherever the specification is put to the requester
(the CLI's `print_spec`, the TUI's specification view), and rendered under the verification in
the specification every agent receives (`render_spec`), so that the producer writes the test
from the same text the requester approved and the reviewers compare against it.

## Consequences

- At approval the requester reads the test as they read the requirement: the same Given/When/
  Then form, the same words. Approving the specification is approving that text, not a
  description of it.
- The scenario is structured (three lists) and not a Gherkin string: the harness can tell an
  empty `then` from a full one, render the steps for a terminal, a tree or a prompt, and hand
  the producer a form it can paste into a `.feature` file (`BehaviourScenario.lines()` gives
  the steps with `Given`, `When`, `Then` and `And`). A free string was rejected because the only
  check the harness could make on it would be a parse of its own, and a scenario title was
  left out because the verification's description already names it.
- The scenario reaches the producer as text under the verification. What the producer must
  make of it when the project has the `bdd` tool (a feature file and steps) and what the
  `test_quality` reviewer checks it against is a separate instruction, not part of this record
  (`docs/etude-harnais-495.md`, E51 (c)).
- Blank steps are dropped when the agent's output is read, and a scenario made of blanks is no
  scenario: the specifier cannot satisfy the requirement with an empty object.
- The rule is enforced on tests to create only. Requiring a scenario of every `test`
  verification was rejected: a non-regression run of the whole suite has no single scenario to
  state, and an existing test's text is already in the repository. The specifier is still told
  to state one for every `test` verification, so that a targeted existing test reads at the gate
  like a new one.
- Cost: the specifier's output grows by three lists per test, and a specification produced by
  an agent that ignores the rule stops at the gate with a gap instead of running; that stop is
  the point.

## Where in the code

- `harness495/core/models.py`: `BehaviourScenario` (`complete`, `lines()`),
  `Verification.scenario`.
- `harness495/core/schemas.py`: the `scenario` property of `SPEC_SCHEMA`.
- `harness495/core/engine.py::_scenario_from_agent`, called from `_spec_from_agent`.
- `harness495/core/verification.py::assess_sufficiency`, `_has_scenario`.
- `harness495/core/prompts.py::SPECIFIER_TASK`, the rule on `scenario`.
- `harness495/core/context.py::render_spec`; `harness495/interfaces/render.py::print_spec`;
  `harness495/interfaces/tui/views/spec.py`: the steps under the verification.
- `tests/features/expected_test.feature` with `tests/test_expected_test_scenarios.py`.
