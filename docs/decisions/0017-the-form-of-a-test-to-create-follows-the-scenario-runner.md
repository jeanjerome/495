# 0017. The form of a test to create follows the project's scenario runner, and the reviewer compares requirement, scenario and test

- Status: accepted
- Date: 2026-09-13

## Context

0016 made every test to create a scenario in the specification: three lists of steps the
requester approves and the producer receives under the verification. The producer's task said
to create the test "exactly as described", and nothing more: whether the steps became a feature
file bound to step definitions or a function in the project's runner was the producer's
choice, and a project that measured the role `bdd` could receive a plain test where its own
suite is made of features. The `test_quality` reviewer was told to judge the tests on public
interfaces, independence from the implementation, coverage of the requirements and the ability
to fail on a revert; it had the scenario in the specification and the test in the tree, and no
instruction to hold them against each other or against the requirement. A scenario that said
less than the requirement, or a test that did something other than its scenario, passed unless
a reviewer thought of it.

## Decision

The form a test to create takes is derived from the profile's role coverage and stated as one
sentence, `render_behaviour_test_form`, placed under the facts of the producer and of every
reviewer under the title "Behaviour scenarios". Where a coverage row of role `bdd` is measured,
the sentence names the tool per technology and says the test is a `.feature` file whose
scenario has the specification's steps, word for word, bound to step definitions the way the
project's existing features are, and run by the verification's command. Where none is, it says
the test is written with the project's test runner, one test per scenario, its body in the
scenario's order (`given` sets the state, `when` is the action, `then` holds the only
assertions), and that the change adds no scenario runner: that tool enters the project through
a proposal (0014).

The producer's task says the scenario is the text of its test: the test sets up, does and
asserts what the steps say and nothing else, in the form the facts state; a step is not
reworded, and a step the producer cannot bind or observe is reported in `not_done`.

The `test_quality` perspective compares three texts for every verification that carries a
scenario: the requirement, the scenario in the specification, the test in the repository. The
scenario says what the requirement says (same inputs, same observable outcome, nothing the
requirement does not state); the test does what the scenario says, step for step, in the stated
form, and asserts its `then` steps and nothing else. A departure between scenario and
requirement, or between test and scenario, is a finding on the verification that quotes the step
and the text it departs from, and so a measurement finding (`verification_id`), never a
requirement assessment on its own (0001).

## Consequences

- The producer and the reviewer read the same sentence, computed by the harness from the same
  profile: what one is told to write is what the other checks, and neither reads the form off
  the profile lines and decides for itself. The sentence is a fact, not an instruction: it is
  measured material (the coverage rows) and the role instructions refer to it (0005).
- A project whose suite is made of features receives its new test as a feature; a project
  without a scenario runner receives it in its runner and is not made to adopt one by a
  change. Telling the producer to add pytest-bdd where it is missing was rejected: the tool is
  the requester's decision, taken through a proposal that is persisted and never asked again
  once declined.
- The `test_quality` reviewer is the one that reads the scenario against the requirement. That
  reading closes the gap 0016 left open: the requester approved steps, and now someone checks
  that the steps say what the requirement says and that the test says what the steps say.
  Giving that comparison to `spec_compliance` was rejected: it compares the diff against the
  requirements, and a scenario that under-states its requirement is a defect of the
  measurement, not of the change.
- The conditional part is in the fact, and the instructions are the same for every project;
  a custom `instructions` override of the `test_quality` reviewer replaces the comparison, as
  it replaces the rest of the perspective's text, and the fact stays.
- Cost: one sentence in every producer and reviewer prompt, and a longer `test_quality`
  instruction.

## Where in the code

- `harness495/core/context.py::render_behaviour_test_form`.
- `harness495/core/engine.py::_produce` and `_review`: the fact "Behaviour scenarios".
- `harness495/core/prompts.py::PRODUCER_TASK`, the paragraph on a verification that carries a
  scenario; `PERSPECTIVES["test_quality"]`, the comparison of the three texts.
- `tests/features/behaviour_test_form.feature` with `tests/test_behaviour_test_form_scenarios.py`.
